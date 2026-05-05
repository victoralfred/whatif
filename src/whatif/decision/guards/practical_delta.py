"""`practical_delta_guard` — cardinal #10 enforcement (blocks_ship).

Per cardinal rule #10 (statistical claims must match the design):
small statistical wins inside the practical-delta noise floor are not
shippable. A change that nudges the failure-cohort median delta by less
than `policy.practical_delta_epsilon` is "statistically observable but
practically negligible" — emit `practical_delta_below_threshold` so the
verdict layer registers a Don't Ship.

This guard reads the failure cohort only — that's where we evaluate
"the change rescued failures by enough to ship". The baseline
non-regression guard (separate, future PR) handles the symmetric check
on the baseline cohort.

Precondition: a `failure` cohort exists with a non-None `median_delta`.
When either is missing this guard emits no finding; the floor or
another guard catches the missing-cohort case. The floor's
`required_cohort_present` rule is the structural check; this guard
operates above the floor on quality.
"""

from __future__ import annotations

from collections.abc import Sequence

from whatif.decision.finding_codes import make_decision_finding
from whatif.serialization.decimal import FieldLabel, parse_decimal_string
from whatif.types.cohort import CohortResult
from whatif.types.finding import DecisionFinding
from whatif.types.policy import DecisionPolicy


def practical_delta_guard(
    cohort_results: Sequence[CohortResult],
    policy: DecisionPolicy,
) -> list[DecisionFinding]:
    """Emit `practical_delta_below_threshold` when the failure cohort's
    median delta is at or below `policy.practical_delta_epsilon`.

    Equality counts as below-threshold: the epsilon represents "the
    smallest meaningful effect"; a delta exactly at that level isn't
    above noise.
    """
    failure = next((c for c in cohort_results if c.name == "failure"), None)
    if failure is None or failure.median_delta is None:
        return []

    median_delta_str = failure.median_delta
    median_delta_float = parse_decimal_string(
        median_delta_str,
        field=FieldLabel(f"CohortResult.median_delta (cohort={failure.name!r})"),
    )

    threshold = policy.practical_delta_epsilon
    if median_delta_float > threshold:
        return []

    return [
        make_decision_finding(
            "practical_delta_below_threshold",
            message=(
                f"failure cohort median delta {median_delta_str} "
                f"<= practical-delta threshold {threshold:.3f}"
            ),
            details={
                "median_delta": median_delta_str,
                "threshold": format(threshold, ".3f"),
            },
        )
    ]
