"""Tests for `whatifd.serialization.lock_io` — Phase 3.3 lock-file
deserialization helpers.

These pin the typed-boundary contract: parse_lock_file_content returns
either a fully-typed LockFileContent or None on any parse failure
shape (empty, corrupted JSON, missing key, wrong type, non-numeric
pid, etc.). The lock module's stale-detection logic depends on the
two-valued return contract.
"""

from __future__ import annotations

from whatifd.cache.lock import LockFileContent
from whatifd.serialization import canonical_json_bytes, parse_lock_file_content

_VALID_DICT = {
    "pid": 12345,
    "process_start_time": 1700000000.0,
    "hostname": "ci-runner-7",
    "started_at": "2026-04-30T14:22:00Z",
}


class TestParseLockFileContent:
    def test_round_trip_via_canonical_bytes(self) -> None:
        # The roundtrip we actually use in lock.py: write canonical
        # bytes, read them back as typed content.
        raw = canonical_json_bytes(_VALID_DICT)
        result = parse_lock_file_content(raw)
        assert result is not None
        assert isinstance(result, LockFileContent)
        assert result.pid == 12345
        assert result.process_start_time == 1700000000.0
        assert result.hostname == "ci-runner-7"
        assert result.started_at == "2026-04-30T14:22:00Z"

    def test_accepts_str_input(self) -> None:
        result = parse_lock_file_content(
            '{"pid":1,"process_start_time":2.0,"hostname":"h","started_at":"s"}'
        )
        assert result is not None
        assert result.pid == 1

    def test_empty_returns_none(self) -> None:
        assert parse_lock_file_content("") is None
        assert parse_lock_file_content(b"") is None

    def test_invalid_json_returns_none(self) -> None:
        assert parse_lock_file_content("{not valid json") is None

    def test_missing_required_key_returns_none(self) -> None:
        assert parse_lock_file_content('{"pid": 1}') is None

    def test_wrong_top_level_type_returns_none(self) -> None:
        # Top-level is a list, not a dict. parsed["pid"] would raise
        # TypeError, which the helper catches → None.
        assert parse_lock_file_content("[1,2,3]") is None

    def test_non_numeric_pid_returns_none(self) -> None:
        # int("not-a-number") raises ValueError, caught → None.
        assert (
            parse_lock_file_content(
                '{"pid":"not-a-number","process_start_time":1.0,"hostname":"h","started_at":"s"}'
            )
            is None
        )

    def test_non_numeric_process_start_time_returns_none(self) -> None:
        # float() raises ValueError on a non-numeric string.
        assert (
            parse_lock_file_content(
                '{"pid":1,"process_start_time":"never","hostname":"h","started_at":"s"}'
            )
            is None
        )
