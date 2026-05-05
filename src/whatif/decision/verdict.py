"""Verdict computation — Phase 2.6a.

`compute_verdict` is the single entry point that turns
`(cohort_results, floor, policy)` into a `Verdict`. It composes the
existing decision pipeline:

1. **Floor evaluation** (`evaluate_floor`) — Cardinal #2 structural
   gate. If the floor returns a `FloorFailureSet`, the verdict is
   `Inconclusive` regardless of any guard findings. The floor
   precedence is absolute.

2. **Guard chain** (`run_guards`) — Each guard in the configured
   sequence emits 0+ `DecisionFinding`s. Order matches registration;
   `run_guards` is the chain composer.

3. **Severity sorting** — Findings are partitioned by severity:
   - `blocks_all` → forces `Inconclusive` (operational catastrophes
     like cache corruption that break the run regardless of policy)
   - `blocks_ship` → produces `DontShip` when no `blocks_all` is
     present; the policy says "no Ship" but evidence existed
   - `degrades_trust` → accumulates against future quality thresholds
     (v1.0+); v0.1 collects but does not blocking-act on these
   - `info` → observational; no verdict impact, included in `findings`
     for the renderer

4. **Verdict construction**:
   - Any `blocks_all` → `Inconclusive(blocking_findings=blocks_all_findings)`
   - Else any `blocks_ship` → `DontShip(blocking_findings=blocks_ship_findings)`
   - Else → `Ship(proof=floor_passed_proof)`

Per cardinal #2, the `Ship` branch is the ONLY branch that consumes
the `FloorPassedProof`. The witness token is structurally required —
`compute_verdict` cannot construct `Ship` without one.

## v0.1 guard registration

Phase 2.6a uses the five landed guards (per cardinal #10's three-layer
structure plus the operational CI-availability check):
- `failure_improvement_guard` (rate-based primary endpoint, blocks_ship)
- `baseline_regression_guard` (symmetric non-regression, blocks_ship)
- `practical_delta_guard` (magnitude floor, blocks_ship)
- `improvement_observation_guard` (observational info)
- `ci_availability_guard` (cohort-level CI availability, blocks_all)

`primary_endpoint_guard` is deferred to Phase 2.6b along with the
`DecisionPolicy.primary_endpoints` configurable; today's primary
endpoint is the failure-rescue rate (handled by `failure_improvement_guard`).
`cache_staleness_guard` is deferred to Phase 3.

## accept_no_ci handling — Phase 2.6c work

`DecisionPolicy.accept_no_ci` is the v0.1 single-flag escape hatch for
the case where CI is unavailable but the user wants to ship anyway
(documented small-sample experiments). Phase 2.6c will implement:
- Filter out `ci_unavailable_for_required_cohort` findings from
  `blocking_findings` when `policy.accept_no_ci=True`
- Emit a separate `info` finding noting the acceptance was used
- Both the original finding AND the acceptance are recorded in the
  manifest so the audit trail is complete

For Phase 2.6a, `accept_no_ci` is NOT consulted — the guard's emission
is unconditional. Tests pin both behaviors so Phase 2.6c can flip the
existing assertions cleanly.
"""

from __future__ import annotations

from collections.abc import Sequence

from whatif.decision.floor import FloorFailureSet, FloorPassedProof, evaluate_floor
from whatif.decision.guards import (
    Guard,
    baseline_regression_guard,
    ci_availability_guard,
    failure_improvement_guard,
    improvement_observation_guard,
    practical_delta_guard,
    run_guards,
)
from whatif.types.cohort import CohortResult
from whatif.types.policy import DecisionPolicy, TrustFloor
from whatif.types.verdict import DontShip, Inconclusive, Ship, Verdict

# v0.1 default guard chain, in registration order. Order matches the
# cardinal #10 layer structure: rate-based primary endpoints first
# (load-bearing), magnitude layer, observational layer, then
# operational guards (CI availability). Test_layer_composition pins
# the no-mutation contract; the per-guard tests pin the boundary
# semantics.
_DEFAULT_GUARDS: tuple[Guard, ...] = (
    failure_improvement_guard,
    baseline_regression_guard,
    practical_delta_guard,
    improvement_observation_guard,
    ci_availability_guard,
)


def compute_verdict(
    cohort_results: Sequence[CohortResult],
    floor: TrustFloor,
    policy: DecisionPolicy,
    *,
    guards: Sequence[Guard] | None = None,
) -> Verdict:
    """Compute the verdict for a run.

    Cardinal #2: floor failures produce `Inconclusive` regardless of
    guard findings. The floor evaluation is the structural gate.

    `guards` defaults to the v0.1 `_DEFAULT_GUARDS` tuple. Tests pass
    a custom sequence to exercise specific scenarios in isolation.

    Returns one of `Ship`, `DontShip`, `Inconclusive`. The `Ship`
    branch consumes the `FloorPassedProof` from `evaluate_floor`;
    structurally cannot construct `Ship` without that token.

    `floor` is typed `TrustFloor` directly — mypy strict enforces the
    contract at call sites. No runtime isinstance check; per the
    project's enforcement-strength hierarchy, type-level prevention
    is stronger than runtime defense-in-depth.
    """
    resolved_guards = guards if guards is not None else _DEFAULT_GUARDS

    floor_outcome = evaluate_floor(
        cohort_results,
        floor,
        policy.required_cohorts,
    )

    # Run guards regardless of floor outcome so observational findings
    # (improvement_observed, etc.) appear in the report even when the
    # floor is the structural reason for Inconclusive.
    findings = run_guards(resolved_guards, cohort_results, policy)

    # Pre-compute severity-partitioned views once; both Inconclusive
    # branches and the DontShip branch read from these.
    inconclusive_blocking = [f for f in findings if f.severity in ("blocks_ship", "blocks_all")]
    blocks_all = [f for f in findings if f.severity == "blocks_all"]
    blocks_ship = [f for f in findings if f.severity == "blocks_ship"]

    cohort_results_list = list(cohort_results)

    # Cardinal #2: floor failures → Inconclusive, regardless of guards.
    if isinstance(floor_outcome, FloorFailureSet):
        return Inconclusive(
            cohort_results=cohort_results_list,
            findings=findings,
            blocking_findings=inconclusive_blocking,
            floor_failures=list(floor_outcome.failures),
        )

    # Floor passed; floor_outcome is a FloorPassedProof.
    assert isinstance(floor_outcome, FloorPassedProof)  # narrows for mypy

    if blocks_all:
        # Operational catastrophe at policy level (e.g., cache lock
        # unavailable). Floor passed but evidence is unrenderable.
        return Inconclusive(
            cohort_results=cohort_results_list,
            findings=findings,
            blocking_findings=inconclusive_blocking,
            floor_failures=[],
        )

    if blocks_ship:
        return DontShip(
            cohort_results=cohort_results_list,
            findings=findings,
            blocking_findings=blocks_ship,
        )

    return Ship(
        proof=floor_outcome,
        cohort_results=cohort_results_list,
        findings=findings,
    )
