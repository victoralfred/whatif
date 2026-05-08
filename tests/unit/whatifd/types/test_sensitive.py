"""Tests for `whatifd.types.sensitive` — cardinal rule #5.

Per phases.md Phase 1 gate, this module must verify:
- repr / str / format all return the redacted form (never the value).
- pickle.dumps raises SensitiveSerializationError.
- .unwrap() returns the value AND emits an audit log entry.
- __slots__ prevents attribute addition after construction.

Plus discipline checks for `_audit_log` (the in-process collector) and
`_infer_caller` (the call-site extractor).
"""

from __future__ import annotations

import pickle
import threading

import pytest

from whatifd.types import (
    Sensitive,
    SensitiveSerializationError,
    SensitiveUnwrap,
    UnredactedSensitiveError,
)
from whatifd.types.sensitive import _audit_log, _AuditLog, _infer_caller


@pytest.fixture(autouse=True)
def _drain_audit_log():
    """Drain the audit log before and after each test so cases don't leak
    records into each other. The module-level `_audit_log` is a process
    singleton in v0.1.
    """
    _audit_log.drain()
    yield
    _audit_log.drain()


class TestRedactedSerialization:
    def test_repr_does_not_leak_value(self) -> None:
        s: Sensitive[str] = Sensitive("hunter2", "credential")
        assert "hunter2" not in repr(s)
        assert repr(s) == "<Sensitive[credential] redacted>"

    def test_str_does_not_leak_value(self) -> None:
        s: Sensitive[str] = Sensitive("hunter2", "credential")
        assert "hunter2" not in str(s)
        assert str(s) == "<Sensitive[credential] redacted>"

    def test_fstring_does_not_leak_value(self) -> None:
        # The most common accidental-leak path: f"{user_input}" in a log line.
        # __format__ is overridden so this redacts instead of unwrapping.
        s: Sensitive[str] = Sensitive("user@example.com", "user_email")
        rendered = f"got value: {s}"
        assert "user@example.com" not in rendered
        assert "<Sensitive[user_email] redacted>" in rendered

    def test_format_with_spec_still_redacts(self) -> None:
        s: Sensitive[str] = Sensitive("plaintext", "user_input")
        # An explicit format spec should not escape the redaction.
        assert format(s, ">20") == "<Sensitive[user_input] redacted>"

    def test_pickle_raises(self) -> None:
        s: Sensitive[str] = Sensitive("secret", "credential")
        with pytest.raises(SensitiveSerializationError) as excinfo:
            pickle.dumps(s)
        # The error message should point at the fix.
        assert "credential" in str(excinfo.value)
        assert ".unwrap" in str(excinfo.value)


class TestSlots:
    def test_cannot_add_arbitrary_attributes(self) -> None:
        s: Sensitive[str] = Sensitive("x", "user_input")
        with pytest.raises(AttributeError):
            s.smuggled = "extra"  # type: ignore[attr-defined]

    def test_cannot_reassign_classification(self) -> None:
        # __setattr__ is overridden to raise on any post-construction
        # assignment. __init__ bypasses via object.__setattr__ exactly
        # once. This is frozen-dataclass semantics without the dataclass
        # machinery (Generic[T] + __slots__ + frozen=True is fragile in
        # some Python versions).
        s: Sensitive[str] = Sensitive("x", "user_input")
        with pytest.raises(AttributeError, match="immutable"):
            s.classification = "renamed"
        # Original classification is unchanged.
        assert s.classification == "user_input"

    def test_cannot_reassign_value(self) -> None:
        s: Sensitive[str] = Sensitive("x", "user_input")
        with pytest.raises(AttributeError, match="immutable"):
            s._value = "y"


class TestUnwrap:
    def test_returns_wrapped_value(self) -> None:
        s: Sensitive[str] = Sensitive("plaintext", "user_input")
        assert s.unwrap(reason="render evidence section") == "plaintext"

    def test_emits_audit_record(self) -> None:
        s: Sensitive[str] = Sensitive("plaintext", "user_input")
        s.unwrap(reason="render evidence section")
        records = _audit_log.drain()
        assert len(records) == 1
        assert records[0].classification == "user_input"
        assert records[0].reason == "render evidence section"
        # location is best-effort but should not be empty
        assert records[0].location  # truthy

    def test_explicit_location_overrides_inferred(self) -> None:
        s: Sensitive[str] = Sensitive("x", "user_input")
        s.unwrap(reason="r", location="explicit/site.py:func:42")
        records = _audit_log.drain()
        assert records[0].location == "explicit/site.py:func:42"

    def test_multiple_unwraps_accumulate(self) -> None:
        s1: Sensitive[str] = Sensitive("a", "user_input")
        s2: Sensitive[bytes] = Sensitive(b"b", "trace_payload")
        s1.unwrap(reason="reason 1")
        s2.unwrap(reason="reason 2")
        records = _audit_log.drain()
        assert len(records) == 2
        classifications = {r.classification for r in records}
        assert classifications == {"user_input", "trace_payload"}

    def test_unwrap_preserves_generic_type_at_runtime(self) -> None:
        # Generic[T] is a type-checker concept; at runtime, unwrap returns
        # whatever was wrapped. Pin the round-trip for non-string types.
        wrapped_int: Sensitive[int] = Sensitive(42, "bounded_id")
        assert wrapped_int.unwrap(reason="test") == 42

        wrapped_dict: Sensitive[dict[str, str]] = Sensitive(
            {"a": "1", "b": "2"}, "structured_payload"
        )
        assert wrapped_dict.unwrap(reason="test") == {"a": "1", "b": "2"}


class TestAuditLogConcurrency:
    def test_concurrent_record_does_not_lose_writes(self) -> None:
        log = _AuditLog()
        records_per_thread = 200
        threads_count = 10

        def worker(tid: int) -> None:
            for i in range(records_per_thread):
                log.record(
                    SensitiveUnwrap(
                        classification="user_input",
                        reason=f"tid={tid} i={i}",
                        location="test",
                    )
                )

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(threads_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        records = log.drain()
        assert len(records) == threads_count * records_per_thread

    def test_drain_clears_buffer(self) -> None:
        log = _AuditLog()
        log.record(SensitiveUnwrap(classification="x", reason="r", location="l"))
        assert len(log) == 1
        records = log.drain()
        assert len(records) == 1
        assert len(log) == 0


class TestInferCaller:
    def test_returns_module_function_lineno(self) -> None:
        # Calling _infer_caller from this test should produce a string of
        # the form "<module>:<function>:<lineno>". The exact module name
        # depends on test discovery, so we just check the shape.
        location = _infer_caller(skip=1)  # skip just _infer_caller itself
        parts = location.split(":")
        assert len(parts) == 3
        # Lineno is numeric
        assert parts[2].isdigit()


class TestExceptionTypes:
    def test_sensitive_serialization_error_is_distinct_from_unredacted(self) -> None:
        # The two errors fire at different points in the pipeline; they're
        # not interchangeable. Pin the distinction so a future refactor
        # doesn't accidentally collapse them.
        assert not issubclass(SensitiveSerializationError, UnredactedSensitiveError)
        assert not issubclass(UnredactedSensitiveError, SensitiveSerializationError)

    def test_unredacted_error_is_distinct_class(self) -> None:
        # Just confirm UnredactedSensitiveError is importable and raisable.
        # It's used at the serializer boundary (Phase 5); Phase 1.2 only
        # needs the type to exist.
        with pytest.raises(UnredactedSensitiveError):
            raise UnredactedSensitiveError("test")
