"""Shared fixture builders for `tests/unit/whatifd/report/`.

`test_models_v01.py` (Phase 5.1) and `test_projection.py` (Phase 5.2)
both need fully-typed instances of the dependent sub-shapes
(`CohortResult`, `CacheSummary`, `MethodologyDisclosure`, `RunManifest`,
etc.) AND realistic `Verdict` instances. Centralizing the builders
here:

- Avoids drift between the two test files' fixture shapes.
- Gives a single place to update when a sub-shape adds a required
  field (one builder edit, not N).
- Keeps individual test files focused on the assertion they're
  pinning, not on the construction boilerplate.
- Centralizes the witness-token path (`ship()` routes through
  `evaluate_floor` to obtain a real `FloorPassedProof`) so future
  test files don't re-implement verdict construction and risk
  diverging from the canonical cardinal #2 path.

Each builder is a no-arg factory returning a known-good instance,
matching the pattern Phase 3.x test files used internally
(`_components()` in `test_v1.py`, `_summary()` in `test_summary.py`).
"""

from __future__ import annotations

from whatifd.cache.summary import CachePolicySnapshot, CacheSummary
from whatifd.decision.finding_codes import make_decision_finding
from whatifd.decision.floor import FloorPassedProof, evaluate_floor
from whatifd.types.cohort import CohortResult
from whatifd.types.manifest import EnvironmentFingerprint, RunManifest
from whatifd.types.policy import DecisionPolicy, PrimaryEndpoint, TrustFloor
from whatifd.types.primitives import DecimalString
from whatifd.types.statistical import (
    BootstrapMethodDisclosure,
    EffectSizeDisclosure,
    JudgeMethodDisclosure,
    MethodologyDisclosure,
    MultiplicityDisclosure,
)
from whatifd.types.verdict import DontShip, Inconclusive, Ship


def trust_floor() -> TrustFloor:
    return TrustFloor()


def decision_policy() -> DecisionPolicy:
    return DecisionPolicy(
        primary_endpoints=(
            PrimaryEndpoint(
                cohort="failure",
                direction="improvement_above_threshold",
            ),
        ),
    )


def cohort(name: str = "failure") -> CohortResult:
    return CohortResult(
        name=name,
        selected=10,
        replayed=10,
        scored=10,
        ci_computable=True,
        ci_unavailable_reason=None,
        median_delta=DecimalString("0.250"),
        ci_lower=DecimalString("0.150"),
        ci_upper=DecimalString("0.350"),
        floor_passed=True,
    )


def cache_summary() -> CacheSummary:
    return CacheSummary(
        schema_version="v1",
        key_version="v1",
        mode="on",
        storage_profile="normalized_result_only",
        storage_path=".whatif/cache",
        hits=8,
        misses=2,
        writes=2,
        stale_hits=0,
        corrupted_entries=0,
        policy=CachePolicySnapshot(
            mode="on",
            warn_after_days=30,
            block_after_days=90,
            storage_profile="normalized_result_only",
        ),
    )


