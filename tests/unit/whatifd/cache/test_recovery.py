"""Tests for `whatifd.cache.recovery` — Phase 8.3.

Pin properties:

1. `rebuild` without `--force` is a no-op safety belt.
2. `rebuild` with `--force` deletes entries + bucket directories,
   preserves meta.json + lock file.
3. `rebuild` on a missing entries dir is a clean no-op.
4. `unlock` with no lock file is idempotent (success).
5. `unlock` refuses to clobber a live lock; `--allow-alive`
   overrides.
6. `unlock` removes a stale (dead-PID) lock cleanly.
7. `verify` reports total / valid / corrupted accurately.
8. `verify` on a missing entries dir is vacuously clean.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import psutil
import pytest

from whatifd.cache.recovery import rebuild, unlock, verify


def _make_entry(entries_dir: Path, key: str, valid: bool = True) -> Path:
    """Write a minimal CacheEntry-shaped JSON file at the expected
    bucket location. `valid=False` writes garbage so verify flags
    it as corrupted.

    The digest is derived from the `key` (sha256 hex) so distinct
    keys land at distinct filenames AND, for non-trivial keys,
    distinct buckets. The earlier hand-constant `'a' * 64` would
    have collided if a future test added two entries with the
    same hardcoded prefix.
    """
    import hashlib

    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    bucket = entries_dir / digest[:2]
    bucket.mkdir(parents=True, exist_ok=True)
    path = bucket / f"{digest}.json"
    if valid:
        payload: dict[str, object] = {
            "key": f"v1:{digest}",
            "value": {"score": 0.5},
            "metadata": {},
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        path.write_text("{not valid json", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# rebuild
# ---------------------------------------------------------------------------


class TestRebuild:
    def test_force_required(self, tmp_path: Path) -> None:
        result = rebuild(tmp_path, force=False)
        assert result.error == "force_required"
        assert result.entries_removed == 0

    def test_missing_entries_dir(self, tmp_path: Path) -> None:
        result = rebuild(tmp_path, force=True)
        assert result.error == "entries_dir_missing"
        assert result.entries_removed == 0

    def test_deletes_entries_and_buckets(self, tmp_path: Path) -> None:
        entries = tmp_path / "entries"
        _make_entry(entries, "a")
        _make_entry(entries, "b")
        # Add another bucket
        (entries / "ff").mkdir()
        (entries / "ff" / ("ff" + "0" * 62 + "-c.json")).write_text(
            json.dumps({"key": "v1:x", "value": {}, "metadata": {}}),
            encoding="utf-8",
        )

        result = rebuild(tmp_path, force=True)
        assert result.error is None
        assert result.entries_removed == 3
        # Three distinct buckets now: sha256("a")[:2],
        # sha256("b")[:2], and the hand-built "ff/" bucket. Per-key
        # digests in `_make_entry` mean keys "a" and "b" land in
        # different buckets (was 2 buckets when both keys hash-
        # collided with the hardcoded 'a' * 64 digest).
        assert result.bucket_dirs_removed == 3
        # entries dir itself remains; bucket dirs gone.
        assert entries.exists()
        assert list(entries.iterdir()) == []

    def test_non_bucket_files_counted(self, tmp_path: Path) -> None:
        # Stray file directly under entries/ shouldn't normally
        # exist (storage only writes inside bucket subdirs), but
        # if one does, rebuild surfaces it via non_bucket_skipped
        # rather than silently ignoring.
        entries = tmp_path / "entries"
        entries.mkdir(parents=True)
        (entries / "stray.json").write_text("garbage", encoding="utf-8")
        _make_entry(entries, "a")  # creates a real bucket too

        result = rebuild(tmp_path, force=True)
        assert result.error is None
        assert result.entries_removed == 1
        assert result.bucket_dirs_removed == 1
        assert result.non_bucket_skipped == 1
        # The stray file is preserved (rebuild doesn't touch it).
        assert (entries / "stray.json").exists()

    def test_non_file_in_bucket_counted_and_preserved(self, tmp_path: Path) -> None:
        # Storage layout is bucket/<file>. A nested subdir inside a
        # bucket is structurally unexpected — rebuild surfaces it
        # via non_file_skipped_in_bucket and leaves the bucket dir
        # behind for operator inspection rather than recursing
        # blindly (which could delete data the rebuild doesn't
        # understand).
        entries = tmp_path / "entries"
        bucket = entries / "aa"
        bucket.mkdir(parents=True)
        # Add a regular entry file
        entry = bucket / ("aa" + "a" * 62 + "-x.json")
        entry.write_text(
            json.dumps({"key": "v1:x", "value": {}, "metadata": {}}),
            encoding="utf-8",
        )
        # Add an unexpected nested subdir
        nested = bucket / "unexpected_subdir"
        nested.mkdir()

        result = rebuild(tmp_path, force=True)
        assert result.error is None
        assert result.entries_removed == 1
        assert result.non_file_skipped_in_bucket == 1
        # The bucket dir is preserved (had a non-file child).
        assert bucket.exists()
        assert nested.exists()
        # The entry file IS removed.
        assert not entry.exists()
        # bucket_dirs_removed counts only buckets that were
        # cleanly emptied.
        assert result.bucket_dirs_removed == 0

    def test_preserves_meta_and_lock_files(self, tmp_path: Path) -> None:
        entries = tmp_path / "entries"
        _make_entry(entries, "a")
        meta = tmp_path / "meta.json"
        meta.write_text("{}", encoding="utf-8")
        lock = tmp_path / ".lock"
        lock.write_text("{}", encoding="utf-8")

        rebuild(tmp_path, force=True)
        assert meta.exists()
        assert lock.exists()


# ---------------------------------------------------------------------------
# unlock
# ---------------------------------------------------------------------------


class TestUnlock:
    def test_no_lock_file_is_idempotent(self, tmp_path: Path) -> None:
        result = unlock(tmp_path, allow_alive=False)
        assert result.error == "no_lock_file"
        assert result.removed is False

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason=(
            "POSIX-only: `true` isn't a standard executable on Windows; "
            "cache subsystem refuses Windows at module load (psutil "
            "conditional + lock.py guard)."
        ),
    )
    def test_stale_lock_removed(self, tmp_path: Path) -> None:
        # Use a freshly-exited subprocess for a hermetic dead PID.
        # The earlier "PID 999999 is virtually guaranteed dead"
        # approach flaked on Linux systems with `kernel.pid_max`
        # set high enough that 999999 could be a live process.
        # Spawning + waiting for `true` guarantees the PID was
        # alive when allocated and dead by the time we use it.
        proc = subprocess.Popen(["true"])
        proc.wait()
        dead_pid = proc.pid

        # Explicit hermetic-PID precondition. If a future platform
        # recycles PIDs faster than this test expects, this
        # assertion fails BEFORE the real check, surfacing the
        # test's brittleness rather than masquerading as a bug in
        # `unlock`.
        #
        # TOCTOU note: there's a window between `proc.wait()` and
        # `psutil.pid_exists(dead_pid)` where the OS could in
        # principle recycle the PID and assign it to a new
        # process. On Linux/macOS the default `kernel.pid_max`
        # range (4M+) and the assertion's microsecond timing
        # make this practically impossible — the OS allocates
        # PIDs sequentially, so the chance of wrapping back to
        # `dead_pid` between two adjacent syscalls is negligible
        # for realistic system loads. If this test ever flakes
        # because of PID recycling, the right fix is to widen
        # the dead-PID window (e.g., spawn a parent + child
        # chain that holds the slot longer), not to remove the
        # precondition assertion.
        assert not psutil.pid_exists(dead_pid), (
            f"test precondition: PID {dead_pid} is still alive "
            "immediately after subprocess.wait(). The "
            "subprocess-for-hermetic-PID approach broke; pick "
            "another mechanism."
        )

        lock = tmp_path / ".lock"
        lock.write_text(json.dumps({"pid": dead_pid}), encoding="utf-8")
        result = unlock(tmp_path, allow_alive=False)
        assert result.removed is True
        assert result.pid_was_alive is False
        assert not lock.exists()

    def test_corrupted_lock_treated_as_stale(self, tmp_path: Path) -> None:
        lock = tmp_path / ".lock"
        lock.write_text("not valid json", encoding="utf-8")
        result = unlock(tmp_path, allow_alive=False)
        assert result.removed is True
        assert result.pid_was_alive is False

    def test_live_lock_refused_without_allow_alive(self, tmp_path: Path) -> None:
        lock = tmp_path / ".lock"
        # Current pytest process is alive.
        lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        result = unlock(tmp_path, allow_alive=False)
        assert result.removed is False
        assert result.pid_was_alive is True
        assert result.error == "lock_holder_alive"
        assert lock.exists()

    def test_live_lock_removed_with_allow_alive(self, tmp_path: Path) -> None:
        lock = tmp_path / ".lock"
        lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        result = unlock(tmp_path, allow_alive=True)
        assert result.removed is True
        assert result.pid_was_alive is True
        assert not lock.exists()


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_missing_entries_dir_is_vacuous_clean(self, tmp_path: Path) -> None:
        result = verify(tmp_path)
        assert result.vacuous is True
        assert result.total == 0

    def test_all_valid(self, tmp_path: Path) -> None:
        entries = tmp_path / "entries"
        _make_entry(entries, "a")
        _make_entry(entries, "b")
        result = verify(tmp_path)
        assert result.vacuous is False
        assert result.total == 2
        assert result.valid == 2
        assert result.corrupted == ()

    def test_corrupted_flagged(self, tmp_path: Path) -> None:
        # Use `in` membership rather than `==` equality on the
        # corrupted list — `bucket.iterdir()` has no guaranteed
        # order, so a future test that adds multiple corrupted
        # files to the same bucket would flake on a list-order
        # comparison.
        entries = tmp_path / "entries"
        good = _make_entry(entries, "a")
        bad = _make_entry(entries, "b", valid=False)
        result = verify(tmp_path)
        assert result.total == 2
        assert result.valid == 1
        assert bad in result.corrupted
        assert good not in result.corrupted
        assert len(result.corrupted) == 1

    def test_non_file_in_bucket_counted(self, tmp_path: Path) -> None:
        # verify mirrors rebuild's non_file_skipped_in_bucket so
        # the two operations describe the same shape of anomalies.
        # Without this, a stray subdirectory inside a bucket would
        # be silently ignored by verify while rebuild reports it.
        entries = tmp_path / "entries"
        bucket = entries / "aa"
        bucket.mkdir(parents=True)
        # One real entry file
        entry = bucket / ("aa" + "a" * 62 + "-x.json")
        entry.write_text(
            json.dumps({"key": "v1:x", "value": {}, "metadata": {}}),
            encoding="utf-8",
        )
        # Plus an unexpected nested subdirectory
        (bucket / "unexpected_subdir").mkdir()

        result = verify(tmp_path)
        assert result.total == 1
        assert result.valid == 1
        assert result.non_file_skipped_in_bucket == 1

    def test_missing_required_field_flagged(self, tmp_path: Path) -> None:
        # Parses as valid JSON but lacks the `value` field — verify
        # treats this as corrupted because it can't be reconstructed
        # as a CacheEntry.
        entries = tmp_path / "entries"
        bucket = entries / "aa"
        bucket.mkdir(parents=True)
        bad = bucket / ("aa" + "a" * 62 + "-x.json")
        bad.write_text(json.dumps({"key": "v1:x"}), encoding="utf-8")
        result = verify(tmp_path)
        assert result.total == 1
        assert result.valid == 0
        assert bad in result.corrupted
        assert len(result.corrupted) == 1


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCacheCliIntegration:
    """Smoke-test the typer subcommands actually wire to recovery
    primitives. Detailed CLI semantics are pinned in
    `tests/unit/whatifd/test_cli.py`."""

    def test_rebuild_force_via_cli(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from whatifd.cli import EXIT_SUCCESS, app

        entries = tmp_path / "entries"
        _make_entry(entries, "a")
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["cache", "rebuild", "--force", "--cache-root", str(tmp_path)],
        )
        assert result.exit_code == EXIT_SUCCESS
        assert list(entries.iterdir()) == []

    def test_rebuild_surfaces_non_bucket_skipped_in_output(self, tmp_path: Path) -> None:
        # Anomaly count must appear in the CLI output when
        # non-zero (the result dataclass carries it; the operator
        # only sees what the CLI prints).
        from typer.testing import CliRunner

        from whatifd.cli import EXIT_SUCCESS, app

        entries = tmp_path / "entries"
        entries.mkdir(parents=True)
        (entries / "stray.json").write_text("garbage", encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(app, ["cache", "rebuild", "--force", "--cache-root", str(tmp_path)])
        assert result.exit_code == EXIT_SUCCESS
        combined = (result.stdout or "") + (result.output or "")
        assert "skipped 1 non-directory path" in combined

    def test_verify_surfaces_non_bucket_skipped_in_output(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from whatifd.cli import EXIT_SUCCESS, app

        entries = tmp_path / "entries"
        entries.mkdir(parents=True)
        (entries / "stray.json").write_text("garbage", encoding="utf-8")
        runner = CliRunner()
        result = runner.invoke(app, ["cache", "verify", "--cache-root", str(tmp_path)])
        assert result.exit_code == EXIT_SUCCESS
        combined = (result.stdout or "") + (result.output or "")
        assert "skipped 1 non-directory path" in combined

    def test_verify_corrupted_via_cli(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from whatifd.cli import EXIT_INCONCLUSIVE_OR_SETUP_FAILURE, app

        entries = tmp_path / "entries"
        _make_entry(entries, "a", valid=False)
        runner = CliRunner()
        result = runner.invoke(app, ["cache", "verify", "--cache-root", str(tmp_path)])
        assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
