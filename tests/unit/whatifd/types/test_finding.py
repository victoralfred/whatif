"""Tests for `whatifd.types.finding` — Phase 1.3 operational types."""

from __future__ import annotations

import dataclasses

import pytest

from whatifd.types import DecisionFinding, Severity


class TestConstruction:
    def test_minimal(self) -> None:
        f = DecisionFinding(
            code="baseline_regression_above_threshold",
            severity="blocks_ship",
            message="baseline cohort regressed 6/20 traces (30%), exceeds 10% threshold",
        )
        assert f.code == "baseline_regression_above_threshold"
        assert f.severity == "blocks_ship"
        assert f.derived_from_failures == []
        assert f.details == {}

    def test_with_derived_failures(self) -> None:
        f = DecisionFinding(
            code="replay_validity_below_floor",
            severity="blocks_all",
            message="baseline replay validity 0.375 below floor 0.50",
            derived_from_failures=["failure_001", "failure_002", "failure_003"],
        )
        assert len(f.derived_from_failures) == 3

    def test_with_details(self) -> None:
        f = DecisionFinding(
            code="ci_uncomputable_for_required_cohort",
            severity="degrades_trust",
            message="baseline cohort: bootstrap unavailable (sample too small)",
            details={"cohort": "baseline", "scored": 3, "threshold": 5},
        )
        assert f.details["cohort"] == "baseline"


class TestSeverityLiteral:
    @pytest.mark.parametrize(
        "severity",
        ["info", "degrades_trust", "blocks_ship", "blocks_all"],
    )
    def test_all_severity_values_accepted(self, severity: Severity) -> None:
        f = DecisionFinding(code="x", severity=severity, message="test")
        assert f.severity == severity


class TestFrozenness:
    def test_cannot_assign(self) -> None:
        f = DecisionFinding(code="x", severity="info", message="test")
        with pytest.raises(dataclasses.FrozenInstanceError):
            f.code = "y"  # type: ignore[misc]


class TestEquality:
    def test_structural_equality(self) -> None:
        f1 = DecisionFinding(code="x", severity="info", message="test")
        f2 = DecisionFinding(code="x", severity="info", message="test")
        assert f1 == f2

    def test_derived_from_failures_distinguishes(self) -> None:
        f1 = DecisionFinding(code="x", severity="info", message="test", derived_from_failures=["a"])
        f2 = DecisionFinding(code="x", severity="info", message="test", derived_from_failures=["b"])
        assert f1 != f2
