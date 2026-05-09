# Type Model

The canonical types for v0.1. All types are frozen dataclasses with `__slots__`. Public types (used in `ReportV01`) are versioned; internal types can refactor freely.

## Canonical type list

```
TrustFloor              (structural, non-overridable)
DecisionPolicy          (user-configurable, must be stricter than floor)
FailureRecord           (operational fact, one per event)
DecisionFinding         (policy conclusion, may reference failures)
Verdict                 (Ship | DontShip | Inconclusive — sealed union)
CohortResult            (per-cohort stats + floor + policy outcome)
RunManifest             (audit anchor)
ReportV01               (public report shape, v0.1)
ArtifactBundle          (on-disk output of one run)
Sensitive[T]            (redaction wrapper)
FloorPassedProof        (witness token for Ship)

# Statistical types (added per cardinal rule #10)
TraceDelta              (paired delta, atomic unit of analysis)
TraceDeltaReportV01     (public DecimalString-serialized form)
BootstrapMethodDisclosure
MultiplicityDisclosure
JudgeMethodDisclosure
EffectSizeDisclosure
MethodologyDisclosure   (required in every ReportV01)
ClusterKeySupport       (declared by tracer adapter)
ClusterSelection        (resolved from policy + adapter capability)
ClusteringPolicy        (user-configurable, layered above adapter capability)
```

## TrustFloor

Structural. Non-overridable. Versioned for CI stability.

```python
@dataclass(frozen=True, slots=True)
class TrustFloor:
    version: str  # "v1", sticky in manifest
    source: str   # e.g., "whatifd-0.1.0"
    min_selected_per_required_cohort: int = 5
    min_replayed_per_required_cohort: int = 5
    min_scored_per_required_cohort: int = 5
    min_replay_validity_ratio_per_required_cohort: float = 0.50  # provisional
```

Provisional notes:
- The 0.50 ratio is provisional with warn-band 0.50–0.70. Marked for revision after first 10 production runs based on observed replay success rates.
- CI availability is **policy**, not floor. A small-sample experiment can produce credible Ship if everything else is healthy and the sample is acknowledged.
- Floor versioning: existing runs use the floor version they were built against; floor version is sticky in manifest. v0.2 may bump to v2; v0.1 runs continue to validate against v1.

## DecisionPolicy

User-configurable. Layers on top of the floor; can be stricter, never weaker.

```python
@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    # Cohort requirements
    require_baseline: bool = True  # baseline required for Ship
    required_cohorts: list[str] = ("failure", "baseline")

    # Quality thresholds (above-floor concerns)
    max_baseline_regression_ratio: float = 0.10
    min_failure_improvement_ratio: float = 0.50
    max_ci_width: float | None = None  # None = no CI width check

    # Cache policy
    scorer_cache_mode: Literal["auto", "on", "off", "read_only", "refresh"] = "auto"
    scorer_cache_warn_after_days: int = 30
    scorer_cache_block_after_days: int = 90
    scorer_cache_storage_profile: Literal["normalized_result_only", "full_judge_io"] = "normalized_result_only"

    # Per V0_1_DECISION_RECORD §6, v0.1 has no --accept-no-ci flag.
    # CI unavailability forces Inconclusive (blocks_all). max_ci_width
    # above is the lever for accepting wider but computable CIs.
```

## FailureRecord

Operational fact. One per event. Adapter emits trace-scope; core emits cohort- and run-scope.

```python
@dataclass(frozen=True, slots=True)
class FailureRecord:
    id: str  # e.g., "failure_001", stable within run
    code: str  # machine-readable, registered in FAILURE_CODE_REGISTRY
    stage: Literal["ingest", "selection", "replay", "score", "diff", "decision", "report"]
    scope: Literal["trace", "cohort", "run"]
    message: str  # human-readable, may be templated
    trace_id: str | None  # required if scope=="trace"
    cohort: str | None  # required if scope=="cohort"
    retryable: bool
    details: Mapping[str, str | int | float | bool | None]
    aggregated_into: str | None = None  # cohort-record ID if folded
```

