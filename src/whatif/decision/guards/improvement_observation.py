"""`improvement_observation_guard` — info-severity observation.

Emits the `improvement_observed` info finding when the failure cohort's
median delta is meaningfully positive (above the practical-delta
epsilon). The finding is observational — it does NOT drive the verdict
on its own; the verdict layer reads it for the report's narrative
section ("the change improved the failure cohort").

The symmetric "regression observed on baseline" finding has a different
shape (severity blocks_ship, not info) and lands with the
baseline-regression guard in a future PR.

This guard pairs with `practical_delta_guard`: at most one of them
emits per run. When the failure cohort's median delta is above epsilon,
this guard fires; when at-or-below, the practical_delta guard fires.
That mutual exclusion isn't enforced structurally (both are pure
functions; verdict layer reads severities), but tests pin the behavior.
"""

from __future__ import annotations

from collections.abc import Sequence

from whatif.decision.finding_codes import make_decision_finding
from whatif.exceptions import InvariantViolationError
from whatif.types.cohort import CohortResult
from whatif.types.finding import DecisionFinding
from whatif.types.policy import DecisionPolicy


def improvement_observation_guard(
    cohort_results: Sequence[CohortResult],
    policy: DecisionPolicy,
) -> list[DecisionFinding]:
    """Emit `improvement_observed` when the failure cohort's median
    delta is strictly above `policy.practical_delta_epsilon`.

    Strict `>` is intentional: the practical-delta epsilon is the "no
    meaningful effect" threshold; a delta exactly at it is noise, not
    improvement. The matching guard (`practical_delta_guard`) uses
    `<=` so the two are mutually exclusive.
    """
    failure = next((c for c in cohort_results if c.name == "failure"), None)
    if failure is None or failure.median_delta is None:
        return []

    # A non-numeric DecimalString is a structural integrity violation
    # upstream, not a precondition the guard should hide. Per cardinal
    # #1, bugs propagate; expected failures are data. We surface as a
    # typed `InvariantViolationError` so the call-site intent is legible —
    # a stdlib `ValueError` would conflate this with value-domain bugs.
    try:
        median_delta_float = float(failure.median_delta)
    except ValueError as e:
        raise InvariantViolationError(
            f"CohortResult.median_delta must be a parseable DecimalString; "
            f"got {failure.median_delta!r} on cohort={failure.name!r}"
        ) from e

    if median_delta_float <= policy.practical_delta_epsilon:
        return []

    return [
        make_decision_finding(
            "improvement_observed",
            message=f"failure cohort median delta {failure.median_delta} (improvement observed)",
            details={"median_delta": failure.median_delta},
        )
    ]
