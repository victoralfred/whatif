# Contracts

The boundaries between whatif and the systems around it. Contracts are stable; internals can refactor.

## The runner contract (user-supplied)

Users write one Python function. whatif owns everything else.

```python
# my_agent/replay.py
from whatifd.contract import TraceInput, ReplayConfig, ToolCache, ReplayOutput

def run(
    trace_input: TraceInput,
    config: ReplayConfig,
    tool_cache: ToolCache,
) -> ReplayOutput:
    """Re-execute the agent for a single trace with the proposed config change."""
    agent = build_agent(
        system_prompt=config.system_prompt,
        tool_cache=tool_cache,
    )
    text = agent.run(trace_input.user_message)
    return ReplayOutput(text=text)
```

CLI invocation:

```
whatif fork --target "python:my_agent.replay:run" ...
```

### Runner responsibilities (only one)

Produce a fresh `ReplayOutput` for a given input + modified config. That is the entire contract.

### whatif responsibilities (everything else)

- Pulling the original trace from the tracer.
- Constructing cohort labels.
- Owning the original output from the trace.
- Constructing the comparison unit (`ScoreCase`).
- Running the scorer against original vs replayed.
- Computing per-trace deltas, aggregate stats, bootstrap CIs.
- Selecting representative evidence cases.
- Producing the verdict and the report.

### Sync and async runners

v0.1 supports both:

```python
class SyncRunner(Protocol):
    def run(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        tool_cache: ToolCache,
    ) -> ReplayOutput: ...

class AsyncRunner(Protocol):
    async def run(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        tool_cache: ToolCache,
    ) -> ReplayOutput: ...
```

Internally whatif handles both via `asyncio.run` for sync runners called from async contexts and direct await for async runners.

### Tool cache is trace-scoped

Each replay receives a `ToolCache` constructed from that trace's tool calls only. Not a global cache. Avoids cross-trace cache hits and unbounded growth.

```python
for trace in selected_traces:
    tool_cache = ToolCache.from_trace(trace)
    replayed = runner.run(trace_input, config, tool_cache)
```

Cache miss is a `FailureRecord(scope="trace", code="cache_miss")`, not an exception. Strict by default.

## Adapter protocols

Adapters are Protocol classes (structural typing). User code does not import or inherit from whatifd's class hierarchy.

### TraceSource (tracer adapter)

```python
class TraceSource(Protocol):
    def stream_traces(
        self,
        policy: SelectionPolicy,
    ) -> Iterator[RawTrace]:
        """Yield traces matching the selection policy. Generator, not list."""

    def adapter_metadata(self) -> AdapterMetadata:
        """Return adapter version, source name, supported features."""

    def cluster_key_support(self) -> ClusterKeySupport:
        """Return real cluster keys this tracer can supply.

        Real keys are stable identifiers from the production system —
        user_id, session_id, conversation_id, account_id, etc.

        whatif uses these for cluster bootstrap to estimate honest CIs
        when traces are correlated. Returning an empty tuple means
        "no clusters available; assume i.i.d." — which is also fine, but
        the report will disclose that assumption.

        Adapters MUST NOT fabricate cluster keys (e.g., k-means on
        embeddings) for confirmatory verdicts in v0.1. Faking cluster
        structure is worse than ignoring the issue.
        """
```

Implementations: `whatifd-langfuse` (v0.1), `whatif-phoenix` (deferred), `whatif-otel-genai` (deferred).

#### Cluster-key disclosure

Tracer adapters declare which real cluster keys they can supply via `cluster_key_support()`. Core uses these for cluster bootstrap when uncertainty estimation is needed.

The chain:

```
ClusteringPolicy (user-configured) + TraceSource.cluster_key_support()
    → resolve_cluster_key() → ClusterSelection
    → recorded in RunManifest and MethodologyDisclosure
```

If no cluster key is available and `ClusteringPolicy.fallback_behavior` is `warn` (default), the report discloses the i.i.d. assumption explicitly:

```
Cluster handling: none. CIs assume trace-level independence and may be
optimistic if traces are correlated.
```

If `fallback_behavior` is `refuse`, the run produces `Inconclusive` when no cluster key is available — useful for high-trust CI environments where the tracer is expected to provide stable session IDs.

See `references/type-model.md` § "Clustering types" for the dataclass definitions and the resolution function semantics.

### Scorer (score adapter)

