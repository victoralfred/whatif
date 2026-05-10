"""`whatifd-phoenix` — Arize Phoenix / OpenInference `TraceSource` adapter.

Phase D of the v0.2 plan. Implements `whatifd.adapters.TraceSource`
against an OpenInference span-iterator surface (Phoenix's native
span shape). The package is span-iterator-shaped so callers can wire
any Phoenix client variant (or any OpenInference-emitting tracer)
without the adapter pinning a specific Phoenix SDK version.

## Usage

```python
from arize.phoenix.client import Client
from whatifd_phoenix import PhoenixTraceSource

client = Client(endpoint="...")

def spans_provider():
    # Cardinal #9 — avoid `df.iterrows()` (pandas/NumPy row iteration).
    # `to_dict(orient="records")` materializes once into a list of
    # dicts; the adapter then iterates that list at orchestration
    # speed.
    spans = client.query_spans(query=...).to_dict(orient="records")
    yield from spans

source = PhoenixTraceSource(
    spans_provider=spans_provider,
    cohort_classifier=lambda spans: "failure" if any(
        s.get("attributes.tag.failed") for s in spans
    ) else "baseline",
)

for raw in source.iter_traces():
    print(raw.trace_id, raw.cohort)
```

## Why span-iterator-shaped (not Phoenix-Client-shaped)

Phoenix's Python client API has shifted across versions
(`arize-phoenix` → `arize-phoenix-client`; the methods on `Client`
have churned between major versions). Pinning a specific Client
shape in this adapter would force a sync-with-Phoenix-release cycle
on every Phoenix major bump. The span-iterator shape is the stable
API: OpenInference span attributes are an open standard
(https://github.com/Arize-ai/openinference) and downstream consumers
(Phoenix, but also custom OTLP collectors) emit this shape.

Callers that want a Phoenix-Client-aware constructor can subclass
`PhoenixTraceSource` and override `__init__` to take a `Client`
directly; the rest of the projection logic doesn't care.

## Cardinal alignment

- **#5 Sensitive[T] at the boundary:** every span attribute that
  carries user content (`input.value`, `output.value`) is wrapped at
  projection time. The `attributes` map itself is NOT wrapped because
  it carries tooling state (path, latency_ms, model_name, ...).
- **#9 orchestration, not compute:** the adapter is a pure projection
  layer — no DataFrames, no NumPy, no pandas in the hot path. Spans
  arrive as dicts; the adapter groups by trace_id and emits.
- **#10 statistical claims:** `cluster_key_support` returns an empty
  `available_keys` tuple. v0.2 does NOT mine cluster keys from
  OpenInference attributes (e.g., `user.id`, `session.id`) because
  those weren't predeclared at experiment design time. v0.3+ may add
  explicit per-attribute opt-in.
"""

from importlib.metadata import PackageNotFoundError, version

from whatifd_phoenix.source import PhoenixTraceSource

try:
    __version__ = version("whatifd-phoenix")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "PhoenixTraceSource",
    "__version__",
]
