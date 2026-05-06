"""Tests for `whatif.types.cohort` — Phase 1.3 operational types."""

from __future__ import annotations

import dataclasses

import pytest

from whatif.exceptions import InvariantViolationError
from whatif.types import (
    CIUnavailableReason,
    CohortResult,
    DecimalString,
    FloorFailure,
)


class TestFloorFailure:
    def test_construction_int_observed(self) -> None:
        f = FloorFailure(
            rule="min_scored_per_required_cohort",
            observed=3,
            threshold=5,
            severity="blocks_all",
        )
        assert f.observed == 3
        assert f.severity == "blocks_all"

    def test_construction_decimal_string_observed(self) -> None:
        f = FloorFailure(
            rule="min_replay_validity_ratio_per_required_cohort",
            observed="0.375",  # DecimalString form
            threshold=0.50,
            severity="blocks_ship",
        )
        assert f.observed == "0.375"

    @pytest.mark.parametrize("severity", ["blocks_ship", "blocks_all"])
    def test_severity_literal(self, severity: str) -> None:
        f = FloorFailure(rule="x", observed=0, threshold=1, severity=severity)  # type: ignore[arg-type]
        assert f.severity == severity

    def test_frozen(self) -> None:
        f = FloorFailure(rule="x", observed=0, threshold=1, severity="blocks_ship")
        with pytest.raises(dataclasses.FrozenInstanceError):
            f.rule = "y"  # type: ignore[misc]


class TestCohortResult:
    def _all_pass(self) -> CohortResult:
        """Cohort with everything in order — Ship-eligible."""
        return CohortResult(
            name="baseline",
            selected=20,
            replayed=20,
            scored=20,
            ci_computable=True,
            ci_unavailable_reason=None,
            median_delta=DecimalString("0.020"),
            ci_lower=DecimalString("-0.010"),
            ci_upper=DecimalString("0.050"),
            floor_passed=True,
        )

    def test_construction_all_pass(self) -> None:
        c = self._all_pass()
        assert c.name == "baseline"
        assert c.ci_computable is True
        assert c.ci_unavailable_reason is None
        assert c.floor_passed is True
        assert c.floor_failures == []

    def test_construction_below_floor(self) -> None:
        c = CohortResult(
            name="baseline",
            selected=8,
            replayed=5,
            scored=3,
            ci_computable=False,
            ci_unavailable_reason="sample_too_small",
            median_delta=DecimalString("0.050"),
            ci_lower=None,
            ci_upper=None,
            floor_passed=False,
            floor_failures=[
                FloorFailure(
                    rule="min_scored_per_required_cohort",
                    observed=3,
                    threshold=5,
                    severity="blocks_all",
                ),
                FloorFailure(
                    rule="min_replay_validity_ratio_per_required_cohort",
                    observed="0.375",
                    threshold=0.50,
                    severity="blocks_ship",
                ),
            ],
        )
        assert c.floor_passed is False
        assert len(c.floor_failures) == 2
        assert c.ci_computable is False
        assert c.ci_unavailable_reason == "sample_too_small"

    def test_ci_unavailable_with_reason_but_no_bounds(self) -> None:
        # When CI is unavailable, the bounds should be None but median_delta
        # may still be present (median is computable without CI).
        c = CohortResult(
            name="baseline",
            selected=8,
            replayed=5,
            scored=3,
            ci_computable=False,
            ci_unavailable_reason="sample_too_small",
            median_delta=DecimalString("0.050"),
            ci_lower=None,
            ci_upper=None,
            floor_passed=True,
            floor_failures=[],
        )
        assert c.ci_lower is None
        assert c.ci_upper is None
        assert c.median_delta == "0.050"

    @pytest.mark.parametrize(
        "reason",
        ["sample_too_small", "zero_variance", "computation_failed"],
    )
    def test_ci_unavailable_reason_literal(self, reason: CIUnavailableReason) -> None:
        c = CohortResult(
            name="x",
            selected=1,
            replayed=1,
            scored=1,
            ci_computable=False,
            ci_unavailable_reason=reason,
            median_delta=None,
            ci_lower=None,
            ci_upper=None,
            floor_passed=True,
        )
        assert c.ci_unavailable_reason == reason

    def test_frozen(self) -> None:
        c = self._all_pass()
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.name = "renamed"  # type: ignore[misc]

    def test_structural_equality(self) -> None:
        c1 = self._all_pass()
        c2 = self._all_pass()
        assert c1 == c2

    def test_floor_failures_distinguish(self) -> None:
        c1 = self._all_pass()
        c2 = dataclasses.replace(
            c1,
            floor_passed=False,
            floor_failures=[
                FloorFailure(rule="r", observed=0, threshold=1, severity="blocks_all"),
            ],
        )
        assert c1 != c2


