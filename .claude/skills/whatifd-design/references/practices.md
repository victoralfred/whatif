# Engineering Practices

Coding decisions, design patterns, library choices, performance discipline.

The frame is fixed: **whatif is a deterministic CI-grade experiment runner, not a numeric processing engine.** The priority order:

1. Typed boundaries
2. Replay validity
3. Deterministic output
4. Timeout / cancellation
5. Evidence-rich reporting
6. Adapter isolation
7. Bounded concurrency
8. Memory optimization

Performance is a follower, not a driver. A slow-but-trustworthy run is useful. A fast-but-opaque run is worthless.

## Language and runtime

- **Python 3.12+** for the determinism subset; broader compat for the rest
- **Pydantic v2** for config validation (Rust-backed; clear error messages; JSON Schema generation)
- **Standard `dataclasses` with `frozen=True, slots=True`** for internal types — not Pydantic for hot paths
- **`typing.Protocol`** for adapter interfaces (structural typing, no inheritance required)
- **`structlog`** for structured logging
- **`fcntl` + `psutil`** for cache lock management
- **No NumPy in v0.1.** Bootstrap CIs and stats can be plain Python; optimize later if profiling shows a bottleneck

## Project structure

```
whatif/
├── __init__.py             (light: no Langfuse, Inspect, OpenAI, Anthropic imports)
├── types/
│   ├── primitives.py       (DecimalString, JsonPrimitive, etc.)
│   ├── sensitive.py        (Sensitive[T] wrapper)
│   ├── failure.py          (FailureRecord)
│   ├── finding.py          (DecisionFinding)
│   ├── cohort.py           (CohortResult, FloorFailure)
│   ├── verdict.py          (Ship, DontShip, Inconclusive, FloorPassedProof)
│   ├── policy.py           (TrustFloor, DecisionPolicy)
│   └── manifest.py         (RunManifest, EnvironmentFingerprint, SensitiveUnwrap)
├── contract/
│   ├── runner.py           (TraceInput, ReplayConfig, ToolCache, ReplayOutput)
│   ├── score_case.py       (ScoreCase, JudgeResult)
│   └── protocols.py        (TraceSource, Scorer, SyncRunner, AsyncRunner)
├── decision/
│   ├── floor.py            (evaluate_floor, _FLOOR_INTERNAL_TOKEN)
│   ├── policy.py           (compute_verdict, guards)
│   ├── guards/             (one file per guard)
│   ├── finding_codes.py    (FINDING_CODE_REGISTRY)
│   ├── failure_codes.py    (FAILURE_CODE_REGISTRY)
│   ├── fix_suggestions.py  (FIX_SUGGESTION_REGISTRY)
│   └── aggregation.py      (cohort-systemic detection)
├── cache/
│   ├── keying/             (cache key construction; bumps CACHE_KEY_VERSION on change)
│   ├── storage/            (cache file format; bumps CACHE_SCHEMA_VERSION on change)
│   ├── lock.py             (fcntl + stale-window)
│   └── policy.py           (CachePolicy, mode resolution)
├── replay/
│   ├── pipeline.py         (the streaming generator chain)
│   ├── tool_cache.py       (trace-scoped ToolCache)
│   └── result.py           (ReplaySuccess | ReplayFailure)
├── report/
│   ├── models_v01.py       (ReportV01 — public, hand-written)
│   ├── projection.py       (internal types → ReportV01)
│   └── schema/
│       └── v0.1.schema.json (committed, generated from models, byte-stable)
├── serialization/
│   ├── encoder.py          (WhatifJSONEncoder, banned everywhere else)
│   ├── graph_walk.py       (assert_no_unredacted_sensitive)
│   └── decimal.py          (DecimalString format/parse)
├── render/
│   ├── markdown.py         (3 formats: 1-line, 30-line summary, full)
│   ├── ci_status.py        (1-line for GitHub check display)
│   └── templates/          (fix-suggestion templates)
├── internal/                (private; refactor freely)
│   ├── stats.py            (bootstrap CIs, deltas)
│   ├── selection.py        (cohort selection, seeded sampling)
│   └── ...
├── adapters/                (each adapter is a separate package; lazy-loaded)
├── cli.py
└── config.py                (Pydantic schemas)
```

