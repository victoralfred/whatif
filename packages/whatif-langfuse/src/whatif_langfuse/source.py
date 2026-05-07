"""`LangfuseTraceSource` — implementation of `whatif.adapters.TraceSource`.

Constructor takes a Langfuse API client (typed via `Protocol` so
tests can substitute a mock without pulling the langfuse module);
`iter_traces` paginates through `api.trace.list(...)` and projects
each `Trace` into a `RawTrace` with content fields wrapped as
`Sensitive[str]`. The runtime contract follows
`whatif.adapters.protocols.TraceSource`; the conformance harness
at `tests/adapters/conformance.py` is the gating test.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from whatif.adapters.protocols import (
    AdapterMetadata,
    RawTrace,
)
from whatif.serialization.canonical import canonical_json_bytes
from whatif.types.sensitive import Sensitive
from whatif.types.statistical import ClusterKeySupport

ADAPTER_ID = "langfuse"


@runtime_checkable
class _TraceLike(Protocol):
    """Structural shape this adapter needs from a Langfuse `Trace`.

    Defined as a Protocol so tests can hand a mock object without
    importing langfuse, AND so any future Langfuse SDK that renames
    or restructures fields can be adapted with a small wrapper
    rather than a rewrite. Mirrors the field set the Langfuse v4
    `Trace` model exposes (`langfuse.api.commons.types.trace.Trace`).
    """

    id: str
    input: Any
    output: Any
    metadata: Any
    tags: Any
    user_id: Any
    session_id: Any


@runtime_checkable
class _TracesResponseLike(Protocol):
    data: list[Any]


@runtime_checkable
class _TraceClientLike(Protocol):
    def list(
        self,
        *,
        page: int | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> _TracesResponseLike: ...


@runtime_checkable
class _LangfuseAPILike(Protocol):
    trace: _TraceClientLike


def _stringify(value: Any) -> str:
    """Project a Langfuse `input` / `output` field (typed Any —
    str | dict | list | None per the SDK) into a canonical string.

    `None` and empty values render as the empty string so downstream
    `Sensitive[str]` wrapping always succeeds with a real `str`
    value. Dicts/lists round-trip through `canonical_json_bytes` so
    the same trace always projects to the same string (cardinal #4
    determinism for the projection step; determinism beyond that is
    the report layer's responsibility).

    Routes through `whatif.serialization.canonical.canonical_json_bytes`
    rather than calling `json.dumps` directly. The project's banned-
    import discipline keeps `json.dumps` inside `whatif/serialization/`
    so all canonical encoding goes through a single review surface
    (one layer of cardinal #5's three-layer defense — the encoder
    rejects unwrapped `Sensitive[T]` values).
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # `canonical_json_bytes` returns ASCII bytes; decode to str for
    # the `Sensitive[str]` wrap downstream. The encoding is stable
    # across platforms (sort_keys=True + ensure_ascii=True per the
    # canonical helper). Explicit `str(...)` so mypy knows the
    # decoded value matches the declared return type without
    # leaking `Any` from the canonical helper's signature.
    decoded: str = canonical_json_bytes(value).decode("ascii")
    return decoded


@dataclass(frozen=True, slots=True)
class LangfuseTraceSource:
    """Langfuse `TraceSource` adapter.

    Construct with a `LangfuseAPI`-shaped client (anything matching
    the `_LangfuseAPILike` Protocol — typically
    `langfuse.api.LangfuseAPI`) plus a `cohort_classifier` callback
    that maps a Langfuse `Trace` to a cohort name (`"failure"` or
    `"baseline"` for v0.1's failure-rescue scope).

    `page_limit` controls the per-page Langfuse fetch; the iterator
    keeps calling `api.trace.list(page=N, limit=page_limit)` until
    a page returns fewer rows than `page_limit` (the standard
    "exhausted" signal in Langfuse's pagination shape). `max_traces`
    caps the total iteration so a fixture run can't accidentally
    drain a production project.
    """

    api: _LangfuseAPILike
    cohort_classifier: Callable[[_TraceLike], str]
    page_limit: int = 50
    max_traces: int | None = None
    list_kwargs: dict[str, Any] = field(default_factory=dict)
    sdk_version: str | None = None

    def iter_traces(self) -> Iterator[RawTrace]:
        emitted = 0
        page = 1
        while True:
            response = self.api.trace.list(
                page=page,
                limit=self.page_limit,
                **self.list_kwargs,
            )
            page_data = list(response.data)
            for trace in page_data:
                if self.max_traces is not None and emitted >= self.max_traces:
                    return
                yield self._project(trace)
                emitted += 1
            if len(page_data) < self.page_limit:
                return
            page += 1

    def adapter_metadata(self) -> AdapterMetadata:
        from whatif_langfuse import __version__ as package_version

        return AdapterMetadata(
            adapter_id=ADAPTER_ID,
            package_version=package_version,
            sdk_version=self.sdk_version or _resolve_sdk_version(),
        )

    def cluster_key_support(self) -> ClusterKeySupport:
        # v0.1: empty. Langfuse traces carry `user_id` and
        # `session_id`, but using either as a cluster key would be
        # an unannounced inferential commitment (cardinal #10
        # forbids fabricating cluster keys for confirmatory
        # verdicts). v0.2+ surfaces explicit per-field opt-in via
        # `LangfuseTraceSource(cluster_keys=("session_id",))` or
        # similar; for now the source declares no clusters and the
        # methodology disclosure reflects that honestly.
        return ClusterKeySupport(available_keys=())

    def _project(self, trace: _TraceLike) -> RawTrace:
        return RawTrace(
            trace_id=trace.id,
            cohort=self.cohort_classifier(trace),
            user_message=Sensitive(_stringify(trace.input), classification="user_content"),
            original_response=Sensitive(_stringify(trace.output), classification="user_content"),
            metadata=dict(trace.metadata or {}),
        )


def _resolve_sdk_version() -> str | None:
    """Read `langfuse.__version__` lazily so importing this module
    doesn't drag the Langfuse SDK in until it's actually needed
    (e.g., a test that constructs `LangfuseTraceSource` with a
    mock client never imports langfuse). Returns None if the SDK
    isn't installed — the resulting `AdapterMetadata.sdk_version`
    is None, which the manifest accepts."""
    try:
        import langfuse

        return getattr(langfuse, "__version__", None)
    except ImportError:
        return None
