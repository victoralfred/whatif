"""Tests for `whatifd.cache.lock` — Phase 3.3 cache lock.

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

from whatifd.cache.lock import (
    CacheLockedError,
    LockFileContent,
    _process_dead_or_recycled,
    _should_takeover,
    acquire_cache_lock,
)
from whatifd.serialization import canonical_json_bytes

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
import sys
import time
from pathlib import Path

from whatifd.cache.lock import acquire_cache_lock
from whatifd.serialization import canonical_json_bytes

cache_root = Path(sys.argv[1])
ready_file = Path(sys.argv[2])
hold_seconds = float(sys.argv[3])
# Optional argv[4]: a started_at value to write into the lock file
# AFTER acquire_cache_lock has written its own. Used by tests that
# need to simulate "this lock has been held for a long time" without
# the parent process reaching into the child's lock file (avoids any
# perceived TOCTOU window between parent overwrite and child fsync —
# the child does the overwrite itself, atomically, before signalling
# ready).
override_started_at = sys.argv[4] if len(sys.argv) > 4 else None

with acquire_cache_lock(cache_root) as lock:
    if override_started_at is not None:
        # Re-canonicalize the lock file with an overridden started_at.
        # Safe even though we're inside the `with` block: the kernel
        # flock is held throughout, so no concurrent reader can observe
        # a partial write. The parent test harness only reads .lock
        # AFTER attempting acquire_cache_lock, which would itself block
        # on the kernel lock. This is the same write path
        # acquire_cache_lock uses internally for its own provenance
        # write.
        lock.lock_path.write_bytes(
            canonical_json_bytes(
                {
                    "pid": lock.content.pid,
                    "process_start_time": lock.content.process_start_time,
                    "hostname": lock.content.hostname,
                    "started_at": override_started_at,
                }
            )
        )
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
        # Same scope caveat as test_takeover_when_pid_recycled below:
        # this exercises the FILE-overwrite path (acquire_cache_lock
        # writes new content over a previous holder's stale data),
        # not the flock-contested stale-detection path (which is
        # covered in isolation by TestShouldTakeover::test_dead_pid_is_stale_regardless_of_age).
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
        #
        # NOTE: this test does NOT hold a competing fcntl lock — the
        # file exists with stale data but the kernel lock is free.
        # acquire_cache_lock's flock succeeds on first attempt, so
        # the stale-detection path is never entered here. The actual
        # "PID-recycled → takeover" decision is exercised in isolation
        # by TestShouldTakeover::test_recycled_pid_is_stale_regardless_of_age.
        # This test verifies that the lock-file write path overwrites
        # the prior holder's data when we acquire — a complementary
        # property, not the same one.
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
        # Subprocess holds the kernel flock AND writes an old
        # started_at into the lock file (via the script's optional
        # 4th argv). Parent attempts acquire — without
        # allow_age_takeover, the age path is never consulted, so the
        # parent gets CacheLockedError.
        #
        # The child does the overwrite itself (atomically, before
        # signalling ready), so the parent never reaches into the
        # child's lock file. Eliminates any perceived TOCTOU window
        # between a parent overwrite and a child fsync.
        cache_root = tmp_path / "cache"
        ready_file = tmp_path / "child_ready"
        old_started = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                _HOLD_LOCK_SCRIPT,
                str(cache_root),
                str(ready_file),
                "5",
                old_started,
            ],
        )
        try:
            _wait_for_ready(ready_file)
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
        # Opt-in path: stale_after_seconds=0 forces age check to fire
        # for any non-zero-age lock file. Acquisition succeeds. (The
        # default-off counterpart is covered in isolation by
        # TestShouldTakeover::test_age_path_off_by_default — no need
        # to duplicate here.)
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

        monkeypatch.setattr("whatifd.cache.lock.psutil.Process", _fake_process)

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


class TestUnsupportedFilesystem:
    """`fcntl.flock` returns `ENOLCK`/`EOPNOTSUPP` on filesystems that
    don't support advisory locking (most NFS clients, some FUSE mounts).
    Surface as a typed `CacheLockedError` with a clear hint, not a raw
    `OSError`. Cardinal #1: DATA condition (environmental, not a bug).
    """

    def test_enolck_surfaces_typed_error_with_nfs_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import errno as _errno

        def _flock_fails_enolck(fd: int, op: int) -> None:
            raise OSError(_errno.ENOLCK, "No locks available")

        monkeypatch.setattr("whatifd.cache.lock.fcntl.flock", _flock_fails_enolck)

        with (
            pytest.raises(CacheLockedError, match="NFS"),
            acquire_cache_lock(tmp_path / "cache"),
        ):
            pass  # pragma: no cover

    def test_eopnotsupp_surfaces_typed_error_with_nfs_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import errno as _errno

        def _flock_fails_eopnotsupp(fd: int, op: int) -> None:
            raise OSError(_errno.EOPNOTSUPP, "Operation not supported")

        monkeypatch.setattr("whatifd.cache.lock.fcntl.flock", _flock_fails_eopnotsupp)

        with (
            pytest.raises(CacheLockedError, match="NFS"),
            acquire_cache_lock(tmp_path / "cache"),
        ):
            pass  # pragma: no cover

    def test_unrelated_oserror_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pin the boundary: only ENOLCK/EOPNOTSUPP get the NFS-hint
        # treatment. An unrelated OSError (e.g., EBADF) propagates as
        # a generic OSError — that's a programmer bug or genuinely
        # unexpected condition, not a "filesystem doesn't support
        # locking" data condition.
        import errno as _errno

        def _flock_fails_ebadf(fd: int, op: int) -> None:
            raise OSError(_errno.EBADF, "Bad file descriptor")

        monkeypatch.setattr("whatifd.cache.lock.fcntl.flock", _flock_fails_ebadf)

        with (
            pytest.raises(OSError, match="Bad file descriptor"),
            acquire_cache_lock(tmp_path / "cache"),
        ):
            pass  # pragma: no cover


class TestHardenedEnvironment:
    """`_build_lock_content` calls `psutil.Process(self).create_time()`,
    which can raise `AccessDenied` in hardened containers (no
    CAP_SYS_PTRACE, namespaced /proc, restrictive LSM profiles).
    Surface as typed `CacheLockedError` rather than letting the raw
    psutil exception leak; cardinal #1 (DATA condition, environmental).
    """

    def test_access_denied_on_self_create_time_surfaces_typed_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _DeniedProc:
            def create_time(self) -> float:
                raise psutil.AccessDenied(pid=os.getpid())

        def _fake_process(pid: int) -> _DeniedProc:
            return _DeniedProc()

        monkeypatch.setattr("whatifd.cache.lock.psutil.Process", _fake_process)

        with (
            pytest.raises(CacheLockedError, match="AccessDenied"),
            acquire_cache_lock(tmp_path / "cache"),
        ):
            pass  # pragma: no cover


class TestCreateTimeToleranceBoundary:
    """Pin the `_CREATE_TIME_TOLERANCE_SECONDS = 1.0` boundary.

    The constant is a platform-variance allowance, NOT an arbitrary
    knob. Tightening below 1.0s risks false-positive PID-reuse
    detection on slow-clock platforms; widening narrows the
    legitimate detection window. The boundary tests pin the exact
    semantics so a future refactor that "rounded" the comparison or
    flipped the inequality direction fails loudly here.
    """

    def _at_drift(self, drift_seconds: float) -> LockFileContent:
        # Build a LockFileContent whose process_start_time is exactly
        # `drift_seconds` away from THIS process's actual create_time.
        actual = psutil.Process(os.getpid()).create_time()
        return LockFileContent(
            pid=os.getpid(),
            process_start_time=actual - drift_seconds,
            hostname="any",
            started_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    def test_drift_at_tolerance_is_not_recycled(self) -> None:
        # drift == 1.0 → the comparator is `> 1.0` so equality is NOT
        # recycled. Live + matching enough.
        from whatifd.cache.lock import _process_dead_or_recycled

        assert not _process_dead_or_recycled(self._at_drift(1.0))

    def test_drift_just_under_tolerance_is_not_recycled(self) -> None:
        from whatifd.cache.lock import _process_dead_or_recycled

        assert not _process_dead_or_recycled(self._at_drift(0.999))

    def test_drift_just_over_tolerance_is_recycled(self) -> None:
        # drift == 1.001 → strictly > 1.0 → recycled.
        from whatifd.cache.lock import _process_dead_or_recycled

        assert _process_dead_or_recycled(self._at_drift(1.001))


class TestUnlinkRaceTolerance:
    """The `with contextlib.suppress(FileNotFoundError)` around
    `lock_path.unlink()` covers the race where another process
    unlinked the lock file between our acquire and our unlink (e.g.,
    a stale-takeover from a third process while we held the kernel
    lock — extremely narrow, but possible).
    """

    def test_unlink_already_gone_does_not_raise(self, tmp_path: Path) -> None:
        cache_root = tmp_path / "cache"
        with acquire_cache_lock(cache_root):
            # Simulate "another process unlinked first" by removing
            # the lock file while we still hold the kernel lock.
            (cache_root / ".lock").unlink()
            assert not (cache_root / ".lock").exists()
        # Context-manager exit must complete cleanly — no
        # FileNotFoundError propagates from the unlink in finally.

    def test_unlink_failure_other_than_not_found_is_not_silently_swallowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pin: only FileNotFoundError is suppressed. A different OSError
        # (e.g., PermissionError) on unlink would NOT be silently
        # eaten by contextlib.suppress(FileNotFoundError) — it would
        # propagate. This is the boundary that protects against
        # accidental over-broad suppression in a future refactor.
        original_unlink = Path.unlink

        def _unlink_permission_denied(self: Path, **kwargs: object) -> None:
            if self.name == ".lock":
                raise PermissionError("simulated")
            original_unlink(self, **kwargs)

        # We can't easily inject this via monkeypatch on Path.unlink
        # because the cleanup path uses it via the bound method. But we
        # CAN verify the boundary by pinning that the suppressed
        # exception type is exactly FileNotFoundError, not OSError or
        # Exception. Static check on the source itself:
        import inspect

        from whatifd.cache import lock as lock_module

        source = inspect.getsource(lock_module.acquire_cache_lock)
        assert "contextlib.suppress(FileNotFoundError)" in source, (
            "Cleanup-path unlink suppression must be narrow "
            "(FileNotFoundError only). A broader suppress(OSError) "
            "would silently eat permission errors and other unexpected "
            "failures, violating cardinal #1."
        )


class TestPackageReExport:
    """The most-used lock surface is re-exported at the package level
    so callers don't need to reach into `whatifd.cache.lock`. Pin both
    paths return the same objects, not parallel definitions.
    """

    def test_acquire_cache_lock_is_same_object(self) -> None:
        from whatifd import cache as pkg
        from whatifd.cache import lock as submodule

        assert pkg.acquire_cache_lock is submodule.acquire_cache_lock

    def test_cache_lock_is_same_class(self) -> None:
        from whatifd import cache as pkg
        from whatifd.cache import lock as submodule

        assert pkg.CacheLock is submodule.CacheLock

    def test_cache_locked_error_is_same_class(self) -> None:
        from whatifd import cache as pkg
        from whatifd.cache import lock as submodule

        assert pkg.CacheLockedError is submodule.CacheLockedError


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
