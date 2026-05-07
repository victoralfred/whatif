"""Self-test: prove the conformance harness machinery is correct.

Phase 4A.2 ships the harness (`tests/adapters/conformance.py`) but
the synthetic stub adapter is Phase 4A.3 — they're separate sub-
phases per the plan split. Without a self-test, Phase 4A.2 would
land an untested harness and we'd discover bugs against the stub
in 4A.3, which conflates "is the harness right" with "does the
stub conform."

This file plugs the **minimum-viable adapters** (in-file fakes,
NOT the Phase 4A.3 stub) into the harness so every conformance
property has a concrete invocation. The fakes are deliberately
trivial — Phase 4A.3 lands a richer, fixture-driven stub
elsewhere.

If you want to add a new conformance property, add the test method
to `conformance.py`, then update the fakes here only enough to
satisfy it. Do NOT grow the fakes into a full stub — that's the
4A.3 file's job.
"""

from __future__ import annotations

from collections.abc import Iterator

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
from whatif.contract import ScoreCase
from whatif.types.sensitive import Sensitive

from .conformance import (
    ScorerConformance,
    StructuralFailureScorerConformance,
    TraceSourceConformance,
    make_score_case,
)

_HEX = "0" * 64  # 64 hex chars satisfies the CacheKeyComponents pre-hash invariant


class _MinimalTraceSource:
    """Smallest object satisfying `TraceSource`. Not for production
    use; not the Phase 4A.3 stub."""

    def iter_traces(self) -> Iterator[RawTrace]:
        yield RawTrace(
            trace_id="t-1",
            cohort="failure",
            user_message=Sensitive("hello", classification="user_content"),
            original_response=Sensitive("hi", classification="user_content"),
        )

    def adapter_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(adapter_id="harness-self-test", package_version="0.0.0")

    def cluster_key_support(self) -> ClusterKeySupport:
        return ClusterKeySupport(available_keys=())


class _MinimalScorer:
    """Smallest object satisfying `Scorer`."""

    def score(self, case: ScoreCase) -> JudgeResult:
        return JudgeResult(
            trace_id=case.trace_id,
            score=0.5,
            rationale=Sensitive("ok", classification="judge_rationale"),
            judge_model_id="harness-judge",
        )

    def cache_key_components(self, case: ScoreCase) -> CacheKeyComponents:
        return CacheKeyComponents(
            whatif_schema_version="v0.1",
            whatif_scorer_adapter_version="0.0.0",
            scorer_type="self-test",
            scorer_package_version="0.0.0",
            judge_provider="self-test",
            judge_model_id="harness-judge",
            judge_model_snapshot=None,
            rendered_prompt_hash=_HEX,
            rubric_hash=_HEX,
            scoring_parameters_hash=_HEX,
            score_case_serialization_version="v1",
            score_case_hash=_HEX,
        )

    def adapter_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(adapter_id="harness-self-test-scorer", package_version="0.0.0")


class _FailingScorer(_MinimalScorer):
    """Variant that emits `score=None` on every call. Exercises the
    cardinal-#1 structural-failure path through the harness."""

    def score(self, case: ScoreCase) -> JudgeResult:
        return JudgeResult(
            trace_id=case.trace_id,
            score=None,
            rationale=Sensitive("structural failure", classification="judge_rationale"),
            judge_model_id="harness-judge",
        )


class TestHarnessTraceSource(TraceSourceConformance):
    __test__ = True

    @pytest.fixture
    def trace_source(self) -> TraceSource:
        return _MinimalTraceSource()


class TestHarnessScorer(ScorerConformance):
    __test__ = True

    @pytest.fixture
    def scorer(self) -> Scorer:
        return _MinimalScorer()


class TestHarnessFailingScorer(StructuralFailureScorerConformance):
    __test__ = True

    @pytest.fixture
    def failing_scorer(self) -> Scorer:
        return _FailingScorer()


class TestHarnessRejectsBadAdapters:
    """Pin that the harness FAILS on adapters that violate the
    contract — proves the assertions are load-bearing, not vacuous.
    """

    def test_score_case_factory_returns_score_case(self) -> None:
        # make_score_case is a small helper; pin its shape so a
        # downstream test can rely on the ScoreCase being valid.
        case = make_score_case()
        assert case.trace_id == "t-1"
        assert case.cohort == "failure"

    def test_iter_traces_returning_list_fails_harness(self) -> None:
        # The Phase 4 contract forbids returning a list. A bad
        # adapter that returns one MUST fail the harness — invoke
        # the harness's check method directly against the bad adapter
        # and assert it raises AssertionError. This proves the
        # harness check is load-bearing (not vacuous) and catches a
        # contributor who narrowed the check by accident.
        class _ListReturningAdapter:
            def iter_traces(self) -> list[RawTrace]:
                return [
                    RawTrace(
                        trace_id="t",
                        cohort="failure",
                        user_message=Sensitive("a", classification="user_content"),
                        original_response=Sensitive("b", classification="user_content"),
                    )
                ]

            def adapter_metadata(self) -> AdapterMetadata:
                return AdapterMetadata(adapter_id="bad", package_version="0.0.0")

            def cluster_key_support(self) -> ClusterKeySupport:
                return ClusterKeySupport(available_keys=())

        harness = TraceSourceConformance()
        with pytest.raises(AssertionError, match="iterator/generator"):
            harness.test_iter_traces_is_generator_or_iterator(_ListReturningAdapter())  # type: ignore[arg-type]
