"""Shared fixtures for Phase 9A integration tests.

Each scenario builder produces a `(StubTraceSource, delta_fn,
RunManifest, MethodologyDisclosure, CacheSummary)` tuple ready to
feed into `whatifd.pipeline.run_pipeline`. Future sub-phases (9A.2)
extend this module with the remaining walkthrough scenarios; the
current module ships scenario 1 (Clean Ship) only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType

from whatifd.adapters.protocols import RawTrace
from whatifd.adapters.stub import StubTraceSource, StubTraceSpec
from whatifd.cache.summary import CachePolicySnapshot, CacheSummary
from whatifd.types.manifest import EnvironmentFingerprint, RunManifest
from whatifd.types.policy import DecisionPolicy, TrustFloor
from whatifd.types.statistical import (
    BootstrapMethodDisclosure,
    EffectSizeDisclosure,
    JudgeMethodDisclosure,
    MethodologyDisclosure,
    MultiplicityDisclosure,
)


@dataclass(frozen=True, slots=True)
class IntegrationFixture:
    trace_source: StubTraceSource
    delta_fn: Callable[[RawTrace], float]
    runtime: RunManifest
    methodology: MethodologyDisclosure
    cache_summary: CacheSummary


def _default_runtime(*, floor: TrustFloor, policy: DecisionPolicy) -> RunManifest:
    return RunManifest(
        experiment_id="integration-test",
        started_at="2026-05-07T00:00:00Z",
        finished_at="2026-05-07T00:00:01Z",
        duration_ms=1000,
        whatif_version="0.1.0",
        config_hash="0" * 64,
        selection_seed=42,
        source="stub",
        target="stub",
        trust_floor=floor,
        decision_policy=policy,
        environment=EnvironmentFingerprint(
            python="3.13.0",
            platform="linux",
            whatif_version="0.1.0",
        ),
    )


def _default_methodology() -> MethodologyDisclosure:
    return MethodologyDisclosure(
        unit_of_analysis="paired_trace_delta",
        primary_metric="faithfulness",
        primary_endpoints=("failure.faithfulness", "baseline.faithfulness"),
        cohorts=("failure", "baseline"),
        # Phase 9A.1 ships an empirical-percentile shortcut, NOT
        # real bootstrap. The methodology disclosure says
        # `method="unavailable"` so consumers (renderers, future
        # determinism tests) don't read inconsistent state — there's
        # no real bootstrap to disclose. The `unavailable_reason`
        # spells out the shortcut. Phase 9A.3+ flips this to
        # `paired_percentile_bootstrap` with non-zero `resamples`
        # when the stats layer lands.
        bootstrap=BootstrapMethodDisclosure(
            method="unavailable",
            resamples=None,
            seed=None,
            sample_unit="paired_trace_delta",
            ci_level="0.950",
            cluster_key=None,
            assumptions=(),
            unavailable_reason=(
                "Phase 9A.1 empirical-percentile shortcut; proper "
                "stratified bootstrap pending stats-layer integration."
            ),
        ),
        multiplicity=MultiplicityDisclosure(
            primary_endpoint_count=2,
            correction="none",
            reason="single primary metric per cohort; no correction applied",
        ),
        judge=JudgeMethodDisclosure(
            scorer="stub",
            scorer_version="0.1.0",
            judge_provider="stub",
            judge_model="stub-judge",
            judge_model_version=None,
            rendered_prompt_hash="0" * 16,
            rubric_hash="0" * 16,
            scorer_cache_enabled=False,
            scorer_cache_mode="off",
            scorer_cache_hits=0,
            scorer_cache_misses=0,
            reproducibility_addressed=True,
            reliability_measured=False,
            validity_measured=False,
            calibration_measured=False,
            bias_audit_measured=False,
        ),
        effect_size=EffectSizeDisclosure(
            practical_delta="0.050",
            practical_delta_source="policy",
            judge_noise_floor=None,
        ),
        per_trace_inference="descriptive_only",
        causal_claim_scope="associated_under_cached_tool_replay",
    )


def _default_cache_summary() -> CacheSummary:
    return CacheSummary(
        schema_version="v1",
        key_version="v1",
        mode="off",
        storage_profile="normalized_result_only",
        storage_path=".whatifd/cache",
        hits=0,
        misses=0,
        writes=0,
        stale_hits=0,
        corrupted_entries=0,
        policy=CachePolicySnapshot(
            mode="off",
            warn_after_days=30,
            block_after_days=90,
            storage_profile="normalized_result_only",
        ),
        policy_violations=(),
        oldest_hit_age_days=None,
        models_distribution=MappingProxyType({}),
    )


def _build_fixture(
    *,
    failure_specs: list[StubTraceSpec],
    baseline_specs: list[StubTraceSpec],
    delta_fn: Callable[[RawTrace], float],
) -> IntegrationFixture:
    floor = TrustFloor()
    policy = DecisionPolicy()
    return IntegrationFixture(
        trace_source=StubTraceSource(specs=[*failure_specs, *baseline_specs]),
        delta_fn=delta_fn,
        runtime=_default_runtime(floor=floor, policy=policy),
        methodology=_default_methodology(),
        cache_summary=_default_cache_summary(),
    )


def _spec(idx: int, *, cohort: str) -> StubTraceSpec:
    prefix = "f" if cohort == "failure" else "b"
    return StubTraceSpec(
        trace_id=f"{prefix}-{idx:02d}",
        user_message=f"{cohort} prompt {idx}",
        original_response=f"{cohort} response {idx}",
        cohort=cohort,
    )


def _idx(trace_id: str) -> int:
    return int(trace_id.split("-")[1])


def scenario_clean_ship() -> IntegrationFixture:
    """Walkthrough scenario 1 — Clean Ship.

    Failure cohort: 20 traces, 14 improved (delta > epsilon),
    6 unchanged. Baseline cohort: 20 traces, all near-zero delta.
    """
    failures = [
        StubTraceSpec(
            trace_id=f"f-{i:02d}",
            user_message=f"failure prompt {i}",
            original_response=f"failure response {i}",
            cohort="failure",
        )
        for i in range(20)
    ]
    baselines = [
        StubTraceSpec(
            trace_id=f"b-{i:02d}",
            user_message=f"baseline prompt {i}",
            original_response=f"baseline response {i}",
            cohort="baseline",
        )
        for i in range(20)
    ]
    source = StubTraceSource(specs=[*failures, *baselines])

    def delta_fn(rt: RawTrace) -> float:
        # Failure cohort: 14 of 20 improved by 0.20; 6 unchanged at 0.0.
        # Baseline cohort: all near-zero (0.01 — under epsilon=0.05).
        if rt.cohort == "failure":
            idx = int(rt.trace_id.split("-")[1])
            return 0.20 if idx < 14 else 0.0
        return 0.01

    floor = TrustFloor()
    policy = DecisionPolicy()
    return IntegrationFixture(
        trace_source=source,
        delta_fn=delta_fn,
        runtime=_default_runtime(floor=floor, policy=policy),
        methodology=_default_methodology(),
        cache_summary=_default_cache_summary(),
    )


def scenario_dont_ship_regression() -> IntegrationFixture:
    """Walkthrough 02 — Don't Ship (baseline regression).

    Failure (20): improved 14, unchanged 3, regressed 3 → looks fine.
    Baseline (20): improved 1, unchanged 13, regressed 6 → 30% regression
    rate exceeds policy.max_baseline_regression_ratio=0.10 →
    `baseline_regression_above_threshold` blocks_ship → DontShip.
    """
    failures = [_spec(i, cohort="failure") for i in range(20)]
    baselines = [_spec(i, cohort="baseline") for i in range(20)]

    def delta_fn(rt: RawTrace) -> float:
        idx = _idx(rt.trace_id)
        if rt.cohort == "failure":
            if idx < 14:
                return 0.28  # improved
            if idx < 17:
                return 0.0  # unchanged
            return -0.10  # regressed (3 traces)
        # baseline: 1 improved, 13 unchanged, 6 regressed
        if idx == 0:
            return 0.10
        if idx < 14:
            return 0.0
        return -0.18  # 6 regressed

    return _build_fixture(failure_specs=failures, baseline_specs=baselines, delta_fn=delta_fn)


def scenario_dont_ship_failure_rescue_gap() -> IntegrationFixture:
    """Walkthrough 03 — Don't Ship (failure-rescue gap).

    Failure (20): improved 2 (10%) → below
    policy.min_failure_improvement_ratio=0.50 →
    `failure_cohort_no_improvement` blocks_ship → DontShip.
    Baseline (20): stable (clean).
    """
    failures = [_spec(i, cohort="failure") for i in range(20)]
    baselines = [_spec(i, cohort="baseline") for i in range(20)]

    def delta_fn(rt: RawTrace) -> float:
        idx = _idx(rt.trace_id)
        if rt.cohort == "failure":
            if idx < 2:
                return 0.20  # improved
            if idx < 18:
                return 0.0  # unchanged
            return -0.10  # 2 regressed
        # baseline: 1 improved, 18 unchanged, 1 regressed
        if idx == 0:
            return 0.08
        if idx < 19:
            return 0.0
        return -0.08

    return _build_fixture(failure_specs=failures, baseline_specs=baselines, delta_fn=delta_fn)


def scenario_inconclusive_insufficient_sample() -> IntegrationFixture:
    """Walkthrough 04 — Inconclusive (insufficient sample).

    Failure (15): improved 11, unchanged 3, regressed 1 — clean.
    Baseline (8 selected, 3 scored): 5 traces marked `skip_reason`
    so they reach the bucket but don't contribute deltas. 3 scored
    is below floor.min_scored_per_required_cohort=5 →
    `min_scored_per_required_cohort` floor_failure (blocks_all) →
    Inconclusive.
    """
    failures = [_spec(i, cohort="failure") for i in range(15)]
    # 8 baseline specs; 5 of them carry `skip_reason` so they're
    # selected but not scored.
    baselines: list[StubTraceSpec] = []
    for i in range(8):
        skip = "ingest_failed" if i >= 3 else None
        baselines.append(
            StubTraceSpec(
                trace_id=f"b-{i:02d}",
                user_message=f"baseline prompt {i}",
                original_response=f"baseline response {i}",
                cohort="baseline",
                skip_reason=skip,
            )
        )

    def delta_fn(rt: RawTrace) -> float:
        idx = _idx(rt.trace_id)
        if rt.cohort == "failure":
            if idx < 11:
                return 0.34
            if idx < 14:
                return 0.0
            return -0.10
        # Only the first 3 baseline specs (no skip_reason) reach here.
        # Boundary behavior pinned: pipeline.py classifies improved
        # via `delta > eps` (strict), so delta == eps is *unchanged*.
        # Returning 0.04 (strictly under eps=0.05) keeps this scenario
        # robust to a future widening of the operator (e.g., `>=`)
        # — the trace stays unchanged either way, isolating the
        # scenario's verdict signal to the floor failure (insufficient
        # baseline scoring), not to a borderline counter shift.
        return 0.04

    return _build_fixture(failure_specs=failures, baseline_specs=baselines, delta_fn=delta_fn)
