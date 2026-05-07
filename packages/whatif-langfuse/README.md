# whatif-langfuse

Langfuse `TraceSource` adapter for [whatif](https://github.com/victoralfred/whatif). Phase 4B.1 of the v0.1 plan.

## Install

```bash
pip install whatif-langfuse
```

Pulls `whatif` and `langfuse>=4.5.1,<5.0` (industry-standard library pinning: lower bound + major-version cap).

## Usage

```python
import os
from langfuse.api import LangfuseAPI
from whatif_langfuse import LangfuseTraceSource

api = LangfuseAPI(
    base_url=os.environ["LANGFUSE_HOST"],
    username=os.environ["LANGFUSE_PUBLIC_KEY"],
    password=os.environ["LANGFUSE_SECRET_KEY"],
)

source = LangfuseTraceSource(
    api=api,
    cohort_classifier=lambda trace: "failure" if "failed" in (trace.tags or []) else "baseline",
    page_limit=50,
    max_traces=200,  # cap iteration so a fixture run can't drain a production project
)

for raw in source.iter_traces():
    print(raw.trace_id, raw.cohort)
```

## Cardinal alignment

- **#5 Sensitive at the boundary:** every text field that carries user content (`user_message`, `original_response`) is wrapped at construction. Trace `input` / `output` may be string, dict, or list per Langfuse's typed-Any field; the adapter projects to a canonical JSON string (sort_keys=True for determinism) and wraps.
- **#9 orchestration, not compute:** streaming pagination is I/O-bound; `iter_traces` is a generator, never a list build-up.
- **#10 statistical claims:** `cluster_key_support()` returns an empty `available_keys` tuple. Surfacing Langfuse `user_id` / `session_id` as cluster keys is an inferential commitment that v0.1 does NOT make; v0.2+ may add explicit per-field opt-in.

## Testing

The package ships two test surfaces:

1. **Mocked-client conformance** (`tests/test_conformance.py`) — runs the parent repo's `TraceSourceConformance` harness against an in-file fake `LangfuseAPI`. No network. CI runs this on every change.

2. **Recorded real-network smoke** (`tests/test_recorded_smoke.py`) — runs against a real Langfuse instance using credentials in environment variables. The first run records HTTP cassettes via `pytest-recording`; subsequent runs replay from the cassette. CI replays from the committed cassette; recording is a local dev step.

### Recording cassettes (one-time, by a contributor with credentials)

```bash
LANGFUSE_HOST=https://cloud.langfuse.com \
LANGFUSE_PUBLIC_KEY=pk-... \
LANGFUSE_SECRET_KEY=sk-... \
uv run pytest packages/whatif-langfuse/tests/test_recorded_smoke.py --record-mode=once
```

The cassette is committed under `tests/cassettes/`. Sensitive headers (`Authorization`, `x-langfuse-public-key`) are filtered out by the `vcr_config` fixture.

## Stability

Pre-1.0; the adapter follows whatif's v0.1 stability contract. The Langfuse SDK upper-cap (`<5.0`) reserves the next major for a coordinated migration if Langfuse changes the `LangfuseAPI.trace.list(...)` shape.
