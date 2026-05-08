"""`whatif-inspect-ai` — Inspect AI `Scorer` adapter for whatif.

Phase 4B.2 of the v0.1 plan. Implements `whatif.adapters.Scorer`
against the Inspect AI scorer abstraction (`inspect_ai.scorer`),
wraps judge rationale as `Sensitive[str]` at the boundary
(cardinal #5), and produces full `CacheKeyComponents` per case.

## Usage

```python
from inspect_ai.scorer import Scorer  # an Inspect AI scorer instance
from whatif_inspect_ai import InspectAIScorer

scorer = InspectAIScorer(
    inspect_scorer=my_inspect_scorer,
    judge_provider="anthropic",
    judge_model_id="claude-opus-4-7",
    rubric_id="faithfulness-v1",
    rubric_text="Score 0-1 by faithfulness to the original output...",
)

# Plug into the whatif pipeline alongside a TraceSource.
```

## Why no recorded-smoke test in this package

Unlike Langfuse (which has a hosted ingestion API replayed via
pytest-recording cassettes), Inspect AI is a **local evaluation
framework** — its scorers run in-process against a model provider
(Anthropic / OpenAI / etc.). There is no "Inspect AI host" to
record HTTP cassettes against. The real-network surface is the
model provider behind Inspect, which Phase 9B's real-adapter
smoke covers via the integration suite. This package ships
mocked-only conformance; cardinal #5 still applies (Sensitive[str]
at the boundary), and the conformance harness pins it.

## Cardinal alignment

- **#5 Sensitive[T] at the boundary:** `JudgeResult.rationale` is
  wrapped at `_project_score`. The Inspect AI `Score.explanation`
  field carries free text from the judge model; it MUST be wrapped
  before any whatif-core code sees it.
- **#1 failures-as-data:** when the wrapped Inspect scorer returns
  `None` or raises, the adapter surfaces a `JudgeResult(score=None)`
  with a structured rationale. The pipeline converts that into a
  `FailureRecord` per cardinal #1.
- **#10 statistical claims:** the adapter is agnostic to the
  scoring metric — that's the user's responsibility when defining
  the Inspect scorer. The methodology disclosure (judge model,
  rubric hash, scoring parameters) flows through
  `cache_key_components`.
"""

from whatif_inspect_ai.scorer import InspectAIScorer

__version__ = "0.1.0"

__all__ = [
    "InspectAIScorer",
    "__version__",
]
