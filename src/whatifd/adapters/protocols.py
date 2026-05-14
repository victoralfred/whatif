"""Adapter protocols + result types.

Phase 4A.1. Two `Protocol`s — `TraceSource` and `Scorer` — and the
small data classes they exchange with core. No implementation.

## Why Protocol, not ABC

Adapter packages are external (`whatifd-langfuse`, `whatifd-inspect-ai`)
and may want to implement the protocol via a callable, a class, or
a module-level shim. `runtime_checkable` Protocol matches the
existing `whatifd.contract.Runner` pattern and gives us `isinstance`
checks at the boundary without forcing inheritance.

## Cardinal alignment

- **#1 failures-as-data:** the protocols don't raise for typed
  adapter problems — failures surface as `RawTrace.skip_reason` or
  `JudgeResult.score is None`. Genuine boundary errors (network
  outage mid-stream, unparseable response) propagate as exceptions
  that the replay/score pipeline converts into `FailureRecord` /
  `ReplayFailure` per cardinal #1.
- **#5 Sensitive[T] at the boundary:** every text field that
  carries user content (`RawTrace.user_message`,
  `RawTrace.original_response`, `JudgeResult.rationale`) is typed
  `Sensitive[str]`. The conformance harness (Phase 4A.2) and
  graph-walk (`whatifd.serialization.graph_walk`) enforce this at
  test and serialization boundaries.
- **#6 typed boundaries:** result types are Pydantic models with
  `extra="forbid"` so an adapter can't smuggle a free-form dict
  into the report shape.
- **#10 statistical claims:** `TraceSource.cluster_key_support()`
  is mandatory — the methodology disclosure depends on knowing
  whether the adapter can supply cluster keys.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from whatifd.adapters.pii import PII_ATTRIBUTE_KEYS
from whatifd.cache.keying.v1 import CacheKeyComponents
from whatifd.contract import ScoreCase
from whatifd.types.sensitive import Sensitive
from whatifd.types.statistical import ClusterKeySupport


@dataclass(frozen=True, slots=True)
class AdapterMetadata:
    """Adapter identity surfaced into `RunManifest` and the report's
    methodology disclosure.

    `adapter_id` is the short string used by the loader (e.g.,
    `"langfuse"`, `"inspect_ai"`, `"stub"`); `package_version` is
    the adapter package's own version string (PEP 440); `sdk_version`
    is the upstream SDK version (Langfuse / Inspect AI), `None` if
    the adapter doesn't wrap a third-party SDK.

    Frozen + slotted to match the rest of the type system (cardinal
    #6); these values are recorded once per run and never mutated.
    """

    adapter_id: str
    package_version: str
    sdk_version: str | None = None


class RawTrace(BaseModel):
    """One trace as the adapter sees it, before projection into
    `whatifd.contract.TraceInput`.

    The adapter is responsible for:
      1. Wrapping `user_message` and `original_response` as
         `Sensitive[str]` (cardinal #5).
      2. Setting `cluster_key` when the source can supply one
         (per `cluster_key_support()` declaration).
      3. Setting `skip_reason` to a non-None string when the trace
         is structurally unusable (e.g., no user message, malformed
         tool span). Skipped traces still flow through so the
         pipeline records the skip in `FailureRecord`s rather than
         silently dropping rows (cardinal #1).
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    trace_id: str = Field(..., description="Stable identifier from the source backend.")
    cohort: str = Field(
        ...,
        description=(
            "Cohort label assigned by the source-side selection rule. v0.1 "
            'expects `"failure"` or `"baseline"`; the schema deliberately '
            "leaves this `str` so future cohort families don't break adapters."
        ),
    )
    user_message: Sensitive[str] = Field(
        ..., description="The original user input. Wrapped at the adapter boundary."
    )
    original_response: Sensitive[str] = Field(
        ..., description="The original agent response. Wrapped at the adapter boundary."
    )
    # `tool_spans` and `metadata` are typed `dict[str, Any]` to
    # mirror `whatifd.contract.TraceInput.metadata` /
    # `ReplayOutput.tool_spans` exactly — the adapter projection
    # produces the contract types unchanged. Cardinal #6 in this
    # project ("public schema hand-written; internal types refactor
    # freely") governs the public report schema (`ReportV01`), not
    # the adapter→core internal boundary. Tightening to a typed
    # `ToolSpan` here without lifting the contract would diverge
    # the two shapes; revisit when the runner contract grows a
    # typed span (currently tracked as a v0.2 cascade).
    tool_spans: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-tool spans recorded in the original trace.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form trace metadata pulled from the source tracer. "
            "Values at keys in `whatifd.adapters.PII_ATTRIBUTE_KEYS` "
            "MUST be `Sensitive[str]` or `None`; the model validator "
            "enforces this at construction time. Use "
            "`whatifd.adapters.wrap_pii_attributes(...)` to wrap the "
            "raw dict at the adapter boundary — that's the typical "
            "happy path. Cardinal #5."
        ),
    )
    cluster_key: str | None = Field(
        default=None,
        description=(
            "Cluster key for stratified bootstrap (cardinal #10). "
            "`None` when the source has no cluster signal or the adapter "
            "declares `cluster_key_support().supported is False`."
        ),
    )
    skip_reason: str | None = Field(
        default=None,
        description=(
            "Non-None when the trace is structurally unusable. Surfaces in "
            "`FailureRecord` rather than silently dropping the row."
        ),
    )

    @model_validator(mode="after")
    def _enforce_pii_attribute_wrapping(self) -> RawTrace:
        """Boundary enforcement for cardinal #5 (PII at known-PII
        attribute keys must be wrapped).

        For each key in `PII_ATTRIBUTE_KEYS` that appears in
        `metadata`, the value must be `Sensitive[str]` or `None`. A
        raw `str` (or any other type) at a registered PII key fails
        validation at construction — *before* the trace flows
        through the replay / scoring / serialization pipeline.

        Per `references/enforcement.md`'s hierarchy of strength,
        this is layer (a) of the cardinal-#5 chain: type-level
        prevention via the Pydantic boundary check. Pre-serialization
        graph-walk (`assert_no_unredacted_sensitive`) is layer (b);
        the JSON encoder fallback is layer (c). Catching at layer
        (a) means an adapter author who forgets to call
        `wrap_pii_attributes` sees the failure at the first
        `RawTrace(...)` construction in their integration test,
        not after a full pipeline run.

        The validator is mode='after' so it sees the post-coercion
        dict (Pydantic has already validated the outer
        `dict[str, Any]` shape). It does NOT walk nested values
        under non-PII keys — those are legitimately free-form
        tooling state per the docstring on `metadata`.
        """
        for key, value in self.metadata.items():
            if key not in PII_ATTRIBUTE_KEYS:
                continue
            if value is None or isinstance(value, Sensitive):
                continue
            raise ValueError(
                f"RawTrace.metadata key {key!r} is registered as PII "
                f"(`whatifd.adapters.PII_ATTRIBUTE_KEYS`) but the value "
                f"is unwrapped ({type(value).__name__}). Cardinal #5: "
                "PII-bearing attributes must be wrapped as "
                "`Sensitive[str]` at the adapter boundary. Call "
                "`whatifd.adapters.wrap_pii_attributes(raw_dict)` in "
                "your adapter's projection step instead of passing "
                "the dict through unchanged."
            )
        return self


class JudgeResult(BaseModel):
    """One scorer output. Projected from `ScoreCase` by `Scorer.score`.

    `score` is a real-valued judgment in the scorer's native scale;
    the decision pipeline converts to a paired `TraceDelta` via the
    statistical types. `score is None` indicates a structural scoring
    failure (e.g., judge returned malformed output) — the pipeline
    surfaces it as a `FailureRecord` rather than substituting a
    neutral value.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    trace_id: str = Field(..., description="Trace this score applies to.")
    score: float | None = Field(
        ...,
        description=(
            "Native-scale score, or `None` to signal structural scoring "
            "failure (cardinal #1; surfaces as FailureRecord, not a "
            "substituted value)."
        ),
    )
    rationale: Sensitive[str] = Field(
        ...,
        description="Judge rationale. Wrapped at the adapter boundary (cardinal #5).",
    )
    judge_model_id: str = Field(
        ..., description="Provider model identifier (e.g., `claude-opus-4-7`)."
    )
    judge_model_snapshot: str | None = Field(
        default=None,
        description=(
            "Provider snapshot/version pin if the provider exposes one. "
            "`None` if absent — adapters MUST pass `None` explicitly so "
            "the cache-key field shape is constant."
        ),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form per-score metadata (token counts, latency, etc.).",
    )


@runtime_checkable
class TraceSource(Protocol):
    """Protocol for trace-source adapters.

    Concrete implementations live in separate packages
    (`whatifd-langfuse`, `whatifd/adapters/stub.py`). The conformance
    harness (Phase 4A.2) parameterizes over the protocol and is the
    single source of truth for "what makes a trace source valid".

    TODO(Phase 4A.2): `runtime_checkable` `isinstance(...)` only
    verifies attribute presence — it does NOT catch signature drift
    (wrong argument counts, swapped return types, etc.). The
    conformance harness at `tests/adapters/test_conformance.py`
    invokes each method with realistic inputs and asserts return
    shapes, which IS the gate for signature drift. New contributors
    extending this protocol should add a matching conformance case
    in the same PR.
    """

    def iter_traces(self) -> Iterator[RawTrace]:
        """Stream traces. MUST be a generator/iterator — Phase 4
        explicitly forbids returning a list to keep memory bounded
        for large backfills."""
        ...

    def adapter_metadata(self) -> AdapterMetadata:
        """Identity surfaced into `RunManifest`."""
        ...

    def cluster_key_support(self) -> ClusterKeySupport:
        """Declare whether this source can supply cluster keys
        (cardinal #10). Drives `MethodologyDisclosure.bootstrap.cluster_key`
        — a source that returns `supported=False` forces the
        clustering policy to fall back to per-trace bootstrap with
        the appropriate disclosure."""
        ...


@runtime_checkable
class Scorer(Protocol):
    """Protocol for scorer adapters.

    Implementations consume `ScoreCase` (constructed by `whatifd`
    core from a `RawTrace` projection plus the user runner's
    `ReplayOutput`) and produce `JudgeResult`. Cache-key components
    flow through `cache_key_components()` so the cache subsystem
    can hash them deterministically without ever seeing raw judge
    prompts (cardinal #5: hashes pre-computed at the boundary).

    TODO(Phase 4A.2): same caveat as `TraceSource` — isinstance only
    checks attribute presence; signature drift is caught by the
    conformance harness at `tests/adapters/test_conformance.py`.
    """

    def score(self, case: ScoreCase) -> JudgeResult:
        """Run the judge. Adapters wrap any free-text outputs in
        `Sensitive[str]` before construction."""
        ...

    def cache_key_components(self, case: ScoreCase) -> CacheKeyComponents:
        """Return the full set of components for cache keying.
        Hash fields MUST be pre-hashed (the `CacheKeyComponents`
        `__post_init__` validates hex-digest shape — raw text fails
        construction)."""
        ...

    def adapter_metadata(self) -> AdapterMetadata:
        """Identity surfaced into `RunManifest`."""
        ...
