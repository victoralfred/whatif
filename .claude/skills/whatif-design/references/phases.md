# Phased Implementation Plan

Bottom-up. Every phase has a test gate that proves the phase works before the next phase starts. No phase can begin until its predecessors' gates are green.

## Phase ordering rationale

The build order is shaped by the closing principle: **walkthroughs come before code, schema freeze comes before implementation depth, the conceptual model document distills from the walkthroughs.**

```
Phase 0:  Walkthroughs and conceptual model     (paper artifacts; pressure-test the design)
Phase 1:  Type model                            (the foundation; everything imports from here)
Phase 2:  Decision pipeline                     (floor + policy; the trust core)
Phase 3:  Cache subsystem                       (scorer cache with lock + disclosure)
Phase 4:  Adapters                              (Langfuse trace source; Inspect AI scorer)
Phase 5:  Serialization and schema              (ReportV01, JSON Schema, redaction)
Phase 6:  Replay pipeline                       (the streaming generator; runner contract)
Phase 7:  Rendering                             (Markdown 3-format system)
Phase 8:  CLI and config                        (Pydantic config, exit codes, environment)
Phase 9:  Integration and end-to-end            (real fixtures, full pipeline)
Phase 10: Release packaging                     (docs, examples, PyPI publication)
```

## Phase 0: Walkthroughs and conceptual model (paper artifacts)

**Goal:** Pressure-test the design by writing the actual rendered output for six scenarios. The walkthroughs are the empirical reviewer.

### 0.1 — Walkthrough scenarios (six rendered Markdown reports)

Write each as the actual `.md` file the engineer would see, plus an outline of the underlying JSON.

1. **Clean Ship** — failures cohort improved 14/20, baseline stable. Compact form.
2. **Don't Ship (regression)** — baseline regressed 6/20 with median Δ -0.18.
3. **Don't Ship (failure rescue gap)** — failure cohort showed no improvement; baseline stable.
4. **Inconclusive (insufficient sample)** — baseline cohort had 3 scored traces, floor requires 5.
5. **Inconclusive (cache corruption)** — `.whatif/cache/scorer/.lock` corrupted; recovery path tested.
6. **Rerun-after-fix (diff mode)** — comparing report A (before fix) to report B (after fix). Surfaces whether diff mode is in v0.1 scope.

**Expected gaps surfaced:**
- Compact-Ship form: does 30 lines including manifest reference still feel like skimming bait?
- Scenario 4 fix suggestion: does the registered template give an engineer something they can act on in 5 minutes?
- Scenario 5: does `whatif cache rebuild` exist? If not, that's a v0.1 scope addition.
- Scenario 6: does whatif have a diff mode? If not, that's a legitimate finding for the cascade catalog.

### 0.2 — Conceptual model document

Two pages plus glossary appendix. Located at `docs/concepts.md`. Distilled from the walkthroughs and the doctrine.

Structure:

1. **Product: defensible verdicts.** One paragraph anchored on "whatif's product is the verdict's defensibility."
2. **Non-claims.** Not safety certification, not proof of no regression, not benchmark, not load test.
3. **Verdict states.** Ship, Don't Ship, Inconclusive. The structural floor and what produces each.
4. **Trust floor and decision policy.** Evidence existence (floor) vs evidence quality (policy).
5. **Failure-as-data.** Operational facts (FailureRecord) vs policy conclusions (DecisionFinding).
6. **Evidence and audit bundle.** What the report contains; what the artifact bundle contains.
7. **Privacy and redaction.** Sensitive[T] discipline; profile levels.
8. **Examples of misleading outputs whatif must never produce.** Verdict Ship with 20% replay validity. Missing baseline hidden in footnote. Scorer cache disabled in CI without disclosure. Raw production traces included by default.

Glossary appendix: verdict, trust, baseline, cohort, condition, failure, finding, floor, policy, manifest, audit, defensible, actionable.

### 0.3 — Audience-distribution decision

A clarifying question for the project owner before scope is locked:

> Of the engineers you've spoken to who are interested in whatif, what fraction have a clear "failed traces I want to rescue without regressing baseline" workflow versus other shapes (A/B prompt comparison, latency optimization, evaluation-suite bootstrapping, model swap evaluation)?

