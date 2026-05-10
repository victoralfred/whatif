"""`PhoenixTraceSource` — implementation of `whatifd.adapters.TraceSource`.

Constructor takes a `spans_provider` callable returning an iterable
of OpenInference-shaped span dicts; `iter_traces` groups spans by
`context.trace_id` and projects each trace into a `RawTrace` with
content fields wrapped as `Sensitive[str]`. The runtime contract
follows `whatifd.adapters.protocols.TraceSource`; the conformance
harness at `tests/adapters/conformance.py` is the gating test.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from whatifd.adapters.protocols import (
    AdapterMetadata,
    RawTrace,
)
from whatifd.serialization.canonical import canonical_json_bytes
from whatifd.types.sensitive import Sensitive
from whatifd.types.statistical import ClusterKeySupport

_log = logging.getLogger(__name__)

ADAPTER_ID = "phoenix"

# OpenInference attribute keys this adapter reads. Defined as
# constants so a future OpenInference-spec revision (e.g.,
# `input.value` → `llm.input_messages`) lands in one place rather
# than scattered through projection logic. See
# https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md
_ATTR_INPUT = "input.value"
_ATTR_OUTPUT = "output.value"
_ATTR_TRACE_ID = "context.trace_id"
_ATTR_PARENT_ID = "parent_id"
_ATTR_SPAN_KIND = "openinference.span.kind"
# Root-span kind fallback. CHAIN and AGENT are top-level orchestration
# kinds; a span with no parent_id and one of these kinds is the trace
# root by OpenInference convention.
#
# LLM is INTENTIONALLY EXCLUDED here (it was in an earlier draft).
# Direct LLM-call spans without a recorded parent_id can occur in
# OpenInference traces produced by less-instrumented libraries; if
# the LLM-kind were a root signal, a child LLM call with a missing
# parent_id would be misidentified as the trace root and `_project`
# would surface the LLM call's prompt as the trace's
# `user_message` — a silent wrong result, not a structured failure
# (cardinal #1). The narrower set is correct: only orchestration-
# kind spans without a parent are roots.
_ROOT_SPAN_KINDS = frozenset({"CHAIN", "AGENT"})


def _stringify(value: object) -> str:
    """Project an OpenInference attribute value into a canonical string.

    Phoenix attributes are typed Any in practice — string is the
    common case (Phoenix renders dict/list payloads as JSON before
    storing), but tool-call outputs and structured response payloads
    occasionally arrive as raw dicts/lists. Using `str(value)` on
    those produces Python-repr garbage (`"{'k': 'v'}"`); routing
    through `whatifd.serialization.canonical.canonical_json_bytes`
    produces stable JSON instead. None and empty values render as
    the empty string so downstream `Sensitive[str]` wrapping always
    succeeds with a real `str` value.

    Mirrors `whatifd_langfuse.source._stringify` exactly — both
    adapters route non-string values through the canonical encoder
    so any downstream rendering of `metadata` (which may include
    pre-stringified attribute values) sees byte-stable JSON, not
    repr output.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    decoded: str = canonical_json_bytes(value).decode("ascii")
    return decoded


def _wrap_user_content_in_span(span: dict[str, object]) -> dict[str, object]:
    """Return a shallow copy of `span` with `input.value` and
    `output.value` wrapped as `Sensitive[str]`.

    Cardinal #5 boundary: any span attribute that may carry user
    content is wrapped at adapter ingress so the classifier callable
    (and any other downstream consumer of the span list) sees a
    `Sensitive[str]` rather than a raw user-content string. Other
    attributes pass through unchanged because they carry tooling
    state (model names, latencies, span kinds), not user content.

    Original spans are NOT mutated — the caller may reuse them.
    """
    if _ATTR_INPUT not in span and _ATTR_OUTPUT not in span:
        return span
    wrapped: dict[str, object] = dict(span)
    if _ATTR_INPUT in wrapped:
        wrapped[_ATTR_INPUT] = Sensitive(
            _stringify(wrapped[_ATTR_INPUT]),
            classification="user_content",
        )
    if _ATTR_OUTPUT in wrapped:
        wrapped[_ATTR_OUTPUT] = Sensitive(
            _stringify(wrapped[_ATTR_OUTPUT]),
            classification="user_content",
        )
    return wrapped