def methodology() -> MethodologyDisclosure:
    return MethodologyDisclosure(
        unit_of_analysis="paired_trace_delta",
        primary_metric="faithfulness",
        primary_endpoints=("failure_improvement_above_0.50",),
        cohorts=("failure", "baseline"),
        bootstrap=BootstrapMethodDisclosure(
            method="paired_percentile_bootstrap",
            resamples=10000,
            seed=42,
            sample_unit="paired_trace_delta",
            ci_level=DecimalString("0.95"),
            cluster_key=None,
            assumptions=("trace_independence",),
        ),
        multiplicity=MultiplicityDisclosure(
            primary_endpoint_count=1,
            correction="none",
            reason="single primary metric per cohort; no correction applied",
        ),
        judge=JudgeMethodDisclosure(
            scorer="inspect_ai.Faithfulness",
            scorer_version="0.3.5",
            judge_provider="anthropic",
            judge_model="claude-sonnet-4-6",
            judge_model_version="20251001",
            rendered_prompt_hash="aa" * 32,
            rubric_hash="bb" * 32,
            scorer_cache_enabled=True,
            scorer_cache_mode="on",
            scorer_cache_hits=8,
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


def runtime() -> RunManifest:
    """Build a known-good `RunManifest` for tests.

    **Omitted (defaulted) fields:** `agent_identity`, `redaction`,
    `sensitive_unwraps`. Each takes its `RunManifest`-declared default:

    - `agent_identity = None` — no operator-attribution override.
    - `redaction = {}` — empty redaction metadata; tests that
      exercise redaction explicitly populate this.
    - `sensitive_unwraps = []` — no `Sensitive[T]` unwraps occurred
      during the simulated run; tests that exercise the audit trail
      populate this.

    If a future `RunManifest` change makes any of those three fields
    REQUIRED, the constructor call here fails loudly with a
    missing-arg error — that's the right surface for catching the
    drift, rather than silently defaulting via the fixture.
    """
    return RunManifest(
        experiment_id="exp-001",
        started_at="2026-05-06T10:00:00Z",
        finished_at="2026-05-06T10:01:00Z",
        duration_ms=60000,
        whatif_version="0.0.1",
        config_hash="cc" * 32,
        selection_seed=42,
        source="langfuse://test",
        target="my_agent.replay:run",
        trust_floor=trust_floor(),
        decision_policy=decision_policy(),
        environment=EnvironmentFingerprint(
            python="3.13.0",
            platform="linux-x86_64",
            whatif_version="0.0.1",
        ),
    )


def ship() -> Ship:
    """Construct a real `Ship` via the witness-token chain.

    Routes through `evaluate_floor()` so the resulting `Ship` carries
    a real `FloorPassedProof`. Tests that exercise any projection or
    verdict-consuming surface MUST go through this path — that's the
    cardinal #2 enforcement (only `evaluate_floor` produces valid
    proofs). A direct construction with a fabricated proof would
    bypass the structural guarantee the witness-token closure-capture
    exists to enforce.
    """
    cohorts = [cohort("failure"), cohort("baseline")]
    proof_or_failures = evaluate_floor(
        cohorts,
        trust_floor(),
        required_cohorts=("failure", "baseline"),
    )
    # Direct isinstance against the witness type — narrows for mypy
    # AND fails loud if the test fixture's cohorts ever stop passing
    # the floor (so the failure surfaces here, not deeper in a
    # consumer test). No `type: ignore` needed.
    assert isinstance(proof_or_failures, FloorPassedProof), (
        f"test fixture invariant: cohort()/trust_floor() must produce a "
        f"floor-passing run; evaluate_floor returned {proof_or_failures!r}"
    )
    return Ship(
        proof=proof_or_failures,
        cohort_results=cohorts,
        findings=[],
    )


def dont_ship() -> DontShip:
    """Construct a `DontShip` with a representative blocking finding.

    Floor passes (Ship's witness-token chain ran upstream); the
    blocking finding is a `baseline_regression_above_threshold`
    `blocks_ship`-severity finding, the canonical example.

    Kept alongside `dont_ship_with_observation()` (single-finding vs
    findings-plus-observation): tests that exercise verdict-state
    mapping or pass-through don't care about findings shape — the
    plain fixture keeps those tests readable. Only tests that pin
    the `findings != blocking_findings` contract need the richer
    variant.
    """
    blocking = make_decision_finding(
        "baseline_regression_above_threshold",
        message="baseline cohort regressed",
        details={"observed": "0.150", "threshold": "0.100"},
    )
    return DontShip(
        cohort_results=[cohort("failure"), cohort("baseline")],
        findings=[blocking],
        blocking_findings=[blocking],
    )


def dont_ship_with_observation() -> DontShip:
    """`DontShip` whose `findings` contains BOTH a non-blocking
    observation AND a blocking finding, so `findings != blocking_findings`.

    Used to make the projection-flatten contract ("wire =
    findings, NOT blocking_findings subset") load-bearing rather
    than vacuously true on a single-finding fixture. The
    `improvement_observed` finding is `info`-severity (does NOT
    appear in `blocking_findings`); the regression finding is
    `blocks_ship` (does).
    """
    observation = make_decision_finding(
        "improvement_observed",
        message="failure cohort showed improvement",
        details={"median_delta": "0.200", "threshold": "0.050"},
    )
    blocking = make_decision_finding(
        "baseline_regression_above_threshold",
        message="baseline cohort regressed",
        details={"observed": "0.150", "threshold": "0.100"},
    )
    return DontShip(
        cohort_results=[cohort("failure"), cohort("baseline")],
        findings=[observation, blocking],
        blocking_findings=[blocking],
    )


def inconclusive() -> Inconclusive:
    """Construct an `Inconclusive` with a representative blocking finding.

    `ci_unavailable_for_required_cohort` is the canonical
    `blocks_all`-severity case; its registry spec requires non-empty
    `derived_from_failures`, so the fixture supplies a placeholder
    failure-record id that matches the pattern used by
    `ci_availability_guard` (the deferred Phase 2.6c plumbing replaces
    the placeholder with real ids).
    """
    blocking = make_decision_finding(
        "ci_unavailable_for_required_cohort",
        message="CI uncomputable on baseline",
        details={"cohort": "baseline", "reason": "sample_too_small"},
        derived_from_failures=["fail-ci-unavailable-1"],
    )
    return Inconclusive(
        cohort_results=[cohort("failure")],
        findings=[blocking],
        blocking_findings=[blocking],
    )
