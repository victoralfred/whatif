"""Tests for `whatifd.replay.kernel_async.replay_one_trace_async` —
Phase 6.3c per-trace async replay kernel.

Pin properties (mirroring the sync kernel suite):

1. Clean async runner returns `ReplaySuccess`.
2. Async runner that raises `CacheMissError` produces
   `ReplayFailure(code="tool_cache_miss")`.
3. Async runner exceeding the timeout produces
   `ReplayFailure(code="runner_timeout")` AND the cancellation is
   clean (no leaked tasks; cleanup ran via `CancelledError`).
4. Async runner raising any other exception produces
   `ReplayFailure(code="runner_exception")`.
5. Catch-order is correct: `CacheMissError` not classified as
   `runner_exception`.
6. External cancellation (caller cancels the kernel's own task)
   propagates as `CancelledError` rather than being swept into
   `runner_exception` — `BaseException` discipline.
"""

from __future__ import annotations

import asyncio

import pytest

from whatifd.contract import ReplayConfig, ReplayOutput, ToolCache, TraceInput
from whatifd.replay import (
    ReplayFailure,
    ReplaySuccess,
    replay_one_trace_async,
)
from whatifd.replay.tool_cache import CacheMissError, make_strict_tool_cache

_TEST_TRACE_ID = "t-async-1"


@pytest.fixture
def trace_input() -> TraceInput:
    return TraceInput(user_message="hello")


@pytest.fixture
def config() -> ReplayConfig:
    return ReplayConfig(system_prompt="be helpful")


@pytest.fixture
def empty_strict_cache() -> ToolCache:
    return make_strict_tool_cache({}, trace_id=_TEST_TRACE_ID)


@pytest.fixture
def empty_loose_cache() -> ToolCache:
    return ToolCache(cache={}, policy="use-original")


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------