**Note:** `verdict_impact` was removed from `FailureRecord`. Verdict consequences live on `DecisionFinding`. This keeps the operational layer pure: `FailureRecord` is what happened, `DecisionFinding` is what it means.

## Two-type scope rule (the bright line)

| `scope` | Emitter | Cardinality |
|---|---|---|
| `trace` | Adapter | One per affected trace event |
| `cohort` | Core (post-aggregation) | One per cohort-level event |
| `run` | Core | One per run-level event |
| (`DecisionFinding`) | Core (decision pipeline) | Aggregates across `FailureRecord`s for verdict |

Discriminator: is the failure per-trace observable?
- Yes → adapter emits trace-scope records.
- No → core emits one cohort-scope record after aggregation.

Aggregation rule (v0.1 simple version): any code that affects ≥50% of cohort traces emits a cohort-scope record alongside the trace records. Trace records are kept (forensic profile shows them) but marked `aggregated_into: <cohort_record_id>`.

## DecisionFinding

Policy conclusion. May or may not derive from `FailureRecord`s. Aggregate baseline regression has no underlying operational failure; cache-miss-driven floor failure has many.

```python
@dataclass(frozen=True, slots=True)
class DecisionFinding:
    code: str  # registered in FINDING_CODE_REGISTRY
    severity: Literal["info", "degrades_trust", "blocks_ship", "blocks_all"]
    message: str
    derived_from_failures: list[str]  # FailureRecord IDs, may be empty
    details: Mapping[str, str | int | float | bool | None]
```

Severity vocabulary is shared with future fields (no separate enum for failures vs findings). `info` is informational only. `degrades_trust` accumulates against thresholds. `blocks_ship` prevents Ship verdict. `blocks_all` forces Inconclusive.

## Verdict (sealed union with witness token)

The witness-token pattern makes `Ship` un-constructable without going through floor evaluation.

```python
class FloorPassedProof:
    """Witness type. Only constructed by evaluate_floor() on success.

    No public constructor. The frozen=True dataclass on Ship requires this token,
    so Ship cannot be instantiated outside the floor pipeline.
    """
    __slots__ = ("_floor_version", "_evaluated_at")

    def __init__(self, *, _internal_token: object, floor_version: str, evaluated_at: str):
        if _internal_token is not _FLOOR_INTERNAL_TOKEN:
            raise TypeError("FloorPassedProof cannot be constructed directly")
        object.__setattr__(self, "_floor_version", floor_version)
        object.__setattr__(self, "_evaluated_at", evaluated_at)

_FLOOR_INTERNAL_TOKEN = object()  # module-private


@dataclass(frozen=True, slots=True)
class Ship:
    proof: FloorPassedProof  # cannot fake without calling evaluate_floor()
    cohort_results: list["CohortResult"]
    findings: list[DecisionFinding]


@dataclass(frozen=True, slots=True)
class DontShip:
    cohort_results: list["CohortResult"]
    findings: list[DecisionFinding]
    blocking_findings: list[DecisionFinding]  # subset, severity=blocks_ship


@dataclass(frozen=True, slots=True)
class Inconclusive:
    cohort_results: list["CohortResult"]
    findings: list[DecisionFinding]
    blocking_findings: list[DecisionFinding]  # subset, severity in {blocks_ship, blocks_all}
    floor_failures: list["FloorFailure"]  # which floor rules failed, if any


Verdict = Ship | DontShip | Inconclusive
```

**Cascade catalog item (deferred to v1.0):** Add `_cohort_results_hash` to `FloorPassedProof` so `Ship.__post_init__` can verify the proof matches its cohort results. Prevents cross-run proof reuse. Closure-capture variant (`evaluate_floor` returned from a module-init factory, token closed over) is the harder version.

## CohortResult

Per-cohort stats. The artifact of cohort propagation.

