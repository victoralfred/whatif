"""Cache lock — Phase 3.3.

Single-writer enforcement on the scorer cache directory. Pairs with
Phase 3.1 keying and Phase 3.2 storage; this is the third sub-phase of
Phase 3 per the v0.1 implementation plan.

## Why a lock at all

The scorer cache lives under `.whatif/cache/`. A `whatif fork` run
writes new entries as it scores traces. If two `whatif` processes
target the same cache concurrently, partial writes can interleave and
produce corrupted entries — the cardinal #1 "failures-as-data"
boundary requires us to fail loud rather than ship a Ship verdict
backed by torn-write evidence. Single-writer enforcement is the
defensive primitive.

## How the lock works

Two layers of defense:

1. **OS-level `fcntl.flock(LOCK_EX | LOCK_NB)`** on `<cache>/.lock`.
   Reliable on Linux/macOS. Releases automatically on process death
   including SIGKILL, kernel panic, or OOM kill. The kernel does not
   leak fcntl locks across exec or process exit.
2. **Stale-lock fallback** for the case where flock thinks the lock
   is held but the recorded process is no longer the one holding it
   (e.g., a hung process the operator killed externally; a container
   restart). Lock file records `{pid, process_start_time, hostname,
   started_at}`; takeover happens when ANY of:
   - The recorded PID is no longer running (`psutil.NoSuchProcess`).
   - The recorded PID is running but its `create_time()` differs from
     the recorded `process_start_time` (PID reused).
   - The lock is older than `stale_after_seconds` (default 24h) AND
     the operator has explicitly opted into time-based takeover via
     `acquire_cache_lock(..., allow_age_takeover=True)`. Default is
     False because age alone is a weak signal — a long-running batch
     might legitimately hold a lock for days.

The double-condition (PID dead OR PID-reused) is what
`references/enforcement.md` calls "the stale-lock-false-positive
defense": if PID 12345 dies and the OS later assigns 12345 to an
unrelated process, the recorded `process_start_time` mismatches and
takeover proceeds. A naive PID-only check would refuse takeover
because the PID is "alive" — it just isn't the same process.

## TOCTOU note on stale takeover

When `flock` initially refuses, we read the recorded lock-file
content, decide it's stale, and re-attempt `flock`. Between those
steps a different process could *also* read the file and *also*
decide stale — but `flock(LOCK_EX | LOCK_NB)` is atomic, so only one
of the contenders can hold it at a time. The losing contender gets
`BlockingIOError` on its re-flock and surfaces `CacheLockedError`
naming us as the new holder; the winner proceeds to truncate and
rewrite the lock file. The window during which the on-disk file
still names the *previous* (stale) holder, while we hold the kernel
flock and are about to overwrite it, is brief and harmless: any
operator-visible inspection of `.lock` during that window resolves on
re-read after our `fsync`. No data is lost; the only observable
artifact is a momentary mismatch between the kernel-truth (us) and
the file-truth (previous holder), which is a diagnostic anomaly, not
a correctness one.

## What this module does NOT do

- **NFS-safe locking.** `fcntl.flock` semantics on NFS are
  implementation-dependent; some clients silently degrade to advisory.
  The module documents this limitation and produces a clear error
  message naming NFS as a likely cause if flock returns an unexpected
  errno; full NFS-safe locking is deferred to v0.3.
- **Cross-host coordination.** The lock is process-local on a single
  filesystem. Multi-tenant cache directories shared across hosts are
  the cascade entry "Multi-tenant cache directories" (v0.3).
- **Read locks.** v0.1 single-writer model only; readers do not need
  to coordinate because writes are atomic-via-canonical-bytes
  (Phase 3.2 already writes whole files via `path.write_bytes`).

## Cardinal alignment

- **#1 (failures-as-data):** lock acquisition failure produces a
  typed `CacheLockedError` with a structured message (PID, hostname,
  started_at, recovery hints). Callers convert to a `FailureRecord`
  at the appropriate scope. This is NOT an `InvariantViolationError`
  — a held lock is a legitimate runtime data condition, not a
  programmer bug.
- **#9 (orchestration not compute):** `fcntl.flock` is the OS doing
  the work. No CPU optimization, no shared-memory tricks. The Python
  layer just records provenance.

## Internal surface (single underscore, importable for tests)

The single-underscore helpers below are part of the package's
internal surface. They have stable names so the unit-test suite can
exercise pure decision logic in isolation from filesystem state:

- `_should_takeover(content, stale_after_seconds, allow_age_takeover) -> bool`
  — pure stale-decision function tested in `TestShouldTakeover`.
- `_process_dead_or_recycled(content) -> bool` — psutil-backed
  helper; tested via monkeypatch for the `AccessDenied` branch.

External callers (outside `whatif.cache.lock`) should NOT import
these — `acquire_cache_lock` is the only public surface. Internal
imports are fine because the package's test suite is the only other
in-tree consumer, and renames will be coordinated.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import json
import os
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

import psutil

from whatif.serialization import canonical_json_bytes

_LOCK_FILENAME = ".lock"
_DEFAULT_STALE_AFTER_SECONDS = 86400  # 24 hours
_CREATE_TIME_TOLERANCE_SECONDS = 1.0  # psutil create_time precision varies by platform


class CacheLockedError(Exception):
    """The cache lock could not be acquired and is not stale.

    DATA condition (a legitimate runtime state — another process holds
    the lock), not a programmer bug. Callers convert to a
    `FailureRecord` per cardinal #1. The message includes the
    structured lock-file contents so operators can decide whether to
    wait, run `whatif cache unlock`, or run `whatif cache rebuild`.
    """


@dataclass(frozen=True, slots=True)
class LockFileContent:
    """The structured payload of `.lock`.

    `pid` and `process_start_time` together identify the holding
    process unambiguously across PID reuse — `os.getpid()` alone can
    collide with a recycled PID after process death.

    `hostname` is informational; cross-host locks are not supported in
    v0.1 (the lock primitive is filesystem-local).

    `started_at` is the wall-clock time the lock was acquired
    (ISO-8601 UTC). Used for age-based stale detection (opt-in) and
    for the recovery message in `CacheLockedError`.
    """

    pid: int
    process_start_time: float
    hostname: str
    started_at: str


@dataclass(frozen=True, slots=True)
class CacheLock:
    """Handle returned by `acquire_cache_lock`.

    Carries the path of the lock file and the recorded `LockFileContent`
    so callers can log/manifest who acquired it. The actual `fcntl`
    handle is held internally by the context manager and released on
    `__exit__`.
    """

    lock_path: Path
    content: LockFileContent


@contextmanager
def acquire_cache_lock(
    cache_root: Path,
    *,
    stale_after_seconds: int = _DEFAULT_STALE_AFTER_SECONDS,
    allow_age_takeover: bool = False,
) -> Iterator[CacheLock]:
    """Acquire the single-writer lock on `cache_root`.

    Yields a `CacheLock` describing the held lock. On exit (normal or
    exceptional), releases `fcntl.flock` and unlinks the lock file.

    Raises `CacheLockedError` when the lock is held by another live
    process and is not stale. Operators can resolve via
    `whatif cache unlock` (Phase 8).

    `allow_age_takeover=True` enables time-based takeover (lock older
    than `stale_after_seconds`) — opt-in only because age alone is a
    weak signal. Default behavior takes over only on dead-process or
    PID-reuse evidence (both surface via the
    `psutil.NoSuchProcess`/`create_time` mismatch path).
    """
    lock_path = cache_root / _LOCK_FILENAME
    cache_root.mkdir(parents=True, exist_ok=True)

    # SIM115 (use `with open(...)`) is suppressed: the file's lifetime
    # spans the entire context manager — we acquire the fcntl lock on
    # this fd, yield the CacheLock to the caller, and only release +
    # close in the conditional-acquired finally path below. A `with`
    # block would close at the wrong scope. `pathlib.Path.open()` has
    # the same scoping issue and offers no advantage here.
    fp = open(lock_path, "a+", encoding="utf-8")  # noqa: SIM115
    acquired = False
    try:
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError as e:
            # flock refused. Inspect the existing lock file for stale
            # evidence; if stale, attempt takeover. Otherwise raise.
            if _try_takeover_if_stale(fp, lock_path, stale_after_seconds, allow_age_takeover):
                # Re-attempt flock. If the OS still refuses, the
                # original process is alive and holding the kernel
                # lock — file-level stale evidence is overridden by
                # the OS truth. The lock is NOT actually stale.
                try:
                    fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except BlockingIOError as inner:
                    raise _build_locked_error(lock_path) from inner
            else:
                raise _build_locked_error(lock_path) from e
        except OSError as e:
            if e.errno in (errno.ENOLCK, errno.EOPNOTSUPP):
                raise CacheLockedError(
                    f"fcntl.flock returned errno={e.errno} ({errno.errorcode.get(e.errno, '?')}) "
                    f"on {lock_path}. The filesystem may not support advisory "
                    "locking — NFS clients commonly degrade silently. v0.1 "
                    "does not support NFS-mounted cache directories; use a "
                    "local filesystem or the cascade entry 'Multi-tenant "
                    "cache directories' (v0.3) for shared-host caches."
                ) from e
            raise

        content = _build_lock_content()
        fp.seek(0)
        fp.truncate()
        fp.write(canonical_json_bytes(_content_to_dict(content)).decode("ascii"))
        fp.flush()
        os.fsync(fp.fileno())

        yield CacheLock(lock_path=lock_path, content=content)
    finally:
        # Cleanup is conditional on acquisition: if we never acquired
        # (CacheLockedError path), we must NOT unlock/unlink — the
        # other process still holds it. Closing the fd is always safe.
        if acquired:
            with contextlib.suppress(OSError):
                fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            fp.close()
        if acquired:
            with contextlib.suppress(FileNotFoundError):
                lock_path.unlink()


def _try_takeover_if_stale(
    fp: IO[str],
    lock_path: Path,
    stale_after_seconds: int,
    allow_age_takeover: bool,
) -> bool:
    """Inspect the existing lock file; return True if takeover is
    justified by stale evidence.

    Wraps the pure decision function `_should_takeover` with the file
    I/O concerns. The split keeps the decision logic unit-testable
    without filesystem state — see `tests/.../test_lock.py::TestShouldTakeover`.
    """
    fp.seek(0)
    raw = fp.read()
    if not raw:
        # Empty lock file: nobody recorded who they are. Treat as stale.
        return True
    try:
        parsed = json.loads(raw)
        recorded = LockFileContent(
            pid=int(parsed["pid"]),
            process_start_time=float(parsed["process_start_time"]),
            hostname=str(parsed["hostname"]),
            started_at=str(parsed["started_at"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        # Corrupted lock file. Stale by definition — nobody we can
        # ask, no provenance to respect.
        return True

    return _should_takeover(recorded, stale_after_seconds, allow_age_takeover)


def _should_takeover(
    recorded: LockFileContent,
    stale_after_seconds: int,
    allow_age_takeover: bool,
) -> bool:
    """Pure decision: is the recorded lock stale?

    Extracted from `_try_takeover_if_stale` so unit tests can cover
    every branch (process dead, PID recycled, age exceeded with opt-in,
    age exceeded without opt-in, all-clear) without faking file I/O or
    `fcntl` state. The integration test (real subprocess) covers the
    file-I/O wrapper; this function covers the decision matrix.
    """
    if _process_dead_or_recycled(recorded):
        return True
    return allow_age_takeover and _lock_age_exceeded(recorded, stale_after_seconds)


def _process_dead_or_recycled(recorded: LockFileContent) -> bool:
    """True if the recorded process is no longer alive OR a different
    process has been assigned the same PID since the lock was written.
    """
    try:
        proc = psutil.Process(recorded.pid)
        actual_create_time = proc.create_time()
    except psutil.NoSuchProcess:
        # Process is gone. Lock is stale.
        return True
    except psutil.AccessDenied:
        # We can't tell. Conservative: do NOT take over — better to
        # surface a CacheLockedError than to clobber a legitimate
        # process whose creation time we can't read.
        return False
    drift = abs(float(actual_create_time) - recorded.process_start_time)
    return drift > _CREATE_TIME_TOLERANCE_SECONDS


def _lock_age_exceeded(recorded: LockFileContent, stale_after_seconds: int) -> bool:
    # Python 3.11+ (project minimum) parses the `Z` suffix natively;
    # no `.replace("Z", "+00:00")` workaround needed.
    try:
        started = datetime.fromisoformat(recorded.started_at)
    except ValueError:
        # Malformed timestamp — treat as not-aged-out so we surface the
        # CacheLockedError rather than silently taking over.
        return False
    age = (datetime.now(UTC) - started).total_seconds()
    return age > stale_after_seconds


def _build_lock_content() -> LockFileContent:
    """Capture the current process's identity for the lock file."""
    pid = os.getpid()
    return LockFileContent(
        pid=pid,
        process_start_time=psutil.Process(pid).create_time(),
        hostname=socket.gethostname(),
        started_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _content_to_dict(content: LockFileContent) -> dict[str, object]:
    return {
        "pid": content.pid,
        "process_start_time": content.process_start_time,
        "hostname": content.hostname,
        "started_at": content.started_at,
    }


def _build_locked_error(lock_path: Path) -> CacheLockedError:
    """Read the held lock for diagnostics and return a typed error
    naming the holder, hostname, and when it was acquired.

    The blocking condition (lock held) is already established by the
    caller; this function ENRICHES the error message with provenance
    when the file is readable. If the file is unreadable (rotated,
    permission-denied, parse error), we still return `CacheLockedError`
    — the held lock is the load-bearing fact — but we chain the
    diagnostic-read error into `__cause__` via `raise ... from` so the
    enrichment failure isn't silent.
    """
    try:
        raw = lock_path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        return CacheLockedError(
            f"Cache lock at {lock_path} is held by another live process. "
            f"PID={parsed.get('pid')!r}, hostname={parsed.get('hostname')!r}, "
            f"started_at={parsed.get('started_at')!r}. If you know the "
            "holding process is no longer running, run `whatif cache unlock`. "
            "If the cache may be corrupted, run `whatif cache rebuild --force`."
        )
    except (OSError, json.JSONDecodeError) as diag_err:
        # Diagnostic-read failure: keep the blocking-condition signal
        # (typed CacheLockedError) AND surface the parse/read failure
        # via __cause__ chaining. The error message names what we know
        # plus what we couldn't read; cardinal #1 satisfied because
        # nothing is silently swallowed.
        err = CacheLockedError(
            f"Cache lock at {lock_path} is held but its content is "
            f"unreadable ({type(diag_err).__name__}: {diag_err}). Run "
            "`whatif cache unlock` if the holding process is no longer "
            "active, or `whatif cache rebuild --force` to reset."
        )
        err.__cause__ = diag_err
        return err
