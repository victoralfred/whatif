"""Tests for `whatifd.replay.pipeline.replay_stream` — Phase 6.3b
streaming pipeline.

Pin properties:

1. Each input bundle produces exactly one output `ReplayResult`.
2. Bundles all return the right `trace_id` (no swap).
3. Bundle counts are preserved (10 in, 10 out; 0 in, 0 out).
4. `max_workers < 1` rejected at the boundary.
5. Mixed success/failure: success and failure bundles in the same
   stream both produce their typed results.
6. Bounded concurrency: with `max_workers=2`, at most 2 runners
   execute concurrently (probe via barrier counters).
7. Lazy input consumption: large iterables don't materialize.
"""

from __future__ import annotations

import threading
import time

import pytest

from whatifd.contract import ReplayConfig, ReplayOutput, ToolCache, TraceInput
from whatifd.replay import (
    ReplayFailure,
    ReplayInputBundle,
    ReplaySuccess,
    replay_stream,
)


def _bundle(trace_id: str, runner) -> ReplayInputBundle:
    return ReplayInputBundle(
        trace_id=trace_id,
        cohort="failure",
        trace_input=TraceInput(user_message=trace_id),
        config=ReplayConfig(system_prompt="x"),
        tool_cache=ToolCache(cache={}, policy="use-original"),
        runner=runner,
    )


def _echo_runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
    return ReplayOutput(text=f"echo: {ti.user_message}")


# ---------------------------------------------------------------------------
# Basic correctness
# ---------------------------------------------------------------------------


class TestBasic:
    def test_empty_input_yields_nothing(self) -> None:
        results = list(replay_stream([], max_workers=2, timeout_seconds=2.0))
        assert results == []

    def test_single_bundle(self) -> None:
        results = list(
            replay_stream([_bundle("t-1", _echo_runner)], max_workers=2, timeout_seconds=2.0)
        )
        assert len(results) == 1
        result = results[0]
        assert isinstance(result, ReplaySuccess)
        assert result.trace_id == "t-1"
        assert result.output.text == "echo: t-1"

    def test_count_preserved(self) -> None:
        bundles = [_bundle(f"t-{i}", _echo_runner) for i in range(10)]
        results = list(replay_stream(bundles, max_workers=3, timeout_seconds=2.0))
        assert len(results) == 10

    def test_trace_ids_preserved_no_swap(self) -> None:
        # Each result's trace_id matches one input. No bundle swap;
        # no missing or duplicated trace_id.
        bundles = [_bundle(f"t-{i}", _echo_runner) for i in range(10)]
        results = list(replay_stream(bundles, max_workers=4, timeout_seconds=2.0))
        result_ids = {r.trace_id for r in results}
        input_ids = {f"t-{i}" for i in range(10)}
        assert result_ids == input_ids


# ---------------------------------------------------------------------------
# Mixed success / failure
# ---------------------------------------------------------------------------


