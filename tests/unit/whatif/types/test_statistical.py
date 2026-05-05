"""Tests for `whatif.types.statistical` — Phase 1.7, cardinal #10."""

from __future__ import annotations

import dataclasses

import pytest

from whatif.types import (
    BootstrapMethodDisclosure,
    ClusteringPolicy,
    ClusterKeySupport,
    ClusterSelection,
    DecimalString,
    EffectSizeDisclosure,
    JudgeMethodDisclosure,
    MethodologyDisclosure,
    MultiplicityDisclosure,
    TraceDelta,
    TraceDeltaReportV01,
)

# --- TraceDelta ---------------------------------------------------------


class TestTraceDelta:
    def test_delta_computed_from_scores(self) -> None:
        td = TraceDelta(
            trace_id="t_4a91f",
            cohort="failure",
            metric="faithfulness",
            original_score=0.50,
            replayed_score=0.81,
        )
        assert td.delta == pytest.approx(0.31)

    def test_negative_delta_for_regression(self) -> None:
        td = TraceDelta(
            trace_id="t_492af",
            cohort="baseline",
            metric="faithfulness",
            original_score=0.80,
            replayed_score=0.49,
        )
        assert td.delta == pytest.approx(-0.31)

    def test_zero_delta_when_scores_equal(self) -> None:
        td = TraceDelta(
            trace_id="t_x",
            cohort="failure",
            metric="faithfulness",
            original_score=0.50,
            replayed_score=0.50,
        )
        assert td.delta == 0.0

    def test_optional_cluster_id(self) -> None:
        td = TraceDelta(
            trace_id="t_x",
            cohort="failure",
            metric="faithfulness",
            original_score=0.5,
            replayed_score=0.7,
            cluster_id="conversation_123",
        )
        assert td.cluster_id == "conversation_123"

    def test_default_cluster_id_is_none(self) -> None:
        # When no cluster key is available, cluster_id is None and the
        # methodology block discloses the i.i.d. assumption.
        td = TraceDelta(
            trace_id="t_x",
            cohort="failure",
            metric="faithfulness",
            original_score=0.5,
            replayed_score=0.7,
        )
        assert td.cluster_id is None

    def test_default_strata_empty(self) -> None:
        td = TraceDelta(
            trace_id="t_x",
            cohort="failure",
            metric="faithfulness",
            original_score=0.5,
            replayed_score=0.7,
        )
        assert td.strata == {}

    def test_frozen(self) -> None:
        td = TraceDelta(
            trace_id="t_x",
            cohort="failure",
            metric="faithfulness",
            original_score=0.5,
            replayed_score=0.7,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            td.delta = 0.0  # type: ignore[misc]


class TestTraceDeltaReportV01:
    def test_construction_with_decimal_strings(self) -> None:
        # Public report shape: numerics as DecimalString for cross-platform
        # determinism.
        tdr = TraceDeltaReportV01(
            trace_id="t_4a91f",
            cohort="failure",
            metric="faithfulness",
            original_score=DecimalString("0.500"),
            replayed_score=DecimalString("0.810"),
            delta=DecimalString("0.310"),
        )
        assert tdr.delta == "0.310"

    def test_frozen(self) -> None:
        tdr = TraceDeltaReportV01(
            trace_id="t_x",
            cohort="failure",
            metric="faithfulness",
            original_score=DecimalString("0.500"),
            replayed_score=DecimalString("0.500"),
            delta=DecimalString("0.000"),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            tdr.delta = DecimalString("0.001")  # type: ignore[misc]


# --- BootstrapMethodDisclosure ------------------------------------------


class TestBootstrapMethodDisclosure:
    def test_paired_percentile_bootstrap(self) -> None:
        b = BootstrapMethodDisclosure(
            method="paired_percentile_bootstrap",
            resamples=5000,
            seed=42,
            sample_unit="paired_trace_delta",
            ci_level=DecimalString("0.95"),
            cluster_key=None,
            assumptions=("trace_independence",),
        )
        assert b.method == "paired_percentile_bootstrap"
        assert b.unavailable_reason is None

    def test_cluster_paired_bootstrap(self) -> None:
        b = BootstrapMethodDisclosure(
            method="cluster_paired_percentile_bootstrap",
            resamples=5000,
            seed=42,
            sample_unit="paired_trace_delta",
            ci_level=DecimalString("0.95"),
            cluster_key="conversation_id",
            assumptions=(),
        )
        assert b.cluster_key == "conversation_id"

    def test_unavailable_with_reason(self) -> None:
        b = BootstrapMethodDisclosure(
            method="unavailable",
            resamples=None,
            seed=None,
            sample_unit="paired_trace_delta",
            ci_level=DecimalString("0.95"),
            cluster_key=None,
            assumptions=(),
            unavailable_reason="cache locked, scoring stage did not run",
        )
        assert b.method == "unavailable"
        assert b.unavailable_reason is not None


# --- MultiplicityDisclosure ---------------------------------------------


class TestMultiplicityDisclosure:
    def test_v0_1_default_no_correction(self) -> None:
        # v0.1 default per cardinal #10: single primary metric per cohort,
        # no multiplicity correction applied.
        m = MultiplicityDisclosure(
            primary_endpoint_count=2,
            correction="none",
            reason="single primary metric per cohort; no correction applied",
        )
        assert m.correction == "none"

    @pytest.mark.parametrize("correction", ["none", "holm", "bonferroni", "bh_fdr"])
    def test_correction_literal_values(self, correction: str) -> None:
        m = MultiplicityDisclosure(
            primary_endpoint_count=1,
            correction=correction,  # type: ignore[arg-type]
            reason="test",
        )
        assert m.correction == correction


# --- JudgeMethodDisclosure ----------------------------------------------


class TestJudgeMethodDisclosure:
    def test_v0_1_default_only_reproducibility_addressed(self) -> None:
        # The cardinal #10 reliability discipline: scorer caching addresses
        # reproducibility; the other four (reliability, validity, calibration,
        # bias) are NOT measured by default.
        j = JudgeMethodDisclosure(
            scorer="inspect_ai",
            scorer_version="0.3.216",
            judge_provider="anthropic",
            judge_model="claude-haiku-4-5",
            judge_model_version=None,
            rendered_prompt_hash="abc123",
            rubric_hash="def456",
            scorer_cache_enabled=True,
            scorer_cache_mode="auto",
            scorer_cache_hits=38,
            scorer_cache_misses=2,
            reproducibility_addressed=True,
            reliability_measured=False,
            validity_measured=False,
            calibration_measured=False,
            bias_audit_measured=False,
        )
        assert j.reproducibility_addressed is True
        # The four NOT-measured concepts MUST be explicitly False, not
        # silently absent.
        assert j.reliability_measured is False
        assert j.validity_measured is False
        assert j.calibration_measured is False
        assert j.bias_audit_measured is False


# --- EffectSizeDisclosure -----------------------------------------------


class TestEffectSizeDisclosure:
    def test_v0_1_default_policy_source(self) -> None:
        # epsilon=0.05 default is policy, not empirically calibrated.
        e = EffectSizeDisclosure(
            practical_delta=DecimalString("0.050"),
            practical_delta_source="policy",
            judge_noise_floor=None,
        )
        assert e.practical_delta_source == "policy"
        assert e.warning is None

    def test_warning_when_epsilon_below_noise_floor(self) -> None:
        e = EffectSizeDisclosure(
            practical_delta=DecimalString("0.030"),
            practical_delta_source="calibrated_from_judge_noise_floor",
            judge_noise_floor=DecimalString("0.050"),
            warning="practical_delta below judge noise floor",
        )
        assert e.warning is not None

    @pytest.mark.parametrize(
        "source",
        ["policy", "calibrated_from_judge_noise_floor", "unknown"],
    )
    def test_source_literal_values(self, source: str) -> None:
        e = EffectSizeDisclosure(
            practical_delta=DecimalString("0.050"),
            practical_delta_source=source,  # type: ignore[arg-type]
            judge_noise_floor=None,
        )
        assert e.practical_delta_source == source


# --- MethodologyDisclosure (composite) ----------------------------------


class TestMethodologyDisclosure:
    def _v0_1_default(self) -> MethodologyDisclosure:
        return MethodologyDisclosure(
            unit_of_analysis="paired_trace_delta",
            primary_metric="faithfulness",
            primary_endpoints=("failure_improvement", "baseline_non_regression"),
            cohorts=("failure", "baseline"),
            bootstrap=BootstrapMethodDisclosure(
                method="paired_percentile_bootstrap",
                resamples=5000,
                seed=42,
                sample_unit="paired_trace_delta",
                ci_level=DecimalString("0.95"),
                cluster_key=None,
                assumptions=("trace_independence",),
            ),
            multiplicity=MultiplicityDisclosure(
                primary_endpoint_count=2,
                correction="none",
                reason="single primary metric per cohort; no correction applied",
            ),
            judge=JudgeMethodDisclosure(
                scorer="inspect_ai",
                scorer_version="0.3.216",
                judge_provider="anthropic",
                judge_model="claude-haiku-4-5",
                judge_model_version=None,
                rendered_prompt_hash="abc",
                rubric_hash="def",
                scorer_cache_enabled=True,
                scorer_cache_mode="auto",
                scorer_cache_hits=38,
                scorer_cache_misses=2,
                reproducibility_addressed=True,
                reliability_measured=False,
                validity_measured=False,
                calibration_measured=False,
                bias_audit_measured=False,
            ),
            effect_size=EffectSizeDisclosure(
                practical_delta=DecimalString("0.050"),
                practical_delta_source="policy",
                judge_noise_floor=None,
            ),
            per_trace_inference="descriptive_only",
            causal_claim_scope="associated_under_cached_tool_replay",
        )

    def test_v0_1_construction(self) -> None:
        m = self._v0_1_default()
        assert m.unit_of_analysis == "paired_trace_delta"
        assert m.per_trace_inference == "descriptive_only"
        assert m.causal_claim_scope == "associated_under_cached_tool_replay"
        assert m.limitations == ()  # default empty

    def test_v0_1_per_trace_inference_sealed_to_descriptive_only(self) -> None:
        # Cardinal #10: per-trace evidence is descriptive, not inferential.
        # The Literal type seals this; v0.2+ may extend with a minor
        # schema bump.
        m = self._v0_1_default()
        # The runtime check (Literal isn't enforced at runtime, just by
        # static analysis) — pin the v0.1 value.
        assert m.per_trace_inference == "descriptive_only"

    def test_v0_1_causal_claim_scope_sealed(self) -> None:
        # Cardinal #10 enforced rejection: "caused production regression"
        # is permanently rejected; "associated under cached-tool replay"
        # is the only allowed scope for v0.1.
        m = self._v0_1_default()
        assert m.causal_claim_scope == "associated_under_cached_tool_replay"

    def test_with_limitations(self) -> None:
        m = dataclasses.replace(
            self._v0_1_default(),
            limitations=(
                "baseline cohort below minimum sample for reliable CI",
                "scorer cache 4-day-stale; results may drift",
            ),
        )
        assert len(m.limitations) == 2

    def test_frozen(self) -> None:
        m = self._v0_1_default()
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.unit_of_analysis = "other"  # type: ignore[misc]


# --- Clustering types ---------------------------------------------------


class TestClusterKeySupport:
    def test_construction_with_keys(self) -> None:
        c = ClusterKeySupport(
            available_keys=("conversation_id", "user_id"),
        )
        assert c.available_keys == ("conversation_id", "user_id")
        assert c.preferred_order[0] == "conversation_id"

    def test_empty_keys_means_iid(self) -> None:
        c = ClusterKeySupport(available_keys=())
        assert len(c.available_keys) == 0


class TestClusterSelection:
    def test_selected_mode(self) -> None:
        s = ClusterSelection(
            mode="selected",
            key="conversation_id",
            reason="adapter declared support; preferred per ClusteringPolicy",
        )
        assert s.mode == "selected"
        assert s.key == "conversation_id"

    def test_none_mode_explicit_iid(self) -> None:
        s = ClusterSelection(
            mode="none",
            key=None,
            reason="user explicitly opted out via ClusteringPolicy.cluster_key='none'",
        )
        assert s.mode == "none"
        assert s.key is None

    def test_unavailable_mode(self) -> None:
        s = ClusterSelection(
            mode="unavailable",
            key=None,
            reason="adapter declared no cluster keys; falling back to i.i.d. with disclosure",
        )
        assert s.mode == "unavailable"


class TestClusteringPolicy:
    def test_default(self) -> None:
        p = ClusteringPolicy()
        assert p.cluster_key == "auto"
        assert p.fallback_behavior == "warn"

    def test_strict_refuse_mode(self) -> None:
        p = ClusteringPolicy(fallback_behavior="refuse")
        assert p.fallback_behavior == "refuse"

    @pytest.mark.parametrize("key", ["none", "auto", "user_id", "session_id", "conversation_id"])
    def test_cluster_key_literal_values(self, key: str) -> None:
        p = ClusteringPolicy(cluster_key=key)  # type: ignore[arg-type]
        assert p.cluster_key == key
