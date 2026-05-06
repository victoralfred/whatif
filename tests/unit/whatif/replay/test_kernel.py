"""Tests for `whatif.replay.kernel.replay_one_trace` — Phase 6.3a
per-trace replay kernel.

Pin properties:

1. Clean runner returns `ReplaySuccess` carrying the runner's
   `ReplayOutput`.
2. Runner that raises `CacheMissError` (via the strict tool cache)
   produces `ReplayFailure(code="tool_cache_miss")` with the
   registry-required `tool_name` detail.
3. Runner that exceeds the timeout produces `ReplayFailure(code=
   "runner_timeout")` with the `timeout_seconds` detail.
4. Runner that raises any other exception produces `ReplayFailure(
   code="runner_exception")` with `exception_type` and `message`.
5. The kernel never raises — every classified failure is structured
   data per cardinal #1.
6. The classification is order-correct: a `CacheMissError` is
   caught as `tool_cache_miss`, NOT swept into `runner_exception`.
"""

from __future__ import annotations

import time

import pytest

from whatif.contract import ReplayConfig, ReplayOutput, ToolCache, TraceInput
from whatif.replay import (
    ReplayFailure,
    ReplaySuccess,
    replay_one_trace,
)
from whatif.replay.tool_cache import make_strict_tool_cache

# Shared constant for the test trace_id. Both the strict-cache
# fixture and the kernel invocations consume this so a future
# variant that drifts the cache's trace_id from the kernel's
# would surface visibly here rather than silently passing.
_TEST_TRACE_ID = "t-1"


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
# Success path
# ---------------------------------------------------------------------------