class TestSuccess:
    async def test_clean_async_runner(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        async def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            return ReplayOutput(text=f"async-echo: {ti.user_message}")

        result = await replay_one_trace_async(
            trace_id=_TEST_TRACE_ID,
            cohort="failure",
            trace_input=trace_input,
            config=config,
            tool_cache=empty_loose_cache,
            runner=runner,
            timeout_seconds=2.0,
        )
        assert isinstance(result, ReplaySuccess)
        assert result.output.text == "async-echo: hello"


# ---------------------------------------------------------------------------
# Cache miss
# ---------------------------------------------------------------------------


class TestCacheMiss:
    async def test_cache_miss_classified(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_strict_cache: ToolCache,
    ) -> None:
        async def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            tc.lookup("get_weather", {"city": "Tokyo"})
            return ReplayOutput(text="never reached")

        result = await replay_one_trace_async(
            trace_id=_TEST_TRACE_ID,
            cohort="failure",
            trace_input=trace_input,
            config=config,
            tool_cache=empty_strict_cache,
            runner=runner,
            timeout_seconds=2.0,
        )
        assert isinstance(result, ReplayFailure)
        assert result.code == "tool_cache_miss"
        assert result.details["tool_name"] == "get_weather"

    async def test_direct_cache_miss_classified(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        # Defense-in-depth: runner raises CacheMissError directly,
        # not via cache.lookup. Verifies classification is
        # type-based, not call-site-based.
        async def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise CacheMissError(trace_id=_TEST_TRACE_ID, tool_name="direct", arg_count=0)

        result = await replay_one_trace_async(
            trace_id=_TEST_TRACE_ID,
            cohort="failure",
            trace_input=trace_input,
            config=config,
            tool_cache=empty_loose_cache,
            runner=runner,
            timeout_seconds=2.0,
        )
        assert isinstance(result, ReplayFailure)
        assert result.code == "tool_cache_miss"


# ---------------------------------------------------------------------------
# Timeout (with cancellation cleanup)
# ---------------------------------------------------------------------------


class TestTimeout:
    async def test_timeout_classified(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        async def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            await asyncio.sleep(2.0)  # past the 0.1s budget
            return ReplayOutput(text="never returned")

        result = await replay_one_trace_async(
            trace_id=_TEST_TRACE_ID,
            cohort="failure",
            trace_input=trace_input,
            config=config,
            tool_cache=empty_loose_cache,
            runner=runner,
            timeout_seconds=0.1,
        )
        assert isinstance(result, ReplayFailure)
        assert result.code == "runner_timeout"
        ts = result.details["timeout_seconds"]
        assert isinstance(ts, float)
        assert ts == 0.1

    async def test_cancellation_runs_runner_cleanup(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        # Pin the cardinal #1 + portable-cancellation property:
        # when timeout fires, the runner's CancelledError-aware
        # cleanup (try/finally) runs. Sets `cleaned` to True;
        # asserting it after the kernel returns proves the
        # cancellation was clean, not a leak.
        cleaned = False

        async def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            nonlocal cleaned
            try:
                await asyncio.sleep(2.0)
                return ReplayOutput(text="x")
            finally:
                cleaned = True

        result = await replay_one_trace_async(
            trace_id=_TEST_TRACE_ID,
            cohort="failure",
            trace_input=trace_input,
            config=config,
            tool_cache=empty_loose_cache,
            runner=runner,
            timeout_seconds=0.1,
        )
        assert isinstance(result, ReplayFailure)
        assert result.code == "runner_timeout"
        # Python 3.11+ behavior pin: `asyncio.wait_for` AWAITS
        # the cancellation (the runner's CancelledError-driven
        # cleanup) before raising `TimeoutError`. So by the time
        # the kernel's `except TimeoutError` returns, the runner's
        # `finally` HAS ALREADY run. Assert `cleaned` BEFORE any
        # additional event-loop tick so the test pins the
        # synchronous-on-the-loop ordering, not a "eventually"
        # property. The pyproject `requires-python = ">=3.11"`
        # makes this assertion safe on every supported version.
        assert cleaned, (
            "runner cleanup did not run synchronously on async timeout. "
            "Python 3.11+ wait_for awaits cancellation before raising "
            "TimeoutError; if this assertion fails, either the Python "
            "floor moved or wait_for semantics changed."
        )


# ---------------------------------------------------------------------------
# Generic exception
# ---------------------------------------------------------------------------


class TestException:
    async def test_runner_exception_classified(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        async def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise ValueError("upstream service unreachable")

        result = await replay_one_trace_async(
            trace_id=_TEST_TRACE_ID,
            cohort="failure",
            trace_input=trace_input,
            config=config,
            tool_cache=empty_loose_cache,
            runner=runner,
            timeout_seconds=2.0,
        )
        assert isinstance(result, ReplayFailure)
        assert result.code == "runner_exception"
        assert result.details["exception_type"] == "ValueError"


# ---------------------------------------------------------------------------
# External cancellation propagates (cardinal #1 boundary)
# ---------------------------------------------------------------------------


class TestExternalCancellation:
    async def test_external_cancellation_propagates(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        # Pin: when an OUTSIDE cancellation arrives (caller
        # cancelled the kernel's own task), CancelledError
        # propagates as-is. NOT swept into runner_exception.
        # Cardinal #1 covers expected failures, not BaseException
        # signals (CancelledError inherits BaseException since
        # Python 3.8).
        async def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            await asyncio.sleep(5.0)
            return ReplayOutput(text="x")

        # Run the kernel inside a Task we cancel from the outside.
        kernel_task: asyncio.Task[object] = asyncio.create_task(
            replay_one_trace_async(
                trace_id=_TEST_TRACE_ID,
                cohort="failure",
                trace_input=trace_input,
                config=config,
                tool_cache=empty_loose_cache,
                runner=runner,
                timeout_seconds=10.0,  # well past our cancel
            )
        )
        # Let the kernel start, then cancel.
        await asyncio.sleep(0.05)
        kernel_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await kernel_task
