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

from whatif.contract import ReplayConfig, ReplayOutput, ToolCache, TraceInput
from whatif.replay import (
    ReplayFailure,
    ReplaySuccess,
    replay_one_trace,
)
from whatif.replay.tool_cache import make_strict_tool_cache


def _input() -> TraceInput:
    return TraceInput(user_message="hello")


def _config() -> ReplayConfig:
    return ReplayConfig(system_prompt="be helpful")


def _empty_strict_cache() -> ToolCache:
    return make_strict_tool_cache({}, trace_id="t-1")


def _empty_loose_cache() -> ToolCache:
    return ToolCache(cache={}, policy="use-original")


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


class TestSuccess:
    def test_clean_runner_returns_replay_success(self) -> None:
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            return ReplayOutput(text=f"echo: {ti.user_message}")

        result = replay_one_trace(
            trace_id="t-1",
            cohort="failure",
            trace_input=_input(),
            config=_config(),
            tool_cache=_empty_loose_cache(),
            runner=runner,
            timeout_seconds=2.0,
        )

        assert isinstance(result, ReplaySuccess)
        assert result.trace_id == "t-1"
        assert result.cohort == "failure"
        assert result.output.text == "echo: hello"


# ---------------------------------------------------------------------------
# Cache-miss classification
# ---------------------------------------------------------------------------


class TestCacheMissClassification:
    def test_cache_miss_produces_typed_failure(self) -> None:
        # Runner calls into a strict cache that has no matching
        # entry. CacheMissError escapes the runner; kernel converts.
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            tc.lookup("get_weather", {"city": "Tokyo"})
            return ReplayOutput(text="never reached")

        result = replay_one_trace(
            trace_id="t-1",
            cohort="failure",
            trace_input=_input(),
            config=_config(),
            tool_cache=_empty_strict_cache(),
            runner=runner,
            timeout_seconds=2.0,
        )

        assert isinstance(result, ReplayFailure)
        assert result.code == "tool_cache_miss"
        assert result.trace_id == "t-1"
        assert result.cohort == "failure"
        assert result.details["tool_name"] == "get_weather"


# ---------------------------------------------------------------------------
# Timeout classification
# ---------------------------------------------------------------------------


class TestTimeoutClassification:
    def test_slow_runner_produces_runner_timeout(self) -> None:
        # Runner sleeps past the timeout. The kernel returns the
        # typed failure immediately; the leaked thread runs to
        # completion in the background (Python can't kill threads).
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            time.sleep(2.0)  # well past the 0.1s timeout below
            return ReplayOutput(text="never returned")

        start = time.monotonic()
        result = replay_one_trace(
            trace_id="t-1",
            cohort="failure",
            trace_input=_input(),
            config=_config(),
            tool_cache=_empty_loose_cache(),
            runner=runner,
            timeout_seconds=0.1,
        )
        elapsed = time.monotonic() - start

        assert isinstance(result, ReplayFailure)
        assert result.code == "runner_timeout"
        assert result.trace_id == "t-1"
        assert result.details["timeout_seconds"] == 0.1
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
    def test_runner_exception_produces_typed_failure(self) -> None:
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise ValueError("upstream service unreachable")

        result = replay_one_trace(
            trace_id="t-1",
            cohort="failure",
            trace_input=_input(),
            config=_config(),
            tool_cache=_empty_loose_cache(),
            runner=runner,
            timeout_seconds=2.0,
        )

        assert isinstance(result, ReplayFailure)
        assert result.code == "runner_exception"
        assert result.details["exception_type"] == "ValueError"
        assert "upstream service unreachable" in result.details["message"]

    def test_long_exception_message_truncated(self) -> None:
        # Defense: a runner that raises with a giant message must
        # not bloat the report. The kernel truncates at 2048 chars.
        big = "x" * 5000

        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise RuntimeError(big)

        result = replay_one_trace(
            trace_id="t-1",
            cohort="failure",
            trace_input=_input(),
            config=_config(),
            tool_cache=_empty_loose_cache(),
            runner=runner,
            timeout_seconds=2.0,
        )

        assert isinstance(result, ReplayFailure)
        msg = result.details["message"]
        assert isinstance(msg, str)
        assert len(msg) <= 2048 + len("...(truncated)")
        assert msg.endswith("...(truncated)")


# ---------------------------------------------------------------------------
# Order: CacheMissError NOT classified as runner_exception
# ---------------------------------------------------------------------------


class TestOrderCorrect:
    def test_cache_miss_is_not_misclassified_as_runner_exception(self) -> None:
        # Defense against catch-order regression: if a future
        # refactor moved the bare-Exception catch BEFORE the
        # CacheMissError catch, a cache miss would be mis-classified
        # as `runner_exception` and the report would be wrong.
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            tc.lookup("missing", {})
            return ReplayOutput(text="x")

        result = replay_one_trace(
            trace_id="t-1",
            cohort="failure",
            trace_input=_input(),
            config=_config(),
            tool_cache=_empty_strict_cache(),
            runner=runner,
            timeout_seconds=2.0,
        )

        assert isinstance(result, ReplayFailure)
        assert result.code == "tool_cache_miss"
        # NOT runner_exception:
        assert result.code != "runner_exception"


# ---------------------------------------------------------------------------
# Kernel never raises (cardinal #1 boundary)
# ---------------------------------------------------------------------------


class TestNeverRaises:
    def test_kernel_swallows_all_runner_exceptions(self) -> None:
        # Even a SystemExit from a misbehaving runner should be
        # caught and converted (SystemExit inherits from BaseException
        # not Exception, so this would NOT be caught by `except
        # Exception` — pin that the kernel intentionally lets
        # BaseException through, since system-exit-during-replay is
        # a programmer bug, not failure-as-data).
        #
        # This pin documents the boundary: cardinal #1 covers
        # EXPECTED failures. Programmer-bug exceptions (KeyboardInterrupt,
        # SystemExit) are NOT failure-as-data and propagate.
        import pytest

        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise SystemExit("don't catch me")

        with pytest.raises(SystemExit):
            replay_one_trace(
                trace_id="t-1",
                cohort="failure",
                trace_input=_input(),
                config=_config(),
                tool_cache=_empty_loose_cache(),
                runner=runner,
                timeout_seconds=2.0,
            )

    def test_kernel_does_not_raise_for_expected_failures(self) -> None:
        # Pin the cardinal #1 boundary: a runner that raises a
        # plain Exception subclass returns a typed failure, not a
        # propagated exception. The classification-shape tests cover
        # the variants individually; this test pins the no-raise
        # property at the kernel boundary.
        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise ValueError("structured failure, not exception")

        result = replay_one_trace(
            trace_id="t-1",
            cohort="failure",
            trace_input=_input(),
            config=_config(),
            tool_cache=_empty_loose_cache(),
            runner=runner,
            timeout_seconds=2.0,
        )
        # No raise reached this assertion.
        assert isinstance(result, ReplayFailure)
