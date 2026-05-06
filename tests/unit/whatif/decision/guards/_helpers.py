"""Shared helpers for `tests/unit/whatif/decision/guards/`.

Consolidates the `_failure_cohort` builder that previously lived in
three separate test files. When `CohortResult` is extended with
rate-count fields (per cascade-catalog "Phase 2.5 deferred guards"),
this helper is the single update site instead of three.

Underscore-prefixed filename keeps pytest from collecting it as a
test module.
"""

from __future__ import annotations

from whatif.types.cohort import CohortResult
from whatif.types.primitives import DecimalString


def _resolve_scored(default_scored: int, improved: int, unchanged: int, regressed: int) -> int:
    """Auto-resolve `scored` to satisfy the rate-count invariant.

    When the test passes rate counts, `scored` must be ≥ their sum
    (CohortResult `__post_init__` invariant). The helper picks
    `max(default, sum)` so tests that pass non-default counts don't
    have to also pass `scored=`.
    """
    return max(default_scored, improved + unchanged + regressed)


def failure_cohort(
    median_delta: str | None = "0.310",
    *,
    improved: int = 0,
    unchanged: int = 0,
    regressed: int = 0,
    scored: int = 10,
) -> CohortResult:
    """Build a `failure` `CohortResult` with the given `median_delta`.

    Default `0.310` is above the practical-delta epsilon (0.050) so
    `improvement_observation_guard` emits and `practical_delta_guard`
    abstains. Override per test for boundary cases.

    Rate counts default to 0 (Phase 2.5 backward-compat); override for
    rate-based guard tests. `scored` auto-resolves to fit the rate-count
    sum unless explicitly overridden.
    """
    resolved_scored = _resolve_scored(scored, improved, unchanged, regressed)
    return CohortResult(
        name="failure",
        selected=resolved_scored,
        replayed=resolved_scored,
        scored=resolved_scored,
        ci_computable=True,
        ci_unavailable_reason=None,
        median_delta=DecimalString(median_delta) if median_delta is not None else None,
        ci_lower=None,
        ci_upper=None,
        floor_passed=True,
        improved_count=improved,
        unchanged_count=unchanged,
        regressed_count=regressed,
    )


def baseline_cohort(
    *,
    improved: int = 0,
    unchanged: int = 0,
    regressed: int = 0,
    median_delta: str | None = "0.000",
    scored: int = 10,
) -> CohortResult:
    """Build a `baseline` `CohortResult` with the given rate counts.

    Default `median_delta=0.000` reflects "no movement" baseline.
    Override per test for boundary cases. `scored` auto-resolves to fit
    the rate-count sum unless explicitly overridden.
    """
    resolved_scored = _resolve_scored(scored, improved, unchanged, regressed)
    return CohortResult(
        name="baseline",
        selected=resolved_scored,
        replayed=resolved_scored,
        scored=resolved_scored,
        ci_computable=True,
        ci_unavailable_reason=None,
        median_delta=DecimalString(median_delta) if median_delta is not None else None,
        ci_lower=None,
        ci_upper=None,
        floor_passed=True,
        improved_count=improved,
        unchanged_count=unchanged,
        regressed_count=regressed,
    )