```python
class Scorer(Protocol):
    def score_batch(
        self,
        cases: Sequence[ScoreCase],
    ) -> Sequence[JudgeResult]:
        """Score a batch of cases. Async or sync internal; batch-first."""

    def cache_key_components(self) -> CacheKeyComponents:
        """Provide all data needed to construct a deterministic cache key
        for this scorer/judge configuration."""

    def adapter_metadata(self) -> AdapterMetadata:
        """Return adapter version, scorer name, judge model identifier."""
```

The `cache_key_components()` method is critical for determinism. It must include:

- whatif report schema version
- whatif scorer adapter version
- scorer type and package version
- judge provider
- judge model identifier
- judge model snapshot/version (if available)
- rendered judge prompt hash (NOT template hash — the actual final string)
- rubric hash
- scoring parameters
- ScoreCase serialization version

If the adapter changes the rendered prompt without bumping its version, cache poisoning becomes possible. Adapter authors are responsible for surfacing version changes to whatif.

Implementations: `whatifd-inspect-ai` (v0.1).

### Runner already covered above

The runner is also a Protocol but lives in user code, not adapter code.

## ScoreCase (the unit handed to scorers)

```python
@dataclass(frozen=True, slots=True)
class ScoreCase:
    trace_id: str
    cohort: str  # "failure" | "baseline" | future
    input: TraceInput
    original_output: TraceOutput  # owned by whatif from the trace
    replayed_output: ReplayOutput  # produced by user runner
    metadata: Mapping[str, str | int | float | bool | None]
```

Users never construct `ScoreCase` directly. It's exposed in the public API so custom scorer plugins (v0.2+) have a typed interface.

## JudgeResult (returned by scorers)

```python
@dataclass(frozen=True, slots=True)
class JudgeResult:
    trace_id: str
    score_delta: DecimalString  # "0.310" not 0.31
    verdict: Literal["improved", "unchanged", "regressed"]
    rationale: Sensitive[str]  # judge text wrapped sensitive
    confidence: DecimalString  # 0.000 to 1.000
    flags: list[str]  # e.g., "output_truncated", "tool_mismatch"
```

Note: `rationale` is wrapped `Sensitive[str]`. Judge rationales can quote user content. Adapters wrap at their boundary; redaction profile determines what reaches the report.

## Public report schema versioning

The schema is the API. Discipline matters more here than in any other part of the codebase.

### Versioning rules

- **Patch (0.1.x → 0.1.y):** Documentation, examples, non-semantic schema metadata. No structural changes. Old reports validate against new schema.
- **Minor (0.1.x → 0.2.0):** Additive optional fields. New failure codes. New finding codes. Old reports validate against new schema; new reports may not validate against old schema.
- **Major (0.x.x → 1.0.0):** Removed fields. Type changes. Required field additions. Verdict state changes. Old reports do NOT validate against new schema; migration tool required.

### Extension points

Three named extension points in v0.1:

- `FailureRecord.details` (Mapping[str, JsonPrimitive])
- `DecisionFinding.details` (Mapping[str, JsonPrimitive])
- `RunManifest.environment` (allows adapter-specific host fields)

Adding a key to one of these is a patch. Adding a new top-level field to `ReportV01` is a minor. Removing or retyping any field is a major.

### Promotion path

A key that has lived in a `details` map across two minor versions, used by at least one shipped consumer, can be promoted to a first-class field in the next minor. Promotion requires:

- Migration documentation in CHANGELOG
- Deprecation notice on the `details` key for one minor cycle
- Both old (in details) and new (first-class) fields present during the deprecation cycle

### Public-vs-internal model split

Public types in `whatif/report/models_v01.py`. Internal types in `whatif/internal/`. Projection functions in `whatif/report/projection.py`.

CI tests:
- `test_no_internal_types_in_public_module` — public module imports nothing from `whatif/internal/`.
- `test_schema_matches_models` — generated JSON Schema from `ReportV01` matches committed `schemas/report/v0.1.schema.json` byte-for-byte.
- `test_golden_reports_validate` — every committed golden report in `tests/golden/` validates against its declared schema version.

### Consumer compatibility guide

Downstream tools must:

- Ignore unknown optional fields (forward compatibility).
- Treat unknown failure codes as `degrades_trust` impact unless `verdict_impact` is explicitly present and recognized. (Note: `verdict_impact` was removed from `FailureRecord`; this rule applies to `DecisionFinding.severity`.)
- Treat unknown verdict states as `Inconclusive`.
- Treat unknown severity values as `degrades_trust`.
- Treat unknown required-field-missing as schema-invalid.

This guide lives in `docs/schema/consumer-guide.md`.

## CLI contract

Stable across patch versions. New flags are additive minor; removing flags is major.

### Core commands

