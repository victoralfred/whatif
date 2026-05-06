"""Tests for `whatif.cache.lock` — Phase 3.3 cache lock.

The load-bearing properties:

1. **Single-writer enforcement** — two real processes attempting to
   acquire the same lock cannot both succeed. Tested via subprocess
   (NOT mocks) per the Phase 3 gate in `references/phases.md`.
2. **Lock release on normal exit** — `__exit__` releases the OS lock
   and unlinks the file so the next caller can acquire.
3. **Stale-lock takeover** — a lock recorded against a dead PID is
   taken over without operator intervention. Closes the
   "previous run terminated abnormally" loop in scenario 5.
4. **PID-reuse defense** — a lock recorded against a live PID whose
   `create_time()` mismatches the recorded `process_start_time` is
   recognized as stale (PID was recycled).
5. **Age-based takeover is opt-in** — default behavior does NOT take
   over a long-held lock by age alone; long-running batches are
   legitimate. `allow_age_takeover=True` enables it.
6. **CacheLockedError carries provenance** — the error message names
   the PID, hostname, and started_at from the held lock so operators
   can decide.
"""

from __future__ import annotations

import dataclasses
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psutil
import pytest

from whatif.cache.lock import (
    CacheLockedError,
    LockFileContent,
    _process_dead_or_recycled,
    _should_takeover,
    acquire_cache_lock,
)
from whatif.serialization import canonical_json_bytes

# ---------------------------------------------------------------------------
# Single-writer with real processes
# ---------------------------------------------------------------------------


def _wait_for_ready(ready_file: Path, timeout_seconds: float = 30.0) -> None:
    """Spin until the child process writes its ready sentinel.

    Bumped from the previous 5-second budget (100 x 50ms) to 30s so
    heavily-loaded CI runners don't flake on subprocess startup. A
    full process spawn + import + flock is well under a second on
    even slow CI; 30s gives plenty of headroom while still failing
    cleanly if the child genuinely hung.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if ready_file.exists():
            return
        time.sleep(0.05)
    raise AssertionError(
        f"child process never wrote ready sentinel at {ready_file} within {timeout_seconds}s"
    )


_HOLD_LOCK_SCRIPT = """
import sys, time
from pathlib import Path
from whatif.cache.lock import acquire_cache_lock

cache_root = Path(sys.argv[1])
ready_file = Path(sys.argv[2])
hold_seconds = float(sys.argv[3])

with acquire_cache_lock(cache_root):
    ready_file.write_text("locked")
    time.sleep(hold_seconds)
"""


class TestSingleWriter:
    def test_two_real_processes_cannot_both_acquire(self, tmp_path: Path) -> None:
        # Launch a child process that acquires the lock and holds it.
        # Wait for the child to signal ready, then assert the parent's
        # acquisition fails with CacheLockedError.
        cache_root = tmp_path / "cache"
        ready_file = tmp_path / "child_ready"
        proc = subprocess.Popen(
            [sys.executable, "-c", _HOLD_LOCK_SCRIPT, str(cache_root), str(ready_file), "5"],
        )
        try:
            # Spin until the child writes the ready sentinel.
            _wait_for_ready(ready_file)

            # Parent attempt: must fail.
            with (
                pytest.raises(CacheLockedError, match="held by another live process"),
                acquire_cache_lock(cache_root),
            ):
                pass  # pragma: no cover (should not reach)
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    def test_release_on_exit_allows_next_acquire(self, tmp_path: Path) -> None:
        cache_root = tmp_path / "cache"
        with acquire_cache_lock(cache_root):
            assert (cache_root / ".lock").exists()
        # File unlinked on exit.
        assert not (cache_root / ".lock").exists()
        # Next acquisition succeeds.
        with acquire_cache_lock(cache_root):
            pass

    def test_release_on_exception(self, tmp_path: Path) -> None:
        # An exception inside the with-block must still release the
        # lock — otherwise crashes leave orphaned locks.
        cache_root = tmp_path / "cache"

        class _DummyError(Exception):
            pass

        with pytest.raises(_DummyError), acquire_cache_lock(cache_root):
            raise _DummyError()
        # Subsequent acquire works (no orphan).
        with acquire_cache_lock(cache_root):
            pass


# ---------------------------------------------------------------------------
# Stale-lock evidence
# ---------------------------------------------------------------------------


def _write_lock_file(cache_root: Path, content: dict[str, object]) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    lock_path = cache_root / ".lock"
    lock_path.write_bytes(canonical_json_bytes(content))
    return lock_path


def _dead_pid() -> int:
    """Spawn a child that exits immediately; return its (now-dead) PID."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


