"""Run the conformance harness against the synthetic stub adapter.

Phase 4A.3. Closes the cascade-catalog Phase 4A.2 conformance-
harness checklist item that says "harness runs against the
synthetic stub at 4A.3 and is green."

This file is the inverse of `test_conformance_self_test.py`:
- Self-test uses minimum-viable in-file fakes to prove the harness
  machinery is correct (4A.2's own coverage).
- This file uses the actual `whatif.adapters.stub` module to prove
  the stub itself satisfies every conformance property.

Phase 4B will add `test_langfuse_conformance.py` and
`test_inspect_ai_conformance.py` following the same pattern.
"""

from __future__ import annotations

import pytest

from whatif.adapters import Scorer, TraceSource
from whatif.adapters.stub import (
    StubScorer,
    StubTraceSource,
    StubTraceSpec,
)

from .conformance import (
    ScorerConformance,
    StructuralFailureScorerConformance,
    TraceSourceConformance,
    make_score_case,
)


def _failure_specs() -> list[StubTraceSpec]:
    return [
        StubTraceSpec(
            trace_id="t-1",
            user_message="why is my code broken?",
            original_response="check your imports",
            cohort="failure",
        ),
        StubTraceSpec(
            trace_id="t-2",
            user_message="what's 2+2?",
            original_response="four",
            cohort="baseline",
        ),
    ]


class TestStubTraceSource(TraceSourceConformance):
    __test__ = True

    @pytest.fixture
    def trace_source(self) -> TraceSource:
        return StubTraceSource(specs=_failure_specs())


class TestStubScorer(ScorerConformance):
    __test__ = True

    @pytest.fixture
    def scorer(self) -> Scorer:
        return StubScorer()


class TestStubScorerStructuralFailure(StructuralFailureScorerConformance):
    __test__ = True

    @pytest.fixture
    def scorer(self) -> Scorer:
        # Configure the stub to emit `score=None` — exercises the
        # cardinal-#1 surface through the harness against the real
        # stub module (not the in-file fake from the self-test).
        # Subclassing the variant means this fixture ALSO has to
        # pass every ScorerConformance base-class property.
        return StubScorer(score_fn=lambda _case: None)


class TestStubBehaviors:
    """Stub-specific behaviors NOT covered by the generic harness.
    The harness pins protocol conformance; this class pins
    stub-shaped guarantees that downstream Phase 9A integration
    tests rely on (deterministic cache keys, configurable
    cluster-key support, fixture ordering)."""

    def test_iter_traces_preserves_spec_order(self) -> None:
        # Phase 9A determinism tests rely on the stub emitting
        # traces in fixture-order; pin it.
        specs = _failure_specs()
        emitted = list(StubTraceSource(specs=specs).iter_traces())
        assert [rt.trace_id for rt in emitted] == [s.trace_id for s in specs]

    def test_cache_key_components_deterministic(self) -> None:
        # The same ScoreCase produces the same hex digests across
        # calls — the cache subsystem's determinism invariant.
        case = make_score_case(trace_id="t-1")
        scorer = StubScorer()
        c1 = scorer.cache_key_components(case)
        c2 = scorer.cache_key_components(case)
        assert c1 == c2

    def test_cache_key_components_distinct_for_distinct_cases(self) -> None:
        # Distinct ScoreCases produce distinct keys; otherwise the
        # cache would conflate runs.
        scorer = StubScorer()
        case1 = make_score_case(trace_id="t-1")
        case2 = make_score_case(trace_id="t-2")
        assert scorer.cache_key_components(case1) != scorer.cache_key_components(case2)