## Import discipline

`import whatifd` must NOT eagerly import:
- Langfuse, Inspect AI, OpenAI, Anthropic SDKs
- NumPy, Pandas
- Any LLM API client

CI test: time `python -c "import whatifd"` and assert under 200ms. Adapters live in separate packages (`whatifd-langfuse`, `whatifd-inspect-ai`) and load lazily when their adapter ID is referenced.

## Concurrency

| Stage | Model |
|---|---|
| Tracer fetch | `asyncio` + bounded connection pool |
| Replay (sync runner) | `ThreadPoolExecutor` with `max_workers=os.cpu_count()` |
| Replay (async runner) | direct `asyncio.gather` with semaphore |
| Scoring | batch first; concurrent fallback via `asyncio.gather` |
| Bootstrap CI | plain Python, single-threaded (small data) |

**No `ProcessPoolExecutor` for replay.** Replay is I/O-bound (LLM API calls, network). Process pool adds pickle pain, breaks non-picklable runners, complicates cache sharing. Thread pool or async, period.

## Memory discipline

**Stream raw traces. Materialize compact scored summaries.**

The pipeline is a generator chain:

```python
def trace_pipeline(source, change, tool_cache_factory):
    for raw in source.stream_traces(policy):
        trace_input = parse_trace(raw)
        cache = tool_cache_factory.from_trace(raw)
        replayed = runner.run(trace_input, change, cache)
        yield build_score_case(trace_input, replayed)
```

Each stage consumes one item, yields one item. Memory is bounded to O(1) trace objects in flight, not O(n).

**Compact summaries** for what survives across stages:

```python
@dataclass(frozen=True, slots=True)
class ScoredCaseSummary:
    trace_id: str
    cohort: str
    original_score: DecimalString
    replayed_score: DecimalString
    delta: DecimalString
    replay_status: ReplayStatus
    evidence_snippet: EvidenceSnippet | None  # may contain Sensitive[str]
```

The full trace and full replayed output are NOT retained after scoring. Only what the report needs.

## Result types over exceptions

Expected failures are values, not exceptions. The replay layer returns:

```python
@dataclass(frozen=True, slots=True)
class ReplaySuccess:
    output: ReplayOutput

@dataclass(frozen=True, slots=True)
class ReplayFailure:
    trace_id: str
    code: str
    message: str
    details: Mapping[str, JsonPrimitive]

ReplayResult = ReplaySuccess | ReplayFailure
```

Exceptions are reserved for bugs in whatif itself (impossible state, contract violation). Adapter failures, runner timeouts, scorer errors — all values.

## Timeouts everywhere

Every external call has explicit timeout. Defaults:

| Call | Timeout | Configurable |
|---|---|---|
| Tracer fetch (per trace) | 10s | yes |
| Tracer fetch (full stream) | 60s | yes |
| Runner execution | 30s | yes |
| Scorer batch | 60s | yes |
| Scorer single (fallback) | 15s | yes |
| Report write | 5s | no |

Timeouts produce typed failures (`runner_timeout`, `scorer_timeout`), not exceptions. Configurable via `whatif.config.yaml`:

```yaml
timeouts:
  runner_seconds: 30
  scorer_batch_seconds: 60
```

## Observability

`structlog` from v0.1. `print()` is forbidden outside the CLI top-level.

```python
logger.info(
    "stage.complete",
    stage="replay",
    experiment_id=ctx.experiment_id,
    replayed=17,
    skipped=3,
    duration_ms=4823,
)
```

OpenTelemetry spans are deferred to v0.2. The stage boundary structure exists in v0.1 logs so spans can be wrapped later without restructuring.

## Configuration

