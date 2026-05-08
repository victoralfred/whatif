"""Minimal reference `Runner` for the whatif v0.1 contract.

A `Runner` is the user-supplied callable that whatif invokes to
replay one trace under a proposed change. It receives the original
input, the modified `ReplayConfig`, and the `ToolCache` (cached
outputs from the original trace, so tools don't re-fire side
effects). It returns a `ReplayOutput` with the agent's final
response and any per-tool spans.

This file demonstrates the **shape** of a Runner. A real
implementation would call into your agent code; this stub returns
a deterministic response so the example works without an LLM
provider.

Use it as a copy-paste starting point — the load-bearing surface is
the function signature, not the body.

Usage (programmatic, via `whatifd.pipeline.run_pipeline`):

    from examples.minimal_agent.replay import run as my_runner
    # ... pass `my_runner` to your replay-kernel call site

Usage (CLI, when Phase 10 wires the runner-target loader):

    whatif fork --target "python:examples.minimal_agent.replay:run" ...
"""

from __future__ import annotations

from whatifd.contract import ReplayConfig, ReplayOutput, ToolCache, TraceInput


def run(
    trace_input: TraceInput,
    config: ReplayConfig,
    tool_cache: ToolCache,
) -> ReplayOutput:
    """Replay one trace under the proposed change.

    Replace this body with your real agent logic. The reference
    here:
    - reads `config.system_prompt` if the proposed change supplied
      one (else falls back to a literal default — your real agent
      would inject it into its prompt assembly);
    - looks up any tool calls via `tool_cache.lookup(name, args)`
      to avoid re-firing side effects;
    - returns a `ReplayOutput` with `text` set to a deterministic
      echo so this example can be unit-tested without a model.
    """
    system_prompt = config.system_prompt or "You are a helpful assistant."

    # A real agent would consult `tool_cache.lookup(name, args)`
    # before calling each tool, e.g.:
    #
    #     cached = tool_cache.lookup("search_docs", {"q": query})
    #     if cached is None:
    #         # v0.1 `use-original` policy: cache miss raises
    #         # CacheMissError up the stack → typed ReplayFailure.
    #         raise CacheMissError("search_docs", {"q": query})
    #     return cached
    #
    # This stub doesn't invoke any tool, so it doesn't exercise the
    # cache. The `tool_cache` parameter is named `_tool_cache` here
    # only to silence the unused-arg lint without dropping the
    # protocol-required signature.
    _tool_cache = tool_cache
    response_text = f"[stub] system={system_prompt!r} input={trace_input.user_message!r}"

    return ReplayOutput(
        text=response_text,
        tool_spans=[],
        metadata={"runner": "examples.minimal-agent"},
    )