```python
@dataclass(frozen=True, slots=True)
class FloorFailure:
    rule: str  # e.g., "min_replayed_per_required_cohort"
    observed: float | int | str
    threshold: float | int
    severity: Literal["blocks_ship", "blocks_all"]


@dataclass(frozen=True, slots=True)
class CohortResult:
    name: str  # "failure", "baseline", or future
    selected: int
    replayed: int
    scored: int
    # Per V0_1_DECISION_RECORD §2 the CI status is split: ci_computable is
    # the structural fact (was the bootstrap successful?), ci_meaningful
    # is the policy-quality assessment (is the width below max_ci_width?).
    # ci_unavailable_reason is populated when ci_computable=False.
    ci_computable: bool
    ci_unavailable_reason: Literal[
        "sample_too_small", "zero_variance", "computation_failed", None
    ]
    median_delta: DecimalString | None  # "0.310" not 0.31, see determinism notes
    ci_lower: DecimalString | None
    ci_upper: DecimalString | None
    floor_passed: bool
    floor_failures: list[FloorFailure]
    improved_count: int = 0
    unchanged_count: int = 0
    regressed_count: int = 0
    ci_meaningful: bool = True  # populated False by deferred policy guard
```

`DecimalString` is a `NewType` over `str` for fields that cross the determinism boundary. Float arithmetic happens internally; emission is via `format(value, '.3f')` which is platform-stable.

## RunManifest

The audit anchor.

```python
@dataclass(frozen=True, slots=True)
class EnvironmentFingerprint:
    python: str  # "3.12.3"
    platform: str  # "linux-x86_64"
    whatif_version: str
    dependencies: Mapping[str, str]  # {"whatifd-langfuse": "0.1.0", ...}


@dataclass(frozen=True, slots=True)
class SensitiveUnwrap:
    classification: str
    reason: str
    location: str  # call-site
    # No timestamp — this lives in non-deterministic runtime metadata


@dataclass(frozen=True, slots=True)
class RunManifest:
    experiment_id: str
    started_at: str  # ISO 8601, NON-DETERMINISTIC
    finished_at: str  # NON-DETERMINISTIC
    duration_ms: int  # NON-DETERMINISTIC
    whatif_version: str
    config_hash: str  # sha256 of resolved config
    selection_seed: int
    source: str  # "langfuse"
    target: str  # "python:my_agent.replay:run"
    trust_floor: TrustFloor
    decision_policy: DecisionPolicy
    environment: EnvironmentFingerprint
    agent_identity: Mapping[str, str] | None  # opt-in v0.1, required v1.0
    redaction: Mapping[str, str | bool]
    sensitive_unwraps: list[SensitiveUnwrap]  # NON-DETERMINISTIC ordering
```

The whole manifest is non-deterministic by default; the schema explicitly tags deterministic sub-fields (`trust_floor`, `decision_policy`, `selection_seed`, `config_hash`, `whatif_version`).

## ReportV01

The public report shape. Hand-written. Internal types project into this via explicit `project_to_report_v01()` functions.

```python
@dataclass(frozen=True, slots=True)
class ReportV01:
    schema_version: str = "0.1"
    schema_uri: str = "https://whatif.codes/schema/report/v0.1.json"

    # Deterministic fields
    verdict_state: Literal["ship", "dont_ship", "inconclusive"]
    cohort_results: list[CohortResult]
    failures: list[FailureRecord]
    decision_findings: list[DecisionFinding]
    cache_summary: CacheSummary
    trust_floor: TrustFloor
    decision_policy: DecisionPolicy
    methodology: MethodologyDisclosure  # required per cardinal #10

    # Non-deterministic fields, segregated
    runtime: RunManifest
```

Schema validation: `runtime` is annotated `x-deterministic: false`; the determinism CI test diffs only fields with `x-deterministic: true`.

## ArtifactBundle

The on-disk output. Profile-driven.