Pydantic v2 strict mode. Clear error messages over decode speed.

```python
from pydantic import BaseModel, Field, ConfigDict

class WhatifConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    source: SourceConfig
    target: TargetConfig
    selection: SelectionConfig
    change: ChangeConfig
    scorer: ScorerConfig
    decision: DecisionConfig = Field(default_factory=DecisionConfig)
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)
    timeouts: TimeoutsConfig = Field(default_factory=TimeoutsConfig)
```

Validation errors must be human-readable:

```
Invalid config (whatif.config.yaml line 14):
  selection.baseline_cohort.limit must be at least 1, got 0

  Hint: baseline cohort is required for Ship verdicts (decision.require_baseline=true).
        Either disable baseline by setting decision.require_baseline=false (will limit
        verdict to Inconclusive), or increase baseline_cohort.limit.
```

Every Pydantic validator has a hint when the failure is actionable.

## Testing strategy

Per `references/phases.md` test gates, the test suite includes:

- **Unit tests** — type construction, validation, projection functions
- **Property tests** (Hypothesis) — determinism, no-Ship-when-floor-fails, no-unhandled-exceptions
- **Golden report tests** — committed JSON reports validate against committed schema
- **Schema diff tests** — generated schema from `ReportV01` matches committed schema byte-for-byte
- **Redaction snapshot tests** — known sensitive inputs produce known redacted outputs across all profiles
- **Lock contention tests** — two simulated processes, second fails with `CacheLockedError`
- **Determinism tests** — same input + same seed → byte-identical deterministic subset
- **Fix suggestion coverage tests** — every blocking code has a registered fix
- **Integration fixtures** — recorded synthetic Langfuse traces against stub adapter
- **Walkthrough scenario tests** — rendered Markdown output for six scenarios matches committed expected output

## Coding patterns

### Discriminated unions in domain types

```python
ReplayResult = ReplaySuccess | ReplayFailure
FloorEvaluation = FloorPassedProof | FloorFailure
Verdict = Ship | DontShip | Inconclusive
```

Pattern matching with `match` statements. mypy strict catches missing cases.

### Dependency injection at the Experiment boundary

```python
experiment = Experiment(
    source=LangfuseAdapter(client),
    runner=user_runner,
    scorer=InspectAIScorer(model="claude-sonnet-4"),
    cache=ScorerCache.from_dir(".whatif/cache/scorer"),
    floor=TrustFloor(version="v1"),
    policy=DecisionPolicy.from_config(config.decision),
    clock=SystemClock(),  # injectable for tests
)
```

The `Experiment` does not construct collaborators internally. Testing is trivial: swap any collaborator for a fake.

### Guard chain for decision policy

```python
GUARDS: list[Guard] = [
    structural_floor_guard,
    replay_validity_guard,
    baseline_coverage_guard,
    regression_threshold_guard,
    improvement_threshold_guard,
    ci_availability_guard,
]

def compute_verdict(result: ExperimentResult, policy: DecisionPolicy) -> Verdict:
    findings: list[DecisionFinding] = []
    for guard in GUARDS:
        findings.extend(guard(result, policy))

    floor_eval = evaluate_floor(result, policy)
    if isinstance(floor_eval, FloorFailure):
        return Inconclusive(
            cohort_results=result.cohort_results,
            findings=findings,
            blocking_findings=[f for f in findings if f.severity in ("blocks_ship", "blocks_all")],
            floor_failures=floor_eval.failures,
        )

    if any(f.severity == "blocks_all" for f in findings):
        return Inconclusive(
            cohort_results=result.cohort_results,
            findings=findings,
            blocking_findings=[f for f in findings if f.severity in ("blocks_ship", "blocks_all")],
            floor_failures=[],
        )

    if any(f.severity == "blocks_ship" for f in findings):
        return DontShip(
            cohort_results=result.cohort_results,
            findings=findings,
            blocking_findings=[f for f in findings if f.severity == "blocks_ship"],
        )

    return Ship(
        proof=floor_eval,  # FloorPassedProof from evaluate_floor()
        cohort_results=result.cohort_results,
        findings=findings,
    )
```

