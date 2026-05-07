"""Adapter conformance harness — Phase 4A.2.

Parameterized base classes that any concrete `TraceSource` /
`Scorer` adapter must subclass and pass. Single source of truth for
"what makes an adapter valid"; runs against the synthetic stub at
Phase 4A.3 and against `whatif-langfuse` / `whatif-inspect-ai` at
Phase 4B.

## How to use this harness

Each adapter package writes a small `test_<name>_conformance.py`
under `tests/adapters/` (or in its own package) that subclasses
`TraceSourceConformance` and/or `ScorerConformance`, overrides the
`trace_source` / `scorer` fixture(s) to construct the adapter under
test, and runs:

```python
import pytest
from tests.adapters.conformance import TraceSourceConformance

class TestStubTraceSource(TraceSourceConformance):
    @pytest.fixture
    def trace_source(self) -> TraceSource:
        return MyStubTraceSource(...)
```

Pytest discovers the subclass, finds the inherited `test_*` methods,
and runs them with the overridden fixture. Add a new conformance
property by adding a `test_*` method to the appropriate base class
here — every concrete subclass inherits it for free.

## Why a base-class pattern (not pytest_generate_tests)

`pytest_generate_tests` parametrizes by value; the harness needs to
parametrize by **adapter implementation**, which is a class-level
discriminator. Subclassing matches that shape without per-test
boilerplate. The cost — `__test__ = False` on the base classes so
pytest doesn't try to run them with the unimplemented fixture — is
a one-line discipline rule documented at each base.

## What this harness does NOT cover

- Adapter-specific behavior (Langfuse-shape projection, Inspect AI
  rubric encoding). Those belong in adapter-package internal tests.
- Performance budgets. Phase 9A's pipeline timing test owns that.
- End-to-end CLI integration. Phase 9 owns that.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from whatif.adapters import (
    AdapterMetadata,
    ClusterKeySupport,
    JudgeResult,
    RawTrace,
    Scorer,
    TraceSource,
)
from whatif.cache.keying.v1 import CacheKeyComponents
from whatif.contract import (
    ReplayOutput,
    ScoreCase,
    TraceInput,
    TraceOutput,
)
from whatif.types.sensitive import Sensitive

if TYPE_CHECKING:
    pass


def make_score_case(trace_id: str = "t-1", cohort: str = "failure") -> ScoreCase:
    """Construct a realistic `ScoreCase` for the harness to feed
    into `Scorer.score` and `Scorer.cache_key_components`. Lives at
    module level so adapter-specific subclasses can extend with
    additional cases without re-deriving the shape."""
    return ScoreCase(
        trace_id=trace_id,
        cohort="failure" if cohort not in ("failure", "baseline") else cohort,
        input=TraceInput(user_message="hello"),
        original_output=TraceOutput(text="orig"),
        replayed_output=ReplayOutput(text="replay"),
    )


class TraceSourceConformance:
    """Conformance properties every `TraceSource` must satisfy.

    Subclass and override the `trace_source` fixture to point at a
    concrete adapter. `__test__ = False` so pytest does not collect
    the base — only concrete subclasses are run.
    """

    __test__ = False

    @pytest.fixture
    def trace_source(self) -> TraceSource:
        raise NotImplementedError(
            "Subclass `TraceSourceConformance` and override the "
            "`trace_source` fixture to return your adapter instance."
        )

    def test_isinstance_protocol(self, trace_source: TraceSource) -> None:
        # Cheap structural check — `runtime_checkable` only verifies
        # attribute presence (see `protocols.py` TODO note). The real
        # signature-drift gate is the call-shape tests below.
        assert isinstance(trace_source, TraceSource)

    def test_adapter_metadata_shape(self, trace_source: TraceSource) -> None:
        meta = trace_source.adapter_metadata()
        assert isinstance(meta, AdapterMetadata)
        assert meta.adapter_id, "adapter_id must be a non-empty string"
        assert meta.package_version, "package_version must be a non-empty string"

    def test_cluster_key_support_shape(self, trace_source: TraceSource) -> None:
        cks = trace_source.cluster_key_support()
        assert isinstance(cks, ClusterKeySupport)

    def test_iter_traces_is_generator_or_iterator(self, trace_source: TraceSource) -> None:
        # Phase 4 explicitly forbids returning a list — bounded-memory
        # contract for large backfills. `iter()` succeeds on any
        # iterable; `__iter__` returning `self` is the load-bearing
        # check that distinguishes a generator/iterator from a list.
        result = trace_source.iter_traces()
        assert iter(result) is result, (
            "iter_traces() must return an iterator/generator, not a list-like "
            "iterable. Phase 4 forbids list returns to keep memory bounded."
        )

    def test_emitted_traces_wrap_user_content(self, trace_source: TraceSource) -> None:
        # Cardinal #5: every emitted RawTrace must wrap user_message
        # and original_response as Sensitive[str]. The Pydantic model
        # already enforces this at construction; this test re-asserts
        # at the harness boundary so a regression that bypasses
        # construction (e.g., model_construct) fails loudly.
        emitted = list(trace_source.iter_traces())
        if not emitted:
            pytest.skip(
                "trace_source emitted no traces; the harness cannot exercise "
                "Sensitive-wrapping. Provide a fixture that emits at least one."
            )
        for rt in emitted:
            assert isinstance(rt, RawTrace)
            assert isinstance(rt.user_message, Sensitive)
            assert isinstance(rt.original_response, Sensitive)


class ScorerConformance:
    """Conformance properties every `Scorer` must satisfy.

    Subclass and override the `scorer` fixture. `__test__ = False`
    so pytest does not collect the base.
    """

    __test__ = False

    @pytest.fixture
    def scorer(self) -> Scorer:
        raise NotImplementedError(
            "Subclass `ScorerConformance` and override the `scorer` "
            "fixture to return your adapter instance."
        )

    def test_isinstance_protocol(self, scorer: Scorer) -> None:
        assert isinstance(scorer, Scorer)

    def test_adapter_metadata_shape(self, scorer: Scorer) -> None:
        meta = scorer.adapter_metadata()
        assert isinstance(meta, AdapterMetadata)
        assert meta.adapter_id
        assert meta.package_version

    def test_score_returns_judge_result(self, scorer: Scorer) -> None:
        result = scorer.score(make_score_case())
        assert isinstance(result, JudgeResult)
        assert isinstance(result.rationale, Sensitive)
        # `score` may be None (structural-failure signal) — both branches valid.
        assert result.score is None or isinstance(result.score, float)
        assert result.judge_model_id

    def test_cache_key_components_returns_valid_shape(self, scorer: Scorer) -> None:
        # The CacheKeyComponents __post_init__ enforces hex-digest
        # invariants on hash fields (≥16 hex chars). A scorer that
        # accidentally passes raw text fails construction here.
        components = scorer.cache_key_components(make_score_case())
        assert isinstance(components, CacheKeyComponents)


class StructuralFailureScorerConformance:
    """Optional conformance variant: scorers that can be configured
    to emit `score=None` should subclass this to exercise the
    cardinal-#1 surface explicitly. Adapters whose backend cannot
    produce structural-failure outputs (e.g., a deterministic stub
    that always succeeds) skip this class.
    """

    __test__ = False

    @pytest.fixture
    def failing_scorer(self) -> Scorer:
        raise NotImplementedError(
            "Subclass `StructuralFailureScorerConformance` and override "
            "the `failing_scorer` fixture to return a scorer that emits "
            "score=None for the next call."
        )

    def test_score_none_path(self, failing_scorer: Scorer) -> None:
        result = failing_scorer.score(make_score_case())
        assert result.score is None, (
            "failing_scorer fixture must emit score=None to exercise the "
            "cardinal-#1 structural-failure path."
        )
        assert isinstance(result.rationale, Sensitive)