```python
class ProfileLevel(IntEnum):
    MINIMAL = 0
    REVIEW = 1
    AUDIT = 2
    FORENSIC = 3  # explicit two-affirmation opt-in


@dataclass(frozen=True, slots=True)
class ArtifactFile:
    name: str  # "report.json", "report.md", etc.
    sha256: str
    size_bytes: int
    profile_required: bool


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    directory: Path
    profile: ProfileLevel
    contents: list[ArtifactFile]


def expected_files_for(profile: ProfileLevel) -> list[ArtifactFileSpec]:
    """Single source of truth for profile→files mapping."""
    base = [REPORT_MD, REPORT_JSON, MANIFEST_JSON, HASHES_JSON]
    if profile >= ProfileLevel.REVIEW:
        base += [CACHE_SUMMARY_JSON, TRACE_SELECTION_JSON]
    if profile >= ProfileLevel.AUDIT:
        base += [CONFIG_RESOLVED_YAML, DEPENDENCIES_JSON]
    if profile == ProfileLevel.FORENSIC:
        base += [RAW_EVIDENCE_DIR]
    return base
```

The bundle constructor consumes `expected_files_for(profile)`. The test asserts the constructor's output matches what the function returns. Single source of truth.

## Sensitive[T] redaction wrapper

Adapters wrap user content at the boundary. Core's serializer refuses unwrapped sensitive values via pre-serialization graph walk.

```python
class Sensitive(Generic[T]):
    """Wrapper that defaults to redacted serialization.

    Any direct serialization (json, repr, str, format) produces a redacted form.
    Unwrapping requires explicit .unwrap(reason: str) which audit-logs.
    """
    __slots__ = ("_value", "classification")

    def __init__(self, value: T, classification: str):
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "classification", classification)

    def __repr__(self) -> str:
        return f"<Sensitive[{self.classification}] redacted>"

    def __str__(self) -> str:
        return self.__repr__()

    def __format__(self, format_spec: str) -> str:
        return self.__repr__()  # f-string formatting also redacts

    def __reduce__(self):
        raise SensitiveSerializationError(
            f"Cannot pickle Sensitive[{self.classification}]; unwrap with audit reason first"
        )

    def unwrap(self, *, reason: str, location: str | None = None) -> T:
        """Explicit unwrap. The reason argument is logged and persisted in manifest."""
        _audit_log.record(SensitiveUnwrap(
            classification=self.classification,
            reason=reason,
            location=location or _infer_caller(),
        ))
        return self._value
```

### Three layers of defense

1. **Type-level (mypy strict):** Adapters return `Sensitive[str]`; core types accept `Sensitive[str]` for sensitive fields. mypy catches misuse at type-check time.

2. **Pre-serialization graph walk:** Before any artifact is written, `assert_no_unredacted_sensitive(report)` walks the full object graph (dataclasses, dicts, lists, tuples) and raises on any `Sensitive` instance. Catches `dataclasses.asdict()` and similar paths that lose type info.

3. **Encoder fallback:** `WhatifJSONEncoder.default()` raises `UnredactedSensitiveError` if a `Sensitive` reaches it. This is the last line of defense.

### Audit becomes grep-able

The discipline inversion: instead of "audit every serialization path," audit becomes "grep for `.unwrap(`." Every unwrap is a reviewable call site with a logged reason. The audit set is closed instead of open.

### Banned-import lint rule

`json.dumps` is banned outside `whatifd/serialization/`. CI lint check enforces. Adapters that need JSON output must go through the whatifd serializer.

## What lives where (boundary summary)

| Concern | Location |
|---|---|
| User content | `Sensitive[T]` at adapter boundary, unwrap with reason |
| Vendor types (Langfuse spans, Inspect AI judgments) | Adapter only; never enter core |
| Operational events | `FailureRecord` |
| Policy conclusions | `DecisionFinding` |
| Stats per cohort | `CohortResult` |
| Floor evaluation | Returns `FloorPassedProof | FloorFailure` (sealed union) |
| Verdict construction | Only via `compute_verdict()` which produces `Ship | DontShip | Inconclusive` |
| Public schema | `ReportV01` hand-written, projection from internal types |
| On-disk output | `ArtifactBundle` driven by `expected_files_for(profile)` |
| Atomic statistical unit | `TraceDelta` (internal, floats) → `TraceDeltaReportV01` (public, DecimalString) |
| Statistical methodology | `MethodologyDisclosure` required in every `ReportV01` |
| Cluster bootstrap eligibility | `TraceSource.cluster_key_support()` declared by adapter |

