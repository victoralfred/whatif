# whatif-inspect-ai

Inspect AI `Scorer` adapter for [whatif](https://github.com/victoralfred/whatif). Phase 4B.2 of the v0.1 plan.

## Install

```bash
pip install whatif-inspect-ai
```

Pulls `whatif` and `inspect-ai>=0.3.216,<0.4` (industry-standard library pinning: lower bound + minor-version cap, since Inspect AI is pre-1.0 and ships breaking changes within minor bumps).

## Usage

```python
from inspect_ai.scorer import Score, Target
from inspect_ai.solver import TaskState
from whatif_inspect_ai import InspectAIScorer
from whatif.contract import ScoreCase


def score_fn(case: ScoreCase) -> Score:
    """Wire the user's Inspect AI scorer into the (ScoreCase) -> Score
    callable shape this adapter expects. Typical pattern: build a
    TaskState from the case, run the Inspect AI scorer, return Score."""
    state = TaskState(
        model="anthropic/claude-opus-4-7",
        sample_id=case.trace_id,
        epoch=0,
        input=case.input.user_message,
        messages=[],
        output=...,  # ModelOutput from case.replayed_output.text
    )
    target = Target(case.original_output.text)
    return my_inspect_scorer(state, target)


scorer = InspectAIScorer(
    score_fn=score_fn,
    judge_provider="anthropic",
    judge_model_id="claude-opus-4-7",
    rubric_id="faithfulness-v1",
    rubric_text="Score 0-1 by faithfulness to the original output...",
    scoring_parameters={"temperature": 0.0, "max_tokens": 256},
)

# Plug into the whatif pipeline alongside a TraceSource.
```

## Cardinal alignment

- **#5 Sensitive at the boundary:** `JudgeResult.rationale` is wrapped at `_project_score`. Inspect AI's `Score.explanation` carries free text from the judge model; it MUST be wrapped before any whatif-core code sees it.
- **#1 failures-as-data:** when the wrapped `score_fn` returns `None` or raises, the adapter surfaces a `JudgeResult(score=None)` with structured rationale. The pipeline converts that into a `FailureRecord`. A non-numeric `Score.value` (e.g., a categorical label) projects to `score=None` instead of crashing on `float()`.
- **#10 statistical claims:** the adapter is metric-agnostic — that's the user's responsibility when defining the Inspect AI scorer. Methodology (judge model, rubric hash, scoring parameters) flows through `cache_key_components`.

## Why no recorded-smoke test in this package

Unlike Langfuse (which has a hosted ingestion API replayed via `pytest-recording` cassettes), Inspect AI is a **local evaluation framework** — its scorers run in-process against a model provider (Anthropic / OpenAI / etc.). There is no "Inspect AI host" to record HTTP cassettes against. The real-network surface is the **model provider behind Inspect**, which Phase 9B's real-adapter smoke covers via the integration suite. This package ships **mocked-only conformance**; cardinal #5 still applies (Sensitive[str] at the boundary), and the conformance harness pins it.

## Contributor setup

This package lives in the parent whatif monorepo as a uv workspace member. From the repo root:

```bash
uv sync --all-extras --dev --group workspace
```

The `--group workspace` flag pulls the in-tree `whatif-inspect-ai` editable install via PEP 735 dependency groups (uv-native). Without it, `uv sync --all-extras --dev` installs the rest of the dev environment but leaves this package out, and `pytest packages/whatif-inspect-ai/tests/` fails with `ModuleNotFoundError: whatif_inspect_ai`.

**Plain `pip install ".[dev]"` will NOT work** for the workspace package — pip ignores PEP 735 groups (deliberate; the workspace dep can't be resolved from PyPI because it isn't published yet). Use `uv` for development setup; pip-only consumers install the published `whatif-inspect-ai` from PyPI once it lands.

## Stability

Pre-1.0; the adapter follows whatif's v0.1 stability contract. The Inspect AI minor-version cap (`<0.4`) reserves the next minor for a coordinated migration if Inspect AI changes the `Scorer` / `Score` shape.