Answer drives v0.1 scope:
- "Mostly failure-rescue" → ship as scoped.
- "Roughly even" → consider expanding to include `regression_check` (baseline-only, no failure cohort required); doubles addressable use cases at low design cost.
- "Don't have a sense" → ship failure-rescue only; put `regression_check` on v0.2 ROADMAP at high priority; revisit after first 5 production users.

### 0.4 — Enforcement audit

Read `references/enforcement.md`. For each "structural" claim across the codebase plan, confirm:
1. The claim appears in the table with a mechanism.
2. The mechanism is implementable with v0.1 tooling.
3. The test that proves the mechanism is in the phase plan below.

Gaps from the audit feed the cascade catalog.

### Phase 0 gate

✅ Six walkthrough Markdown files committed.
✅ Conceptual model document approved.
✅ Audience-distribution answer received from project owner.
✅ Enforcement audit complete; cascade catalog updated.
✅ Project owner confirms v0.1 scope (failure-rescue only, or expanded to regression-check).

**Cannot proceed to Phase 1 until all five gate items are green.**

## Phase 1: Type model

**Goal:** The foundation. All other phases import from here. Get the types right; everything else gets easier.

### 1.1 — Primitive types

`whatif/types/primitives.py`:
- `DecimalString` (NewType over str; format/parse helpers in `whatif/serialization/decimal.py`)
- `JsonPrimitive = str | int | float | bool | None`

### 1.2 — Sensitive[T] wrapper

`whatif/types/sensitive.py`:
- `Sensitive` generic wrapper with `__repr__`, `__str__`, `__format__`, `__reduce__` overrides
- `unwrap(reason: str)` method with audit log
- `_audit_log` module-private structlog logger
- `SensitiveSerializationError`, `UnredactedSensitiveError` exception types

### 1.3 — Operational types

`whatif/types/failure.py`:
- `FailureRecord` (frozen, slots, no `verdict_impact`)

`whatif/types/finding.py`:
- `DecisionFinding` (frozen, slots, severity enum)
- Severity vocabulary: `info | degrades_trust | blocks_ship | blocks_all`

`whatif/types/cohort.py`:
- `FloorFailure` (frozen, slots)
- `CohortResult` (frozen, slots)

### 1.4 — Verdict types and witness token

`whatif/types/verdict.py`:
- `FloorPassedProof` with `_FLOOR_INTERNAL_TOKEN` (module-private object)
- `Ship`, `DontShip`, `Inconclusive` dataclasses
- `Verdict` union type alias

### 1.5 — Policy types

`whatif/types/policy.py`:
- `TrustFloor` (frozen, slots, versioned)
- `DecisionPolicy` (frozen, slots)

### 1.6 — Manifest types

`whatif/types/manifest.py`:
- `EnvironmentFingerprint`
- `SensitiveUnwrap`
- `RunManifest`

### 1.7 — Statistical types (cardinal #10)

`whatif/types/statistical.py`:
- `TraceDelta` (internal; float arithmetic, paired)
- `TraceDeltaReportV01` (public; DecimalString numeric fields)
- `BootstrapMethodDisclosure`, `MultiplicityDisclosure`, `JudgeMethodDisclosure`, `EffectSizeDisclosure`
- `MethodologyDisclosure` (composite, required field on `ReportV01`)
- `ClusterKeySupport`, `ClusterSelection`, `ClusteringPolicy`

### Phase 1 tests

- **Unit tests:** Each type constructs correctly, frozen prevents mutation, slots prevents arbitrary attributes, equality is structural.
- **Sensitive tests:** `repr(Sensitive("password", "credential"))` returns redacted form. `f"{sensitive}"` returns redacted form. `pickle.dumps(sensitive)` raises `SensitiveSerializationError`. `unwrap()` returns value AND emits audit log entry.
- **Witness token tests:** `Ship(proof=...)` requires a `FloorPassedProof`. Direct construction `FloorPassedProof()` raises `TypeError` outside the floor module. `evaluate_floor()` is the only producer (verified by import-graph test).
- **Property test (Hypothesis):** Generate arbitrary `DecisionPolicy` configurations; confirm none can construct `Ship` without a `FloorPassedProof`.

### Phase 1 gate