Guards return findings, not verdicts. Aggregation produces verdict. All findings are reported, not just the first one.

### Pydantic at boundaries; dataclasses internally

Pydantic for: config validation, JSON Schema generation for `ReportV01`. Dataclasses for: hot-path internal types. Don't pay Pydantic overhead on every `FailureRecord`.

### Typed boundaries — `dict[str, Any]` is forbidden across function boundaries

```python
# WRONG
def process(raw: dict[str, Any]) -> dict[str, Any]: ...

# RIGHT
def process(raw: RawTrace) -> TraceInput: ...
```

`dict[str, Any]` only crosses adapter→core boundary, where it's immediately validated to a typed object. Internal functions never accept it.

### Frozen dataclasses with __slots__ for hot types

```python
@dataclass(frozen=True, slots=True)
class FailureRecord:
    id: str
    code: str
    ...
```

`frozen=True` means immutability and hashability. `slots=True` means ~50% less memory per instance. For types instantiated thousands of times, both matter.

### Banned patterns

- `print()` outside `whatif/cli.py`
- `json.dumps()` outside `whatif/serialization/`
- `dict[str, Any]` as a function argument or return type, except at the adapter boundary
- Bare `except:` clauses
- Catching `Exception` in a way that swallows it (must produce a `FailureRecord`)
- `time.time()` directly (use injected clock)
- `random` directly (use seeded RNG from selection)
- Module-level mutable globals (constants are fine)

CI lint enforces all of these.

## Performance budgets

| Operation | Budget |
|---|---|
| `import whatifd` | < 200ms |
| Cold start (CLI invocation, no work) | < 500ms |
| Per-trace replay overhead (excluding runner) | < 50ms |
| Per-trace scoring overhead (excluding judge) | < 30ms |
| Report rendering (Markdown + JSON) | < 1s for 100-trace experiment |
| Determinism test (two runs, diff) | < 30s on 20-trace experiment |

Budgets are soft for v0.1. Profile at the end of Phase 7 (renderer) and address violations.

## Statistical methodology

> **whatif's verdict is only as defensible as its sampling, scoring, and uncertainty model.**

v0.1 uses a deliberately modest statistical model. It does not attempt to prove behavioral equivalence, certify safety, or make causal claims about production behavior. It estimates paired changes in scored behavior over selected production trace cohorts under a declared replay policy. The mathematical posture: **endpoint discipline first, statistical machinery second.**

### Unit of analysis: paired trace delta

The atomic statistical unit is the paired trace delta:

```
delta_i = replayed_score_i - original_score_i
```

The same trace input is evaluated under two configurations: original production behavior, and replayed behavior under the proposed change. Because the comparison is paired, whatif must not treat original and replayed scores as independent samples.

All cohort-level statistics are computed over paired deltas. Internal Python representation uses `float` for delta arithmetic and bootstrap computation. Public JSON output uses `DecimalString` for cross-platform determinism (see "Float platform-stability" notes earlier in this file).

The internal `TraceDelta` type stores both raw scores and the computed delta — this preserves auditability — but the analysis API consumes deltas, not separate score arrays. Storing both without exposing both prevents accidental unpaired analysis.

### Primary endpoints

Every run must declare primary endpoints before evaluation.

v0.1 default endpoints:

- failure cohort: improvement on the primary quality metric
- baseline cohort: non-regression on the primary quality metric

Per-trace examples are descriptive evidence. They are not treated as independent statistical hypothesis tests. Forty trace deltas going into one cohort-level aggregate is one statistical claim, not forty.

Multiple-comparison correction is required only when the run declares multiple primary endpoints, multiple primary metrics, or promotes subgroup analysis to inferential status. The default for v0.1 (one primary metric per cohort, descriptive evidence) requires no multiplicity correction.

### Bootstrap confidence intervals

v0.1 default uncertainty method:

