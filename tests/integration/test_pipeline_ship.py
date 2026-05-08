"""Phase 9A.1 integration test — Clean Ship scenario.

Drives the synthetic stub adapter through `run_pipeline` end-to-end
and pins:
- The verdict resolves to Ship.
- Floor passed on both required cohorts.
- Cohort counts match the fixture's delta function.
- Median delta and CI bounds are populated as DecimalString.

This is the architectural-proof test for cardinal #2 floor +
projection in Phase 9A.1. Phase 9A.2 adds the remaining five
walkthrough scenarios; Phase 9A.3 adds determinism byte-equality;
Phase 9A.4 adds failure injection.
"""

from __future__ import annotations

import pytest

from whatifd.pipeline import run_pipeline
from whatifd.report.models_v01 import ReportV01
from whatifd.types.policy import DecisionPolicy, TrustFloor

from ._fixtures import scenario_clean_ship


class TestCleanShipScenario:
    @pytest.fixture(scope="class")
    def report(self) -> ReportV01:
        # Class-scoped: run_pipeline is deterministic for a given
        # fixture, so each test method asserts a different property
        # of the same report. Halves fixture setup cost; clarifies
        # intent as Phase 9A.2 adds more scenarios to similar classes.
        fx = scenario_clean_ship()
        return run_pipeline(
            fx.trace_source,
            delta_fn=fx.delta_fn,
            floor=TrustFloor(),
            policy=DecisionPolicy(),
            runtime=fx.runtime,
            methodology=fx.methodology,
            cache_summary=fx.cache_summary,
        )

    def test_verdict_is_ship(self, report: ReportV01) -> None:
        assert report.verdict_state == "ship"

    def test_cohort_counts_match_fixture(self, report: ReportV01) -> None:
        cohorts = {c.name: c for c in report.cohort_results}
        assert cohorts["failure"].selected == 20
        assert cohorts["failure"].scored == 20
        assert cohorts["failure"].improved_count == 14
        assert cohorts["failure"].unchanged_count == 6
        assert cohorts["failure"].regressed_count == 0
        assert cohorts["baseline"].selected == 20
        assert cohorts["baseline"].regressed_count == 0
        # All 20 baseline deltas are 0.01 < epsilon=0.05 — unchanged.
        assert cohorts["baseline"].unchanged_count == 20

    def test_floor_passed_on_required_cohorts(self, report: ReportV01) -> None:
        for c in report.cohort_results:
            assert c.floor_passed, f"cohort {c.name} did not pass the floor"
            assert c.floor_failures == []

    def test_ci_bounds_populated(self, report: ReportV01) -> None:
        for c in report.cohort_results:
            assert c.ci_computable, f"cohort {c.name} CI not computed"
            assert c.median_delta is not None
            assert c.ci_lower is not None
            assert c.ci_upper is not None


class TestPipelineFailurePaths:
    """Cardinal #1: pipeline failures surface as structured
    `FailureRecord`s in `ReportV01.failures`, not as exceptions."""

    def test_delta_fn_exception_recorded_as_failure(self) -> None:
        # delta_fn raises on one specific trace; that trace lands in
        # ReportV01.failures with code='scorer_unavailable' (the
        # registered stand-in for delta_fn since delta_fn IS the
        # 9A.1 scoring step), trace_id matches, and
        # trace_id populated, and is excluded from the cohort's
        # scored count. The pipeline does NOT crash.
        fx = scenario_clean_ship()

        def flaky(rt):
            if rt.trace_id == "f-00":
                raise RuntimeError("scorer outage")
            return fx.delta_fn(rt)

        report = run_pipeline(
            fx.trace_source,
            delta_fn=flaky,
            floor=TrustFloor(),
            policy=DecisionPolicy(),
            runtime=fx.runtime,
            methodology=fx.methodology,
            cache_summary=fx.cache_summary,
        )
        # Trace-scope FailureRecords carry trace_id and have
        # cohort=None (per make_failure_record's scope rules);
        # the cohort is implicit from the trace.
        #
        # Audit (Phase 9A.4 review): no production code in
        # src/whatifd/ reads `FailureRecord.cohort` for routing — the
        # field is informational only. Cohort-routed handling
        # happens via `ReportV01.cohort_results[*].floor_failures`,
        # which is a different field on a different type. So
        # dropping the per-trace cohort assertion here is safe; the
        # cohort signal for trace-scope failures lives on the
        # adjacent CohortResult, not on the FailureRecord itself.
        assert any(
            f.code == "scorer_unavailable" and f.trace_id == "f-00" and f.scope == "trace"
            for f in report.failures
        )
        # Failed trace counted toward selected but not scored.
        cohorts = {c.name: c for c in report.cohort_results}
        assert cohorts["failure"].selected == 20
        assert cohorts["failure"].scored == 19

    def test_delta_fn_exception_does_not_crash_pipeline(self) -> None:
        fx = scenario_clean_ship()
        report = run_pipeline(
            fx.trace_source,
            delta_fn=lambda _rt: (_ for _ in ()).throw(RuntimeError("always fails")),
            floor=TrustFloor(),
            policy=DecisionPolicy(),
            runtime=fx.runtime,
            methodology=fx.methodology,
            cache_summary=fx.cache_summary,
        )
        # Every trace produced a FailureRecord; cohorts have 0 scored
        # so the floor blocks → Inconclusive.
        assert report.verdict_state == "inconclusive"
        assert len(report.failures) == 40
