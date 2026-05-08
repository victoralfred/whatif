"""Per-trace `delta_fn` closure threading runner + scorer.

Phase 10.3 of the v0.1 implementation plan. The CLI's
`_run_fork_pipeline` (Phase 10.4) needs a `Callable[[RawTrace],
float]` to hand to `whatif.pipeline.run_pipeline`. That closure
must:

1. Run the user-supplied runner against the trace input — sync
   via `whatif.replay.kernel.replay_one_trace`, async via
   `whatif.replay.kernel_async.replay_one_trace_async`. The
   `LoadedRunner.kind` from Phase 10.2 picks the kernel.
2. Project the resulting `ReplayOutput` into a `ScoreCase` along
   with the original trace artifacts.
3. Call `Scorer.score(case)` and return `JudgeResult.score`.

## Failure mapping (cardinal #1)

The closure is consumed by `run_pipeline`, which catches every
exception from `delta_fn` and constructs a `scorer_unavailable`
`FailureRecord`. The closure leverages this contract:

- A `ReplayFailure` from the kernel raises a typed
  `_ReplayStageError` with the kernel's code in the message;
  the pipeline's exception path captures it. The replay code
  ends up in the `FailureRecord.details["replay_code"]` slot —
  not as expressive as projecting `ReplayFailure` directly, but
  consistent with v0.1's `delta_fn`-shape pipeline.
- A `JudgeResult.score == None` (cardinal-#1 structural scorer
  failure) raises `_ScorerStructuralError` with the rationale
  in the message. Same pipeline path.

Phase 10.4+ may widen the pipeline to consume `ReplayResult`
directly so replay failures get their own typed
`FailureRecord` projection. v0.1's surface is this closure;
the upgrade path doesn't change its signature.

## Why a module, not a method

The closure carries state — the runner, the scorer, the change
config, the timeout — but it must be a plain function callable to
fit `run_pipeline`'s `delta_fn` parameter shape. A factory
function (`build_delta_fn(...)`) returning a closure keeps the
state-binding explicit and testable in isolation, separate from
the CLI dispatcher in Phase 10.4.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, cast

from whatif.contract import (
    AsyncRunner,
    ReplayConfig,
    ReplayOutput,
    Runner,
    ScoreCase,
    ToolCache,
    TraceInput,
    TraceOutput,
)
from whatif.replay.kernel import replay_one_trace
from whatif.replay.kernel_async import replay_one_trace_async
from whatif.replay.result import ReplayFailure, ReplaySuccess

if TYPE_CHECKING:
    from collections.abc import Callable

    from whatif.adapters.protocols import RawTrace, Scorer
    from whatif.config import ChangeConfig
    from whatif.runner_loader import LoadedRunner


class _ReplayStageError(Exception):
    """Internal: replay-stage failure raised inside the `delta_fn`
    closure to signal the pipeline's exception capture.

    Carries the kernel's `ReplayFailure.code` as a structured
    attribute (not only baked into the message). Cardinal #1: a
    consumer walking the exception sees a typed code, not a
    parsed string. The pipeline converts this to a
    `scorer_unavailable` `FailureRecord` at the top-level `code`
    field (v0.1 scope); Phase 11+ may widen to per-stage codes.
    """

    def __init__(self, *, replay_code: str, message: str) -> None:
        super().__init__(message)
        self.replay_code = replay_code


class _ScorerStructuralError(Exception):
    """Internal: `JudgeResult.score is None` (cardinal-#1) raised
    so the pipeline's exception path captures it as a structured
    `FailureRecord`. Carries the rationale's `classification` as
    a typed attribute so downstream consumers attribute the
    failure without parsing the message string."""

    def __init__(self, *, rationale_classification: str, message: str) -> None:
        super().__init__(message)
        self.rationale_classification = rationale_classification


def build_delta_fn(
    *,
    loaded_runner: LoadedRunner,
    scorer: Scorer,
    change: ChangeConfig,
    replay_timeout_seconds: float,
) -> Callable[[RawTrace], float]:
    """Build a per-trace `delta_fn` for `run_pipeline`.

    The returned closure does replay → score per trace. Sync vs
    async runner is selected by `loaded_runner.kind`; the async
    branch wraps the kernel call in `asyncio.run` (one event loop
    per trace, acceptable for v0.1 — the pipeline is I/O-bound and
    fork concurrency is bounded by `run_pipeline`'s sequential
    iteration anyway).
    """
    replay_config = ReplayConfig(
        system_prompt=change.system_prompt,
        model=change.model,
    )
    runner = loaded_runner.callable_
    is_async = loaded_runner.kind == "async"

    def _delta_fn(rt: RawTrace) -> float:
        # Cardinal #5 unwrap at the boundary. The Sensitive[str]
        # protections are for serialization-redaction; the runner's
        # contract takes plain str, so we unwrap with an explicit
        # audit reason naming this call site.
        user_message = rt.user_message.unwrap(
            reason="cli_pipeline.delta_fn: feed runner trace_input"
        )
        original_response = rt.original_response.unwrap(
            reason="cli_pipeline.delta_fn: build ScoreCase.original_output"
        )

        trace_input = TraceInput(user_message=user_message)
        # v0.1's strict tool-cache policy is `use-original`; the
        # cache is constructed empty here because the v0.1
        # adapters don't yet emit per-trace tool spans. A real
        # runner that calls `tool_cache.lookup` will hit
        # `CacheMissError` → ReplayFailure(tool_cache_miss), which
        # is the correct surface for v0.1's no-tool-spans path.
        tool_cache = ToolCache()

        if is_async:
            # `asyncio.run` creates a fresh event loop and
            # therefore can't be called from inside a running loop.
            # The CLI dispatcher is sync; this is fine for v0.1.
            #
            # TODO(Phase 11): one event loop per async-runner trace
            # defeats httpx.AsyncClient connection reuse for users
            # whose runners construct a client per call. The fix is
            # a shared loop optionally injected into `build_delta_fn`;
            # cascade-catalog entry "Phase 11: shared asyncio loop
            # for async-runner trace stream". v0.1 acceptable
            # because (a) the workload is I/O-bound by judge latency
            # not connection setup, and (b) sync runners get reuse
            # via httpx.Client normally — async-runner users with
            # connection-reuse needs can use the sync API.
            #
            # The Phase 10.2 loader already validated this is an
            # AsyncRunner (via `inspect.iscoroutinefunction` +
            # `isinstance` belt-and-suspenders). The cast tells
            # mypy what we already proved at load time, without
            # widening LoadedRunner.callable_'s type.
            replay_result = asyncio.run(
                replay_one_trace_async(
                    trace_id=rt.trace_id,
                    cohort=rt.cohort,
                    trace_input=trace_input,
                    config=replay_config,
                    tool_cache=tool_cache,
                    runner=cast(AsyncRunner, runner),
                    timeout_seconds=replay_timeout_seconds,
                )
            )
        else:
            replay_result = replay_one_trace(
                trace_id=rt.trace_id,
                cohort=rt.cohort,
                trace_input=trace_input,
                config=replay_config,
                tool_cache=tool_cache,
                runner=cast(Runner, runner),
                timeout_seconds=replay_timeout_seconds,
            )

        if isinstance(replay_result, ReplayFailure):
            raise _ReplayStageError(
                replay_code=replay_result.code,
                message=f"replay failed [{replay_result.code}]: {replay_result.message}",
            )
        # The kernel's contract is `ReplaySuccess | ReplayFailure`;
        # mypy doesn't narrow without an explicit type assertion.
        assert isinstance(replay_result, ReplaySuccess)
        replayed_output: ReplayOutput = replay_result.output

        case = ScoreCase(
            trace_id=rt.trace_id,
            cohort=rt.cohort,  # type: ignore[arg-type]
            input=trace_input,
            original_output=TraceOutput(text=original_response),
            replayed_output=replayed_output,
        )
        judge = scorer.score(case)
        if judge.score is None:
            # Cardinal #1: structural scorer failure. The rationale
            # is Sensitive[str]; surface its classification only
            # (not the unwrapped text) in the exception message so
            # the pipeline's `make_failure_record` doesn't bake
            # rationale text into a FailureRecord.message field.
            raise _ScorerStructuralError(
                rationale_classification=judge.rationale.classification,
                message=(
                    "scorer returned JudgeResult(score=None); see rationale "
                    f"(classification={judge.rationale.classification!r})"
                ),
            )
        # `judge.score` is float | None; the None branch raised, so
        # narrow.
        score = judge.score
        return float(score)

    # Document the closure's runner-shape on the returned callable
    # so a future debugger / tracer that inspects the function can
    # see whether async or sync runner is active without needing
    # to query the LoadedRunner directly.
    _delta_fn.__doc__ = (
        f"delta_fn closure (runner={loaded_runner.reference}, kind={loaded_runner.kind})"
    )
    return _delta_fn


__all__ = ["build_delta_fn"]