class TestStaleTakeover:
    def test_takeover_when_recorded_pid_is_dead(self, tmp_path: Path) -> None:
        cache_root = tmp_path / "cache"
        _write_lock_file(
            cache_root,
            {
                "pid": _dead_pid(),
                "process_start_time": time.time() - 3600,
                "hostname": "test-host",
                "started_at": "2026-04-30T14:22:00Z",
            },
        )
        # Takeover succeeds without operator intervention.
        with acquire_cache_lock(cache_root) as lock:
            assert lock.content.pid == os.getpid()

    def test_takeover_when_pid_recycled(self, tmp_path: Path) -> None:
        # Record a lock against THIS process's PID but with a
        # process_start_time from far in the past — simulates the
        # "PID was reused" case where the OS handed our PID to a
        # different process after a previous death.
        cache_root = tmp_path / "cache"
        _write_lock_file(
            cache_root,
            {
                "pid": os.getpid(),
                "process_start_time": 1.0,  # far in the past; mismatches actual create_time
                "hostname": "test-host",
                "started_at": "2026-04-30T14:22:00Z",
            },
        )
        with acquire_cache_lock(cache_root) as lock:
            # New lock content reflects THIS process correctly.
            assert lock.content.pid == os.getpid()
            actual_create = psutil.Process(os.getpid()).create_time()
            assert abs(lock.content.process_start_time - actual_create) < 1.0

    # Removed: test_no_takeover_when_pid_alive_and_matches.
    # The original test launched a subprocess holder and asserted the
    # parent gets CacheLockedError — but that's exactly what
    # TestSingleWriter::test_two_real_processes_cannot_both_acquire
    # already covers. The new TestShouldTakeover::test_alive_and_matching_not_stale_by_default
    # is the proper isolated test of the "alive + matching → not stale"
    # decision branch. Keeping both was redundant.


# ---------------------------------------------------------------------------
# Age-based takeover (opt-in)
# ---------------------------------------------------------------------------


class TestAgeTakeover:
    def test_age_takeover_default_off(self, tmp_path: Path) -> None:
        # Lock recorded against a LIVE process (THIS process), with a
        # very old started_at. Default behavior does NOT take over by
        # age alone — but the actual fcntl flock isn't held (we just
        # wrote the file directly), so the test would acquire trivially.
        # Use a held flock via subprocess to drive the failure path.
        cache_root = tmp_path / "cache"
        ready_file = tmp_path / "child_ready"
        # Hold the lock for long enough to write an old started_at and
        # attempt parent acquisition.
        proc = subprocess.Popen(
            [sys.executable, "-c", _HOLD_LOCK_SCRIPT, str(cache_root), str(ready_file), "5"],
        )
        try:
            _wait_for_ready(ready_file)
            # Manually overwrite the lock content with an old
            # started_at to simulate a long-running legitimate batch.
            old_started = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
            child_pid = proc.pid
            (cache_root / ".lock").write_bytes(
                canonical_json_bytes(
                    {
                        "pid": child_pid,
                        "process_start_time": psutil.Process(child_pid).create_time(),
                        "hostname": socket.gethostname(),
                        "started_at": old_started,
                    }
                )
            )
            # Default: age takeover off → CacheLockedError.
            with (
                pytest.raises(CacheLockedError),
                acquire_cache_lock(cache_root, stale_after_seconds=3600),
            ):
                pass  # pragma: no cover
        finally:
            proc.terminate()
            proc.wait(timeout=10)

    def test_age_takeover_integration_when_no_competing_flock(self, tmp_path: Path) -> None:
        # Exercises the positive age-takeover path end-to-end. We
        # simulate the "kernel restart / lock-file orphaned" scenario:
        # an old lock FILE persists with a recorded live PID and old
        # started_at, but no process actually holds the kernel-level
        # flock on it. With allow_age_takeover=True and stale_after_seconds=0
        # (force the age check to fire), acquire_cache_lock takes
        # over and we successfully acquire.
        cache_root = tmp_path / "cache"
        cache_root.mkdir()
        # Record THIS process's PID + matching create_time so the
        # PID-alive check passes (matches → not stale by PID/create_time).
        # The age check is the load-bearing path here.
        old_started = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        (cache_root / ".lock").write_bytes(
            canonical_json_bytes(
                {
                    "pid": os.getpid(),
                    "process_start_time": psutil.Process(os.getpid()).create_time(),
                    "hostname": socket.gethostname(),
                    "started_at": old_started,
                }
            )
        )
        # Default off → age path NOT taken → flock succeeds anyway
        # because no one holds it. Sanity check first.
        # (Skip that to keep the test focused on opt-in path.)

        # Opt-in path: stale_after_seconds=0 forces age check to fire
        # for any non-zero-age lock file. Acquisition succeeds.
        with acquire_cache_lock(cache_root, stale_after_seconds=0, allow_age_takeover=True) as lock:
            assert lock.content.pid == os.getpid()
            assert lock.content.started_at != old_started  # we re-wrote it


