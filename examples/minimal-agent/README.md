# minimal-agent

Reference `Runner` for the whatifd v0.1 contract. The smallest legal implementation that satisfies `whatifd.contract.Runner` (the `Protocol` that whatifd calls during replay).

**This is a shape, not a working agent.** The body returns a deterministic echo so the example is testable without an LLM provider; replace the body with your real replay logic.

## What's in here

- [`replay.py`](./replay.py) — the `run(...)` callable. Sync runner; matches `Runner` (not `AsyncRunner`).

## Files you'd add in your own project

- A real prompt-assembly path that reads `config.system_prompt`
- Tool implementations that consult `tool_cache.lookup(name, args)` *before* calling the tool live
- Either a sync OR async runner — pick one; whatifd doesn't mix them in a single run

## Wire it up (programmatic — works today)

```python
from whatifd.pipeline import run_pipeline
from examples.minimal_agent.replay import run as my_runner
# ... build your TraceSource, delta_fn, floor, policy, runtime,
#     methodology, cache_summary and call run_pipeline(...)
```

## Wire it up (CLI — Phase 10)

```bash
whatifd fork --target "python:examples.minimal_agent.replay:run" ...
```

The `python:<module>:<attr>` syntax is the v0.1 runner-target loader. The CLI dispatcher in `_run_fork_pipeline` is currently a stub returning the setup-failure exit code with a clear "Phase 4 adapter integration not yet wired" message — Phase 10 wires this end-to-end.

## Cardinal alignment

- **Cardinal #1 (failure-as-data):** if your runner can't replay (e.g., tool cache miss under the strict `use-original` policy), raise a typed `CacheMissError` from your tool layer — the replay kernel catches it and emits a structured `ReplayFailure` rather than crashing the experiment.
- **Cardinal #5 (Sensitive at boundary):** the `TraceInput.user_message` your runner receives is a plain `str` — whatifd unwraps the `Sensitive[str]` from the adapter side before handing it to you. Your `ReplayOutput.text` is also plain `str`; whatifd rewraps for the report.
- **Cardinal #7 (two-affirmation):** if your runner produces forensic output (e.g., raw user content in metadata), the CLI's two-affirmation gate is what authorizes that — your runner doesn't make that decision.

## See also

- `docs/runner-contract.md` — the full contract reference
- `docs/getting-started.md` — worked end-to-end example
- `src/whatifd/contract/__init__.py` — the canonical Pydantic models
