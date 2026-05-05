"""`baseline_regression_guard` — cardinal #10 baseline non-regression endpoint.

The baseline cohort's role under cardinal rule #10 is "the change
should not silently regress traces it doesn't target". This guard
emits `baseline_regression_above_threshold` (blocks_ship) when the
baseline regression rate exceeds `policy.max_baseline_regression_ratio`.

Regression rate = `regressed_count / total_scored` where
`total_scored = improved_count + unchanged_count + regressed_count`.
If `total_scored == 0` the guard abstains — the floor's
`min_scored_per_required_cohort` rule catches that case structurally.

Pairs with `failure_improvement_guard` (the symmetric primary endpoint
on the failure cohort). Together they implement the rate-based primary
endpoints from cardinal #10's v0.1 doctrine; `practical_delta_guard`
is the supplementary magnitude layer.

Precondition: a `baseline` cohort exists with non-zero scored traces.
When missing or empty this guard emits no finding; the floor catches
the structural case via `required_cohort_present` and
`min_scored_per_required_cohort`.

Note on float-vs-displayed comparison: same caveat as
`failure_improvement_guard` — the comparator runs on the underlying
float; displayed strings round to 3 decimal places. Standard
thresholds (default 0.10) agree on both sides; exotic sub-precision
thresholds may diverge. Phase 5's `format_decimal_string` round-trip
dissolves the concern.
"""

from __future__ import annotations

from collections.abc import Sequence

from whatif.decision.finding_codes import make_decision_finding
from whatif.types.cohort import CohortResult
from whatif.types.finding import DecisionFinding
from whatif.types.policy import DecisionPolicy
from whatif.types.primitives import DecimalString


def baseline_regression_guard(
    cohort_results: Sequence[CohortResult],
    policy: DecisionPolicy,
) -> list[DecisionFinding]:
    """Emit `baseline_regression_above_threshold` when the baseline
    regression rate strictly exceeds `policy.max_baseline_regression_ratio`.

    Strict `>` is intentional: a rate exactly at the threshold is the
    boundary; the policy promises "at most N% regression". Equality
    meets the promise.
    """
    baseline = next((c for c in cohort_results if c.name == "baseline"), None)
    if baseline is None:
        return []

    total_scored = baseline.improved_count + baseline.unchanged_count + baseline.regressed_count
    if total_scored == 0:
        # See `failure_improvement_guard` for the lenient-`<=`-invariant
        # rationale. Cascade-catalog "`CohortResult` rate-count
        # partition — tighten `<=` to `==` at Phase 2.6" tracks the
        # tightening that makes this branch unreachable for production
        # cohorts; today the floor catches all-zero partitions
        # structurally.
        return []

    regression_rate = baseline.regressed_count / total_scored
    threshold = policy.max_baseline_regression_ratio

    if regression_rate <= threshold:
        return []

    observed_str = DecimalString(format(regression_rate, ".3f"))
    threshold_str = DecimalString(format(threshold, ".3f"))
    return [
        make_decision_finding(
            "baseline_regression_above_threshold",
            message=(
                f"baseline regression rate {observed_str} exceeds "
                f"threshold {threshold_str} "
                f"({baseline.regressed_count}/{total_scored} traces regressed)"
            ),
            details={"observed": observed_str, "threshold": threshold_str},
        )
    ]
