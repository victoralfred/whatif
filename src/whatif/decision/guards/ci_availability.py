"""`ci_availability_guard` — required-cohort CI availability check.

Per cardinal rule #10's predeclared-cohort-endpoint doctrine, a verdict
that depends on cohort-level uncertainty cannot be defensibly rendered
when CI is unavailable on a required cohort. This guard reads
`CohortResult.ci_available` for each cohort named in
`policy.required_cohorts` and emits
`ci_unavailable_for_required_cohort` (blocks_all) when CI is missing
on any of them.

Pairs with `FAILURE_CODE_REGISTRY['ci_uncomputable_for_required_cohort']`:
the failure record is the operational fact (bootstrap returned
None / sample too small / zero variance); this finding is the policy
conclusion (verdict cannot ship without it).

The blocks_all severity forces Inconclusive. The companion
`DecisionPolicy.accept_no_ci` flag (v0.1 single-flag escape hatch) is
the configured opt-out — when set, the verdict layer (Phase 2.6) will
suppress this finding's blocking effect. This guard does NOT consult
`accept_no_ci`; emission is unconditional. Phase 2.6 does the
acceptance arithmetic so the manifest can record both the finding AND
the explicit acceptance.

Precondition: a cohort named in `policy.required_cohorts` exists in
`cohort_results`. Missing cohorts are the floor's
`required_cohort_present` rule, not this guard's concern.

The `derived_from_failures` field on the emitted finding is left
empty here. Phase 2.6 / projection layer threads the matching failure
record IDs in once the failure-record collection is plumbed end-to-end;
the cascade catalog tracks that wiring.
"""

from __future__ import annotations

from collections.abc import Sequence

from whatif.decision.finding_codes import make_decision_finding
from whatif.types.cohort import CohortResult
from whatif.types.finding import DecisionFinding
from whatif.types.policy import DecisionPolicy

# Placeholder for `derived_from_failures` until Phase 2.6 plumbs real
# failure-record IDs through the verdict pipeline. Exported (single
# underscore) so tests can lock it; once Phase 2.6 lands, the test
# that asserts this constant flips and the constant is removed.
_PHASE_2_6_PLACEHOLDER = "pending_phase_2_6_plumbing"


def ci_availability_guard(
    cohort_results: Sequence[CohortResult],
    policy: DecisionPolicy,
) -> list[DecisionFinding]:
    """Emit `ci_unavailable_for_required_cohort` for every required
    cohort whose `ci_available` is False.

    One finding per affected cohort. Order matches the order of
    `policy.required_cohorts`; cohorts not present in `cohort_results`
    are skipped (the floor's `required_cohort_present` rule catches
    them structurally).
    """
    by_name = {c.name: c for c in cohort_results}
    findings: list[DecisionFinding] = []
    for required_name in policy.required_cohorts:
        cohort = by_name.get(required_name)
        if cohort is None:
            # Floor's required_cohort_present rule catches missing
            # cohorts. This guard is above the floor; missing cohort
            # is structural, not a CI-availability concern.
            continue
        if cohort.ci_available:
            continue
        # CI is unavailable. The reason field on CohortResult is
        # CIUnavailableReason | None — when ci_available is False the
        # reason should be populated, but we guard against None anyway
        # to keep the guard pure (no upstream-bug hiding; if reason is
        # None when ci_available is False, that's a projection-layer bug
        # that surfaces as a "reason: unspecified" finding the renderer
        # makes visible).
        reason = cohort.ci_unavailable_reason or "unspecified"
        findings.append(
            make_decision_finding(
                "ci_unavailable_for_required_cohort",
                message=(f"CI unavailable for required cohort {cohort.name!r}: {reason}"),
                details={"cohort": cohort.name, "reason": reason},
                # TODO(phase-2.6): replace this placeholder with the
                # real failure-record IDs once Phase 2.6 plumbs failure
                # records end-to-end through the verdict pipeline. See
                # cascade-catalog "Phase 2.5 deferred guards" → bullet 4.
                # The constant string makes this grep-discoverable.
                derived_from_failures=[_PHASE_2_6_PLACEHOLDER],
            )
        )
    return findings