## Statistical types (cardinal rule #10)

These types implement the statistical methodology described in `references/practices.md` § "Statistical methodology". The internal/public split mirrors the established pattern: `float` internally for arithmetic, `DecimalString` at the serialization boundary for cross-platform determinism.

### TraceDelta (internal, float)

Atomic unit of analysis. Pairing is structural — whatifd compares original and replayed behavior for the same trace input. Statistical analysis operates on `delta`, not on unpaired score arrays.

```python
@dataclass(frozen=True, slots=True)
class TraceDelta:
    trace_id: TraceId
    cohort: CohortId
    metric: MetricName

    original_score: float
    replayed_score: float
    delta: float  # = replayed_score - original_score, computed at construction

    # Optional fields supplied by tracer adapters.
    cluster_id: str | None = None
    strata: Mapping[str, str] = field(default_factory=dict)
```

The internal type stores both scores and the delta. This preserves auditability — you can inspect what produced any delta — but the analysis API consumes deltas, not separate score arrays. The discipline is "store both, expose the delta." Functions in `whatifd/internal/stats.py` accept `Sequence[TraceDelta]` and never accept `Sequence[float]` original + `Sequence[float]` replayed as a pair, which would invite accidental unpaired analysis.

### TraceDeltaReportV01 (public, DecimalString)

Public JSON representation. Numeric values serialized as decimal strings.

```python
@dataclass(frozen=True, slots=True)
class TraceDeltaReportV01:
    trace_id: TraceId
    cohort: CohortId
    metric: MetricName

    original_score: DecimalString
    replayed_score: DecimalString
    delta: DecimalString

    cluster_id: str | None = None
    strata: Mapping[str, str] = field(default_factory=dict)
```

### Methodology disclosure types

These types compose into `MethodologyDisclosure`, which is a required field on `ReportV01`. Schema validation enforces presence; required-field validation enforces content.

```python
@dataclass(frozen=True, slots=True)
class BootstrapMethodDisclosure:
    method: Literal[
        "paired_percentile_bootstrap",
        "cluster_paired_percentile_bootstrap",
        "unavailable",
    ]
    resamples: int | None
    seed: int | None
    sample_unit: Literal["paired_trace_delta"]
    ci_level: DecimalString  # e.g., "0.95"
    cluster_key: str | None
    assumptions: tuple[str, ...]  # e.g., ("trace_independence",) when no cluster
    unavailable_reason: str | None = None  # populated when method == "unavailable"


@dataclass(frozen=True, slots=True)
class MultiplicityDisclosure:
    primary_endpoint_count: int
    correction: Literal["none", "holm", "bonferroni", "bh_fdr"]
    reason: str  # e.g., "single primary metric per cohort; no correction applied"


@dataclass(frozen=True, slots=True)
class JudgeMethodDisclosure:
    scorer: str
    scorer_version: str | None
    judge_provider: str | None
    judge_model: str
    judge_model_version: str | None
    rendered_prompt_hash: str
    rubric_hash: str | None

    scorer_cache_enabled: bool
    scorer_cache_mode: Literal["off", "on", "read_only", "refresh", "auto"]
    scorer_cache_hits: int
    scorer_cache_misses: int

    # The five reliability concepts. v0.1 default: only reproducibility addressed.
    reproducibility_addressed: bool
    reliability_measured: bool
    validity_measured: bool
    calibration_measured: bool
    bias_audit_measured: bool


@dataclass(frozen=True, slots=True)
class EffectSizeDisclosure:
    practical_delta: DecimalString  # epsilon, the magnitude threshold
    practical_delta_source: Literal[
        "policy",                              # user-configured
        "calibrated_from_judge_noise_floor",   # measured against calibration set
        "unknown",                             # default; not empirically calibrated
    ]
    judge_noise_floor: DecimalString | None
    warning: str | None = None  # e.g., "epsilon < judge_noise_floor"


@dataclass(frozen=True, slots=True)
class MethodologyDisclosure:
    """Required in every ReportV01. Tells reviewers what claims the report
    is allowed to make."""

    unit_of_analysis: Literal["paired_trace_delta"]
    primary_metric: MetricName
    primary_endpoints: tuple[str, ...]
    cohorts: tuple[CohortId, ...]

    bootstrap: BootstrapMethodDisclosure
    multiplicity: MultiplicityDisclosure
    judge: JudgeMethodDisclosure
    effect_size: EffectSizeDisclosure

    per_trace_inference: Literal["descriptive_only"]
    causal_claim_scope: Literal["associated_under_cached_tool_replay"]

    limitations: tuple[str, ...]  # known caveats; rendered into report
```