class TestSuccess:
    def test_clean_runner_returns_replay_success(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            return ReplayOutput(text=f"echo: {ti.user_message}")

        result = replay_one_trace(
            trace_id=_TEST_TRACE_ID,
            cohort="failure",
            trace_input=trace_input,
            config=config,
            tool_cache=empty_loose_cache,
            runner=runner,
            timeout_seconds=2.0,
        )

        assert isinstance(result, ReplaySuccess)
        assert result.trace_id == _TEST_TRACE_ID
        assert result.cohort == "failure"
        assert result.output.text == "echo: hello"


# ---------------------------------------------------------------------------
# Cache-miss classification
# ---------------------------------------------------------------------------


class TestCacheMissClassification:
    def test_cache_miss_produces_typed_failure(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_strict_cache: ToolCache,
    ) -> None:
        # Runner calls into a strict cache that has no matching
        # entry. CacheMissError escapes the runner; kernel converts.
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            tc.lookup("get_weather", {"city": "Tokyo"})
            return ReplayOutput(text="never reached")

        result = replay_one_trace(
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
        assert result.trace_id == _TEST_TRACE_ID
        assert result.cohort == "failure"
        assert result.details["tool_name"] == "get_weather"


# ---------------------------------------------------------------------------
# Timeout classification
# ---------------------------------------------------------------------------


class TestTimeoutClassification:
    def test_slow_runner_produces_runner_timeout(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        # Runner sleeps past the timeout. The kernel returns the
        # typed failure immediately; the leaked thread runs to
        # completion in the background (Python can't kill threads).
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            time.sleep(2.0)  # well past the 0.1s timeout below
            return ReplayOutput(text="never returned")

        start = time.monotonic()
        result = replay_one_trace(
            trace_id=_TEST_TRACE_ID,
            cohort="failure",
            trace_input=trace_input,
            config=config,
            tool_cache=empty_loose_cache,
            runner=runner,
            timeout_seconds=0.1,
        )
        elapsed = time.monotonic() - start

        assert isinstance(result, ReplayFailure)
        assert result.code == "runner_timeout"
        assert result.trace_id == _TEST_TRACE_ID
        # Schema-type pin: timeout_seconds emitted as float, NOT
        # int. The kernel's _timeout_failure converts via
        # `float(timeout_seconds)` for shape consistency. A future
        # contributor reverting to "int when whole, else float"
        # would fail this isinstance check.
        ts = result.details["timeout_seconds"]
        assert isinstance(ts, float)
        assert ts == 0.1
        # The kernel must not block past the timeout — pin a
        # generous upper bound (10x) so a future regression that
        # accidentally waits for the runner to finish surfaces here.
        assert elapsed < 1.0, (
            f"kernel blocked for {elapsed:.2f}s after timeout — "
            "should return immediately and let the thread leak"
        )


# ---------------------------------------------------------------------------
# Generic exception classification
# ---------------------------------------------------------------------------


class TestExceptionClassification:
    def test_runner_exception_produces_typed_failure(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise ValueError("upstream service unreachable")

        result = replay_one_trace(
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
        assert "upstream service unreachable" in result.details["message"]

    def test_long_exception_message_truncated(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        # Defense: a runner that raises with a giant message must
        # not bloat the report. The kernel truncates at 2048 chars.
        big = "x" * 5000

        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise RuntimeError(big)

        result = replay_one_trace(
            trace_id=_TEST_TRACE_ID,
            cohort="failure",
            trace_input=trace_input,
            config=config,
            tool_cache=empty_loose_cache,
            runner=runner,
            timeout_seconds=2.0,
        )

        assert isinstance(result, ReplayFailure)
        msg = result.details["message"]
        assert isinstance(msg, str)
        # Truncation contract: 2048 chars of original + suffix.
        # Pinned exactly so an off-by-one in the `<=` boundary
        # surfaces (the previous `<= 2048 + len(suffix)` was a
        # weaker upper bound).
        assert msg == ("x" * 2048) + "...(truncated)"

    def test_truncation_boundary_at_exactly_2048(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        # Exactly 2048 chars: NO truncation suffix. The kernel
        # condition is `if len(raw_message) <= 2048` — at exactly
        # 2048, we keep the message as-is.
        boundary = "x" * 2048

        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise RuntimeError(boundary)

        result = replay_one_trace(
            trace_id=_TEST_TRACE_ID,
            cohort="failure",
            trace_input=trace_input,
            config=config,
            tool_cache=empty_loose_cache,
            runner=runner,
            timeout_seconds=2.0,
        )
        assert isinstance(result, ReplayFailure)
        msg = result.details["message"]
        assert msg == boundary
        assert "...(truncated)" not in msg

    def test_truncation_boundary_at_2049(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        # Exactly 2049 chars: TRUNCATION fires. One char over the
        # boundary is enough to trigger the suffix path. Pins the
        # off-by-one direction precisely.
        over = "x" * 2049

        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise RuntimeError(over)

        result = replay_one_trace(
            trace_id=_TEST_TRACE_ID,
            cohort="failure",
            trace_input=trace_input,
            config=config,
            tool_cache=empty_loose_cache,
            runner=runner,
            timeout_seconds=2.0,
        )
        assert isinstance(result, ReplayFailure)
        msg = result.details["message"]
        assert msg == ("x" * 2048) + "...(truncated)"


# ---------------------------------------------------------------------------
# Order: CacheMissError NOT classified as runner_exception
# ---------------------------------------------------------------------------


class TestOrderCorrect:
    def test_cache_miss_is_not_misclassified_as_runner_exception(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_strict_cache: ToolCache,
    ) -> None:
        # Defense against catch-order regression: if a future
        # refactor moved the bare-Exception catch BEFORE the
        # CacheMissError catch, a cache miss would be mis-classified
        # as `runner_exception` and the report would be wrong.
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            tc.lookup("missing", {})
            return ReplayOutput(text="x")

        result = replay_one_trace(
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
        # NOT runner_exception:
        assert result.code != "runner_exception"

    def test_runner_raising_cache_miss_directly_is_classified_as_tool_cache_miss(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        # Defense against the integration gap: the catch-order test
        # above goes through the strict cache's `lookup`, which IS
        # the canonical path. This test exercises the exception
        # path DIRECTLY — a runner that constructs CacheMissError
        # and raises it without touching the cache. Pins that the
        # kernel's classification depends only on the EXCEPTION
        # TYPE, not on which call site raised it. If a future
        # refactor changed CacheMissError's class hierarchy (e.g.,
        # making it not inherit Exception), this test would fail
        # alongside the strict-cache integration test, surfacing
        # the change at the kernel boundary specifically.
        from whatif.replay.tool_cache import CacheMissError

        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise CacheMissError(trace_id="t-1", tool_name="direct", arg_count=0)

        result = replay_one_trace(
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
        assert result.details["tool_name"] == "direct"


# ---------------------------------------------------------------------------
# Kernel never raises (cardinal #1 boundary)
# ---------------------------------------------------------------------------


class TestNeverRaises:
    def test_kernel_propagates_base_exception(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        # Cardinal #1 covers EXPECTED failures (cache miss, timeout,
        # runner exception). It does NOT cover programmer-bug exit
        # signals — `KeyboardInterrupt` and `SystemExit` inherit from
        # `BaseException`, not `Exception`, so the kernel's
        # `except Exception` does NOT catch them. These propagate
        # out to the caller, which is the right behavior: a runner
        # raising SystemExit during replay is a bug, not data.
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise SystemExit("don't catch me")

        with pytest.raises(SystemExit):
            replay_one_trace(
                trace_id=_TEST_TRACE_ID,
                cohort="failure",
                trace_input=trace_input,
                config=config,
                tool_cache=empty_loose_cache,
                runner=runner,
                timeout_seconds=2.0,
            )

    def test_kernel_does_not_raise_for_expected_failures(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        empty_loose_cache: ToolCache,
    ) -> None:
        # Pin the cardinal #1 boundary: a runner that raises a
        # plain Exception subclass returns a typed failure, not a
        # propagated exception. The classification-shape tests cover
        # the variants individually; this test pins the no-raise
        # property at the kernel boundary.
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise ValueError("structured failure, not exception")

        result = replay_one_trace(
            trace_id=_TEST_TRACE_ID,
            cohort="failure",
            trace_input=trace_input,
            config=config,
            tool_cache=empty_loose_cache,
            runner=runner,
            timeout_seconds=2.0,
        )
        # No raise reached this assertion.
        assert isinstance(result, ReplayFailure)


# ---------------------------------------------------------------------------
# CPython futures unwrap-re-raise behavior pin
# ---------------------------------------------------------------------------


class TestFuturesUnwrapBehavior:
    def test_future_result_re_raises_original_exception_unwrapped(self) -> None:
        # The kernel's CacheMissError catch-order argument relies on
        # `concurrent.futures.Future.result()` re-raising the worker
        # thread's exception UNWRAPPED — i.e., as the original type,
        # not a "thread exception" wrapper. CPython implements this
        # via `_invoke_callbacks` storing `self._exception = exc` and
        # `result()` doing `raise self._exception`.
        #
        # This test runs that contract directly against the
        # `concurrent.futures` API (not through the kernel) so a
        # future Python that wrapped exceptions surfaces here as a
        # type mismatch, with a clear message pointing at the kernel
        # contract that depends on this behavior.
        from concurrent.futures import ThreadPoolExecutor

        class _SentinelError(Exception):
            pass

        def _raise() -> None:
            raise _SentinelError("from worker")

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_raise)
            with pytest.raises(_SentinelError) as excinfo:
                future.result()

        assert type(excinfo.value) is _SentinelError, (
            "concurrent.futures.Future.result() wrapped the worker "
            f"exception (got {type(excinfo.value).__name__}). The "
            "kernel's CacheMissError catch-order in replay_one_trace "
            "depends on unwrapped re-raise — see kernel.py docstring."
        )
        assert str(excinfo.value) == "from worker"
