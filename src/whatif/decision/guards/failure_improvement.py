"""`failure_improvement_guard` — cardinal #10 failure-rescue primary endpoint.

The failure cohort's role under cardinal rule #10 is "the change
should rescue at least N% of the targeted failures". This guard emits
`failure_improvement_below_threshold` (blocks_ship) when the failure
cohort improvement rate is strictly below
`policy.min_failure_improvement_ratio`.

Improvement rate = `improved_count / total_scored` where
`total_scored = improved_count + unchanged_count + regressed_count`.
If `total_scored == 0` the guard abstains — the floor's
`min_scored_per_required_cohort` rule catches that case structurally.

This is the **load-bearing primary endpoint** for cardinal #10's
failure-rescue audience: the rate-based check that drives Ship vs
DontShip on the cohort the change targets. `practical_delta_guard`
is the supplementary magnitude layer (median delta vs noise floor);
`baseline_regression_guard` is the symmetric non-regression endpoint
on the baseline cohort.

Precondition: a `failure` cohort exists with non-zero scored traces.
When missing or empty this guard emits no finding; the floor catches
the structural case via `required_cohort_present` and
`min_scored_per_required_cohort`.

The framing-cleanup that PR #23 noted is now in effect: this guard is
the rate-based primary endpoint; `practical_delta_guard` is the
supplementary magnitude layer. Read them as a pair — neither alone
provides full cardinal #10 coverage.
"""

from __future__ import annotations

from collections.abc import Sequence

from whatif.decision.finding_codes import make_decision_finding
from whatif.types.cohort import CohortResult
from whatif.types.finding import DecisionFinding
from whatif.types.policy import DecisionPolicy
from whatif.types.primitives import DecimalString


def failure_improvement_guard(
    cohort_results: Sequence[CohortResult],
    policy: DecisionPolicy,
) -> list[DecisionFinding]:
    """Emit `failure_improvement_below_threshold` when the failure
    improvement rate is strictly below `policy.min_failure_improvement_ratio`.

    Strict `<` is intentional: a rate exactly at the threshold meets
    the policy's "at least N%" promise; only rates BELOW the threshold
    fail it.
    """
    failure = next((c for c in cohort_results if c.name == "failure"), None)
    if failure is None:
        return []

    total_scored = failure.improved_count + failure.unchanged_count + failure.regressed_count
    if total_scored == 0:
        return []

    improvement_rate = failure.improved_count / total_scored
    threshold = policy.min_failure_improvement_ratio

    if improvement_rate >= threshold:
        return []

    observed_str = DecimalString(format(improvement_rate, ".3f"))
    threshold_str = DecimalString(format(threshold, ".3f"))
    return [
        make_decision_finding(
            "failure_improvement_below_threshold",
            message=(
                f"failure-cohort improvement rate {observed_str} below "
                f"threshold {threshold_str} "
                f"({failure.improved_count}/{total_scored} traces improved)"
            ),
            details={"observed": observed_str, "threshold": threshold_str},
        )
    ]