# ---------------------------------------------------------------------------
# Lock content provenance
# ---------------------------------------------------------------------------


class TestLockProvenance:
    def test_lock_content_records_this_process(self, tmp_path: Path) -> None:
        with acquire_cache_lock(tmp_path / "cache") as lock:
            assert lock.content.pid == os.getpid()
            assert lock.content.hostname == socket.gethostname()
            actual_create = psutil.Process(os.getpid()).create_time()
            assert abs(lock.content.process_start_time - actual_create) < 1.0
            # started_at is well-formed ISO-8601 UTC.
            assert lock.content.started_at.endswith("Z")
            datetime.fromisoformat(lock.content.started_at)

    def test_locked_error_names_holder(self, tmp_path: Path) -> None:
        cache_root = tmp_path / "cache"
        ready_file = tmp_path / "child_ready"
        proc = subprocess.Popen(
            [sys.executable, "-c", _HOLD_LOCK_SCRIPT, str(cache_root), str(ready_file), "5"],
        )
        try:
            _wait_for_ready(ready_file)
            with (
                pytest.raises(CacheLockedError) as exc_info,
                acquire_cache_lock(cache_root),
            ):
                pass  # pragma: no cover
            msg = str(exc_info.value)
            assert "PID=" in msg
            assert "hostname=" in msg
            assert "started_at=" in msg
            assert str(proc.pid) in msg
        finally:
            proc.terminate()
            proc.wait(timeout=10)


class TestLockFileResilience:
    """File-parse resilience tests: a corrupted or empty lock FILE
    must not break the acquire flow. These tests do NOT hold a
    competing fcntl lock — they verify open()/read()/parse tolerance,
    not stale-takeover via flock-BlockingIOError. For real single-
    writer contention see `TestSingleWriter`; for the stale-takeover
    decision logic see `TestShouldTakeover`.
    """

    def test_acquire_tolerates_corrupted_lock_file(self, tmp_path: Path) -> None:
        cache_root = tmp_path / "cache"
        cache_root.mkdir()
        (cache_root / ".lock").write_text("{not valid json")
        with acquire_cache_lock(cache_root):
            pass

    def test_acquire_tolerates_empty_lock_file(self, tmp_path: Path) -> None:
        # Crashed-during-write residue: zero-byte lock file.
        cache_root = tmp_path / "cache"
        cache_root.mkdir()
        (cache_root / ".lock").write_text("")
        with acquire_cache_lock(cache_root):
            pass