- paired non-parametric bootstrap
- sample unit: trace-level delta
- interval: percentile interval
- deterministic seed
- default resamples: B = 5000

The report must disclose: bootstrap method, resample count, seed, sample unit, whether cluster bootstrap was used, and the cluster key if any. A confidence interval without method, sample unit, and assumptions is not defensible — it is decoration.

If the cohort does not meet the trust floor for selected, replayed, and scored traces, whatif must not produce an actionable Ship verdict. Below the floor, the report still emits with `Inconclusive` but the bootstrap method may be `unavailable`.

### Cluster bootstrap (conditional)

If traces are correlated, ordinary i.i.d. bootstrap intervals may be too optimistic. When a tracer adapter can provide a real cluster key (such as `user_id`, `session_id`, `conversation_id`), whatif may use cluster bootstrap by resampling clusters rather than individual traces.

If no cluster key is available, the report must disclose the i.i.d. assumption explicitly:

```
Cluster handling: none. CIs assume trace-level independence and may be optimistic if traces are correlated.
```

whatif must not manufacture cluster structure using unstable heuristics (e.g., k-means on embeddings) for v0.1 verdicts. Faking cluster structure is worse than ignoring the issue.

### Effect size and practical significance

Statistical significance is not enough. whatif reports magnitude.

v0.1 should report, per cohort:

- median paired delta
- trimmed mean paired delta
- probability of practical improvement: `P(delta > epsilon)`
- probability of practical regression: `P(delta < -epsilon)`
- paired standardized effect size `d_z = mean(delta) / sd(delta)`, when `sd(delta) > 0`

Use paired effect measures, not generic two-sample measures (Cohen's d for independent samples or Cliff's delta on raw score arrays both discard pairing).

The practical-delta threshold `epsilon` is policy-controlled and must be shown in the report. If judge noise-floor data is available (from a calibration subset), the report should warn when:

```
epsilon < measured_judge_noise_floor
```

If no judge noise-floor data is available, the report must not imply that `epsilon` has been empirically calibrated.

### Per-trace evidence is descriptive

Per-trace evidence examples support review, but they do not carry inferential claims in v0.1.

Allowed:

```
Trace abc123 regressed by -0.42 on faithfulness.
```

Not allowed without inferential testing with multiplicity correction:

```
Trace abc123 significantly regressed.
```

The methodology block must include the disclaimer:

> No per-trace statistical significance is claimed. Evidence examples are descriptive.

This single sentence prevents a class of misuse.

### Reproducibility, reliability, validity, calibration, bias

These are five separate concepts. Conflating them produces overclaim.

| Concept | Meaning | v0.1 stance |
|---|---|---|
| Reproducibility | Same inputs produce same report | Addressed: scorer cache, deterministic seed, sorted JSON |
| Reliability | Repeated judge calls agree | Not measured by default; disclosed as unmeasured |
| Validity | Judge agrees with task truth or human labels | Not measured by default; disclosed as unmeasured |
| Calibration | Judge confidence matches empirical correctness | Not measured by default; disclosed as unmeasured |
| Bias | Judge changes under irrelevant presentation factors | Not measured by default; disclosed as unmeasured |

Scorer caching freezes a judge sample. It does not estimate judge reliability, validity, calibration, or bias. v0.1's stance is **addressed via disclosure, not via measurement** — the methodology block must explicitly mark these properties as unmeasured if no measurement was configured.

Adding actual measurement is a v0.2 (reliability via repeat judging, position-bias mitigation) and v0.3 (validity and calibration via human-labeled sets) concern.

### Causal language

whatif estimates the effect of a configuration change under cached-tool replay against past traces. This is **not the same as the change's effect in production.**

Cached-tool replay is biased in known ways:

