"""Tests for `ci_availability_guard`."""

from __future__ import annotations

from whatifd.decision.guards.ci_availability import ci_availability_guard
from whatifd.types.cohort import CIUnavailableReason, CohortResult
from whatifd.types.policy import DecisionPolicy


def _cohort(
    name: str,
    *,
    ci_computable: bool = True,
    ci_unavailable_reason: CIUnavailableReason | None = None,
) -> CohortResult:
    return CohortResult(
        name=name,
        selected=10,
        replayed=10,
        scored=10,
        ci_computable=ci_computable,
        ci_unavailable_reason=ci_unavailable_reason,
        median_delta=None,
        ci_lower=None,
        ci_upper=None,
        floor_passed=True,
    )


class TestCiAvailabilityEmits:
    def test_emits_when_ci_unavailable_on_required_cohort(self) -> None:
        cohort = _cohort("failure", ci_computable=False, ci_unavailable_reason="sample_too_small")
        findings = ci_availability_guard(
            [cohort, _cohort("baseline")],
            DecisionPolicy(),
        )
        assert len(findings) == 1
        f = findings[0]
        assert f.code == "ci_unavailable_for_required_cohort"
        assert f.severity == "blocks_all"
        assert f.details["cohort"] == "failure"
        assert f.details["reason"] == "sample_too_small"

    def test_emits_one_finding_per_affected_required_cohort(self) -> None:
        # Both required cohorts have CI unavailable → two findings.
        cohorts = [
            _cohort("failure", ci_computable=False, ci_unavailable_reason="zero_variance"),
            _cohort("baseline", ci_computable=False, ci_unavailable_reason="sample_too_small"),
        ]
        findings = ci_availability_guard(cohorts, DecisionPolicy())
        assert len(findings) == 2
        codes = {f.details["cohort"] for f in findings}
        assert codes == {"failure", "baseline"}

    def test_findings_in_required_cohort_order(self) -> None:
        # Ordering matches policy.required_cohorts, not cohort_results order.
        cohorts = [
            _cohort("baseline", ci_computable=False, ci_unavailable_reason="zero_variance"),
            _cohort("failure", ci_computable=False, ci_unavailable_reason="sample_too_small"),
        ]
        # Default policy: required_cohorts = ("failure", "baseline")
        findings = ci_availability_guard(cohorts, DecisionPolicy())
        assert [f.details["cohort"] for f in findings] == ["failure", "baseline"]


class TestCiAvailabilitySilent:
    def test_silent_when_ci_computable_on_all_required_cohorts(self) -> None:
        findings = ci_availability_guard(
            [_cohort("failure"), _cohort("baseline")],
            DecisionPolicy(),
        )
        assert findings == []

    def test_silent_when_ci_unavailable_on_non_required_cohort(self) -> None:
        # Custom policy: only "failure" is required. baseline's missing CI
        # is not this guard's concern.
        policy = DecisionPolicy(required_cohorts=("failure",))
        findings = ci_availability_guard(
            [
                _cohort("failure"),
                _cohort("baseline", ci_computable=False, ci_unavailable_reason="sample_too_small"),
            ],
            policy,
        )
        assert findings == []

    def test_silent_when_required_cohort_missing(self) -> None:
        # Floor's required_cohort_present rule catches missing cohorts;
        # this guard does not double-emit.
        findings = ci_availability_guard(
            [_cohort("failure")],  # baseline missing entirely
            DecisionPolicy(),
        )
        assert findings == []

    def test_silent_when_no_cohorts_at_all(self) -> None:
        findings = ci_availability_guard([], DecisionPolicy())
        assert findings == []


class TestCiMeaningfulBoundary:
    """Pin the layer boundary: `ci_availability_guard` reads only
    `ci_computable`. `ci_meaningful` is the deferred Phase 3 policy-
    quality concern at a different severity (`blocks_ship` vs this
    guard's `blocks_all`); see cascade-catalog "ci_meaningful policy-
    guard wiring". When the Phase 3 guard lands, it MUST be a separate
    guard — folding `ci_meaningful` into this one would conflate the
    structural and policy-quality severities the V0_1_DECISION_RECORD
    §2 split exists to keep apart.
    """

    def test_meaningful_false_alone_does_not_emit(self) -> None:
        # ci_computable=True so this guard's precondition fails; the
        # ci_meaningful=False signal is the future guard's territory.
        cohort = CohortResult(
            name="failure",
            selected=10,
            replayed=10,
            scored=10,
            ci_computable=True,
            ci_unavailable_reason=None,
            median_delta=None,
            ci_lower=None,
            ci_upper=None,
            floor_passed=True,
            ci_meaningful=False,
        )
        findings = ci_availability_guard([cohort], DecisionPolicy())
        assert findings == []


class TestCiAvailabilityReasonFallback:
    def test_unspecified_reason_when_none(self) -> None:
        # CohortResult.ci_unavailable_reason is None despite ci_computable=False
        # — projection-layer bug. Guard surfaces it as "unspecified" rather
        # than hiding the missing data.
        cohort = _cohort("failure", ci_computable=False, ci_unavailable_reason=None)
        findings = ci_availability_guard([cohort], DecisionPolicy())
        assert len(findings) == 1
        assert findings[0].details["reason"] == "unspecified"


class TestCiAvailabilityPlaceholderContract:
    """Lock the `pending_phase_2_6_plumbing` placeholder on
    `derived_from_failures` so Phase 2.6 (which wires real failure
    records end-to-end) is forced to update this test when it lands.

    The placeholder is the in-code surface for the cascade-catalog
    "Phase 2.5 deferred guards" → bullet 4 work item.
    """

    def test_derived_from_failures_uses_placeholder(self) -> None:
        from whatifd.decision.guards.ci_availability import _PHASE_2_6_PLACEHOLDER

        cohort = _cohort("failure", ci_computable=False, ci_unavailable_reason="sample_too_small")
        findings = ci_availability_guard([cohort], DecisionPolicy())
        assert len(findings) == 1
        # Phase 2.6 will replace this placeholder with real failure-record
        # IDs. When this test fails, the guard's emit logic should be
        # updated to use the real IDs and this test deleted.
        assert findings[0].derived_from_failures == [_PHASE_2_6_PLACEHOLDER]

    def test_placeholder_constant_is_grep_discoverable(self) -> None:
        # The placeholder string itself should be greppable as a single
        # constant. If a future contributor types the literal inline
        # somewhere instead of importing the constant, this test still
        # protects the central definition.
        from whatifd.decision.guards.ci_availability import _PHASE_2_6_PLACEHOLDER

        assert _PHASE_2_6_PLACEHOLDER == "pending_phase_2_6_plumbing"


class TestCiAvailabilityCustomPolicy:
    def test_respects_custom_required_cohorts(self) -> None:
        # Policy with three required cohorts (forward-looking — v0.2 may
        # support this). All three have CI unavailable.
        policy = DecisionPolicy(required_cohorts=("failure", "baseline", "regression"))
        cohorts = [
            _cohort("failure", ci_computable=False, ci_unavailable_reason="sample_too_small"),
            _cohort("baseline", ci_computable=False, ci_unavailable_reason="zero_variance"),
            _cohort("regression", ci_computable=False, ci_unavailable_reason="computation_failed"),
        ]
        findings = ci_availability_guard(cohorts, policy)
        assert len(findings) == 3
        # Order matches policy.required_cohorts.
        assert [f.details["cohort"] for f in findings] == ["failure", "baseline", "regression"]
