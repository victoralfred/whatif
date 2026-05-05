"""Tests for `baseline_regression_guard`."""

from __future__ import annotations

from whatif.decision.guards.baseline_regression import baseline_regression_guard
from whatif.types.policy import DecisionPolicy

from ._helpers import baseline_cohort, failure_cohort


class TestBaselineRegressionEmits:
    def test_emits_when_regression_rate_above_threshold(self) -> None:
        # 3/20 = 0.150 > default threshold 0.10 → emit
        cohort = baseline_cohort(improved=10, unchanged=7, regressed=3)
        findings = baseline_regression_guard([cohort], DecisionPolicy())
        assert len(findings) == 1
        f = findings[0]
        assert f.code == "baseline_regression_above_threshold"
        assert f.severity == "blocks_ship"
        assert f.details["observed"] == "0.150"
        assert f.details["threshold"] == "0.100"

    def test_message_includes_count_breakdown(self) -> None:
        cohort = baseline_cohort(improved=10, unchanged=7, regressed=3)
        findings = baseline_regression_guard([cohort], DecisionPolicy())
        assert "3/20" in findings[0].message


class TestBaselineRegressionSilent:
    def test_silent_at_exactly_threshold(self) -> None:
        # 1/10 = 0.100 == threshold → meets policy "at most 10%" promise
        cohort = baseline_cohort(improved=5, unchanged=4, regressed=1)
        findings = baseline_regression_guard([cohort], DecisionPolicy())
        assert findings == []

    def test_silent_below_threshold(self) -> None:
        cohort = baseline_cohort(improved=8, unchanged=11, regressed=1)
        findings = baseline_regression_guard([cohort], DecisionPolicy())
        assert findings == []

    def test_silent_when_no_baseline_cohort(self) -> None:
        # Only failure cohort present; guard abstains.
        findings = baseline_regression_guard(
            [failure_cohort(improved=10, regressed=2)], DecisionPolicy()
        )
        assert findings == []

    def test_silent_when_total_scored_zero(self) -> None:
        # Zero counts → can't compute rate; floor catches structural case.
        cohort = baseline_cohort(improved=0, unchanged=0, regressed=0)
        findings = baseline_regression_guard([cohort], DecisionPolicy())
        assert findings == []

    def test_silent_when_all_improved(self) -> None:
        cohort = baseline_cohort(improved=20, unchanged=0, regressed=0)
        findings = baseline_regression_guard([cohort], DecisionPolicy())
        assert findings == []


class TestBaselineRegressionCustomThreshold:
    def test_respects_custom_threshold_strict(self) -> None:
        # 2/10 = 0.200 vs custom threshold 0.50 → no emit
        policy = DecisionPolicy(max_baseline_regression_ratio=0.50)
        cohort = baseline_cohort(improved=6, unchanged=2, regressed=2)
        findings = baseline_regression_guard([cohort], policy)
        assert findings == []

    def test_respects_custom_threshold_lenient(self) -> None:
        # 1/10 = 0.100 vs custom threshold 0.05 → emit (0.10 > 0.05)
        policy = DecisionPolicy(max_baseline_regression_ratio=0.05)
        cohort = baseline_cohort(improved=8, unchanged=1, regressed=1)
        findings = baseline_regression_guard([cohort], policy)
        assert len(findings) == 1
        assert findings[0].details["threshold"] == "0.050"


class TestPrimaryEndpointPairing:
    """Symmetric to `test_failure_improvement.py::TestPrimaryEndpointPairing`.
    The two rate-based guards are independent: each reads only its own
    cohort's counts. Pin the property on this side too so order- and
    isolation-independence are structurally tested.
    """

    def test_baseline_guard_ignores_failure_cohort(self) -> None:
        # Failure cohort is in catastrophe; baseline is healthy.
        # baseline_regression_guard should NOT fire on failure-cohort state.
        cohorts = [
            baseline_cohort(improved=10, unchanged=0, regressed=0),  # 0% regression
            failure_cohort(improved=0, unchanged=0, regressed=10),  # 100% regression in failure
        ]
        findings = baseline_regression_guard(cohorts, DecisionPolicy())
        assert findings == []  # baseline passes; failure regression is the other guard's concern

    def test_baseline_guard_only_reads_baseline_cohort_counts(self) -> None:
        # Baseline guard fires because baseline regressed_rate=2/10 > 0.10,
        # regardless of healthy failure counts.
        cohorts = [
            baseline_cohort(improved=6, unchanged=2, regressed=2),
            failure_cohort(improved=10, unchanged=0, regressed=0),
        ]
        findings = baseline_regression_guard(cohorts, DecisionPolicy())
        assert len(findings) == 1
        assert findings[0].details["observed"] == "0.200"