- It may miss regressions that depend on the changed agent making different tool calls (the tool cache pins the original agent's tool sequence).
- It may miss regressions caused by future input-distribution drift.
- It isolates prompt/model behavior better than live replay, but at the cost of realism.

Preferred language:

> associated regression under cached-tool replay

Rejected language:

> caused production regression

The bias direction is consistent: replay-conservative on tool-mediated regressions, replay-optimistic on input-distribution drift. Naming the direction is more honest than waving at "limitations."

### Methodology disclosure (required in every report)

Every report must include a methodology block. Schema validation enforces presence; required-field validation enforces content. Example:

```
Methodology
- Unit of analysis: paired trace delta
- Primary metric: faithfulness
- Cohorts: failure, baseline
- Primary endpoints: failure improvement, baseline non-regression
- Bootstrap: paired percentile, B=5000, seed=42
- Cluster handling: conversation_id cluster bootstrap
- Multiplicity: none; one primary metric per cohort
- Evidence examples: descriptive, not inferential
- Judge: claude-haiku-4-5
- Scorer cache: enabled
- Practical delta threshold: 0.05
- Reliability: not measured
- Validity / calibration: not measured
- Bias audit: not measured
- Causal scope: associated under cached-tool replay
```

If the methodology does not support a claim, the report must not make it.

## What this workload is NOT (and what advice doesn't apply)

This section exists because well-meaning generic "high-performance Python" advice will appear in design discussions, and most of it is **wrong for whatif** even when it's correct for its actual domain. Apply the wrong advice and the trust-first guarantees collapse. Worth being explicit.

### whatif is orchestration, not compute

The total CPU work in a 100-trace whatif run, excluding what the user's runner does, is under 2 seconds. Wall-clock time is 30–60 seconds, dominated by external API latency:

| Stage | What dominates | CPU-bound? |
|---|---|---|
| Trace ingestion | Network I/O to tracer API | No |
| Replay | Network I/O to LLM API (user's agent) | No |
| Tool cache lookup | Disk I/O + dict lookup | No |
| Scoring | Network I/O to judge LLM API | No |
| Bootstrap CIs | ~40 floats × 1000 resamples | Negligible |
| Report rendering | String formatting | Negligible |
| JSON serialization | String building | Negligible |

**Pegging the CPU is not a goal. It would be a sign that something has gone wrong.** If a profile shows whatif using >50% CPU on a single core during a normal run, the design has drifted — most likely a synchronous loop crept in where async I/O belonged, or someone added a numerical computation that doesn't belong in this layer.

### Recommendations for CPU-bound AI compute do not apply

The following stack is **industry standard for AI compute workloads** (custom inference servers, simulation engines, numerical solvers, tensor pipelines). It is **the wrong tool for whatif** in nearly every component:

| Tool / pattern | Right for | Wrong for whatif because |
|---|---|---|
| Ray / Dask | Distributed cluster compute | 200MB+ dependency; blows `import whatifd` < 200ms budget; forces user runner to be Ray-actor-compatible, breaking the simple `def run(...)` contract |
| `ProcessPoolExecutor` for replay | CPU-bound parallel work | Replay is I/O-bound (LLM API calls); pickle pain breaks non-picklable runners; complicates `ToolCache` sharing; structural guarantees harder to enforce across process boundaries |
| NumPy throughout | Numerical / tensor workloads | Pulls 50MB to save sub-millisecond on bootstrap CIs; introduces float platform-instability that conflicts with `DecimalString` determinism guarantee |
| `multiprocessing.shared_memory` | Large array IPC | `Sensitive[T]` cannot survive shared-memory roundtrip; `FloorPassedProof` cannot live in shared memory; breaks redaction enforcement |
| MKL / oneDNN / AOCL | BLAS-heavy code | whatif makes zero BLAS calls; would be empty dependencies inflating install size |
| SIMD / AVX-512 vectorization | Loop-heavy numerics | No numerical loops to vectorize |
| BF16 / INT8 precision reduction | Tensor inference throughput | Different rounding behavior across precisions; conflicts with byte-identical JSON determinism requirement |
| Numba `@njit(fastmath=True)` | Custom numerical kernels | No numerical kernels; `@njit` doesn't compose with `frozen=True` dataclasses; conflicts with mypy strict |
| ONNX Runtime / OpenVINO | Running AI models | whatif does not run AI models; the user's *agent* might, but that's outside whatif's scope |
| SoA vs AoS layout | Cache-friendly tensor processing | At most a few thousand structured records per run; total typed-record memory under 1MB; cache locality not the bottleneck |

The pattern: every one of these tools is correct for its actual domain (tensor compute, numerical processing, distributed batch jobs). None of them are correct for **orchestration of I/O-bound workflows**, which is what whatif does.

### How to tell which workload class you're in

Before reaching for any performance tool, identify the actual bottleneck:

1. **Profile, don't guess.** `python -X importtime`, `cProfile`, `py-spy`. Numbers, not intuition.
2. **Classify the bottleneck.** Is it CPU (compute-limited), I/O (network/disk-limited), memory (allocation-limited), or coordination (lock-contention-limited)?
3. **Pick a tool from the matching category.**

For whatif's actual bottlenecks (in order):

| Bottleneck | Right tool |
|---|---|
| LLM API latency (judge calls) | Scorer cache, batch scoring, async concurrency |
| Tracer API latency | Async streaming with bounded connection pool |
| Disk I/O (cache reads) | Sharded cache layout (already specified), small entries |
| JSON serialization on large reports | `orjson` if profiling shows it matters (releases GIL, 5–10× faster than stdlib) |
| Memory growth on large runs | Streaming generator pipeline (already specified), compact `ScoredCaseSummary` retention |

CPU compute is not on the list. It will not be on the list. If a contributor proposes a CPU-optimization change, the question to ask is: *what profile data shows CPU as the bottleneck?* Without that data, the change is solving the wrong problem.

### What to adopt, narrowly scoped

Two things from the broader high-performance ecosystem are worth adopting if profiling justifies them. Both are v0.2 optimizations, not v0.1 requirements.

**1. Vectorized bootstrap with NumPy (deferred to v0.2 if needed).** If profiling shows bootstrap CI computation as a non-trivial fraction of runtime, `numpy.random.choice` with vectorized resampling beats the Python loop by ~50–100×. The schema is unchanged (`DecimalString` output is identical); the dependency cost is real (50MB) and only justified if the absolute time saved is meaningful. Cascade catalog tracks this.

**2. `orjson` for serialization (deferred to v0.2 if needed).** Releases the GIL during serialization. The custom `WhatifJSONEncoder` can be reimplemented over `orjson` without changing semantics — sorted keys, custom default(), Sensitive-rejection all preserved. Adopt only if JSON serialization shows up in profile.

Everything else — Ray, MKL, Numba, ONNX Runtime, shared memory, precision reduction — is either inapplicable to this domain or actively harmful to the trust-first guarantees. The skill encodes this so the next time the question comes up, contributors don't have to re-derive the answer.

### The principle

> **Performance optimization is domain-specific. The right answer for tensor compute is the wrong answer for orchestration. The right answer for orchestration is the wrong answer for streaming. Identify the workload's actual bottleneck before reaching for tools.**

For whatif: the bottleneck is external API latency. The optimizations that matter are caching, batching, and async concurrency. Everything else is solving the wrong problem.

## Style

- Type hints are required on all public functions and method signatures.
- Docstrings on all public types and functions; brief on internal.
- Line length 100. Use `ruff format`.
- Imports sorted by `ruff`. Adapter packages always lazy-imported.
- No `from x import *`.
- `TODO` comments must reference a cascade catalog item or a GitHub issue.

## What good looks like (summary)

- Every external boundary has a typed adapter.
- Every expected failure is a value.
- Every "structural" claim has an enforcement mechanism (see `references/enforcement.md`).
- Every blocking finding has a registered fix suggestion.
- Every change to cache identity bumps the cache key version.
- Every PR runs the full property test suite.
- Every release ships with golden reports that validate against the committed schema.
