"""Walkthrough fixture builders for Phase 7.1c.

Each builder produces a `ReportV01` matching the "Underlying state"
section of the corresponding `docs/walkthroughs/0X-*.md` scenario.
The shared assertion surface is in `test_walkthroughs.py` —
builders here just shape the data.

## Why structural fidelity, not byte equality

The original Phase 7 gate per `phases.md` is "render → byte-equal
docs/walkthroughs/*.md". The walkthroughs reference features
that are deferred from v0.1:

- Per-trace evidence schema (scenarios 2, 3) — not in v0.1
  `CohortResult` / `FailureRecord`. Cascade entry tracks.
- Multi-cause fix-suggestion templating (scenario 3) — current
  `FixSuggestion` shape is single-template; multi-cause is v0.2.
- Floor evaluation table with PASSING rules surfaced (scenario 4)
  — `CohortResult.floor_failures` only carries failures; passing
  rules require `TrustFloor` enumeration. Cascade entry tracks.

Phase 7.1c ships STRUCTURAL fidelity tests now and defers byte-
equality to a follow-up that lands alongside the deferred
features. Each fixture is concrete enough to drive a future byte-
equality test without re-discovery.
"""

from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import NamedTuple

from whatifd.cache.summary import CachePolicySnapshot, CacheSummary
from whatifd.decision.finding_codes import make_decision_finding
from whatifd.report.models_v01 import ReportV01
from whatifd.types.cohort import CohortResult, FloorFailure
from whatifd.types.failure import FailureRecord
from whatifd.types.primitives import DecimalString
from whatifd.types.statistical import (
    BootstrapMethodDisclosure,
    EffectSizeDisclosure,
    JudgeMethodDisclosure,
    MethodologyDisclosure,
    MultiplicityDisclosure,
)


def _methodology() -> MethodologyDisclosure:
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
            cluster_key="conversation_id",
            assumptions=(),
            unavailable_reason=None,
        ),
        multiplicity=MultiplicityDisclosure(
            primary_endpoint_count=2,
            correction="none",
            reason="single primary metric per cohort",
        ),
        judge=JudgeMethodDisclosure(
            scorer="faithfulness",
            scorer_version="0.1",
            judge_provider="anthropic",
            judge_model="claude-haiku-4-5",
            judge_model_version=None,
            rendered_prompt_hash="x" * 64,
            rubric_hash=None,
            scorer_cache_enabled=True,
            scorer_cache_mode="on",
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
            warning=None,
        ),
        per_trace_inference="descriptive_only",
        causal_claim_scope="associated_under_cached_tool_replay",
    )


def _cache_summary(hits: int = 38, misses: int = 2) -> CacheSummary:
    return CacheSummary(
        schema_version="v1",
        key_version="v1",
        mode="on",
        storage_profile="normalized_result_only",
        storage_path=".whatif/cache",
        hits=hits,
        misses=misses,
        writes=misses,
        stale_hits=0,
        corrupted_entries=0,
        policy=CachePolicySnapshot(
            mode="on",
            warn_after_days=30,
            block_after_days=90,
            storage_profile="normalized_result_only",
        ),
        models_distribution=MappingProxyType({"claude-haiku-4-5": hits + misses}),
    )


def _cohort(
    name: str,
    *,
    selected: int,
    replayed: int,
    scored: int,
    improved: int,
    unchanged: int,
    regressed: int,
    median_delta: str | None = None,
    ci_lower: str | None = None,
    ci_upper: str | None = None,
    floor_failures: tuple[FloorFailure, ...] = (),
    ci_unavailable_reason: str | None = None,
) -> CohortResult:
    return CohortResult(
        name=name,
        selected=selected,
        replayed=replayed,
        scored=scored,
        ci_computable=ci_lower is not None,
        ci_unavailable_reason=ci_unavailable_reason,
        median_delta=DecimalString(median_delta) if median_delta else None,
        ci_lower=DecimalString(ci_lower) if ci_lower else None,
        ci_upper=DecimalString(ci_upper) if ci_upper else None,
        floor_passed=not floor_failures,
        floor_failures=list(floor_failures),
        improved_count=improved,
        unchanged_count=unchanged,
        regressed_count=regressed,
        # ci_meaningful is the quality assessment of a computed CI;
        # for non-computable CIs the field is irrelevant and defaults
        # to True (benign no-op per CohortResult.__post_init__).
        ci_meaningful=True,
    )


# ---------------------------------------------------------------------------
# Scenario builders
# ---------------------------------------------------------------------------


