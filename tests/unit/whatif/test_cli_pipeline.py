"""Phase 10.3 — `build_delta_fn` closure tests."""

from __future__ import annotations

from typing import Any, Literal

import pytest

from whatif.adapters.protocols import AdapterMetadata, JudgeResult, RawTrace, Scorer
from whatif.adapters.stub import StubScorer
from whatif.cache.keying.v1 import CacheKeyComponents
from whatif.cli_pipeline import build_delta_fn
from whatif.config import ChangeConfig
from whatif.contract import ReplayConfig, ReplayOutput, ScoreCase, ToolCache, TraceInput
from whatif.runner_loader import LoadedRunner
from whatif.types.sensitive import Sensitive


def _raw(trace_id: str = "t-1", cohort: str = "failure") -> RawTrace:
    return RawTrace(
        trace_id=trace_id,
        cohort=cohort,
        user_message=Sensitive("hello", classification="user_message"),
        original_response=Sensitive("orig response", classification="original_response"),
    )


def _sync_runner(
    trace_input: TraceInput,
    config: ReplayConfig,
    tool_cache: ToolCache,
) -> ReplayOutput:
    _ = (config, tool_cache)
    return ReplayOutput(text=f"replayed:{trace_input.user_message}")


async def _async_runner(
    trace_input: TraceInput,
    config: ReplayConfig,
    tool_cache: ToolCache,
) -> ReplayOutput:
    _ = (config, tool_cache)
    return ReplayOutput(text=f"async-replayed:{trace_input.user_message}")


def _raising_runner(
    _trace_input: TraceInput,
    _config: ReplayConfig,
    _tool_cache: ToolCache,
) -> ReplayOutput:
    raise RuntimeError("simulated runner failure")


class _ScoringScorer:
    """Scorer that returns a fixed score, recording the ScoreCase
    it received so tests can assert the closure projected the
    runner output correctly."""

    def __init__(self, score: float | None = 0.42) -> None:
        self._score = score
        self.last_case: ScoreCase | None = None

    def score(self, case: ScoreCase) -> JudgeResult:
        self.last_case = case
        return JudgeResult(
            trace_id=case.trace_id,
            score=self._score,
            rationale=Sensitive("ok", classification="judge_rationale"),
            judge_model_id="test",
        )

    def cache_key_components(self, case: ScoreCase) -> CacheKeyComponents:
        _ = case
        return CacheKeyComponents(
            whatif_schema_version="v0.1",
            whatif_scorer_adapter_version="0.0.0",
            scorer_type="test",
            scorer_package_version="0.0.0",
            judge_provider="test",
            judge_model_id="test",
            judge_model_snapshot=None,
            rendered_prompt_hash="0" * 16,
            rubric_hash="0" * 16,
            scoring_parameters_hash="0" * 16,
            score_case_serialization_version="v1",
            score_case_hash="0" * 16,
        )

    def adapter_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(adapter_id="test", package_version="0.0.0", sdk_version=None)


def _change() -> ChangeConfig:
    return ChangeConfig(system_prompt="new prompt", model=None)


def _loaded(callable_: Any, kind: Literal["sync", "async"]) -> LoadedRunner:
    return LoadedRunner(callable_=callable_, kind=kind, reference="python:test:fixture")


def test_sync_runner_runs_through_kernel_and_produces_score() -> None:
    scorer = _ScoringScorer(score=0.7)
    delta_fn = build_delta_fn(
        loaded_runner=_loaded(_sync_runner, "sync"),
        scorer=scorer,
        change=_change(),
        replay_timeout_seconds=10.0,
    )
    delta = delta_fn(_raw())
    assert delta == 0.7
    # The closure built the ScoreCase with the runner's output.
    assert scorer.last_case is not None
    assert scorer.last_case.replayed_output.text == "replayed:hello"
    # And projected original/input from the RawTrace's Sensitive
    # fields via .unwrap.
    assert scorer.last_case.input.user_message == "hello"
    assert scorer.last_case.original_output.text == "orig response"


def test_async_runner_via_asyncio_run() -> None:
    scorer = _ScoringScorer(score=0.3)
    delta_fn = build_delta_fn(
        loaded_runner=_loaded(_async_runner, "async"),
        scorer=scorer,
        change=_change(),
        replay_timeout_seconds=10.0,
    )
    delta = delta_fn(_raw())
    assert delta == 0.3
    assert scorer.last_case is not None
    assert scorer.last_case.replayed_output.text == "async-replayed:hello"