✅ All unit tests green.
✅ Property test passes 1000 iterations.
✅ `python -c "import whatif.types"` under 50ms.
✅ mypy strict passes on `whatif/types/`.
✅ Banned-import lint: nothing in `whatif/types/` imports from `whatif/internal/`, `whatif/adapters/`, or external SDKs.

## Phase 2: Decision pipeline

**Goal:** The trust core. Floor evaluation that produces `FloorPassedProof`. Policy guards that produce findings. The verdict computation.

### 2.1 — Floor evaluator

`whatif/decision/floor.py`:
- `evaluate_floor(result, floor) -> FloorPassedProof | FloorFailureSet`
- `FloorFailureSet(failures: list[FloorFailure])` for the failure case
- The `_FLOOR_INTERNAL_TOKEN` is constructed here as the only place that can produce proofs

Per-cohort evaluation. Each required cohort is checked against:
- `min_selected_per_required_cohort`
- `min_replayed_per_required_cohort`
- `min_scored_per_required_cohort`
- `min_replay_validity_ratio_per_required_cohort`

### 2.2 — Failure code registry

`whatif/decision/failure_codes.py`:
- `FAILURE_CODE_REGISTRY: dict[str, FailureCodeSpec]`
- Each entry: stage, default scope, required details keys

```python
FAILURE_CODE_REGISTRY = {
    "cache_miss": FailureCodeSpec(
        stage="replay", scope="trace",
        required_details=["tool_name", "expected_args_hash"],
    ),
    "runner_timeout": FailureCodeSpec(
        stage="replay", scope="trace",
        required_details=["timeout_seconds"],
    ),
    # ...
}
```

### 2.3 — Finding code registry

`whatif/decision/finding_codes.py`:
- `FINDING_CODE_REGISTRY: dict[str, FindingCodeSpec]`
- Each entry: severity, message template, required details keys, derived_from_failures expectation

### 2.4 — Fix suggestion registry

`whatif/decision/fix_suggestions.py`:
- `FIX_SUGGESTION_REGISTRY: dict[str, FixSuggestion]`
- Each entry: template string, list of suggestions

```python
FIX_SUGGESTION_REGISTRY = {
    "min_replayed_per_required_cohort": FixSuggestion(
        template="The {cohort} cohort had {observed} replayed traces (floor requires {threshold}).",
        suggestions=[
            "Increase the cohort selection limit in whatif.config.yaml.",
            "Check tracer logs for ingestion failures.",
            "Run with --debug to see why traces were skipped.",
        ],
    ),
    # ...
}
```

### 2.5 — Guards

