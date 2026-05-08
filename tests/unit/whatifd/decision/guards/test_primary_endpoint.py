"""Tests for `primary_endpoint_guard` — Phase 2.6b consolidation.

Replaces `test_failure_improvement.py` + `test_baseline_regression.py`
with a single test surface parametrized over the two endpoint
directions. The hardcoded boundary semantics (strict `<` for
improvement, strict `>` for regression) are preserved; the dispatcher
test class exercises the configurable surface.
"""

from __future__ import annotations

from whatifd.decision.guards.primary_endpoint import primary_endpoint_guard
from whatifd.types.policy import DecisionPolicy, PrimaryEndpoint

from ._helpers import baseline_cohort, failure_cohort

# ---------------------------------------------------------------------------
# Default-policy behavior — must match the Phase 2.5b hardcoded guards
# ---------------------------------------------------------------------------


class TestPrimaryEndpointDefaultPolicyImprovement:
    """`improvement_above_threshold` direction (default for `failure` cohort)."""

    def test_emits_when_rate_below_threshold(self) -> None:
        # 4/20 = 0.200 < default 0.500 → emit
        cohort = failure_cohort(improved=4, unchanged=10, regressed=6)
        findings = primary_endpoint_guard([cohort], DecisionPolicy())
        assert len(findings) == 1
        f = findings[0]
        assert f.code == "failure_improvement_below_threshold"
        assert f.severity == "blocks_ship"
        assert f.details["observed"] == "0.200"
        assert f.details["threshold"] == "0.500"

    def test_silent_at_exactly_threshold(self) -> None:
        # 5/10 = 0.500 == threshold → meets policy "at least 50%" promise
        cohort = failure_cohort(improved=5, unchanged=3, regressed=2)
        findings = primary_endpoint_guard([cohort], DecisionPolicy())
        # No improvement emit; baseline endpoint also doesn't fire because
        # baseline cohort isn't present.
        assert findings == []

    def test_silent_above_threshold(self) -> None:
        cohort = failure_cohort(improved=8, unchanged=2, regressed=0)
        findings = primary_endpoint_guard([cohort], DecisionPolicy())
        assert findings == []

    def test_silent_when_zero_scored(self) -> None:
        cohort = failure_cohort(improved=0, unchanged=0, regressed=0)
        findings = primary_endpoint_guard([cohort], DecisionPolicy())
        assert findings == []

    def test_message_includes_count_breakdown(self) -> None:
        cohort = failure_cohort(improved=4, unchanged=10, regressed=6)
        findings = primary_endpoint_guard([cohort], DecisionPolicy())
        assert "4/20" in findings[0].message


class TestPrimaryEndpointDefaultPolicyNonRegression:
    """`non_regression_below_threshold` direction (default for `baseline` cohort)."""

    def test_emits_when_rate_above_threshold(self) -> None:
        # 3/20 = 0.150 > default 0.10 → emit
        cohort = baseline_cohort(improved=10, unchanged=7, regressed=3)
        findings = primary_endpoint_guard([cohort], DecisionPolicy())
        assert len(findings) == 1
        f = findings[0]
        assert f.code == "baseline_regression_above_threshold"
        assert f.severity == "blocks_ship"
        assert f.details["observed"] == "0.150"
        assert f.details["threshold"] == "0.100"

    def test_silent_at_exactly_threshold(self) -> None:
        # 1/10 = 0.100 == threshold → meets policy "at most 10%" promise
        cohort = baseline_cohort(improved=5, unchanged=4, regressed=1)
        findings = primary_endpoint_guard([cohort], DecisionPolicy())
        assert findings == []

    def test_silent_below_threshold(self) -> None:
        cohort = baseline_cohort(improved=8, unchanged=11, regressed=1)
        findings = primary_endpoint_guard([cohort], DecisionPolicy())
        assert findings == []

    def test_silent_when_no_baseline_cohort(self) -> None:
        # Default policy declares BOTH the failure and baseline endpoints.
        # This test pins zero findings via two distinct paths in one run:
        #   - failure endpoint PASSES: improved=10/12 = 0.833, threshold 0.500,
        #     strict-< check fails → no emit.
        #   - baseline endpoint ABSTAINS: baseline cohort missing from results,
        #     guard's `if cohort is None: continue` branch fires.
        findings = primary_endpoint_guard(
            [failure_cohort(improved=10, regressed=2)], DecisionPolicy()
        )
        assert findings == []


