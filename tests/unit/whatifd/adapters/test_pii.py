"""Tests for `whatifd.adapters.pii` — PII registry, wrapping helper,
and the `RawTrace.metadata` model-validator that closes the
cardinal-#5 boundary gap (issue #87).

The four behaviors under test:
  1. `wrap_pii_attributes` happy path — registered keys get wrapped,
     unknown keys pass through.
  2. `wrap_pii_attributes` idempotence — calling twice produces the
     same shape as calling once.
  3. `wrap_pii_attributes` typed failure — non-string at a registered
     key raises `PIIAttributeTypeError`.
  4. `RawTrace` boundary validator — raw `str` at a registered key
     fails Pydantic validation at construction (the structural
     enforcement that doesn't depend on adapters calling the helper).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from whatifd.adapters.pii import (
    PII_ATTRIBUTE_KEYS,
    PIIAttributeTypeError,
    wrap_pii_attributes,
)
from whatifd.adapters.protocols import RawTrace
from whatifd.types.sensitive import Sensitive


def _minimal_rawtrace_kwargs(**overrides):
    base = {
        "trace_id": "t1",
        "cohort": "failure",
        "user_message": Sensitive(value="hi", classification="user_content"),
        "original_response": Sensitive(value="bye", classification="user_content"),
        "metadata": {},
    }
    base.update(overrides)
    return base


class TestRegistry:
    def test_registry_includes_openinference_keys(self) -> None:
        # The shipped Phoenix adapter reads OpenInference attrs.
        # If one of these moves out of the registry, the Phoenix
        # adapter's conformance test fails — pin the membership
        # here so a refactor of the registry surface name fails
        # loudly.
        assert "user.id" in PII_ATTRIBUTE_KEYS
        assert "session.id" in PII_ATTRIBUTE_KEYS
        assert "user.email" in PII_ATTRIBUTE_KEYS

    def test_registry_includes_langfuse_keys(self) -> None:
        # The shipped Langfuse adapter reads `trace.metadata` which
        # uses snake_case or camelCase per SDK version. Both
        # spellings must be in the registry; the harness assertion
        # depends on this.
        assert "user_id" in PII_ATTRIBUTE_KEYS
        assert "userId" in PII_ATTRIBUTE_KEYS
        assert "session_id" in PII_ATTRIBUTE_KEYS
        assert "sessionId" in PII_ATTRIBUTE_KEYS

    def test_registry_is_frozen(self) -> None:
        # frozenset, not set — accidental mutation must not be
        # possible. A future v0.3 register_pii_attribute() API
        # would rebind the module-level name, not mutate the set.
        assert isinstance(PII_ATTRIBUTE_KEYS, frozenset)


class TestWrapHappyPath:
    def test_registered_key_with_str_value_gets_wrapped(self) -> None:
        result = wrap_pii_attributes({"user.id": "u-12345"})
        assert isinstance(result["user.id"], Sensitive)
        assert result["user.id"].classification == "user_content"

    def test_unregistered_key_passes_through_unchanged(self) -> None:
        result = wrap_pii_attributes({"environment": "production"})
        # Identity-equal because the helper is non-mutating on
        # passthrough values.
        assert result["environment"] == "production"
        assert not isinstance(result["environment"], Sensitive)

    def test_registered_key_with_none_passes_through(self) -> None:
        # A missing identifier is not PII to wrap.
        result = wrap_pii_attributes({"user.id": None})
        assert result["user.id"] is None

    def test_mixed_dict_processes_each_key_independently(self) -> None:
        result = wrap_pii_attributes(
            {
                "user.id": "u-1",
                "environment": "production",
                "session.id": "s-2",
                "request_count": 42,
            }
        )
        assert isinstance(result["user.id"], Sensitive)
        assert isinstance(result["session.id"], Sensitive)
        assert result["environment"] == "production"
        assert result["request_count"] == 42

    def test_returns_fresh_dict_does_not_mutate_input(self) -> None:
        source = {"user.id": "u-1"}
        result = wrap_pii_attributes(source)
        # Input dict is left raw — the helper returns a new dict.
        assert source["user.id"] == "u-1"
        assert isinstance(result["user.id"], Sensitive)


class TestWrapIdempotence:
    def test_already_wrapped_value_passes_through(self) -> None:
        already_wrapped = Sensitive(value="u-1", classification="user_content")
        result = wrap_pii_attributes({"user.id": already_wrapped})
        # Same identity — no double-wrap.
        assert result["user.id"] is already_wrapped

    def test_double_call_is_identity(self) -> None:
        once = wrap_pii_attributes({"user.id": "u-1", "other": "x"})
        twice = wrap_pii_attributes(once)
        assert twice["user.id"] is once["user.id"]
        assert twice["other"] == once["other"]


class TestWrapTypedFailure:
    def test_int_at_pii_key_raises(self) -> None:
        # Cardinal #1: silent passthrough is forbidden. A future
        # adapter that emits a structured value at user.id must
        # restructure it (e.g., flatten the identifier) rather than
        # let it through.
        with pytest.raises(PIIAttributeTypeError, match=r"user\.id.*int.*not str"):
            wrap_pii_attributes({"user.id": 12345})

    def test_dict_at_pii_key_raises(self) -> None:
        with pytest.raises(PIIAttributeTypeError, match=r"session\.id.*dict.*not str"):
            wrap_pii_attributes({"session.id": {"nested": "structure"}})

    def test_list_at_pii_key_raises(self) -> None:
        with pytest.raises(PIIAttributeTypeError, match=r"user\.email.*list.*not str"):
            wrap_pii_attributes({"user.email": ["a@x.com", "b@y.com"]})


class TestRawTraceBoundaryValidator:
    """The Pydantic model_validator enforces cardinal #5 even when
    an adapter author forgets to call `wrap_pii_attributes`. This
    is the structural backstop; the helper is the ergonomic
    front-door."""

    def test_construction_with_wrapped_pii_succeeds(self) -> None:
        wrapped = Sensitive(value="u-1", classification="user_content")
        # No exception.
        rt = RawTrace(**_minimal_rawtrace_kwargs(metadata={"user.id": wrapped}))
        assert rt.metadata["user.id"] is wrapped

    def test_construction_with_none_at_pii_key_succeeds(self) -> None:
        rt = RawTrace(**_minimal_rawtrace_kwargs(metadata={"user.id": None}))
        assert rt.metadata["user.id"] is None

    def test_construction_with_raw_str_at_pii_key_fails(self) -> None:
        with pytest.raises(ValidationError, match=r"user\.id.*unwrapped"):
            RawTrace(**_minimal_rawtrace_kwargs(metadata={"user.id": "leaked-id"}))

    def test_construction_with_int_at_pii_key_fails(self) -> None:
        with pytest.raises(ValidationError, match=r"user\.id.*unwrapped"):
            RawTrace(**_minimal_rawtrace_kwargs(metadata={"user.id": 12345}))

    def test_construction_with_unregistered_key_does_not_fire(self) -> None:
        # Non-PII keys retain their `Mapping[str, Any]` flexibility;
        # the validator must not over-reach.
        rt = RawTrace(
            **_minimal_rawtrace_kwargs(metadata={"environment": "prod", "request_count": 42})
        )
        assert rt.metadata["environment"] == "prod"
        assert rt.metadata["request_count"] == 42

    def test_validator_errors_name_the_offending_key(self) -> None:
        # The error message must point the adapter author at the
        # specific key, not just say "PII rule violated." Cardinal
        # #8: every blocking failure must be actionable.
        with pytest.raises(ValidationError) as exc_info:
            RawTrace(**_minimal_rawtrace_kwargs(metadata={"session.id": "s-leak"}))
        msg = str(exc_info.value)
        assert "session.id" in msg
        assert "wrap_pii_attributes" in msg
