"""Tests for `whatif.types.cohort` — Phase 1.3 operational types."""

from __future__ import annotations

import dataclasses

import pytest

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
            ci_available=True,
            ci_unavailable_reason=None,
            median_delta=DecimalString("0.020"),
            ci_lower=DecimalString("-0.010"),
            ci_upper=DecimalString("0.050"),
            floor_passed=True,
        )

    def test_construction_all_pass(self) -> None:
        c = self._all_pass()
        assert c.name == "baseline"
        assert c.ci_available is True
        assert c.ci_unavailable_reason is None
        assert c.floor_passed is True
        assert c.floor_failures == []

    def test_construction_below_floor(self) -> None:
        c = CohortResult(
            name="baseline",
            selected=8,
            replayed=5,
            scored=3,
            ci_available=False,
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
        assert c.ci_available is False
        assert c.ci_unavailable_reason == "sample_too_small"

    def test_ci_unavailable_with_reason_but_no_bounds(self) -> None:
        # When CI is unavailable, the bounds should be None but median_delta
        # may still be present (median is computable without CI).
        c = CohortResult(
            name="baseline",
            selected=8,
            replayed=5,
            scored=3,
            ci_available=False,
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
            ci_available=False,
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