class TestPrimaryEndpointDefaultPolicyBothCohorts:
    """Both endpoints active simultaneously."""

    def test_both_endpoints_pass_no_findings(self) -> None:
        cohorts = [
            failure_cohort(improved=8, unchanged=2, regressed=0),
            baseline_cohort(improved=2, unchanged=8, regressed=0),
        ]
        findings = primary_endpoint_guard(cohorts, DecisionPolicy())
        assert findings == []

    def test_both_endpoints_fail_two_findings(self) -> None:
        cohorts = [
            failure_cohort(improved=2, unchanged=4, regressed=4),  # rate too low
            baseline_cohort(improved=4, unchanged=3, regressed=3),  # regression too high
        ]
        findings = primary_endpoint_guard(cohorts, DecisionPolicy())
        assert len(findings) == 2
        codes = [f.code for f in findings]
        # Order matches policy.primary_endpoints (failure first by default).
        assert codes == [
            "failure_improvement_below_threshold",
            "baseline_regression_above_threshold",
        ]

    def test_findings_in_policy_order_not_cohort_order(self) -> None:
        # Cohort list order: baseline first, failure second.
        cohorts = [
            baseline_cohort(improved=4, unchanged=3, regressed=3),
            failure_cohort(improved=2, unchanged=4, regressed=4),
        ]
        # Default policy: failure endpoint first.
        findings = primary_endpoint_guard(cohorts, DecisionPolicy())
        codes = [f.code for f in findings]
        assert codes == [
            "failure_improvement_below_threshold",
            "baseline_regression_above_threshold",
        ]


# ---------------------------------------------------------------------------
# Custom-policy behavior — the configurable surface this guard adds
# ---------------------------------------------------------------------------


class TestPrimaryEndpointCustomPolicy:
    def test_only_failure_endpoint_declared(self) -> None:
        """Policy with a single endpoint: only that one fires; the other
        cohort is ignored even if it would have triggered the default."""
        policy = DecisionPolicy(
            primary_endpoints=(
                PrimaryEndpoint(cohort="failure", direction="improvement_above_threshold"),
            ),
            required_cohorts=("failure",),
        )
        cohorts = [
            failure_cohort(improved=2, unchanged=4, regressed=4),
            # Baseline regression that would normally fire — but no
            # baseline endpoint declared, so silent.
            baseline_cohort(improved=4, unchanged=3, regressed=3),
        ]
        findings = primary_endpoint_guard(cohorts, policy)
        assert len(findings) == 1
        assert findings[0].code == "failure_improvement_below_threshold"

    def test_custom_threshold_strict(self) -> None:
        policy = DecisionPolicy(min_failure_improvement_ratio=0.80)
        # 5/10 = 0.500 < 0.800 → emit
        cohort = failure_cohort(improved=5, unchanged=3, regressed=2)
        findings = primary_endpoint_guard([cohort], policy)
        assert len(findings) == 1
        assert findings[0].details["threshold"] == "0.800"

    def test_custom_threshold_lenient(self) -> None:
        policy = DecisionPolicy(min_failure_improvement_ratio=0.10)
        # 2/10 = 0.200 > 0.100 → no emit (strict <)
        cohort = failure_cohort(improved=2, unchanged=4, regressed=4)
        findings = primary_endpoint_guard([cohort], policy)
        assert findings == []

    def test_missing_endpoint_cohort_abstains_passing_cohort_passes(self) -> None:
        # Two endpoints declared. Both produce zero findings, but via
        # DIFFERENT code paths — this test pins both paths in one
        # scenario rather than splitting into two tests:
        #
        #   PATH A — endpoint cohort present, evaluation passes:
        #     "failure" cohort exists, improvement rate 8/10=0.800,
        #     threshold 0.500 → 0.800 > 0.500 → strict-< check fails →
        #     guard does NOT emit. Passing condition; `_evaluate_improvement`
        #     returns None.
        #
        #   PATH B — endpoint cohort missing, guard abstains:
        #     "exploratory" cohort is NOT in cohort_results.
        #     `cohorts_by_name.get("exploratory")` returns None, the
        #     guard's `if cohort is None: continue` branch fires, no
        #     evaluation happens. Floor's `required_cohort_present`
        #     rule catches missing REQUIRED cohorts (this one isn't
        #     required), so the policy-level guard silently abstains.
        #
        # If a future change conflates these two paths (e.g., emits a
        # "missing-cohort" finding for path B), the assertion below
        # fails with a diagnostic listing the offending finding codes.
        policy = DecisionPolicy(
            primary_endpoints=(
                PrimaryEndpoint(cohort="failure", direction="improvement_above_threshold"),
                PrimaryEndpoint(cohort="exploratory", direction="improvement_above_threshold"),
            ),
        )
        cohorts = [failure_cohort(improved=8, unchanged=2, regressed=0)]
        findings = primary_endpoint_guard(cohorts, policy)
        assert len(findings) == 0, (
            "expected zero findings via two distinct code paths "
            "(failure cohort PASSED its check; exploratory cohort MISSING "
            f"from results so guard abstained); got {[f.code for f in findings]}"
        )


