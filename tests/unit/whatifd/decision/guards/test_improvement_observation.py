"""Tests for `improvement_observation_guard`."""

from __future__ import annotations

from whatifd.decision.guards.improvement_observation import improvement_observation_guard
from whatifd.decision.guards.practical_delta import practical_delta_guard
from whatifd.types.policy import DecisionPolicy

from ._helpers import failure_cohort as _failure_cohort


class TestImprovementObservationEmits:
    def test_emits_when_delta_above_epsilon(self) -> None:
        # 0.310 > 0.050 default → emit info finding
        findings = improvement_observation_guard([_failure_cohort("0.310")], DecisionPolicy())
        assert len(findings) == 1
        f = findings[0]
        assert f.code == "improvement_observed"
        assert f.severity == "info"
        assert f.details["median_delta"] == "0.310"
        # Self-describing: threshold is in details so the renderer can
        # show "your delta X is above threshold Y → improvement observed".
        assert f.details["threshold"] == "0.050"

    def test_threshold_detail_reflects_custom_epsilon(self) -> None:
        # Custom policy epsilon → emitted threshold matches policy.
        policy = DecisionPolicy(practical_delta_epsilon=0.10)
        findings = improvement_observation_guard([_failure_cohort("0.310")], policy)
        assert len(findings) == 1
        assert findings[0].details["threshold"] == "0.100"


class TestImprovementObservationSilent:
    def test_silent_at_exactly_epsilon(self) -> None:
        # Strict > means equality does NOT emit. practical_delta_guard
        # picks this up instead. Pin the boundary behavior.
        findings = improvement_observation_guard([_failure_cohort("0.050")], DecisionPolicy())
        assert findings == []

    def test_silent_below_epsilon(self) -> None:
        findings = improvement_observation_guard([_failure_cohort("0.030")], DecisionPolicy())
        assert findings == []

    def test_silent_for_negative_delta(self) -> None:
        # Negative delta is regression; this guard is the improvement observer.
        findings = improvement_observation_guard([_failure_cohort("-0.100")], DecisionPolicy())
        assert findings == []

    def test_silent_when_no_failure_cohort(self) -> None:
        findings = improvement_observation_guard([], DecisionPolicy())
        assert findings == []

    def test_silent_when_median_delta_is_none(self) -> None:
        findings = improvement_observation_guard([_failure_cohort(None)], DecisionPolicy())
        assert findings == []


class TestMutualExclusionWithPracticalDelta:
    """The two guards are contracted-as-mutually-exclusive on a single cohort.

    practical_delta uses `<=`; improvement_observation uses `>`. Together
    they partition the real number line cleanly. Tests pin the boundary.
    """

    def test_exactly_at_epsilon_only_practical_delta_emits(self) -> None:
        cohorts = [_failure_cohort("0.050")]
        practical = practical_delta_guard(cohorts, DecisionPolicy())
        observation = improvement_observation_guard(cohorts, DecisionPolicy())
        assert len(practical) == 1
        assert observation == []

    def test_just_above_epsilon_only_observation_emits(self) -> None:
        # 0.051 > 0.050 → observation only
        cohorts = [_failure_cohort("0.051")]
        practical = practical_delta_guard(cohorts, DecisionPolicy())
        observation = improvement_observation_guard(cohorts, DecisionPolicy())
        assert practical == []
        assert len(observation) == 1

    def test_just_below_epsilon_only_practical_delta_emits(self) -> None:
        # 0.049 < 0.050 → practical only
        cohorts = [_failure_cohort("0.049")]
        practical = practical_delta_guard(cohorts, DecisionPolicy())
        observation = improvement_observation_guard(cohorts, DecisionPolicy())
        assert len(practical) == 1
        assert observation == []