def scenario_1_clean_ship():
    """Clean Ship: failures 14/20 improved, baseline stable."""
    from whatifd.report.projection import project_to_report_v01
    from whatifd.types.policy import TrustFloor
    from whatifd.types.verdict import Ship

    from ..report._fixtures import (
        runtime as _runtime,
    )

    failure = _cohort(
        "failure",
        selected=20,
        replayed=20,
        scored=20,
        improved=14,
        unchanged=4,
        regressed=2,
        median_delta="0.310",
        ci_lower="0.180",
        ci_upper="0.440",
    )
    baseline = _cohort(
        "baseline",
        selected=20,
        replayed=20,
        scored=20,
        improved=3,
        unchanged=16,
        regressed=1,
        median_delta="0.020",
        ci_lower="-0.010",
        ci_upper="0.050",
    )

    from whatifd.decision.floor import FloorPassedProof, evaluate_floor

    proof_or_failures = evaluate_floor(
        [failure, baseline],
        TrustFloor(),
        required_cohorts=("failure", "baseline"),
    )
    assert isinstance(proof_or_failures, FloorPassedProof)
    verdict = Ship(
        proof=proof_or_failures,
        cohort_results=[failure, baseline],
        findings=[],
    )
    return project_to_report_v01(
        verdict,
        failures=[],
        cache_summary=_cache_summary(38, 2),
        methodology=_methodology(),
        runtime=_runtime(),
    )


def scenario_2_dont_ship_regression():
    """Don't Ship: 30% baseline regression."""
    from whatifd.report.projection import project_to_report_v01
    from whatifd.types.verdict import DontShip

    from ..report._fixtures import runtime as _runtime

    failure = _cohort(
        "failure",
        selected=20,
        replayed=20,
        scored=20,
        improved=14,
        unchanged=3,
        regressed=3,
        median_delta="0.280",
        ci_lower="0.150",
        ci_upper="0.410",
    )
    baseline = _cohort(
        "baseline",
        selected=20,
        replayed=20,
        scored=20,
        improved=1,
        unchanged=13,
        regressed=6,
        median_delta="-0.180",
        ci_lower="-0.240",
        ci_upper="-0.120",
    )
    finding = make_decision_finding(
        code="baseline_regression_above_threshold",
        message="baseline cohort regressed 6/20 traces (30%), exceeding the 10% threshold.",
        details={"observed": "0.300", "threshold": "0.100"},
    )
    verdict = DontShip(
        cohort_results=[failure, baseline],
        findings=[finding],
        blocking_findings=[finding],
    )
    return project_to_report_v01(
        verdict,
        failures=[],
        cache_summary=_cache_summary(39, 1),
        methodology=_methodology(),
        runtime=_runtime(),
    )


def scenario_3_dont_ship_failure_rescue_gap():
    """Don't Ship: failure cohort improved only 2/20."""
    from whatifd.report.projection import project_to_report_v01
    from whatifd.types.verdict import DontShip

    from ..report._fixtures import runtime as _runtime

    failure = _cohort(
        "failure",
        selected=20,
        replayed=20,
        scored=20,
        improved=2,
        unchanged=16,
        regressed=2,
        median_delta="0.030",
        ci_lower="-0.020",
        ci_upper="0.080",
    )
    baseline = _cohort(
        "baseline",
        selected=20,
        replayed=20,
        scored=20,
        improved=1,
        unchanged=18,
        regressed=1,
        median_delta="0.010",
        ci_lower="-0.020",
        ci_upper="0.040",
    )
    finding = make_decision_finding(
        code="failure_improvement_below_threshold",
        message="failure cohort only 2/20 (10%) improved; need 50%.",
        details={"observed": "0.100", "threshold": "0.500"},
    )
    verdict = DontShip(
        cohort_results=[failure, baseline],
        findings=[finding],
        blocking_findings=[finding],
    )
    return project_to_report_v01(
        verdict,
        failures=[],
        cache_summary=_cache_summary(39, 1),
        methodology=_methodology(),
        runtime=_runtime(),
    )


def scenario_4_inconclusive_insufficient_sample():
    """Inconclusive: baseline floor failure (3 scored < 5 required)."""
    from whatifd.report.projection import project_to_report_v01
    from whatifd.types.verdict import Inconclusive

    from ..report._fixtures import runtime as _runtime

    failure = _cohort(
        "failure",
        selected=15,
        replayed=15,
        scored=15,
        improved=11,
        unchanged=3,
        regressed=1,
        median_delta="0.340",
        ci_lower="0.210",
        ci_upper="0.470",
    )
    baseline_floor = (
        FloorFailure(
            rule="min_scored_per_required_cohort",
            observed=3,
            threshold=5,
            severity="blocks_all",
        ),
    )
    baseline = _cohort(
        "baseline",
        selected=8,
        replayed=5,
        scored=3,
        improved=2,
        unchanged=1,
        regressed=0,
        median_delta="0.050",
        ci_unavailable_reason="sample_too_small",
        floor_failures=baseline_floor,
    )
    verdict = Inconclusive(
        cohort_results=[failure, baseline],
        findings=[],
        floor_failures=list(baseline_floor),
    )
    return project_to_report_v01(
        verdict,
        failures=[],
        cache_summary=_cache_summary(33, 7),
        methodology=_methodology(),
        runtime=_runtime(),
    )


