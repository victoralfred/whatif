"""Phase 9A.2 integration tests — Don't Ship scenarios.

Covers walkthroughs 02 (baseline regression) and 03 (failure-rescue
gap). Each scenario asserts that the policy guards fire correctly
ABOVE the floor and resolve to DontShip rather than Inconclusive
or Ship.
"""

from __future__ import annotations

import pytest

from whatifd.pipeline import run_pipeline
from whatifd.report.models_v01 import ReportV01
from whatifd.types.policy import DecisionPolicy, TrustFloor

from ._fixtures import (
    scenario_dont_ship_failure_rescue_gap,
    scenario_dont_ship_regression,
)


class TestDontShipRegressionScenario:
    """Walkthrough 02 — baseline cohort regressed beyond threshold."""

    @pytest.fixture(scope="class")
    def report(self) -> ReportV01:
        fx = scenario_dont_ship_regression()
        return run_pipeline(
            fx.trace_source,
            delta_fn=fx.delta_fn,
            floor=TrustFloor(),
            policy=DecisionPolicy(),
            runtime=fx.runtime,
            methodology=fx.methodology,
            cache_summary=fx.cache_summary,
        )

    def test_verdict_is_dont_ship(self, report: ReportV01) -> None:
        assert report.verdict_state == "dont_ship"

    def test_floor_passes(self, report: ReportV01) -> None:
        # Floor passes — DontShip is a policy verdict, not a floor verdict.
        for c in report.cohort_results:
            assert c.floor_passed, f"cohort {c.name} did not pass the floor"

    def test_baseline_regression_finding_present(self, report: ReportV01) -> None:
        codes = {f.code for f in report.decision_findings}
        assert "baseline_regression_above_threshold" in codes

    def test_baseline_regressed_count_matches_fixture(self, report: ReportV01) -> None:
        cohorts = {c.name: c for c in report.cohort_results}
        assert cohorts["baseline"].regressed_count == 6
        assert cohorts["baseline"].scored == 20


class TestDontShipFailureRescueGapScenario:
    """Walkthrough 03 — failure cohort improvement below threshold."""

    @pytest.fixture(scope="class")
    def report(self) -> ReportV01:
        fx = scenario_dont_ship_failure_rescue_gap()
        return run_pipeline(
            fx.trace_source,
            delta_fn=fx.delta_fn,
            floor=TrustFloor(),
            policy=DecisionPolicy(),
            runtime=fx.runtime,
            methodology=fx.methodology,
            cache_summary=fx.cache_summary,
        )

    def test_verdict_is_dont_ship(self, report: ReportV01) -> None:
        assert report.verdict_state == "dont_ship"

    def test_floor_passes(self, report: ReportV01) -> None:
        for c in report.cohort_results:
            assert c.floor_passed

    def test_failure_cohort_no_improvement_finding(self, report: ReportV01) -> None:
        codes = {f.code for f in report.decision_findings}
        assert "failure_improvement_below_threshold" in codes

    def test_failure_improved_count_matches_fixture(self, report: ReportV01) -> None:
        cohorts = {c.name: c for c in report.cohort_results}
        assert cohorts["failure"].improved_count == 2
        assert cohorts["failure"].scored == 20