class TestPrimaryEndpointsSubsetOfRequiredCohorts:
    """Document the current `DecisionPolicy` invariant state.

    `policy.primary_endpoints` and `policy.required_cohorts` are two
    independent fields. There is NO validator enforcing that endpoint
    cohorts ⊆ required_cohorts. PR #27 bot iter-3 raised this:
    confirm the unrestricted state via test, OR add a validator. For
    v0.1 we document the current state — the invariant is sometimes
    desirable (best-effort endpoints on non-required cohorts) and
    sometimes a bug (silent abstain when user expected a finding).
    The cascade entry "Direction-keyed finding codes for v0.2 multi-
    cohort primary_endpoint_guard" tracks the v0.2 resolution decision
    (Pydantic validator vs documented best-effort).

    These tests exist so a future change adding a validator surfaces
    them as failures the contributor must engage with — they're the
    deletion-trigger pattern from `_PHASE_2_6_PLACEHOLDER` applied
    to this invariant.
    """

    def test_endpoint_cohort_outside_required_cohorts_constructs_cleanly(self) -> None:
        # No validator: policy with mismatch constructs without raising.
        policy = DecisionPolicy(
            required_cohorts=("failure",),
            primary_endpoints=(
                PrimaryEndpoint(cohort="exploratory", direction="improvement_above_threshold"),
            ),
        )
        # Object exists; no exception was raised at construction.
        assert policy.required_cohorts == ("failure",)
        assert policy.primary_endpoints[0].cohort == "exploratory"

    def test_endpoint_on_non_required_cohort_silently_abstains_when_missing(self) -> None:
        # Mismatch surfaces at runtime as silent abstain. Today this is
        # by design (best-effort); v0.2 may tighten with a validator.
        policy = DecisionPolicy(
            required_cohorts=("failure",),
            primary_endpoints=(
                PrimaryEndpoint(cohort="exploratory", direction="improvement_above_threshold"),
            ),
        )
        # Cohort results don't include "exploratory".
        cohorts = [failure_cohort(improved=8, unchanged=2, regressed=0)]
        findings = primary_endpoint_guard(cohorts, policy)
        assert findings == []  # silent abstain — the documented best-effort behavior


class TestSubPrecisionThresholdDivergence:
    """Pin the float-vs-displayed-string caveat documented in the
    rate-based guards' module docstrings.

    Migrated from `test_failure_improvement.py::TestSubPrecisionThresholdDivergence`
    when Phase 2.6b consolidated the two hardcoded guards into
    `primary_endpoint_guard`. The caveat applies identically — the
    comparator runs on float, displayed strings round to 3 decimal
    places via `format(rate, '.3f')`, and at sub-precision thresholds
    the displayed equality may not match the comparator's verdict.

    Phase 5's `format_decimal_string` round-trip pair will dissolve
    this concern; until then, the documented divergence is empirically
    pinned. See cascade-catalog "`parse_decimal_string` permissiveness".
    """

    def test_one_third_rate_at_one_third_threshold_does_not_emit(self) -> None:
        # 1/3 = 0.3333... > 0.333 in float; guard does NOT emit even
        # though both displayed strings would round to "0.333". Strict
        # `<` improvement-rate comparator wins; reader-side ambiguity
        # in the displayed strings is the cost.
        policy = DecisionPolicy(min_failure_improvement_ratio=0.333)
        cohort = failure_cohort(improved=1, unchanged=1, regressed=1)  # 1/3 rate
        findings = primary_endpoint_guard([cohort], policy)
        assert findings == [], (
            "1/3 rate (0.3333...) is strictly > threshold 0.333 in float, "
            "so the guard should not emit even though displayed strings "
            "would both round to '0.333'. Phase 5 dissolves this divergence."
        )

    def test_two_thirds_rate_at_two_thirds_threshold_emits(self) -> None:
        # 2/3 = 0.6666... < 0.667 in float; guard emits with
        # observed="0.667" and threshold="0.667" — pinned identity in
        # displayed form. Comparator wins; display rounds.
        policy = DecisionPolicy(min_failure_improvement_ratio=0.667)
        cohort = failure_cohort(improved=2, unchanged=1, regressed=0)  # 2/3 rate
        findings = primary_endpoint_guard([cohort], policy)
        assert len(findings) == 1
        assert findings[0].details["observed"] == "0.667"
        assert findings[0].details["threshold"] == "0.667"