class TestMixed:
    def test_success_and_failure_in_same_stream(self) -> None:
        def good(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            return ReplayOutput(text="ok")

        def bad(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            raise ValueError("nope")

        bundles = [
            _bundle("ok-1", good),
            _bundle("bad-1", bad),
            _bundle("ok-2", good),
            _bundle("bad-2", bad),
        ]
        results = {
            r.trace_id: r for r in replay_stream(bundles, max_workers=2, timeout_seconds=2.0)
        }

        assert isinstance(results["ok-1"], ReplaySuccess)
        assert isinstance(results["ok-2"], ReplaySuccess)
        assert isinstance(results["bad-1"], ReplayFailure)
        assert results["bad-1"].code == "runner_exception"
        assert isinstance(results["bad-2"], ReplayFailure)
        assert results["bad-2"].code == "runner_exception"


# ---------------------------------------------------------------------------
# Bounded concurrency
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_max_workers_bound_observed(self) -> None:
        # Probe the bound by counting concurrent runner entries via a
        # threading.Lock-protected counter. With max_workers=2, the
        # peak should be <= 2 even when 8 bundles are submitted.
        #
        # Scope of the lock-protected counter: it measures
        # RUNNER-level concurrency (how many user-runner functions
        # are inside their `time.sleep` simultaneously). This is the
        # observable that matches the user-facing contract — "no
        # more than max_workers runners run concurrently". The
        # outer streaming pool's worker count is an implementation
        # detail; user code only sees runner invocations. So the
        # peak <= max_workers assertion is the right load-bearing
        # check, and an off-by-one in the streaming layer's slide
        # logic would surface here as runner concurrency violation.
        #
        # NOTE on OS-thread count vs runner concurrency: the
        # double-executor pattern means peak OS threads can reach
        # 2 * max_workers (one outer streaming worker + one inner
        # kernel-timeout worker per concurrent kernel). This test
        # does NOT assert against thread count — it asserts against
        # the user-facing concurrency contract. Don't conflate the
        # two: an off-by-one in OS-thread bookkeeping would NOT
        # fail this test.
        active = 0
        peak = 0
        lock = threading.Lock()

        def slow_runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.05)  # hold the slot long enough to overlap
            with lock:
                active -= 1
            return ReplayOutput(text="ok")

        bundles = [_bundle(f"t-{i}", slow_runner) for i in range(8)]
        results = list(replay_stream(bundles, max_workers=2, timeout_seconds=5.0))

        assert len(results) == 8
        assert peak <= 2, f"max_workers=2 violated: peak concurrent runners = {peak}"

    def test_max_workers_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_workers must be >= 1"):
            list(replay_stream([], max_workers=0, timeout_seconds=2.0))

    def test_max_workers_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_workers must be >= 1"):
            list(replay_stream([], max_workers=-1, timeout_seconds=2.0))


# ---------------------------------------------------------------------------
# Streaming semantics (lazy input consumption)
# ---------------------------------------------------------------------------


class TestStreaming:
    def test_input_consumed_lazily(self) -> None:
        # The input is a generator that records how many bundles
        # have been pulled. After the first result is yielded, the
        # pulled count should be at most max_workers + 1 (the prime
        # plus one slide). This pins that the streaming layer
        # doesn't eagerly drain the iterator.
        pulled = 0

        def bundle_gen():
            nonlocal pulled
            for i in range(100):
                pulled += 1
                yield _bundle(f"t-{i}", _echo_runner)

        # Single source of truth for the worker count: passed to
        # both `replay_stream` and the bound assertion below so a
        # future tuning change can't silently drift one without
        # the other.
        workers = 3
        stream = replay_stream(bundle_gen(), max_workers=workers, timeout_seconds=2.0)

        # Pull just the first result.
        first = next(stream)
        # ReplayResult is a Union[ReplaySuccess, ReplayFailure];
        # `isinstance` against the Union itself is vacuous in
        # Python. Assert against the concrete variants instead.
        assert isinstance(first, (ReplaySuccess, ReplayFailure))

        # Sliding-window invariant: at the moment the first result
        # is yielded, at most `max_workers` bundles have been
        # primed plus one slide for the just-completed slot. Tight
        # bound (`<= max_workers + 1`) so a future change to the
        # priming logic surfaces immediately rather than hiding
        # behind a generous `<100` upper bound.
        # Race-condition note: the priming step submits N bundles
        # (each pulls from the iterator) and the wait+slide step
        # pulls one more after a completion. Under normal
        # scheduling `pulled` lands at exactly `workers + 1` when
        # the first result arrives. If a future scheduling change
        # causes the priming submit to overlap with the first
        # completion such that the slide pulls before the first
        # `next()` returns, `pulled` could in principle be
        # `workers + 2`. Currently neither path appears in
        # practice, but if this test flakes intermittently in CI,
        # widening to `workers + 2` is the right adjustment — NOT
        # falling back to a loose `< 100` bound that hides real
        # priming-logic regressions.
        assert pulled <= workers + 1, (
            f"streaming layer drained {pulled} bundles before "
            f"yielding the first result; sliding-window bound is "
            f"max_workers + 1 = {workers + 1}"
        )

        # Drain the rest so the executor shuts down cleanly.
        list(stream)

    def test_max_workers_one_processes_all_bundles_sequentially(self) -> None:
        # Regression guard: max_workers=1 is the boundary value of
        # the >= 1 check. Confirms the priming + sliding-window
        # logic doesn't accidentally require max_workers >= 2.
        bundles = [_bundle(f"t-{i}", _echo_runner) for i in range(5)]
        results = list(replay_stream(bundles, max_workers=1, timeout_seconds=2.0))
        assert len(results) == 5
        assert {r.trace_id for r in results} == {f"t-{i}" for i in range(5)}

    def test_timeout_in_one_bundle_does_not_block_others(self) -> None:
        # A single timing-out bundle in a stream must not block the
        # rest. Pin: with max_workers=2, a slow runner on bundle 0
        # still allows the fast bundles to yield. The slow one
        # eventually surfaces as a runner_timeout failure.
        def slow_runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            time.sleep(2.0)  # past the 0.1s timeout below
            return ReplayOutput(text="never returned")

        bundles = [
            _bundle("slow-0", slow_runner),
            _bundle("fast-1", _echo_runner),
            _bundle("fast-2", _echo_runner),
            _bundle("fast-3", _echo_runner),
        ]

        start = time.monotonic()
        results = {
            r.trace_id: r for r in replay_stream(bundles, max_workers=2, timeout_seconds=0.1)
        }
        elapsed = time.monotonic() - start

        # All four bundles produced a result.
        assert set(results.keys()) == {"slow-0", "fast-1", "fast-2", "fast-3"}
        # Three fast bundles are successes; the slow one is a
        # runner_timeout failure.
        assert isinstance(results["slow-0"], ReplayFailure)
        assert results["slow-0"].code == "runner_timeout"
        for fast_id in ("fast-1", "fast-2", "fast-3"):
            assert isinstance(results[fast_id], ReplaySuccess)
        # Stream completes in well under the 2s the slow runner
        # takes — the timeout doesn't serialize behind the leaked
        # thread. Allow generous headroom for test-runner overhead.
        assert elapsed < 1.5, (
            f"stream blocked for {elapsed:.2f}s — timeout serialized "
            "behind the leaked runner thread (cascade-catalog "
            "constraint violated)"
        )


# ---------------------------------------------------------------------------
# Bundle data carrier
# ---------------------------------------------------------------------------


class TestBundle:
    def test_bundle_is_frozen(self) -> None:
        b = _bundle("t-1", _echo_runner)
        with pytest.raises(AttributeError):
            b.trace_id = "t-2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Trampoline signature coupling
# ---------------------------------------------------------------------------


class TestCallKernelTrampoline:
    def test_trampoline_forwards_all_bundle_fields_to_kernel(self) -> None:
        # `_call_kernel` adapts a `ReplayInputBundle` into the
        # kernel's keyword-only signature. If `replay_one_trace`
        # gains a parameter (e.g., per-bundle timeout in Phase 6.3c)
        # the trampoline MUST be updated alongside it. This test
        # closes the gap by capturing what the kernel actually
        # received and asserting every bundle field landed on the
        # right kernel parameter.
        from whatifd.replay.pipeline import _call_kernel

        captured: dict[str, object] = {}

        def runner(ti: TraceInput, cfg: ReplayConfig, tc: ToolCache) -> ReplayOutput:
            captured["trace_input_msg"] = ti.user_message
            captured["config_prompt"] = cfg.system_prompt
            captured["cache_policy"] = tc.policy
            return ReplayOutput(text="ok")

        b = ReplayInputBundle(
            trace_id="t-trampoline",
            cohort="failure",
            trace_input=TraceInput(user_message="probe-input"),
            config=ReplayConfig(system_prompt="probe-prompt"),
            tool_cache=ToolCache(cache={}, policy="use-original"),
            runner=runner,
        )

        result = _call_kernel(b, timeout_seconds=2.0)

        # Kernel got the bundle's runner with the bundle's args.
        assert isinstance(result, ReplaySuccess)
        assert result.trace_id == "t-trampoline"
        assert result.cohort == "failure"
        assert captured["trace_input_msg"] == "probe-input"
        assert captured["config_prompt"] == "probe-prompt"
        assert captured["cache_policy"] == "use-original"
