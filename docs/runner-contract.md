# Runner contract

The `Runner` protocol is whatifd's only user-facing extension point in v0.1. You implement it; whatifd calls it once per selected trace during replay.

The canonical Pydantic models live in [`src/whatifd/contract/__init__.py`](../src/whatifd/contract/__init__.py) — that file is the source of truth. This page is the consumer-facing reference.

## The protocol

```python
from typing import Awaitable, Protocol, runtime_checkable
from whatifd.contract import ReplayConfig, ReplayOutput, ToolCache, TraceInput


@runtime_checkable
class Runner(Protocol):
    """Sync runner."""
    def __call__(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        tool_cache: ToolCache,
    ) -> ReplayOutput: ...


@runtime_checkable
class AsyncRunner(Protocol):
    """Async runner. Sync and async are NOT interchangeable."""
    def __call__(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        tool_cache: ToolCache,
    ) -> Awaitable[ReplayOutput]: ...
```

## Inputs

### `TraceInput`

The original input recovered from the production trace.

| Field | Type | Notes |
|---|---|---|
| `user_message` | `str` | Plain text. Whatif unwraps `Sensitive[str]` from the adapter side before handing it to your runner. |
| `metadata` | `dict[str, Any]` | Free-form trace metadata pulled from the source tracer. `extra="allow"` — extra fields preserved. |

### `ReplayConfig`

The proposed change to apply during replay. Only set fields differ from the original config; everything else falls back to your `build_agent()` defaults.

| Field | Type | v0.1 status |
|---|---|---|
| `system_prompt` | `str \| None` | **Supported.** Apply to your prompt assembly. |
| `model` | `str \| None` | v0.2+. Field exists; v0.1 ignores at the contract level (your runner may still consume it). |
| `overrides` | `dict[str, Any]` | v0.3+. Free-form per-tool/parameter overrides. |

`extra="forbid"` — typos fail loud.

### `ToolCache`

Cached tool outputs from the original trace. **Look up cached outputs before calling tools live**; this is what prevents replay from re-firing side effects.

```python
cached = tool_cache.lookup("search_docs", {"q": query})
```

v0.1 enforces a strict `use-original` policy:
- **Cache hit** → use the cached value.
- **Cache miss** → raise a `CacheMissError` (your tool layer's responsibility); the replay kernel converts it to a typed `ReplayFailure`. Surfaces in the report's "Replay validity" section. (Cardinal #1: failures are data, not crashes.)

v0.3 adds an opt-in `live` policy with per-tool allowlists (e.g., for time-sensitive APIs).

## Output

### `ReplayOutput`

The agent's final response.

| Field | Type | Notes |
|---|---|---|
| `text` | `str` | The final response. Plain text; whatifd rewraps as `Sensitive` for the report. |
| `tool_spans` | `list[dict[str, Any]]` | Per-tool spans recorded during replay. Optional but useful for "Replay validity" auditing. |
| `metadata` | `dict[str, Any]` | Free-form. `extra="allow"`. |

## Sync vs async

Sync and async runners are **not interchangeable**. Pick one for your project:

- **Sync runner** → `whatifd.replay.kernel.replay_one_trace` runs you on a `ThreadPoolExecutor` worker.
- **Async runner** → `whatifd.replay.kernel_async.replay_one_trace_async` awaits you directly with portable `asyncio.wait_for(timeout=...)` cancellation.

Detection happens at runner-target import time when the CLI loads `python:<module>:<attr>`. If you return a coroutine from a function declared as a sync `Runner`, the kernel treats it as a value (and likely fails the `isinstance(out, ReplayOutput)` check downstream). Match the protocol you declared.

## Cardinal alignment

- **#1 Failures-as-data:** if your runner can't replay, raise a typed exception (`CacheMissError`, your own `RunnerInputError`, etc.) — the kernel catches it and emits a structured `ReplayFailure`. **Do not** swallow exceptions yourself; the kernel needs the type to classify the failure.
- **#5 Sensitive at boundary:** the `TraceInput.user_message` you receive is plain `str` (whatifd unwraps from the adapter's `Sensitive[str]` before handing it to you). Your `ReplayOutput.text` is also plain `str` (whatifd rewraps for the report). Don't try to wrap on either side; the boundary discipline is whatifd's responsibility, not yours.
- **#7 Two-affirmation:** if your runner produces forensic content (raw user data in `metadata`, full trace context, etc.), the CLI's two-affirmation gate (`reporting.profile=forensic` + `--profile forensic`) is what authorizes the unredacted bundle. Your runner doesn't make that decision; it always emits the same shape.

## Reference Runner

[`examples/minimal-agent/replay.py`](../examples/minimal-agent/replay.py) — copy-paste starting point. The body is a deterministic stub so the example is testable without an LLM provider; replace it with your real replay logic.

## Wire-up patterns

### Programmatic (works today)

```python
from examples.minimal_agent.replay import run as my_runner
# … construct TraceSource, delta_fn that invokes my_runner + scorer,
# floor, policy, runtime, methodology, cache_summary
report = run_pipeline(trace_source, delta_fn=delta_fn, ...)
```

The Phase 9B integration suite (`tests/integration/test_real_adapters.py`) is a load-bearing reference for the closure pattern.

### CLI (Phase 10)

```bash
whatifd fork --target "python:my_agent.replay:run" \
            --source langfuse \
            --change "system_prompt=prompts/v3.txt" \
            --score "inspect_ai:faithfulness"
```

The runner-target loader resolves `python:<module>:<attr>` via `importlib`. The `_run_fork_pipeline` dispatcher in `src/whatifd/cli.py` is currently a documented stub for v0.1.0; the signature is stable (witness-token thread per cardinal #7), so closing the wiring is a body fill, not a contract change.