def scenario_5_inconclusive_cache_corruption():
    """Inconclusive: scorer cache locked by stale process.

    NOTE: this Inconclusive is FINDING-DRIVEN, not floor-driven.
    `cache_lock_unavailable` is a `blocks_all` finding (registered
    in FINDING_CODE_REGISTRY); it makes the verdict Inconclusive
    even though `floor_failures=[]` because no cohorts were
    evaluated (scoring stage couldn't run). This is NOT a cardinal-
    rule-#2 bypass — the floor wasn't bypassed; it was never
    reached. `Inconclusive.blocking_findings` is the load-bearing
    field here, not `floor_failures`.
    """
    from whatifd.report.projection import project_to_report_v01
    from whatifd.types.verdict import Inconclusive

    from ..report._fixtures import runtime as _runtime

    finding = make_decision_finding(
        code="cache_lock_unavailable",
        message="scorer cache locked by stale process",
        details={"lock_path": ".whatif/cache/.lock"},
        derived_from_failures=["failure_001"],
    )
    failure_record = FailureRecord(
        id="failure_001",
        code="cache_lock_unavailable",
        stage="replay",
        scope="run",
        message="cache lock file held by PID 42 (alive)",
        trace_id=None,
        cohort=None,
        retryable=False,
        details={"lock_path": ".whatif/cache/.lock"},
    )
    verdict = Inconclusive(
        cohort_results=[],
        findings=[finding],
        blocking_findings=[finding],
    )
    return project_to_report_v01(
        verdict,
        failures=[failure_record],
        cache_summary=_cache_summary(0, 0),
        methodology=_methodology(),
        runtime=_runtime(),
    )


def scenario_6_rerun_after_fix() -> ReportV01:
    """Rerun-after-fix: post-fix Ship verdict.

    Structurally similar to scenario 1 (clean Ship), but represents
    the recovery path from a previous Inconclusive run. Distinguished
    via the runtime's `experiment_id` so tests that assert on the
    walkthrough identity (vs scenario 1) have a discriminator.

    RISK: this builder DELEGATES to scenario_1_clean_ship() and
    only overrides experiment_id. If scenario 6's walkthrough
    later diverges from scenario 1 in stats (e.g., post-fix
    numbers don't match the original clean-Ship counts), the
    delegation will silently produce stale data — the test would
    pass against scenario 1's stats, not scenario 6's. Future
    divergence MUST be expressed by replacing the delegation with
    explicit per-field overrides (or a fresh builder) so the
    drift surfaces.
    """
    import dataclasses

    base = scenario_1_clean_ship()
    rerun_runtime = dataclasses.replace(
        base.runtime,
        experiment_id="rerun-after-fix-001",
    )
    return dataclasses.replace(base, runtime=rerun_runtime)


class Scenario(NamedTuple):
    """Named record for one walkthrough scenario.

    Replaces a positional `(name, expected_verdict_state, builder)`
    tuple — explicit fields prevent silent index-shift bugs if the
    record shape ever grows (e.g., adding `expected_ci_status` for
    a future byte-equality test).
    """

    name: str
    expected_verdict_state: str
    builder: Callable[[], ReportV01]


# Map by scenario number for parameterized testing.
SCENARIOS: dict[int, Scenario] = {
    1: Scenario("Clean Ship", "ship", scenario_1_clean_ship),
    2: Scenario("Don't Ship (regression)", "dont_ship", scenario_2_dont_ship_regression),
    3: Scenario(
        "Don't Ship (failure rescue gap)",
        "dont_ship",
        scenario_3_dont_ship_failure_rescue_gap,
    ),
    4: Scenario(
        "Inconclusive (insufficient sample)",
        "inconclusive",
        scenario_4_inconclusive_insufficient_sample,
    ),
    5: Scenario(
        "Inconclusive (cache corruption)",
        "inconclusive",
        scenario_5_inconclusive_cache_corruption,
    ),
    6: Scenario("Rerun after fix", "ship", scenario_6_rerun_after_fix),
}


__all__ = [
    "SCENARIOS",
    "Scenario",
    "scenario_1_clean_ship",
    "scenario_2_dont_ship_regression",
    "scenario_3_dont_ship_failure_rescue_gap",
    "scenario_4_inconclusive_insufficient_sample",
    "scenario_5_inconclusive_cache_corruption",
    "scenario_6_rerun_after_fix",
]