```
whatif fork \
    --source <adapter:identifier> \
    --target <python:module.path:function> \
    --change <kind=value>... \
    --tool-cache <use-original | live | mock> \
    --score <adapter:scorer> \
    [--config <path>] \
    [--profile <minimal | review | audit | forensic>] \
    [--output <directory>] \
    [--accept-no-ci]
```

### Exit codes (stable)

```
0 - Passed configured policy.
1 - Failed configured policy (Don't Ship).
2 - Inconclusive (setup, replay, scoring failure, OR floor violation).
```

Floor violations always produce exit 2, regardless of policy state. Policy precedence: floor > policy. Acceptance (v1.0) cannot override floor.

### CI environment detection

`CI=true`, `GITHUB_ACTIONS=true`, etc. flips defaults toward CI-correct behavior:

- Scorer cache defaults to `read_write` (vs `auto` in interactive).
- Artifact profile defaults to `audit` (vs `review`).
- Determinism strict mode on.

CLI flags override environment defaults. Resolved config is captured in manifest.

## Configuration contract

`whatif.config.yaml` schema. Pydantic strict mode for validation with clear error messages.

```yaml
source:
  adapter: langfuse
  project: my-project

target:
  module: my_agent.replay
  function: run

selection:
  failure_cohort:
    limit: 20
    filter: "tag:incident-2026-04"
  baseline_cohort:
    limit: 20
    sampling: random
    seed: 42

change:
  system_prompt: prompts/v3.txt

tool_cache:
  policy: use-original

scorer:
  adapter: inspect_ai
  rubric: faithfulness
  cache:
    mode: auto
    warn_after_days: 30
    block_after_days: 90
    storage_profile: normalized_result_only
    storage_path: .whatif/cache/scorer

decision:
  require_baseline: true
  max_baseline_regression_ratio: 0.10
  min_failure_improvement_ratio: 0.50

reporting:
  profile: review
  output_directory: reports/

# Forensic acknowledgment (v0.1+)
# reporting:
#   profile: forensic
#   forensic_acknowledgment:
#     confirmed: true
#     reviewer: "alice@example.com"
#     justification: "..."
# AND: --profile forensic on CLI
```

## What changes the schema vs what doesn't

| Change | Type | Allowed in v0.1 |
|---|---|---|
| Add a new failure code to registry | Minor | After v0.1 |
| Add a new finding code to registry | Minor | After v0.1 |
| Add a key to `FailureRecord.details` for an existing code | Patch | Yes |
| Add a new optional field to `ReportV01` | Minor | After v0.1 |
| Add a new required field | Major | Major bump |
| Change a field's type | Major | Major bump |
| Add a verdict state | Major | Major bump |
| Add an extension point | Minor | After v0.1 |
| Update fix-suggestion text for a code | Patch | Yes |
| Bump cache key version | Internal patch | Yes (cache invalidates) |
| Bump cache schema version | Internal patch | Yes (file format migration) |

## Cache contract

Storage location, format, and key derivation.

### Storage layout

```
.whatif/cache/
├── .lock               (file lock; JSON contents)
├── meta.json           (cache schema version, key version, created_at)
└── entries/
    └── <hash[0:2]>/
        └── <hash>.json (one entry per cache key)
```

Sharded by first 2 hex chars of cache key to avoid filesystem-level slowdowns at scale.

### Entry format

```json
{
  "cache_key_version": "v1",
  "cache_schema_version": "v1",
  "created_at": "2026-04-01T...",
  "key_components": {
    "scorer_adapter_version": "...",
    "judge_model": "...",
    "rendered_prompt_hash": "...",
    "rubric_hash": "...",
    "input_hash": "...",
    "original_output_hash": "...",
    "replayed_output_hash": "..."
  },
  "result": {
    "score_delta": "0.310",
    "verdict": "improved",
    "rationale": "<redacted-or-stored-per-profile>",
    "confidence": "0.850",
    "flags": []
  }
}
```

The `rationale` is included only if `storage_profile: full_judge_io`. Default profile (`normalized_result_only`) stores hashes and the score, not the rationale text.

### Key version vs schema version

- **Key version** changes when cache identity logic changes. PRs touching `whatif/cache/keying/` bump it. Old entries miss naturally.
- **Schema version** changes when cache file format changes. PRs touching `whatif/cache/storage/` bump it. Entries with old schema version are read with migration or ignored.

CI test asserts both versions are bumped if their respective directories are touched. Pre-commit hook warns.

### Concurrency

Single-writer per cache directory, enforced by `fcntl.flock`. See `references/enforcement.md` for the full mechanism. Concurrent runs against a shared cache directory: second writer fails fast with `CacheLockedError`, exit 2.
