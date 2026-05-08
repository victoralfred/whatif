"""Phase 9A.2 integration test — Inconclusive (insufficient sample).

Walkthrough 04 — baseline cohort has 8 selected but only 3 scored
(below floor.min_scored_per_required_cohort=5). Cardinal #2: floor
failure produces Inconclusive regardless of policy.

Walkthroughs 05 (cache corruption) and 06 (rerun-after-fix / diff)
are deliberately NOT covered here:

- **05 cache corruption** is a recovery-path scenario exercised by
  the `whatifd.cache.recovery` unit tests + the `whatif cache verify`
  CLI surface. It produces Inconclusive via the cache-policy guard,
  not the integration pipeline. Surfacing it here would require a
  parallel CLI integration harness — Phase 9A.4 territory.
- **06 rerun-after-fix** is the `whatif diff` surface, fully tested
  in `tests/unit/whatifd/test_diff.py` end-to-end against synthetic
  reports. The pipeline that produces the inputs IS exercised here
  (scenario 1 produces "before-fix"; downstream scenarios produce
  "after-fix"); the diff itself is tested at its own seam.

Both deferrals are tracked in the cascade-catalog Phase 9A.2 entry
(this PR adds it).
"""

from __future__ import annotations

import pytest

from whatifd.pipeline import run_pipeline
from whatifd.report.models_v01 import ReportV01
from whatifd.types.policy import DecisionPolicy, TrustFloor

from ._fixtures import scenario_inconclusive_insufficient_sample


class TestInconclusiveInsufficientSampleScenario:
    @pytest.fixture(scope="class")
    def report(self) -> ReportV01:
        fx = scenario_inconclusive_insufficient_sample()
        return run_pipeline(
            fx.trace_source,
            delta_fn=fx.delta_fn,
            floor=TrustFloor(),
            policy=DecisionPolicy(),
            runtime=fx.runtime,
            methodology=fx.methodology,
            cache_summary=fx.cache_summary,
        )

    def test_verdict_is_inconclusive(self, report: ReportV01) -> None:
        assert report.verdict_state == "inconclusive"

    def test_baseline_floor_failed(self, report: ReportV01) -> None:
        cohorts = {c.name: c for c in report.cohort_results}
        baseline = cohorts["baseline"]
        assert baseline.floor_passed is False
        # Pin the EXACT set of rules that fire for the 8-selected /
        # 3-replayed / 3-scored shape. min_selected (8 >= 5) passes;
        # the other three fail. Asserting the exact set catches a
        # future stub or floor change that silently moves the failing
        # set — e.g., if min_replayed stops firing because the stub
        # starts "replaying" skipped traces, this test fails loudly
        # rather than continuing to pass on the back of
        # min_scored_per_required_cohort alone.
        rules = {f.rule for f in baseline.floor_failures}
        assert rules == {
            "min_replayed_per_required_cohort",
            "min_scored_per_required_cohort",
            "min_replay_validity_ratio_per_required_cohort",
        }

    def test_failure_cohort_floor_passes(self, report: ReportV01) -> None:
        # Failure cohort had 15 traces all scored — well above floor.
        cohorts = {c.name: c for c in report.cohort_results}
        assert cohorts["failure"].floor_passed
        assert cohorts["failure"].scored == 15

    def test_baseline_skipped_traces_counted_as_selected(self, report: ReportV01) -> None:
        # Cardinal #1: skipped traces (skip_reason populated) flow
        # through and contribute to `selected` count, even though
        # they don't reach scoring. The walkthrough's "8 selected,
        # 3 scored" shape is preserved end-to-end.
        cohorts = {c.name: c for c in report.cohort_results}
        baseline = cohorts["baseline"]
        assert baseline.selected == 8
        assert baseline.scored == 3
