"""`whatifd-langfuse` — Langfuse `TraceSource` adapter for whatif.

Phase 4B.1 of the v0.1 plan. Implements `whatifd.adapters.TraceSource`
against the Langfuse v4 SDK (`langfuse.api.LangfuseAPI`), wraps user
content as `Sensitive[str]` at the boundary (cardinal #5), and
streams traces via a generator (Phase 4 contract: bounded memory
for large backfills).

## Usage

```python
import os
from langfuse.api import LangfuseAPI
from whatifd_langfuse import LangfuseTraceSource

api = LangfuseAPI(
    base_url=os.environ["LANGFUSE_HOST"],
    username=os.environ["LANGFUSE_PUBLIC_KEY"],
    password=os.environ["LANGFUSE_SECRET_KEY"],
)

source = LangfuseTraceSource(
    api=api,
    cohort_classifier=lambda trace: "failure" if "failed" in (trace.tags or []) else "baseline",
    page_limit=50,
)

for raw in source.iter_traces():
    print(raw.trace_id, raw.cohort)
```

## Cardinal alignment

- **#5 Sensitive[T] at the boundary:** every text field that carries
  user content (`user_message`, `original_response`) is wrapped at
  construction. Trace `input` / `output` may be string, dict, or
  list per Langfuse's typed-Any field; the adapter projects to a
  canonical string and wraps.
- **#9 orchestration, not compute:** the streaming pagination is
  I/O-bound; no CPU optimization tricks. `iter_traces` is a
  generator, not a list build-up.
- **#10 statistical claims:** `cluster_key_support` returns an
  empty `available_keys` tuple. v0.1 does NOT mine cluster keys
  from Langfuse `user_id` / `session_id` because those weren't
  declared as cluster signals at predeclaration time; v0.2+ may
  add explicit configuration for which Langfuse fields to surface
  as cluster keys.
"""

from whatifd_langfuse.source import LangfuseTraceSource

__version__ = "0.1.0"

__all__ = [
    "LangfuseTraceSource",
    "__version__",
]
