"""Tests for `failure_improvement_guard` — cardinal #10 primary endpoint."""

from __future__ import annotations

from whatif.decision.guards.failure_improvement import failure_improvement_guard
from whatif.types.policy import DecisionPolicy

from ._helpers import baseline_cohort, failure_cohort


class TestFailureImprovementEmits:
    def test_emits_when_improvement_rate_below_threshold(self) -> None:
        # 4/20 = 0.200 < default threshold 0.50 → emit
        cohort = failure_cohort(improved=4, unchanged=10, regressed=6)
        findings = failure_improvement_guard([cohort], DecisionPolicy())
        assert len(findings) == 1
        f = findings[0]
        assert f.code == "failure_improvement_below_threshold"
        assert f.severity == "blocks_ship"
        assert f.details["observed"] == "0.200"
        assert f.details["threshold"] == "0.500"

    def test_message_includes_count_breakdown(self) -> None:
        cohort = failure_cohort(improved=4, unchanged=10, regressed=6)
        findings = failure_improvement_guard([cohort], DecisionPolicy())
        assert "4/20" in findings[0].message


class TestFailureImprovementSilent:
    def test_silent_at_exactly_threshold(self) -> None:
        # 5/10 = 0.500 == threshold → meets policy "at least 50%" promise
        cohort = failure_cohort(improved=5, unchanged=3, regressed=2)
        findings = failure_improvement_guard([cohort], DecisionPolicy())
        assert findings == []

    def test_silent_above_threshold(self) -> None:
        # 11/15 ≈ 0.733 > 0.50
        cohort = failure_cohort(improved=11, unchanged=3, regressed=1)
        findings = failure_improvement_guard([cohort], DecisionPolicy())
        assert findings == []

    def test_silent_when_no_failure_cohort(self) -> None:
        # Only baseline cohort; this guard targets failure.
        findings = failure_improvement_guard(
            [baseline_cohort(improved=2, unchanged=8)], DecisionPolicy()
        )
        assert findings == []

    def test_silent_when_total_scored_zero(self) -> None:
        # Zero counts → can't compute rate; floor catches structural case.
        cohort = failure_cohort(improved=0, unchanged=0, regressed=0)
        findings = failure_improvement_guard([cohort], DecisionPolicy())
        assert findings == []


class TestFailureImprovementCustomThreshold:
    def test_respects_custom_higher_threshold(self) -> None:
        # 5/10 = 0.500 vs custom threshold 0.80 → emit (below)
        policy = DecisionPolicy(min_failure_improvement_ratio=0.80)
        cohort = failure_cohort(improved=5, unchanged=3, regressed=2)
        findings = failure_improvement_guard([cohort], policy)
        assert len(findings) == 1
        assert findings[0].details["threshold"] == "0.800"

    def test_respects_custom_lower_threshold(self) -> None:
        # 2/10 = 0.200 vs custom threshold 0.10 → meets (no emit)
        policy = DecisionPolicy(min_failure_improvement_ratio=0.10)
        cohort = failure_cohort(improved=2, unchanged=4, regressed=4)
        findings = failure_improvement_guard([cohort], policy)
        assert findings == []


class TestPrimaryEndpointPairing:
    """The two rate-based guards form cardinal #10's primary endpoints
    for v0.1's failure-rescue scope. Test that they're independent —
    one cohort's outcome doesn't affect the other guard's decision.
    """

    def test_failure_guard_ignores_baseline_cohort(self) -> None:
        # Baseline regression doesn't cause the failure guard to fire.
        cohorts = [
            failure_cohort(improved=10, unchanged=0, regressed=0),  # 100% improvement
            baseline_cohort(improved=0, unchanged=0, regressed=10),  # 100% regression
        ]
        findings = failure_improvement_guard(cohorts, DecisionPolicy())
        assert findings == []  # failure passes; baseline regression is the other guard's concern

    def test_failure_guard_only_reads_failure_cohort_counts(self) -> None:
        # Failure guard fires because failure_improved=2/10 < 0.5,
        # regardless of healthy baseline counts.
        cohorts = [
            failure_cohort(improved=2, unchanged=4, regressed=4),
            baseline_cohort(improved=10, unchanged=0, regressed=0),
        ]
        findings = failure_improvement_guard(cohorts, DecisionPolicy())
        assert len(findings) == 1
        assert findings[0].details["observed"] == "0.200"
