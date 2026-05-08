"""Tests for `whatifd.types.policy` — Phase 1.5 policy types."""

from __future__ import annotations

import dataclasses

import pytest

from whatifd.types import (
    DecisionPolicy,
    EndpointDirection,
    PrimaryEndpoint,
    TrustFloor,
)

# --- PrimaryEndpoint ----------------------------------------------------


class TestPrimaryEndpoint:
    def test_construction_with_required_fields(self) -> None:
        e = PrimaryEndpoint(cohort="failure", direction="improvement_above_threshold")
        assert e.cohort == "failure"
        assert e.metric == "faithfulness"  # default

    def test_construction_with_explicit_metric(self) -> None:
        e = PrimaryEndpoint(
            cohort="baseline",
            direction="non_regression_below_threshold",
            metric="helpfulness",
        )
        assert e.metric == "helpfulness"

    @pytest.mark.parametrize(
        "direction",
        ["improvement_above_threshold", "non_regression_below_threshold"],
    )
    def test_direction_literal(self, direction: EndpointDirection) -> None:
        e = PrimaryEndpoint(cohort="x", direction=direction)
        assert e.direction == direction

    def test_frozen(self) -> None:
        e = PrimaryEndpoint(cohort="x", direction="improvement_above_threshold")
        with pytest.raises(dataclasses.FrozenInstanceError):
            e.cohort = "y"  # type: ignore[misc]

    def test_structural_equality(self) -> None:
        e1 = PrimaryEndpoint(cohort="x", direction="improvement_above_threshold")
        e2 = PrimaryEndpoint(cohort="x", direction="improvement_above_threshold")
        assert e1 == e2


# --- TrustFloor ---------------------------------------------------------


class TestTrustFloor:
    def test_construction_with_defaults(self) -> None:
        f = TrustFloor()
        assert f.version == "v1"
        assert f.source == "whatif-0.1.0"
        assert f.min_selected_per_required_cohort == 5
        assert f.min_replayed_per_required_cohort == 5
        assert f.min_scored_per_required_cohort == 5
        assert f.min_replay_validity_ratio_per_required_cohort == 0.50

    def test_construction_with_overrides(self) -> None:
        # Overriding floor values: in production the floor is structural
        # and shouldn't be lowered by config; this test pins that the
        # type ALLOWS overrides (the structural enforcement is at
        # evaluate_floor() time, not at TrustFloor construction).
        f = TrustFloor(
            version="v2",
            source="whatif-0.2.0",
            min_scored_per_required_cohort=10,
            min_replay_validity_ratio_per_required_cohort=0.60,
        )
        assert f.version == "v2"
        assert f.min_scored_per_required_cohort == 10

    def test_frozen(self) -> None:
        f = TrustFloor()
        with pytest.raises(dataclasses.FrozenInstanceError):
            f.version = "v2"  # type: ignore[misc]

    def test_structural_equality(self) -> None:
        f1 = TrustFloor()
        f2 = TrustFloor()
        assert f1 == f2

    def test_hashable(self) -> None:
        # All fields are hashable scalars; TrustFloor is hashable.
        f = TrustFloor()
        assert hash(f) == hash(TrustFloor())


class TestTrustFloorRuleNames:
    def test_returns_canonical_order(self) -> None:
        # Per the cascade entry "Floor table rendering — passing rules
        # need to be enumerable", the renderer iterates this list in
        # canonical order to produce the per-cohort floor evaluation
        # table.
        names = TrustFloor.rule_names()
        assert names == (
            "min_selected_per_required_cohort",
            "min_replayed_per_required_cohort",
            "min_scored_per_required_cohort",
            "min_replay_validity_ratio_per_required_cohort",
        )

    def test_returns_tuple_not_list(self) -> None:
        # Tuple signals immutability; reordering is a schema change.
        assert isinstance(TrustFloor.rule_names(), tuple)

    def test_classmethod_callable_without_instance(self) -> None:
        # Renderer doesn't need a TrustFloor instance to enumerate rules.
        # Phase 7 renderer test will exercise this directly.
        assert len(TrustFloor.rule_names()) == 4

    def test_rule_names_match_dataclass_fields(self) -> None:
        # Discipline check: every rule name in the canonical list
        # corresponds to a real field on TrustFloor. If a future contributor
        # adds a floor field but forgets to update rule_names(), this test
        # catches it.
        floor_fields = {f.name for f in dataclasses.fields(TrustFloor)}
        rule_names = set(TrustFloor.rule_names())
        # All declared rules must exist as fields
        assert rule_names.issubset(floor_fields), (
            f"rule_names() includes names not in TrustFloor fields: {rule_names - floor_fields}"
        )