The `per_trace_inference` and `causal_claim_scope` fields are sealed literals because v0.1 has only one allowed value for each. v0.2+ may extend these, which would be a minor schema bump.

### Clustering types

The cluster bootstrap eligibility chain: tracer adapter declares what cluster keys it can supply; user policy expresses preference; resolver picks the actual key used; result is recorded in manifest and methodology block.

```python
@dataclass(frozen=True, slots=True)
class ClusterKeySupport:
    """Declared by TraceSource.cluster_key_support(). Describes which real
    clustering keys this tracer adapter can supply. whatifd must not fabricate
    cluster keys for confirmatory verdicts in v0.1."""
    available_keys: tuple[str, ...]
    preferred_order: tuple[str, ...] = (
        "conversation_id",
        "session_id",
        "user_id",
    )


@dataclass(frozen=True, slots=True)
class ClusterSelection:
    mode: Literal["none", "selected", "unavailable"]
    key: str | None
    reason: str  # explanation rendered into the methodology block


@dataclass(frozen=True, slots=True)
class ClusteringPolicy:
    cluster_key: Literal[
        "none",       # explicit i.i.d. assumption
        "auto",       # use most granular available
        "user_id",
        "session_id",
        "conversation_id",
    ] = "auto"

    fallback_behavior: Literal[
        "assume_independent",  # silent fallback (NOT recommended; warns by default)
        "warn",                # default; report discloses i.i.d. assumption
        "refuse",              # block Ship if no cluster key available
    ] = "warn"
```

### Resolution function

The resolver lives in `whatifd/decision/clustering.py`:

```python
def resolve_cluster_key(
    source: TraceSource,
    policy: ClusteringPolicy,
) -> ClusterSelection:
    """Resolve the cluster key for uncertainty estimation.

    Rules:
    - If policy.cluster_key == "none", use no clustering.
    - If a specific key is requested, use it only if the adapter supports it.
    - If policy.cluster_key == "auto", use the most granular available key.
    - If no key is available, follow fallback_behavior.

    The resolved choice MUST be recorded in the run manifest and the
    methodology block of the report.
    """
    ...
```

### What this enables in the report

A reader of the methodology block can answer:

- What was the unit of analysis? (`unit_of_analysis: paired_trace_delta`)
- What primary endpoints drove the verdict? (`primary_endpoints`)
- How was uncertainty estimated? (`bootstrap.method, resamples, seed`)
- Were correlations between traces accounted for? (`bootstrap.cluster_key`)
- Was the judge consistent across runs? (`judge.scorer_cache_enabled` — note: cache addresses reproducibility, not reliability)
- Has the judge been validated against ground truth? (`judge.validity_measured` — v0.1 default: false)
- What magnitude threshold was used? (`effect_size.practical_delta`)
- Has that threshold been calibrated empirically? (`effect_size.practical_delta_source` — v0.1 default: "unknown")
- What multiplicity correction was applied? (`multiplicity.correction` — v0.1 default: "none" with reason)
- What's the maximum claim the report is allowed to make? (`causal_claim_scope: associated_under_cached_tool_replay`)

If a reviewer cannot answer these from the methodology block alone, the disclosure is incomplete. Schema validation catches the structural cases; renderer tests catch the rendering cases.
