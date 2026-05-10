# whatifd-phoenix

Arize Phoenix / OpenInference `TraceSource` adapter for `whatifd`.

Phase D of the v0.2 plan. Implements `whatifd.adapters.TraceSource`
against an OpenInference span-iterator surface — Phoenix's native
span shape — so callers can wire any Phoenix client variant (or any
OpenInference-emitting tracer) without the adapter pinning a specific
Phoenix SDK version.

## Install

```bash
uv pip install whatifd-phoenix              # adapter only
uv pip install whatifd-phoenix[live]        # + arize-phoenix-client
```

The base install gives you the Protocol surface; the `[live]` extra
pulls `arize-phoenix-client` for live integration. The adapter is
API-agnostic beyond the span-iterator shape, so you can use any
Phoenix client variant by writing a small `spans_provider` adapter.

## Usage

```python
from arize.phoenix.client import Client
from whatifd_phoenix import PhoenixTraceSource

client = Client(endpoint="http://localhost:6006")

def spans_provider():
    # Cardinal #9 (orchestration, not compute) note: avoid
    # `df.iterrows()` — it's pandas-backed row iteration that pulls
    # NumPy buffers per row. Prefer the streaming form below
    # (`itertuples` returns lightweight named tuples) or, better,
    # iterate a list-of-dicts response directly if your Phoenix
    # client surface offers one.
    spans = client.query_spans(query=...).to_dict(orient="records")
    yield from spans

def classify(spans):
    # Cohort classification has access to ALL spans of a trace
    # (root + children), so a tag set on a tool span is reachable.
    if any(s.get("attributes.tag.failed") for s in spans):
        return "failure"
    return "baseline"

source = PhoenixTraceSource(
    spans_provider=spans_provider,
    cohort_classifier=classify,
    max_traces=40,
)

for raw in source.iter_traces():
    print(raw.trace_id, raw.cohort)
```

## Why span-iterator-shaped (not Phoenix-Client-shaped)

Phoenix's Python client API has shifted across versions
(`arize-phoenix` → `arize-phoenix-client`; methods on `Client` have
churned between major versions). Pinning a specific Client shape in
this adapter would force a sync-with-Phoenix-release cycle on every
Phoenix major bump.

The span-iterator shape is the stable API:
[OpenInference](https://github.com/Arize-ai/openinference) span
attributes are an open standard, and downstream consumers (Phoenix,
but also custom OTLP collectors) emit this shape. Wiring is a
~5-line `spans_provider` callable that you control.

## OpenInference attributes the adapter reads

| Attribute | Used for |
|---|---|
| `context.trace_id` | Grouping spans into traces. Required. |
| `parent_id` | Identifying the root span (parent-less). |
| `openinference.span.kind` | Fallback root identification. |
| `input.value` | Wrapped as `Sensitive[str]` → `RawTrace.user_message`. |
| `output.value` | Wrapped as `Sensitive[str]` → `RawTrace.original_response`. |
| All other attributes | Pass through to `RawTrace.metadata` (NOT wrapped). |

Spans without `context.trace_id` are silently dropped (logged at
DEBUG level). Other malformed spans are best-effort: missing input
or output values render as empty `Sensitive[""]`, which downstream
guards surface as a structured failure rather than crashing the run.

## Cardinal alignment

- **#5 Sensitive[T] at the boundary:** `input.value` and `output.value`
  are wrapped. Other attributes pass through unwrapped because they
  carry tooling state (model name, latency, tool calls), not user
  content. The conformance test pins this contract.
- **#9 orchestration, not compute:** no DataFrames, no NumPy in the
  hot path. Spans arrive as dicts; the adapter groups by trace_id
  and emits.
- **#10 statistical claims:** `cluster_key_support` returns an empty
  `available_keys` tuple. v0.2 does NOT mine cluster keys from
  OpenInference attributes (e.g., `user.id`, `session.id`) because
  those weren't predeclared at experiment design time. v0.3+ may
  add explicit per-attribute opt-in.

## Status

| Surface | v0.2 | Notes |
|---|---|---|
| Protocol shape (`TraceSource`) | ✅ | Conformance test against the parent repo's harness. |
| Span grouping by trace_id | ✅ | Pinned by `TestSpanGrouping`. |
| Root span identification | ✅ | Parent-less + OpenInference kind fallback. |
| Recorded-cassette smoke (live Phoenix) | ❌ — v0.3 | Awaiting Phoenix HTTP-cassette infrastructure parity with `whatifd-langfuse`. |
| Cluster keys from `user.id` / `session.id` | ❌ — v0.3+ | Cardinal #10 requires predeclaration; opt-in landed alongside cluster bootstrap. |

## License

Apache-2.0.