def _is_root_span(span: dict[str, object]) -> bool:
    """Identify the root span of a trace.

    OpenInference root spans either (a) have no `parent_id` or
    (b) carry an `openinference.span.kind` of `CHAIN` / `AGENT` at
    the top level. The adapter prefers (a) for correctness — a
    trace's root span is structurally the one with no parent — and
    falls back to (b) for malformed traces where the parent_id was
    dropped upstream. **`LLM` is intentionally excluded from the
    fallback set**: a child LLM-call span with a missing parent_id
    would otherwise be misidentified as the trace root and surface
    its prompt as the user's question. See
    `TestRootIdentificationCorrectness` and the comment on
    `_ROOT_SPAN_KINDS` for the full rationale.
    """
    if span.get(_ATTR_PARENT_ID) in (None, ""):
        return True
    kind = span.get(_ATTR_SPAN_KIND)
    return kind in _ROOT_SPAN_KINDS


@dataclass(frozen=True, slots=True)
class PhoenixTraceSource:
    """Phoenix / OpenInference `TraceSource` adapter.

    Construct with:

    - `spans_provider`: a zero-argument callable returning an iterable
      of span dicts. Each span dict is OpenInference-shaped — `context.trace_id`
      identifies the trace, `parent_id` builds the tree, and
      `input.value` / `output.value` carry user content. Callers wire
      this from their Phoenix client (`Client.query_spans(...).to_dict()`)
      or any OTLP collector emitting OpenInference attributes.
    - `cohort_classifier`: a callable mapping the span list of a single
      trace to a cohort name (`"failure"` / `"baseline"` for
      failure-rescue scope; `"baseline"` only for regression-check).
      Receives the full span list so classifiers can read non-root
      attributes (e.g., a tag set on a tool span).
    - `max_traces`: optional cap on the total iteration; matches the
      `LangfuseTraceSource.max_traces` behavior. None means unbounded.
    - `sdk_version`: optional override for the `arize-phoenix-client`
      version string. None = best-effort detection via
      `_resolve_sdk_version`.
    """

    spans_provider: Callable[[], Iterable[dict[str, object]]]
    cohort_classifier: Callable[[list[dict[str, object]]], str]
    max_traces: int | None = None
    sdk_version: str | None = None

    def iter_traces(self) -> Iterator[RawTrace]:
        spans_by_trace: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
        for span in self.spans_provider():
            trace_id = span.get(_ATTR_TRACE_ID)
            if not isinstance(trace_id, str) or not trace_id:
                _log.debug(
                    "PhoenixTraceSource: span missing %s; skipping. span=%r",
                    _ATTR_TRACE_ID,
                    {k: v for k, v in span.items() if k != _ATTR_INPUT},
                )
                continue
            # Cardinal #5: pre-wrap input.value / output.value on
            # EVERY span (not just the root) before the classifier
            # sees them. The classifier receives the full span list
            # — child spans may carry user content in their own
            # input.value / output.value (e.g., a sub-agent call's
            # prompt). Wrapping at ingress means the classifier
            # cannot accidentally exfiltrate user content via plain
            # dict-key access; an operator who genuinely needs to
            # read those values must call .unwrap(reason=...) and
            # an audit record is generated.
            spans_by_trace[trace_id].append(_wrap_user_content_in_span(span))

        for emitted, (trace_id, spans) in enumerate(spans_by_trace.items()):
            if self.max_traces is not None and emitted >= self.max_traces:
                return
            yield self._project(trace_id, spans)

    def adapter_metadata(self) -> AdapterMetadata:
        from whatifd_phoenix import __version__ as package_version

        return AdapterMetadata(
            adapter_id=ADAPTER_ID,
            package_version=package_version,
            sdk_version=self.sdk_version or _resolve_sdk_version(),
        )

    def cluster_key_support(self) -> ClusterKeySupport:
        # v0.2: empty. OpenInference spans carry `user.id` and
        # `session.id` attributes when set, but using either as a
        # cluster key would be an unannounced inferential commitment
        # (cardinal #10 forbids fabricating cluster keys for
        # confirmatory verdicts). v0.3+ surfaces explicit per-attribute
        # opt-in via `PhoenixTraceSource(cluster_attributes=("user.id",))`
        # or similar; for now the source declares no clusters and the
        # methodology disclosure reflects that honestly.
        return ClusterKeySupport(available_keys=())

    def _project(self, trace_id: str, spans: list[dict[str, object]]) -> RawTrace:
        # Defensive: an empty `spans` list is structurally impossible
        # under the current iter_traces (a span is only added to
        # spans_by_trace if it has a valid trace_id; no trace_id =>
        # no entry => _project not called). Cardinal #1 belt-and-
        # suspenders for a future refactor that decouples grouping
        # from projection.
        if not spans:
            return RawTrace(
                trace_id=trace_id,
                cohort=self.cohort_classifier(spans),
                user_message=Sensitive("", classification="user_content"),
                original_response=Sensitive("", classification="user_content"),
                metadata={},
            )

        # Find the root span via the unified `_is_root_span` helper.
        # `_is_root_span` returns True for parent-less spans first
        # and falls back to OpenInference span-kind. A previous
        # version inlined the parent_id check here, drifting from
        # _is_root_span; the two now share a single source of truth.
        roots = [s for s in spans if _is_root_span(s)]
        root = roots[0] if roots else spans[0]

        # `input.value` / `output.value` arrived pre-wrapped as
        # Sensitive[str] from `_wrap_user_content_in_span` (cardinal
        # #5 ingress boundary). Re-bind to the typed slots on
        # RawTrace; fall back to an empty Sensitive[""] if the root
        # span lacks them (downstream guards surface that as a
        # structured failure).
        wrapped_input = root.get(_ATTR_INPUT)
        wrapped_output = root.get(_ATTR_OUTPUT)
        user_message = (
            wrapped_input
            if isinstance(wrapped_input, Sensitive)
            else Sensitive(_stringify(wrapped_input), classification="user_content")
        )
        original_response = (
            wrapped_output
            if isinstance(wrapped_output, Sensitive)
            else Sensitive(_stringify(wrapped_output), classification="user_content")
        )
        return RawTrace(
            trace_id=trace_id,
            cohort=self.cohort_classifier(spans),
            user_message=user_message,
            original_response=original_response,
            metadata={k: v for k, v in root.items() if k not in (_ATTR_INPUT, _ATTR_OUTPUT)},
        )


def _resolve_sdk_version() -> str | None:
    """Read `arize_phoenix_client.__version__` lazily so importing
    this module doesn't drag the Phoenix SDK in until it's actually
    needed. Returns None if the SDK isn't installed — the resulting
    `AdapterMetadata.sdk_version` is None, which the manifest accepts.
    """
    try:
        import arize_phoenix_client  # type: ignore[import-not-found]

        version = getattr(arize_phoenix_client, "__version__", None)
        if version is None:
            _log.debug(
                "arize-phoenix-client imported but exposes no __version__; "
                "AdapterMetadata.sdk_version will be None"
            )
        sdk_version: str | None = version
        return sdk_version
    except ImportError:
        _log.debug(
            "arize-phoenix-client not installed; AdapterMetadata.sdk_version "
            "will be None. Install via `pip install whatifd-phoenix[live]` "
            "or directly with `pip install arize-phoenix-client`."
        )
        return None
