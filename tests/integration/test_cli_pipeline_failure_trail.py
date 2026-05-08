"""End-to-end pin: the closure's typed failures land in
`report.failures[].details` with structured fields, not
parsed-from-message strings.

Phase 10.3 doctrine-review feedback: the unit-level test for
`_ReplayStageError` / `_ScorerStructuralError` distinction only
asserted exception class names — it never invoked
`run_pipeline` or actually constructed a `FailureRecord`. The
`exc_type` capture in `pipeline.py:165` could be deleted without
that test failing. This integration test runs the full pipeline
path and pins the structured trail.
"""

from __future__ import annotations

from typing import Any

from whatifd.adapters.protocols import AdapterMetadata, JudgeResult
from whatifd.adapters.stub import StubTraceSource, StubTraceSpec
from whatifd.cache.keying.v1 import CacheKeyComponents
from whatifd.cli_pipeline import build_delta_fn
from whatifd.config import ChangeConfig
from whatifd.contract import ReplayConfig, ReplayOutput, ScoreCase, ToolCache, TraceInput
from whatifd.pipeline import run_pipeline
from whatifd.runner_loader import LoadedRunner
from whatifd.types.policy import DecisionPolicy, TrustFloor
from whatifd.types.sensitive import Sensitive

from ._fixtures import (
    _default_cache_summary,
    _default_methodology,
    _default_runtime,
)


def _two_branch_runner(
    trace_input: TraceInput,
    config: ReplayConfig,
    tool_cache: ToolCache,
) -> ReplayOutput:
    _ = (config, tool_cache)
    if "raise" in trace_input.user_message:
        raise RuntimeError("forced runner failure")
    return ReplayOutput(text="ok")


def _ckc() -> CacheKeyComponents:
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


class _NoneScorer:
    """Scorer that returns `score=None` for every case (cardinal
    #1 structural failure path)."""

    def score(self, case: ScoreCase) -> JudgeResult:
        return JudgeResult(
            trace_id=case.trace_id,
            score=None,
            rationale=Sensitive("structural", classification="judge_rationale"),
            judge_model_id="test",
        )

    def cache_key_components(self, case: ScoreCase) -> CacheKeyComponents:
        _ = case
        return _ckc()

    def adapter_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(adapter_id="test", package_version="0.0.0", sdk_version=None)


def _loaded(callable_: Any) -> LoadedRunner:
    return LoadedRunner(callable_=callable_, kind="sync", reference="python:test:fixture")


def test_structured_trail_through_run_pipeline() -> None:
    """End-to-end: `_ReplayStageError` and `_ScorerStructuralError`
    surface as `FailureRecord` entries whose `details["exc_type"]`
    distinguishes the two — even though the top-level `code` is
    `scorer_unavailable` in both cases (v0.1 scope; Phase 11+
    widens to per-stage codes).

    A future refactor that removes the `type(exc).__name__`
    capture in `pipeline.py:165` collapses the structured trail
    and this test fails — exactly the regression coverage the
    doctrine review flagged as missing."""
    specs = (
        [
            # 3 traces force replay failure (runner raises)
            StubTraceSpec(
                trace_id=f"f-raise-{i:02d}",
                user_message="raise",
                original_response="orig",
                cohort="failure",
            )
            for i in range(3)
        ]
        + [
            # 3 traces force scorer-structural failure (None score)
            StubTraceSpec(
                trace_id=f"f-none-{i:02d}",
                user_message="ok",
                original_response="orig",
                cohort="failure",
            )
            for i in range(3)
        ]
        + [
            # 5 baseline traces also force scorer-None
            StubTraceSpec(
                trace_id=f"b-{i:02d}",
                user_message="ok",
                original_response="orig",
                cohort="baseline",
            )
            for i in range(5)
        ]
    )
    source = StubTraceSource(specs=specs)

    delta_fn = build_delta_fn(
        loaded_runner=_loaded(_two_branch_runner),
        scorer=_NoneScorer(),  # type: ignore[arg-type]
        change=ChangeConfig(system_prompt="x", model=None),
        replay_timeout_seconds=10.0,
    )

    floor = TrustFloor()
    policy = DecisionPolicy()
    report = run_pipeline(
        source,
        delta_fn=delta_fn,
        floor=floor,
        policy=policy,
        runtime=_default_runtime(floor=floor, policy=policy),
        methodology=_default_methodology(),
        cache_summary=_default_cache_summary(),
    )

    exc_types = {f.details.get("exc_type") for f in report.failures}
    assert "_ReplayStageError" in exc_types, exc_types
    assert "_ScorerStructuralError" in exc_types, exc_types
    # v0.1 scope: top-level code collapses to scorer_unavailable;
    # the structured distinction lives in details.exc_type.
    assert all(f.code == "scorer_unavailable" for f in report.failures)


def test_replay_stage_error_replay_code_reaches_failure_record() -> None:
    """The closure raises `_ReplayStageError(replay_code=...)`; the
    pipeline `isinstance`-narrows against `_ReplayStageError` and
    reads `exc.replay_code` into `FailureRecord.details["replay_code"]`
    as a typed projection (cardinal #1: failure classification is
    type-level, NOT `getattr` duck-typing on attribute names).

    Pin both surfaces:
    1. `details["exc_type"]` carries the closure's exception class
       name (the v0.1 catch-all distinction across replay vs scorer
       failure).
    2. `details["replay_code"]` carries the kernel's
       `ReplayFailure.code` as a TYPED FIELD via the
       isinstance-projection — not parsed from the exception
       message.

    A regression that drops the isinstance branch in `pipeline.py`
    (collapsing back to message-only) fails this test."""
    specs = [
        StubTraceSpec(
            trace_id=f"f-{i:02d}",
            user_message="raise",
            original_response="orig",
            cohort="failure",
        )
        for i in range(5)
    ] + [
        StubTraceSpec(
            trace_id=f"b-{i:02d}",
            user_message="ok",
            original_response="orig",
            cohort="baseline",
        )
        for i in range(5)
    ]
    source = StubTraceSource(specs=specs)

    delta_fn = build_delta_fn(
        loaded_runner=_loaded(_two_branch_runner),
        scorer=_NoneScorer(),  # type: ignore[arg-type]
        change=ChangeConfig(system_prompt="x", model=None),
        replay_timeout_seconds=10.0,
    )
    floor = TrustFloor()
    policy = DecisionPolicy()
    report = run_pipeline(
        source,
        delta_fn=delta_fn,
        floor=floor,
        policy=policy,
        runtime=_default_runtime(floor=floor, policy=policy),
        methodology=_default_methodology(),
        cache_summary=_default_cache_summary(),
    )
    replay_failures = [
        f for f in report.failures if f.details.get("exc_type") == "_ReplayStageError"
    ]
    assert replay_failures, [f.details for f in report.failures]
    # Cardinal #1: the kernel's ReplayFailure.code reaches the
    # report as a STRUCTURED FIELD via details["replay_code"] —
    # NOT via string-extraction from the message. The pipeline's
    # exception capture isinstance-narrows against
    # `_ReplayStageError` and reads `exc.replay_code` directly
    # (failure classification is type-level per cardinal #1).
    # Pin the typed projection so a future refactor that drops the
    # isinstance branch (collapsing back to message-only) fails
    # first.
    replay_codes = [f.details.get("replay_code") for f in replay_failures]
    assert all(rc == "runner_exception" for rc in replay_codes), replay_codes