class TestRateCountInvariant:
    """`CohortResult.__post_init__` enforces that the rate-count
    partition cannot exceed scored. Catches projection-layer bugs that
    would otherwise silently skew rate-based guards.
    """

    def _build(
        self, *, improved: int, unchanged: int, regressed: int, scored: int = 10
    ) -> CohortResult:
        return CohortResult(
            name="failure",
            selected=10,
            replayed=10,
            scored=scored,
            ci_computable=True,
            ci_unavailable_reason=None,
            median_delta=None,
            ci_lower=None,
            ci_upper=None,
            floor_passed=True,
            improved_count=improved,
            unchanged_count=unchanged,
            regressed_count=regressed,
        )

    def test_default_zero_counts_pass(self) -> None:
        # Phase 2.5b backward compat: counts default to 0; sum=0 <= scored.
        c = self._build(improved=0, unchanged=0, regressed=0)
        assert c.improved_count == 0

    def test_partition_summing_to_scored_passes(self) -> None:
        # Exhaustive partition (every scored trace categorized): scored=10, sum=10.
        c = self._build(improved=4, unchanged=3, regressed=3)
        assert c.improved_count + c.unchanged_count + c.regressed_count == 10

    def test_partial_population_passes(self) -> None:
        # Lenient `<=` allows partial population during early integration.
        c = self._build(improved=2, unchanged=0, regressed=0)
        assert c.improved_count == 2

    def test_partition_exceeding_scored_raises(self) -> None:
        with pytest.raises(InvariantViolationError, match="exceeds scored"):
            self._build(improved=5, unchanged=4, regressed=2)  # sum=11 > scored=10

    def test_error_message_includes_breakdown(self) -> None:
        with pytest.raises(InvariantViolationError, match="improved=5"):
            self._build(improved=5, unchanged=4, regressed=2)
        with pytest.raises(InvariantViolationError, match="scored=10"):
            self._build(improved=5, unchanged=4, regressed=2)

    def test_negative_counts_raise(self) -> None:
        with pytest.raises(InvariantViolationError, match="non-negative"):
            self._build(improved=-1, unchanged=0, regressed=0)

    def test_error_includes_cohort_name(self) -> None:
        # Diagnostic: the cohort name appears so callers can locate the bug.
        with pytest.raises(InvariantViolationError, match="'failure'"):
            self._build(improved=11, unchanged=0, regressed=0)


class TestCiMeaningfulSplit:
    """`ci_meaningful` is the policy-quality assessment of a CI that
    exists. Per V0_1_DECISION_RECORD §2 + 2026-05-05 addendum, the field
    is only valid when `ci_computable=True`. Defaults True for v0.1 since
    the width-vs-`max_ci_width` check is deferred to Phase 3 (cascade
    entry "ci_meaningful policy-guard wiring").
    """

    def _build(
        self,
        *,
        ci_computable: bool,
        ci_meaningful: bool = True,
        reason: CIUnavailableReason | None = None,
    ) -> CohortResult:
        return CohortResult(
            name="failure",
            selected=10,
            replayed=10,
            scored=10,
            ci_computable=ci_computable,
            ci_unavailable_reason=reason,
            median_delta=None,
            ci_lower=None,
            ci_upper=None,
            floor_passed=True,
            ci_meaningful=ci_meaningful,
        )

    def test_default_ci_meaningful_is_true(self) -> None:
        c = self._build(ci_computable=True)
        assert c.ci_meaningful is True

    def test_ci_computable_true_meaningful_false_constructs(self) -> None:
        # The Phase 3 outcome we're staging the field for.
        c = self._build(ci_computable=True, ci_meaningful=False)
        assert c.ci_computable is True
        assert c.ci_meaningful is False

    def test_ci_computable_false_meaningful_true_constructs(self) -> None:
        # Default ci_meaningful=True is a benign no-op when CI is not
        # computable — the guard never reads the field for non-computable
        # cohorts. Pinned so a future tightening doesn't accidentally
        # forbid this default-construction shape.
        c = self._build(ci_computable=False, ci_meaningful=True, reason="sample_too_small")
        assert c.ci_meaningful is True

    def test_ci_computable_false_meaningful_false_raises(self) -> None:
        # Incoherent: ci_meaningful is the quality assessment of a CI
        # that exists. If no CI exists, meaningfulness is undefined.
        with pytest.raises(
            InvariantViolationError, match="ci_meaningful=False requires ci_computable=True"
        ):
            self._build(ci_computable=False, ci_meaningful=False, reason="sample_too_small")
