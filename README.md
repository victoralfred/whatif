# whatif

[![CI](https://github.com/victoralfred/whatif/actions/workflows/ci.yml/badge.svg)](https://github.com/victoralfred/whatif/actions/workflows/ci.yml)
[![CodeQL](https://github.com/victoralfred/whatif/actions/workflows/codeql.yml/badge.svg)](https://github.com/victoralfred/whatif/actions/workflows/codeql.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)](#status)

> **Open experiment runner for LLM behavior changes.** Fork production traces, replay with a proposed change, score the diff, emit a PR-ready verdict report.

![whatif workflow](./what_if_archi.png)

When you change a prompt, model, or tool in an LLM system, you don't actually know whether it improves behavior-you guess, with a handful of cherry-picked traces and inconsistent evaluation. Every step in the workflow has a tool: Langfuse for traces, Inspect AI for scoring, GitHub for PRs. **The experiment doesn't.**

**whatif** is the experiment runner. Fork production traces (failed cases plus a representative baseline), replay them with your proposed change (original tool outputs cached so side effects don't re-fire), score with Inspect AI, and produce a diff + verdict report you can attach to the PR. You stop shipping changes that fix one failure while silently regressing ten others. You go from *"this feels better"* to *"this improved 14/20, regressed 3-  here's exactly where, and here's the evidence I'd defend in review."*

Run it interactively today. Wire it into PR checks tomorrow.

**Stop shipping LLM changes on gut feel.**

---

![whatif on one page](./experiment_runner_overview.png)

## Status

**Pre-alpha.** v0.1 in active development. See [DESIGN.md](./DESIGN.md) for the full design, scope, and roadmap.

| Version | Target | What it does |
|---|---|---|
| v0.1 | M10 | Langfuse ingest, prompt override, cached-tool replay, Inspect AI scorer, evidence-first Markdown + JSON reports, CI exit codes. |
| v0.2 | M11 | Config file mode, deterministic output, second tracer adapter, model swap, GitHub Action wrapper. |
| v0.3 | M12 | Live-tool replay (opt-in, allowlist), worked CI sample repo. |
| v1.0 | year 2 | The pre-merge regression gate for LLM behavior. |

## Quickstart (preview-v0.1 not yet released)

```bash
# Once published:
uv pip install whatif

# Or from source:
git clone https://github.com/victoralfred/whatif
cd whatif
uv sync
```

A typical invocation will look like:

```bash
whatif fork \
    --source langfuse \
    --target "python:my_agent.replay:run" \
    --failures "score-below:0.6,since:24h,limit:20" \
    --baseline "score-above:0.8,since:24h,limit:20" \
    --change "system_prompt=prompts/v3.txt" \
    --tool-cache use-original \
    --score "inspect_ai:faithfulness" \
    --report ./reports/$(date +%F)-prompt-v3.md \
    --json   ./reports/$(date +%F)-prompt-v3.json \
    --fail-on-regression

# exit 0 = passed configured policy
# exit 1 = failed configured policy
# exit 2 = inconclusive (setup/replay/scoring failure)
```

## How it composes

`whatif` doesn't replace your tracer or your eval framework - it composes them into an experiment.

- **Tracers (read from)**: Langfuse (v0.1), Phoenix / LangSmith / OpenTelemetry GenAI (v0.2+).
- **Scorers (wraps)**: Inspect AI (v0.1), pluggable via the scorer registry.
- **Your agent (calls back into)**: any Python callable matching the [runner contract](#the-runner-contract).
- **Downstream of `whatif`'s decisions**: your existing CI (GitHub Actions, GitLab CI), SLO platforms (Nobl9, sloth, Honeycomb), incident tooling.

## The runner contract

A trace alone is not executable. You supply the entry point that reconstitutes your agent:

```python
# my_agent/replay.py
from whatif.contract import TraceInput, ReplayConfig, ToolCache, ReplayOutput

def run(trace_input: TraceInput, config: ReplayConfig, tool_cache: ToolCache) -> ReplayOutput:
    agent = build_agent(system_prompt=config.system_prompt, tool_cache=tool_cache)
    return ReplayOutput(text=agent.run(trace_input.user_message))
```

That's it. `whatif` owns the original output, the cohort label, the comparison, and the scoring. Your runner only produces the replayed output.

A reference adapter for the raw Anthropic SDK ships in v0.1; LangChain and LangGraph stubs land in v0.1.1.

## What `whatif` is not

- Not a tracer (use Langfuse / Phoenix / LangSmith / OpenTelemetry GenAI).
- Not an offline eval harness (use Inspect AI / Promptfoo; we wrap them).
- Not an SLO platform (use Nobl9 / sloth / Honeycomb downstream of `whatif`'s decisions).
- Not an agent runtime-the runner contract is the boundary.
- Not a UI or dashboard.

## Design

The full design - problem framing, prior art, runner contract, report shape, eval target, milestones, risks - lives in [DESIGN.md](./DESIGN.md).

## Contributing

Pre-alpha. Issues and design discussion welcome; pull requests deferred until v0.1 ships.

## License

Apache 2.0. See [LICENSE](./LICENSE).