def test_runner_exception_surfaces_through_replay_failure_to_pipeline() -> None:
    """A runner that raises produces a `ReplayFailure(runner_exception)`
    from the kernel, which the closure raises as `_ReplayStageError`.
    The pipeline's exception path catches it as `scorer_unavailable`
    (cardinal #1: every expected failure is structured data; v0.1
    shape collapses replay+score into one closure surface)."""
    scorer = _ScoringScorer()
    delta_fn = build_delta_fn(
        loaded_runner=_loaded(_raising_runner, "sync"),
        scorer=scorer,
        change=_change(),
        replay_timeout_seconds=10.0,
    )
    with pytest.raises(Exception, match="replay failed"):
        delta_fn(_raw())
    # Scorer never invoked because replay failed first.
    assert scorer.last_case is None


def test_scorer_returning_none_raises_scorer_structural_error() -> None:
    """Cardinal #1: `JudgeResult.score == None` raises into the
    pipeline's exception path. Pin the message so a refactor that
    drops the `score is None` check fails first."""
    scorer = _ScoringScorer(score=None)
    delta_fn = build_delta_fn(
        loaded_runner=_loaded(_sync_runner, "sync"),
        scorer=scorer,
        change=_change(),
        replay_timeout_seconds=10.0,
    )
    with pytest.raises(Exception, match=r"JudgeResult\(score=None\)"):
        delta_fn(_raw())


def test_change_config_system_prompt_threads_through_replay_config() -> None:
    """The runner receives a `ReplayConfig` constructed from
    `cfg.change`. Pin that the system_prompt makes it through —
    a regression that drops the field would silently run the
    runner against the original prompt, which would Ship-misclassify
    every change."""

    received: list[ReplayConfig] = []

    def _capturing_runner(
        trace_input: TraceInput,
        config: ReplayConfig,
        tool_cache: ToolCache,
    ) -> ReplayOutput:
        _ = (trace_input, tool_cache)
        received.append(config)
        return ReplayOutput(text="ok")

    delta_fn = build_delta_fn(
        loaded_runner=_loaded(_capturing_runner, "sync"),
        scorer=_ScoringScorer(),
        change=ChangeConfig(system_prompt="THE NEW PROMPT", model=None),
        replay_timeout_seconds=10.0,
    )
    delta_fn(_raw())
    assert len(received) == 1
    assert received[0].system_prompt == "THE NEW PROMPT"


def test_stub_scorer_returns_constant_0_5() -> None:
    """The factory's StubScorer default returns 0.5 (pinned in PR
    #68); the closure surfaces that to the pipeline. End-to-end
    integration sanity check: build_delta_fn + StubScorer +
    sync_runner produces 0.5 deltas across the board."""
    scorer: Scorer = StubScorer()
    delta_fn = build_delta_fn(
        loaded_runner=_loaded(_sync_runner, "sync"),
        scorer=scorer,
        change=_change(),
        replay_timeout_seconds=10.0,
    )
    assert delta_fn(_raw("t-1")) == 0.5
    assert delta_fn(_raw("t-2", cohort="baseline")) == 0.5


def test_replay_stage_error_carries_structured_replay_code() -> None:
    """The `_ReplayStageError.replay_code` attribute carries the
    kernel's ReplayFailure.code as a typed field — not only baked
    into the message. Cardinal #1: structured data over string-
    parsed messages.

    Pin this so a future refactor that drops the attribute (e.g.,
    collapses back to single-arg Exception) fails first."""
    from whatif.cli_pipeline import _ReplayStageError

    err = _ReplayStageError(replay_code="runner_timeout", message="msg")
    assert err.replay_code == "runner_timeout"
    assert "msg" in str(err)


def test_scorer_structural_error_carries_rationale_classification() -> None:
    """`_ScorerStructuralError.rationale_classification` carries
    the Sensitive classification as a typed attribute."""
    from whatif.cli_pipeline import _ScorerStructuralError

    err = _ScorerStructuralError(rationale_classification="judge_rationale", message="msg")
    assert err.rationale_classification == "judge_rationale"


def test_closure_docstring_carries_runner_reference() -> None:
    """The closure's __doc__ records the LoadedRunner reference for
    debugger / tracer visibility — useful when run_pipeline's
    delta_fn shows up in a stack trace."""
    delta_fn = build_delta_fn(
        loaded_runner=LoadedRunner(
            callable_=_sync_runner, kind="sync", reference="python:my.module:run"
        ),
        scorer=_ScoringScorer(),
        change=_change(),
        replay_timeout_seconds=10.0,
    )
    assert "python:my.module:run" in (delta_fn.__doc__ or "")
    assert "kind=sync" in (delta_fn.__doc__ or "")