# --- DecisionPolicy -----------------------------------------------------


class TestDecisionPolicy:
    def test_construction_with_defaults(self) -> None:
        p = DecisionPolicy()
        assert p.require_baseline is True
        assert p.required_cohorts == ("failure", "baseline")
        assert p.max_baseline_regression_ratio == 0.10
        assert p.min_failure_improvement_ratio == 0.50
        assert p.max_ci_width is None
        assert p.practical_delta_epsilon == 0.05
        assert p.scorer_cache_mode == "auto"
        assert p.scorer_cache_warn_after_days == 30
        assert p.scorer_cache_block_after_days == 90
        assert p.scorer_cache_storage_profile == "normalized_result_only"

    def test_default_primary_endpoints_match_v0_1_design(self) -> None:
        p = DecisionPolicy()
        assert len(p.primary_endpoints) == 2

        cohorts = {e.cohort for e in p.primary_endpoints}
        assert cohorts == {"failure", "baseline"}

        directions_by_cohort = {e.cohort: e.direction for e in p.primary_endpoints}
        assert directions_by_cohort["failure"] == "improvement_above_threshold"
        assert directions_by_cohort["baseline"] == "non_regression_below_threshold"

        # All v0.1 default endpoints use the same metric
        metrics = {e.metric for e in p.primary_endpoints}
        assert metrics == {"faithfulness"}

    def test_default_primary_endpoints_are_separate_per_instance(self) -> None:
        # field(default_factory=lambda: ...) returns the same tuple each
        # time. Tuples are immutable so sharing is safe — but pin this
        # so a future refactor (e.g., to list[PrimaryEndpoint]) doesn't
        # introduce shared mutable state.
        p1 = DecisionPolicy()
        p2 = DecisionPolicy()
        assert p1.primary_endpoints == p2.primary_endpoints

    def test_construction_with_custom_primary_endpoints(self) -> None:
        custom = (PrimaryEndpoint(cohort="failure", direction="improvement_above_threshold"),)
        p = DecisionPolicy(primary_endpoints=custom)
        assert len(p.primary_endpoints) == 1

    def test_max_ci_width_can_be_set(self) -> None:
        p = DecisionPolicy(max_ci_width=0.30)
        assert p.max_ci_width == 0.30

    def test_cache_storage_profile_literal(self) -> None:
        p = DecisionPolicy(scorer_cache_storage_profile="full_judge_io")
        assert p.scorer_cache_storage_profile == "full_judge_io"

    @pytest.mark.parametrize(
        "mode",
        ["auto", "on", "off", "read_only", "refresh"],
    )
    def test_cache_mode_literal_values(self, mode: str) -> None:
        p = DecisionPolicy(scorer_cache_mode=mode)  # type: ignore[arg-type]
        assert p.scorer_cache_mode == mode

    def test_frozen(self) -> None:
        p = DecisionPolicy()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.require_baseline = False  # type: ignore[misc]

    def test_structural_equality(self) -> None:
        p1 = DecisionPolicy()
        p2 = DecisionPolicy()
        assert p1 == p2

    def test_inequality_on_field_diff(self) -> None:
        p1 = DecisionPolicy()
        p2 = DecisionPolicy(max_baseline_regression_ratio=0.05)
        assert p1 != p2