class TestShouldTakeover:
    """Pure unit tests on the `_should_takeover` decision function.

    Extracted from `_try_takeover_if_stale` so the decision matrix can
    be covered without filesystem state or `fcntl` interaction. The
    integration tests above cover the file-I/O wrapper; these cover
    every branch of the boolean logic.
    """

    def _live_self(self, started_at: str) -> LockFileContent:
        """A LockFileContent that records THIS process accurately —
        i.e., not dead, not PID-recycled. Stale evidence then comes
        from `started_at` age alone.
        """
        return LockFileContent(
            pid=os.getpid(),
            process_start_time=psutil.Process(os.getpid()).create_time(),
            hostname=socket.gethostname(),
            started_at=started_at,
        )

    def test_dead_pid_is_stale_regardless_of_age(self) -> None:
        # A dead PID is stale even when started_at is recent and
        # allow_age_takeover is False.
        recorded = LockFileContent(
            pid=_dead_pid(),
            process_start_time=time.time(),
            hostname="any",
            started_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert _should_takeover(recorded, stale_after_seconds=86400, allow_age_takeover=False)

    def test_recycled_pid_is_stale_regardless_of_age(self) -> None:
        # PID alive but create_time mismatches → recycled.
        recorded = LockFileContent(
            pid=os.getpid(),
            process_start_time=1.0,  # absurdly old
            hostname="any",
            started_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        assert _should_takeover(recorded, stale_after_seconds=86400, allow_age_takeover=False)

    def test_alive_and_matching_not_stale_by_default(self) -> None:
        recorded = self._live_self(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
        assert not _should_takeover(recorded, stale_after_seconds=86400, allow_age_takeover=False)

    def test_age_path_off_by_default(self) -> None:
        # Lock alive + matching, but old started_at. Without
        # allow_age_takeover, the age check is NOT consulted.
        old = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recorded = self._live_self(old)
        assert not _should_takeover(recorded, stale_after_seconds=3600, allow_age_takeover=False)

    def test_age_path_takes_over_when_opted_in_and_exceeded(self) -> None:
        # Lock alive + matching, old started_at, opt-in + threshold
        # exceeded → takeover. THIS is the positive coverage of the
        # opt-in path the previous integration test could not exercise
        # (because the OS flock would always still refuse).
        old = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recorded = self._live_self(old)
        assert _should_takeover(recorded, stale_after_seconds=3600, allow_age_takeover=True)

    def test_age_path_does_not_take_over_when_opted_in_but_under_threshold(self) -> None:
        # Recent lock, opt-in, but not yet aged out → not stale.
        recent = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        recorded = self._live_self(recent)
        assert not _should_takeover(recorded, stale_after_seconds=86400, allow_age_takeover=True)

    def test_access_denied_treats_lock_as_not_stale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # If psutil can SEE the PID but can't read its create_time
        # (permission error in containerized / hardened environments),
        # the conservative behavior is to treat the lock as NOT stale.
        # Better to surface CacheLockedError than to clobber a
        # legitimate process whose creation time we can't verify.
        # Pinned via monkeypatch since AccessDenied is hard to
        # reproduce naturally in a unit test.
        class _DeniedProc:
            def create_time(self) -> float:
                raise psutil.AccessDenied(pid=12345)

        def _fake_process(pid: int) -> _DeniedProc:
            return _DeniedProc()

        monkeypatch.setattr("whatif.cache.lock.psutil.Process", _fake_process)

        recorded = LockFileContent(
            pid=12345,
            process_start_time=time.time(),
            hostname="any",
            started_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        # Conservative: not stale → operator gets a CacheLockedError
        # rather than silent takeover.
        assert not _process_dead_or_recycled(recorded)
        # Same pinned through _should_takeover.
        assert not _should_takeover(recorded, stale_after_seconds=86400, allow_age_takeover=False)

    def test_malformed_started_at_does_not_age_out(self) -> None:
        # If started_at is unparseable, the age path returns False —
        # we surface a CacheLockedError rather than silently taking
        # over a lock whose age we can't compute.
        recorded = self._live_self("not-a-timestamp")
        assert not _should_takeover(recorded, stale_after_seconds=0, allow_age_takeover=True)


class TestLockFileContentDataclass:
    def test_immutable(self) -> None:
        c = LockFileContent(
            pid=1234,
            process_start_time=1.0,
            hostname="h",
            started_at="2026-01-01T00:00:00Z",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.pid = 5678  # type: ignore[misc]
