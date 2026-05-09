# Getting started

A worked, end-to-end example that runs the whatifd pipeline and produces a `Ship` / `Don't Ship` / `Inconclusive` verdict report. Read top-to-bottom.

> **What works today (v0.1):** the programmatic API (`whatifd.pipeline.run_pipeline`) drives the full pipeline end-to-end with both real adapters (`whatifd-langfuse`, `whatifd-inspect-ai`) in the path. The `whatifd fork` CLI command is wired through config + the cardinal-#7 two-affirmation gate but its dispatcher body is a documented stub for v0.1.0; see [`phases.md`](../.claude/skills/whatifd-design/references/phases.md) "Implementation gaps." The integration-test suite (`tests/integration/test_real_adapters.py`) is the load-bearing reference for the pattern below.

## Install

```bash
# Once published to PyPI:
uv pip install whatifd whatifd-langfuse whatifd-inspect-ai

# From source (uv workspace):
git clone https://github.com/victoralfred/whatifd
cd whatifd
uv sync --all-extras --dev --group workspace
```

## The shape

A whatifd run has six inputs:

1. **A `TraceSource`** — your tracer's adapter. v0.1 ships `whatifd-langfuse`. The synthetic `whatifd.adapters.stub.StubTraceSource` is in-tree for tests and out-of-tree adapter authors.
2. **A `delta_fn(RawTrace) -> float`** — the per-trace effect size. In v0.1 you build this from a `Scorer` (see [Wiring a real scorer](#wiring-a-real-scorer) below).
3. **A `TrustFloor`** — the cardinal-#2 floor. Defaults are reasonable for v0.1.
4. **A `DecisionPolicy`** — the above-floor policy thresholds.
5. **A `RunManifest`** — runtime metadata (timestamps, env fingerprint, whatifd version).
6. **A `MethodologyDisclosure` + `CacheSummary`** — required-presence fields per cardinal #10.

You hand all six to `run_pipeline`; you get a `ReportV01` back with `verdict_state ∈ {"ship", "dont_ship", "inconclusive"}`.

## Minimal example (programmatic, works today)

This script runs the pipeline end-to-end against the in-tree synthetic stub adapter, with a deterministic `delta_fn`. It produces a Ship verdict on this fixture and writes the JSON report.

```python
from collections.abc import Callable
from types import MappingProxyType

from whatifd.adapters.protocols import RawTrace
from whatifd.adapters.stub import StubTraceSource, StubTraceSpec
from whatifd.cache.summary import CachePolicySnapshot, CacheSummary
from whatifd.pipeline import run_pipeline
from whatifd.serialization import encode_report_v01
from whatifd.types.manifest import EnvironmentFingerprint, RunManifest
from whatifd.types.policy import DecisionPolicy, TrustFloor
from whatifd.types.statistical import (
    BootstrapMethodDisclosure,
    EffectSizeDisclosure,
    JudgeMethodDisclosure,
    MethodologyDisclosure,
    MultiplicityDisclosure,
)


def build_source() -> StubTraceSource:
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
    return StubTraceSource(specs=[*failures, *baselines])


def delta_fn(rt: RawTrace) -> float:
    """Per-trace effect size. In a real run this would invoke your
    Runner + Scorer; here it's deterministic so the example is
    reproducible without an LLM provider."""
    if rt.cohort == "failure":
        idx = int(rt.trace_id.split("-")[1])
        return 0.20 if idx < 14 else 0.0
    return 0.01


floor = TrustFloor()
policy = DecisionPolicy()
runtime = RunManifest(
    experiment_id="getting-started",
    started_at="2026-05-08T00:00:00Z",
    finished_at="2026-05-08T00:00:01Z",
    duration_ms=1000,
    whatif_version="0.1.0",
    config_hash="0" * 64,
    selection_seed=42,
    source="stub",
    target="stub",
    trust_floor=floor,
    decision_policy=policy,
    environment=EnvironmentFingerprint(
        python="3.13.0", platform="linux", whatif_version="0.1.0"
    ),
)
methodology = MethodologyDisclosure(
    unit_of_analysis="paired_trace_delta",
    primary_metric="faithfulness",
    primary_endpoints=("failure.faithfulness", "baseline.faithfulness"),
    cohorts=("failure", "baseline"),
    bootstrap=BootstrapMethodDisclosure(
        method="unavailable",
        resamples=None,
        seed=None,
        sample_unit="paired_trace_delta",
        ci_level="0.950",
        cluster_key=None,
        assumptions=(),
        unavailable_reason="empirical-percentile shortcut; v0.2 stats layer",
    ),
    multiplicity=MultiplicityDisclosure(
        primary_endpoint_count=2,
        correction="none",
        reason="single primary metric per cohort",
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
cache_summary = CacheSummary(
    schema_version="v1",
    key_version="v1",
    mode="off",
    storage_profile="normalized_result_only",
    storage_path=".whatifd/cache",
    hits=0, misses=0, writes=0, stale_hits=0, corrupted_entries=0,
    policy=CachePolicySnapshot(
        mode="off", warn_after_days=30, block_after_days=90,
        storage_profile="normalized_result_only",
    ),
    policy_violations=(),
    oldest_hit_age_days=None,
    models_distribution=MappingProxyType({}),
)

report = run_pipeline(
    build_source(),
    delta_fn=delta_fn,
    floor=floor,
    policy=policy,
    runtime=runtime,
    methodology=methodology,
    cache_summary=cache_summary,
)
print(f"verdict: {report.verdict_state}")
# → verdict: ship

with open("report.json", "wb") as fh:
    fh.write(encode_report_v01(report))
```

## Wiring a real scorer

Replace the deterministic `delta_fn` above with a closure over a real `Scorer`. Pattern from `tests/integration/test_real_adapters.py`:

```python
from whatifd.contract import ReplayOutput, ScoreCase, TraceInput, TraceOutput
from whatifd_inspect_ai import InspectAIScorer

scorer = InspectAIScorer(
    score_fn=my_inspect_scorer,           # see whatifd-inspect-ai README
    judge_provider="anthropic",
    judge_model_id="claude-opus-4-7",
    rubric_id="faithfulness-v1",
    rubric_text="Score 0-1 by faithfulness to the original output...",
)


def delta_fn(rt: RawTrace) -> float:
    case = ScoreCase(
        trace_id=rt.trace_id,
        cohort=rt.cohort,
        input=TraceInput(
            user_message=rt.user_message.unwrap(reason="feed scorer")
        ),
        original_output=TraceOutput(
            text=rt.original_response.unwrap(reason="feed scorer")
        ),
        replayed_output=ReplayOutput(text=run_my_replay(rt)),
    )
    result = scorer.score(case)
    if result.score is None:
        # Cardinal #1: structural failure surfaces as a typed
        # FailureRecord in the report instead of crashing the run.
        raise RuntimeError("scorer returned None; see JudgeResult.rationale")
    return result.score
```

The same pattern works with `whatifd_langfuse.LangfuseTraceSource` instead of the stub: hand it a Langfuse `api` client (see [whatifd-langfuse README](../packages/whatifd-langfuse/README.md)).

## Reading the verdict

`report.verdict_state` is a closed string literal:

| Verdict | Exit code | Meaning |
|---|---|---|
| `"ship"` | 0 | Floor passed; no above-floor `blocks_ship` finding. |
| `"dont_ship"` | 1 | Floor passed; at least one above-floor guard blocks. |
| `"inconclusive"` | 2 | Floor failed (cardinal #2 — overrides policy) OR setup failure. |

Render the full report:

```python
from whatifd.render.markdown import render_full_report
print(render_full_report(report))
```

The five-section structure (header → cohort table → findings → cache + methodology → run manifest) is what the six committed walkthroughs in `docs/walkthroughs/` show.

## What's next

- **[Runner contract](./runner-contract.md)** — the protocol your replay code implements
- **[Concepts](./concepts.md)** — the doctrine: defensible verdicts, non-claims, trust floor vs decision policy
- **[Walkthroughs](./walkthroughs/)** — six rendered examples (Ship, Don't Ship, Inconclusive)
- **[`examples/minimal-agent/`](../examples/minimal-agent/)** — copy-paste reference Runner

## Stub adapters: what they do (and don't)

Two CLI-friendly placeholders ship with whatifd core for credentialless smokes:

- **`source.adapter: "stub"`** — `whatifd.adapters.factory.build_trace_source` returns `StubTraceSource(specs=[])`. **Empty by design** — the factory's job is dispatch, not fixture provisioning. Tests/users that need traces construct `StubTraceSource(specs=[...])` directly. A `whatifd fork` smoke run with the empty stub source produces a Floor-failure Inconclusive verdict (cardinal #2: no data → not Ship), not a crash.
- **`scorer.adapter: "stub"`** — `StubScorer()` with the default `score_fn` that returns the constant **`0.5` for every case**, not "no judgment" and not zero. Each trace gets a deterministic 0.5 delta. This is intentional: the stub is for wiring-validation, not behavioral evaluation. **A real run that accidentally uses `scorer.adapter: "stub"` will appear to improve uniformly across every trace** — a misleading Ship verdict pattern. If you see uniform 0.5 deltas in a real run, check your scorer config.

The stub is the right default for an end-to-end CLI smoke that proves the wiring works. It is the wrong default for an experiment whose verdict you want to act on.

## Known limitations (v0.1.0)

- The `whatifd fork` CLI dispatcher is stubbed; use the programmatic API above. End-to-end CLI wiring is the next branch.
- CI bounds are empirical 5th/95th percentiles, not stratified bootstrap. The methodology disclosure declares this with `bootstrap.method="unavailable"` so consumers see the truth.
- Cache `verify` does structural checks but not cryptographic content-hash. Deferred to v0.2.

See [`phases.md` § "Implementation gaps"](../.claude/skills/whatifd-design/references/phases.md) for the full list and closure paths.