`whatif/decision/guards/`:
- `replay_validity_guard.py`
- `baseline_coverage_guard.py`
- `regression_threshold_guard.py`
- `improvement_threshold_guard.py`
- `ci_availability_guard.py`
- `cache_staleness_guard.py`
- `primary_endpoint_guard.py` (cardinal #10): evaluates `DecisionPolicy.primary_endpoints` against per-cohort paired bootstrap output; produces `DecisionFinding(code="primary_endpoint_failed", severity="blocks_ship")` when the cohort-level endpoint fails

Each guard is a pure function `(ExperimentResult, DecisionPolicy) -> list[DecisionFinding]`.

`whatif/decision/clustering.py`:
- `resolve_cluster_key(source: TraceSource, policy: ClusteringPolicy) -> ClusterSelection` (cardinal #10)
- Records resolved choice in `RunManifest` and `MethodologyDisclosure.bootstrap.cluster_key`
- v0.1 declares structure; cluster-bootstrap math deferred to v0.2 (uses i.i.d. bootstrap under the hood for now, with explicit disclosure)

### 2.6 — Verdict computation

Implementation lands as three sub-phases (one PR each):

- **2.6a** — `whatif/decision/verdict.py::compute_verdict(cohort_results, floor, policy, *, guards=None) -> Verdict`. Single Ship-construction site; closure-captured `FloorPassedProof`; default guard chain composes the registered guards. (Resolved by PR #26.)
- **2.6b** — `primary_endpoint_guard` consolidation. Replaces the Phase 2.5b `failure_improvement_guard` + `baseline_regression_guard` pair with a configurable dispatcher reading `policy.primary_endpoints`; emits the existing finding codes by direction. The default guard chain shrinks from 5 to 4 guards; behavior on default policy is identical. (Resolved by PR #27.)
- **2.6c** — Real `derived_from_failures` wiring on `ci_availability_guard` (replace `_PHASE_2_6_PLACEHOLDER` with failure-record IDs threaded through projection). Per V0_1_DECISION_RECORD §6 there is no `accept_no_ci` work in 2.6c; the flag was removed in the 2026-05-05 skill-alignment pass.

Common to all three:
- Implements the guard chain pattern from `references/practices.md`
- All findings collected; verdict derived from worst severity present
- Floor-failure case returns `Inconclusive` regardless of findings

### 2.7 — Aggregation logic

`whatif/decision/aggregation.py`:
- `aggregate_cohort_systemic(failures: list[FailureRecord]) -> list[FailureRecord]`
- Implements the ≥50% rule: if same code affects ≥50% of cohort traces, emit cohort-scope record
- Trace records marked `aggregated_into: <cohort_record_id>` when folded

### Phase 2 tests

- **Unit tests:** Each guard tested in isolation with constructed `ExperimentResult` fixtures. Floor evaluator tested with edge cases (empty cohort, exactly-at-threshold, all-pass).
- **Coverage test:** Every floor rule has a registered fix suggestion. Every blocking finding code has a registered fix suggestion. CI test enumerates `FloorRule` and blocking codes; asserts each has an entry in `FIX_SUGGESTION_REGISTRY`.
- **Property test (Hypothesis):** Generate arbitrary `DecisionPolicy` configs and `ExperimentResult` fixtures. Assert: when `evaluate_floor()` returns `FloorFailureSet`, `compute_verdict()` returns `Inconclusive` regardless of policy.
- **Property test:** Aggregation idempotent — running aggregator twice on same input yields same output.
- **Property test:** All findings appear in returned verdict's `findings` list (no early-return data loss).
- **Schema-bypass test:** Attempt to construct `Ship` with a fake `FloorPassedProof` (e.g., `Mock()`). Confirm it raises.

### Phase 2 gate

✅ All unit tests green.
✅ All property tests pass 1000 iterations.
✅ Coverage test green: every floor rule and blocking code has a fix suggestion.
✅ Aggregation rule tested against scenarios from walkthroughs.
✅ mypy strict passes on `whatif/decision/`.

## Phase 3: Cache subsystem

**Goal:** Scorer cache with disclosure-mandatory, single-writer enforcement, key versioning.

### 3.1 — Cache key construction

`whatif/cache/keying/v1.py`:
- `build_cache_key(components: CacheKeyComponents) -> str`
- Includes all required components (see `references/contracts.md`)
- `CACHE_KEY_VERSION = "v1"`
- PRs touching this directory bump version

### 3.2 — Cache storage

`whatif/cache/storage/v1.py`:
- File layout: `.whatif/cache/entries/<hash[0:2]>/<hash>.json`
- `meta.json` at cache root tracking schema version
- `CACHE_SCHEMA_VERSION = "v1"`
- PRs touching this directory bump version

### 3.3 — Cache lock

`whatif/cache/lock.py`:
- `acquire_cache_lock(path) -> CacheLock` context manager
- `fcntl.flock(LOCK_EX | LOCK_NB)` primary
- Stale detection via lock file with PID + process_start_time + hostname
- Takeover requires both `os.kill(pid, 0)` raising `ProcessLookupError` AND `psutil.Process(pid).create_time()` mismatch
- Default `stale_after_seconds: 86400` (24h); configurable

### 3.4 — Cache policy

`whatif/cache/policy.py`:
- `CachePolicy` resolves mode from config + environment
- `CI=true` defaults to `read_write`; interactive defaults to `auto`
- Mode resolution emits a `DecisionFinding` if mode was inferred (so CI runs disclose what was used)

### 3.5 — Cache summary

`whatif/cache/summary.py`:
- `CacheSummary` typed object with all required fields
- Construction at end of run; included in `ReportV01` (required field; schema validation enforces presence)

### Phase 3 tests

- **Unit tests:** Key construction is deterministic given same components. Storage round-trip preserves data. Lock acquire/release works.
- **Lock contention test:** Two simulated processes attempt to acquire same lock. First succeeds, second fails with `CacheLockedError`.
- **Stale lock test:** Write a lock file with a dead PID; new process can take over after stale window.
- **Stale lock false-positive test:** Write a lock file with a live PID but mismatched create_time; takeover succeeds (PID was reused).
- **Lock NFS test:** Documented as unsupported; test asserts the error message names NFS as the likely cause if `EAGAIN` returned without `EWOULDBLOCK`.
- **Cache key version test:** PR touching `whatif/cache/keying/` without bumping `CACHE_KEY_VERSION` fails CI.
- **Cache schema version test:** Same for storage.
- **Disclosure test:** Constructing a `ReportV01` without a `cache_summary` field raises validation error.

### Phase 3 gate

✅ All cache unit tests green.
✅ Lock contention test green (real processes, not mocks).
✅ CI version-bump tests green.
✅ Cache summary required-field test green.
✅ Performance: 1000 cache lookups under 5s on local SSD.

## Phase 4: Adapters

**Goal:** Reference adapters for trace source (Langfuse) and scorer (Inspect AI). Each is a separate package, lazy-loaded.

### 4.1 — Langfuse trace source adapter

`whatif-langfuse/` (separate package):
- Implements `TraceSource` protocol
- Wraps user content as `Sensitive[str]` at adapter boundary
- Streams traces (generator, not list)
- Builds `RawTrace` → `TraceInput` projection
- Adapter version exposed via `adapter_metadata()`

### 4.2 — Inspect AI scorer adapter

`whatif-inspect-ai/` (separate package):
- Implements `Scorer` protocol
- Builds `ScoreCase` → `JudgeResult` projection
- `cache_key_components()` returns full required component set
- Wraps judge rationale as `Sensitive[str]`
- Adapter version exposed via `adapter_metadata()`

### 4.3 — Adapter loading

`whatif/adapters/loader.py`:
- Lazy import based on adapter ID string (`langfuse` → import `whatif_langfuse`)
- Importing whatif core does NOT import any adapter
- Test: `python -c "import whatif"` does not import `whatif_langfuse` or `whatif_inspect_ai`

### Phase 4 tests

- **Adapter conformance tests:** Both adapters pass a shared conformance test suite that exercises the protocol.
- **Sensitive wrap test:** Adapter outputs always wrap user content; serializer refuses adapter output that has unwrapped user content.
- **Lazy load test:** `import whatif` does not import any adapter.
- **Cache key components test:** Inspect AI adapter returns all required components; missing any one fails the test.
- **Stub adapter test:** Synthetic stub adapter for use in integration tests; produces realistic-shaped data.

### Phase 4 gate

✅ Both adapters pass conformance suite.
✅ Lazy load test green.
✅ Stub adapter implemented (used in Phase 9 integration).
✅ Sensitive wrapping verified end-to-end (adapter output → serializer rejects unwrapped).

## Phase 5: Serialization and schema

**Goal:** `ReportV01`, JSON Schema generation, redaction enforcement, deterministic output.

### 5.1 — Public report model

`whatif/report/models_v01.py`:
- `ReportV01` hand-written; includes `methodology: MethodologyDisclosure` required field per cardinal #10
- `CacheSummary` typed object
- All public types
- Pydantic v2 for JSON Schema generation
- Methodology disclosure types (`BootstrapMethodDisclosure`, `MultiplicityDisclosure`, `JudgeMethodDisclosure`, `EffectSizeDisclosure`) projected from internal statistical types

### 5.2 — Projection functions

`whatif/report/projection.py`:
- `project_to_report_v01(experiment_result: ExperimentResult) -> ReportV01`
- One projection per top-level field
- Internal types refactor; projection layer absorbs the change

### 5.3 — JSON Schema generation

`scripts/generate_schema.py`:
- Generates JSON Schema from `ReportV01` Pydantic model
- Output: `whatif/report/schema/v0.1.schema.json`
- Includes `x-deterministic` annotations on each property
- Committed to repo; CI test asserts no drift

### 5.4 — Custom JSON encoder

`whatif/serialization/encoder.py`:
- `WhatifJSONEncoder(json.JSONEncoder)`
- Sorted keys
- `default()` raises `UnredactedSensitiveError` on `Sensitive` instances
- Banned everywhere else via lint rule

### 5.5 — Pre-serialization graph walk

`whatif/serialization/graph_walk.py`:
- `assert_no_unredacted_sensitive(obj, path="")` walks dataclasses, dicts, lists, tuples
- Raises with full path to offending field
- Called before any artifact write

### 5.6 — Decimal string handling

`whatif/serialization/decimal.py`:
- `to_decimal_string(value: float, precision: int = 3) -> DecimalString`
- `from_decimal_string(s: DecimalString) -> Decimal`
- Stable across platforms (uses `format(value, '.3f')`)

### 5.7 — Determinism infrastructure

`whatif/serialization/determinism.py`:
- `extract_deterministic_subset(report: ReportV01, schema: dict) -> dict`
- Reads `x-deterministic: true` annotations from schema
- Extracts only those fields for byte-equality testing

### Phase 5 tests

- **Schema match test:** Generated schema from `ReportV01` byte-equals committed `v0.1.schema.json`.
- **Public-internal isolation test:** No imports from `whatif/internal/` in `whatif/report/models_v01.py`.
- **Golden report test:** Six committed golden reports validate against schema.
- **Encoder rejection test:** Attempting to encode an unwrapped `Sensitive` raises typed error.
- **Graph walk test:** Object graphs containing nested `Sensitive` (in dicts, in lists, in dataclass fields) all detected.
- **Determinism test:** Same input + same seed → byte-identical deterministic subset.
- **Float platform-stability test:** `to_decimal_string(0.1 + 0.2)` produces "0.300" on Linux x86_64, macOS arm64, Windows x86_64.

### Phase 5 gate

✅ All serialization tests green.
✅ Schema match test green (zero drift).
✅ Six golden reports committed and validating.
✅ Determinism test green (same input, twice, byte-identical).
✅ Banned-import lint enforced (`json.dumps` only in `whatif/serialization/`).

## Phase 6: Replay pipeline

**Goal:** The streaming generator chain. Trace → replay → score case.

### 6.1 — Tool cache (trace-scoped)

`whatif/replay/tool_cache.py`:
- `ToolCache.from_trace(raw: RawTrace) -> ToolCache`
- Strict: cache miss raises typed `CacheMissError` which the pipeline converts to `ReplayFailure`
- Per-trace, not global

### 6.2 — Replay result types

`whatif/replay/result.py`:
- `ReplaySuccess(output: ReplayOutput)`
- `ReplayFailure(trace_id, code, message, details)`
- `ReplayResult = ReplaySuccess | ReplayFailure`

### 6.3 — Pipeline

`whatif/replay/pipeline.py`:
- Generator chain consuming `Iterator[RawTrace]`, producing `Iterator[ScoreCase | ReplayFailure]`
- Bounded concurrency via `ThreadPoolExecutor` for sync runners
- Async runners via `asyncio.gather` with semaphore
- Timeouts wrap runner execution; produce typed failures, not exceptions

### 6.4 — Runner contract surface

`whatif/contract/runner.py`:
- `TraceInput`, `ReplayConfig`, `ToolCache`, `ReplayOutput` (frozen dataclasses)
- Imported from user code via `from whatif.contract import ...`
- No internal types leak through this module

### Phase 6 tests

- **Pipeline test:** Stub adapter + stub runner → pipeline produces expected `ScoreCase` and `ReplayFailure` instances.
- **Timeout test:** Slow runner triggers timeout; produces `ReplayFailure(code="runner_timeout")`.
- **Concurrency test:** 100 traces with bounded executor; memory bounded, no race conditions.
- **Memory test:** Pipeline run on 1000-trace stream; peak memory stays within budget.
- **Cache miss test:** Trace with missing tool output produces `ReplayFailure(code="cache_miss")`, NOT an exception.
- **Async runner test:** `AsyncRunner` protocol works end-to-end.

### Phase 6 gate

✅ All pipeline tests green.
✅ Memory budget held on 1000-trace synthetic run.
✅ Timeout test green.
✅ Both sync and async runners work via stub.

## Phase 7: Rendering

**Goal:** Three output formats (1-line, 30-line summary, full report) from the same JSON.

### 7.1 — Markdown renderer (full report)

`whatif/render/markdown.py`:
- `render_full_report(report: ReportV01) -> str`
- Five-section structure: Verdict, Stats, Replay validity, Baseline integrity, Evidence
- Plus a Methodology block (cardinal #10) rendered from `report.methodology` — bootstrap method, multiplicity stance, judge state with reliability/validity/calibration/bias booleans, effect-size policy, per-trace-inference scope, causal-claim scope
- Anchored jump links from summary section to detail
- Queries `FIX_SUGGESTION_REGISTRY` for Inconclusive / Don't Ship verdicts

### 7.2 — Summary section

`whatif/render/summary.py`:
- `render_summary_section(report: ReportV01) -> str`
- Lines budget: ≤ 30 lines
- Compact-Ship case: just the summary, no detail section
- Test enforces line count

### 7.3 — CI status line

`whatif/render/ci_status.py`:
- `render_ci_status(report: ReportV01) -> str`
- ~80 character limit
- Verdict + headline finding
- Used in GitHub Actions check display

### 7.4 — Fix suggestion templating

`whatif/render/templates/`:
- One file per fix suggestion code
- Markdown templates with placeholder substitution
- Linted for placeholder consistency

### Phase 7 tests

- **Walkthrough match tests:** Six rendered Markdown outputs match the committed walkthrough scenarios from Phase 0.
- **Line budget test:** Summary section ≤ 30 lines for all six scenarios.
- **CI status budget test:** CI status line ≤ 80 characters for all six scenarios.
- **Fix suggestion coverage:** Every Inconclusive scenario in walkthroughs has fix-suggestion text rendered.
- **Three-format consistency test:** Same `ReportV01` produces consistent verdict across CI status, summary, and full report (no contradictions).

### Phase 7 gate

✅ All six walkthrough scenarios round-trip: ReportV01 → render → matches committed Markdown.
✅ Line/character budgets enforced.
✅ Fix suggestions present for all blocking codes in scenarios 4 and 5.
✅ Three-format consistency test green.

## Phase 8: CLI and config

**Goal:** Pydantic config validation; CLI argument parsing; exit code semantics; environment-aware defaults.

### 8.1 — Config schema

`whatif/config.py`:
- Pydantic v2 strict mode
- All sections: source, target, selection, change, scorer, decision, reporting, timeouts
- Hint generation on validation errors
- Two-affirmation logic for forensic profile

### 8.2 — CLI

`whatif/cli.py`:
- `whatif fork ...` command
- `whatif report-migrate ...` (v0.1 stub; real logic v0.2+)
- `whatif cache rebuild ...` (if surfaced by Phase 0 walkthroughs as needed)
- Exit codes: 0 (Ship), 1 (Don't Ship), 2 (Inconclusive / setup failure)
- Floor violation always produces exit 2

### 8.3 — Environment detection

`whatif/cli/environment.py`:
- Detect `CI=true`, `GITHUB_ACTIONS=true`
- Adjust defaults: cache mode, profile, determinism strictness
- Captured in manifest

### 8.4 — Exit code precedence

Resolved in `whatif/cli.py`:
- Floor violation → exit 2 (highest priority; never overridden)
- Setup/replay/scoring failure preventing verdict → exit 2
- `DontShip` verdict → exit 1
- `Ship` verdict → exit 0

### Phase 8 tests

- **Config validation tests:** Bad configs produce hints; good configs validate.
- **Two-affirmation test:** Forensic profile with config-only or CLI-only fails; both required.
- **Exit code tests:** Each verdict produces correct exit code; floor violation always 2.
- **Environment test:** Setting `CI=true` flips defaults as expected.

### Phase 8 gate

✅ All CLI tests green.
✅ Two-affirmation forensic test green.
✅ Exit code precedence test green.
✅ Hint generation produces actionable errors for top 10 misconfigurations.

## Phase 9: Integration and end-to-end

**Goal:** Full pipeline against recorded synthetic Langfuse traces. Real fixtures, real adapter, real renderer, real CLI.

### 9.1 — Integration test fixtures

`tests/fixtures/`:
- Synthetic Langfuse traces (regenerable from a stub agent)
- Six scenario configurations (one per walkthrough)
- Expected `ReportV01` JSON for each
- Expected rendered Markdown for each

### 9.2 — End-to-end test suite

`tests/integration/`:
- One test per walkthrough scenario
- Run `whatif fork` against fixtures
- Assert exit code, JSON output, Markdown output match expectations

### 9.3 — Determinism property test

`tests/integration/test_determinism.py`:
- Run same fixture twice
- Diff JSON deterministic subset
- Assert byte-equality

### 9.4 — Failure injection

`tests/integration/test_failures.py`:
- Inject scorer outage, runner timeout, cache corruption, malformed traces
- Assert each produces structured `FailureRecord`s, not exceptions
- Assert exit code 2 with appropriate verdict

### Phase 9 tests

- **All six scenarios pass end-to-end.**
- **Determinism test passes byte-equality.**
- **Failure injection test passes for all 8+ injected failure types.**
- **Performance test:** Full pipeline on 40-trace fixture under 60s (excluding judge calls; mock judge for this test).

### Phase 9 gate

✅ Six end-to-end scenarios match committed expectations.
✅ Determinism test green.
✅ Failure injection covers all `FAILURE_CODE_REGISTRY` entries.
✅ Performance budget met.
✅ Full enforcement audit re-run; all entries green.

## Phase 10: Release packaging

**Goal:** v0.1 ships.

### 10.1 — Documentation

- `README.md` leading with v0.1 doctrine
- `docs/concepts.md` (from Phase 0)
- `docs/getting-started.md` with worked example
- `docs/runner-contract.md`
- `docs/schema/v0.1.md` with consumer compatibility guide
- `docs/path-z.md` describing tool doctrine

### 10.2 — Examples

- `examples/minimal-agent/` — reference SyncRunner implementation
- `examples/langchain-agent/` (stub + docs in v0.1.1)
- `examples/langgraph-agent/` (stub + docs in v0.1.1)

### 10.3 — Schema publication

- `schemas/report/v0.1.schema.json` published to public URL
- `https://whatif.codes/schema/report/v0.1.json` returns the file

### 10.4 — PyPI publication

- `whatif` package
- `whatif-langfuse` package
- `whatif-inspect-ai` package
- All with stable v0.1.0 version

### 10.5 — Release verification

- Install from PyPI in clean env
- Run getting-started example
- Verify all six walkthrough scenarios reproduce
- Verify schema URL serves correct file

### Phase 10 gate

✅ All documentation reviewed and committed.
✅ PyPI install + walkthrough reproduction works.
✅ Schema URL resolves correctly.
✅ CHANGELOG complete with all decisions traced.

## Post-v0.1 trajectory

These are not phases — they are the trajectory toward v1.0. Each becomes its own phase plan when scoped.

- **v0.1.1**: LangChain and LangGraph reference adapters (stubs + docs).
- **v0.2 (M11):** Config-file mode polish, second tracer adapter (Phoenix), model swap as a `--change` kind, GitHub Action wrapper. Possible expansion to `regression_check` experiment type if audience-distribution justifies.
- **v0.3 (M12):** Live-tool replay (opt-in, allowlist), worked CI sample repo.
- **v1.0 (year 2):** The pre-merge regression gate. Conditional verdicts. Acceptance mechanism. Schema v1 with breaking changes if needed.

## Cross-cutting test discipline

These tests run on every PR, not just at phase gates:

- `mypy --strict whatif/`
- `ruff check whatif/`
- `pytest tests/unit/ tests/property/ tests/integration/`
- `python -c "import whatif"` time budget
- Generated schema vs committed schema diff
- Banned-import lint
- Cache version-bump check (if cache directories touched)
- Schema version bump check (if `models_v01.py` touched)

## What completion looks like

v0.1 is complete when:

1. The six walkthrough scenarios reproduce end-to-end via CLI.
2. All ten phase gates are green.
3. The cascade catalog has no `open` items (only `resolved` or `deferred`).
4. The enforcement audit is clean: every "structural" claim has a paired mechanism with a passing test.
5. PyPI install in a clean env reproduces a Ship verdict on the minimal-agent example.
6. The README's first paragraph accurately describes what v0.1 ships, with no aspirational claims.

The deliberation has earned the right to meet reality. The phases are how that meeting happens, with structured discipline at every gate.
