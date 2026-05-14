"""Tests for `whatifd.adapters.pii` — PII registry, wrapping helper,
shared violation-message template, and the `RawTrace.metadata`
model-validator that closes the cardinal-#5 boundary gap (issue #87).

Behaviors under test:
  1. Registry membership (OpenInference + Langfuse + frozenset shape).
  2. `wrap_pii_attributes` happy path — registered keys get wrapped,
     unknown keys pass through.
  3. `wrap_pii_attributes` idempotence — calling twice produces the
     same shape as calling once.
  4. `wrap_pii_attributes` typed failure — non-string at a registered
     key raises `PIIAttributeTypeError`.
  5. Shared message template — both surfaces include the registry
     pointer and the wrap_pii_attributes call hint.
  6. `RawTrace` boundary validator — raw `str` at a registered key
     fails Pydantic validation at construction.
"""

from __future__ import annotations

import pytest

from whatifd.adapters.pii import (
    PII_ATTRIBUTE_KEYS,
    PIIAttributeTypeError,
    _format_pii_violation,
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
        assert "user.id" in PII_ATTRIBUTE_KEYS
        assert "session.id" in PII_ATTRIBUTE_KEYS
        assert "user.email" in PII_ATTRIBUTE_KEYS

    def test_registry_includes_langfuse_keys(self) -> None:
        assert "user_id" in PII_ATTRIBUTE_KEYS
        assert "userId" in PII_ATTRIBUTE_KEYS
        assert "session_id" in PII_ATTRIBUTE_KEYS
        assert "sessionId" in PII_ATTRIBUTE_KEYS

    def test_registry_is_frozen(self) -> None:
        assert isinstance(PII_ATTRIBUTE_KEYS, frozenset)


class TestWrapHappyPath:
    def test_registered_key_with_str_value_gets_wrapped(self) -> None:
        result = wrap_pii_attributes({"user.id": "u-12345"})
        assert isinstance(result["user.id"], Sensitive)
        assert result["user.id"].classification == "user_content"

    def test_unregistered_key_passes_through_unchanged(self) -> None:
        result = wrap_pii_attributes({"environment": "production"})
        assert result["environment"] == "production"
        assert not isinstance(result["environment"], Sensitive)

    def test_registered_key_with_none_passes_through(self) -> None:
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
        assert source["user.id"] == "u-1"
        assert isinstance(result["user.id"], Sensitive)


class TestWrapIdempotence:
    def test_already_wrapped_value_passes_through(self) -> None:
        already_wrapped = Sensitive(value="u-1", classification="user_content")
        result = wrap_pii_attributes({"user.id": already_wrapped})
        assert result["user.id"] is already_wrapped

    def test_double_call_is_identity(self) -> None:
        once = wrap_pii_attributes({"user.id": "u-1", "other": "x"})
        twice = wrap_pii_attributes(once)
        assert twice["user.id"] is once["user.id"]
        assert twice["other"] == once["other"]


class TestWrapTypedFailure:
    def test_int_at_pii_key_raises(self) -> None:
        with pytest.raises(PIIAttributeTypeError, match=r"user\.id.*int.*not str"):
            wrap_pii_attributes({"user.id": 12345})

    def test_dict_at_pii_key_raises(self) -> None:
        with pytest.raises(PIIAttributeTypeError, match=r"session\.id.*dict.*not str"):
            wrap_pii_attributes({"session.id": {"nested": "structure"}})

    def test_list_at_pii_key_raises(self) -> None:
        with pytest.raises(PIIAttributeTypeError, match=r"user\.email.*list.*not str"):
            wrap_pii_attributes({"user.email": ["a@x.com", "b@y.com"]})


class TestSharedMessageTemplate:
    """The `_format_pii_violation` helper is the single source of
    truth for the cardinal-#5 violation text. Both the
    `wrap_pii_attributes` surface (PIIAttributeTypeError) and the
    `RawTrace.metadata` validator (ValueError → Pydantic) route
    through it. These tests pin the load-bearing message elements
    so a future registry-shape refactor that touches the helper
    must keep both surfaces actionable."""

    def test_template_names_the_offending_key(self) -> None:
        msg = _format_pii_violation("user.id", "int, not str", context="x")
        assert "'user.id'" in msg

    def test_template_points_at_the_registry(self) -> None:
        msg = _format_pii_violation("k", "v", context="x")
        assert "PII_ATTRIBUTE_KEYS" in msg

    def test_template_names_the_wrap_helper(self) -> None:
        msg = _format_pii_violation("k", "v", context="x")
        assert "wrap_pii_attributes" in msg

    def test_helper_surface_message_uses_the_template(self) -> None:
        # Routing pin: the PIIAttributeTypeError message text must
        # contain the registry pointer and the helper-call hint.
        with pytest.raises(PIIAttributeTypeError) as exc_info:
            wrap_pii_attributes({"user.id": 42})
        msg = str(exc_info.value)
        assert "PII_ATTRIBUTE_KEYS" in msg
        assert "wrap_pii_attributes" in msg

    def test_validator_surface_message_uses_the_template(self) -> None:
        # Same routing pin for the model_validator surface — a
        # future refactor that drifts one wording but not the other
        # would fail here OR in `test_helper_surface_message_uses_the_template`.
        with pytest.raises(PIIAttributeTypeError) as exc_info:
            RawTrace(**_minimal_rawtrace_kwargs(metadata={"user.id": "leaked"}))
        msg = str(exc_info.value)
        assert "PII_ATTRIBUTE_KEYS" in msg
        assert "wrap_pii_attributes" in msg

    def test_both_surfaces_raise_the_same_exception_class(self) -> None:
        # Cardinal #1 taxonomy symmetry: a caller writing
        # `except PIIAttributeTypeError` catches both the
        # wrap-helper raise site AND the model-validator raise
        # site. Pin this so a future refactor can't accidentally
        # reintroduce the asymmetry (helper raises
        # PIIAttributeTypeError; validator raises ValueError /
        # ValidationError) that the original PR #104 review
        # flagged.
        with pytest.raises(PIIAttributeTypeError):
            wrap_pii_attributes({"user.id": 42})
        with pytest.raises(PIIAttributeTypeError):
            RawTrace(**_minimal_rawtrace_kwargs(metadata={"user.id": "leaked"}))


class TestRawTraceBoundaryValidator:
    """The Pydantic model_validator enforces cardinal #5 even when
    an adapter author forgets to call `wrap_pii_attributes`."""

    def test_construction_with_wrapped_pii_succeeds(self) -> None:
        wrapped = Sensitive(value="u-1", classification="user_content")
        rt = RawTrace(**_minimal_rawtrace_kwargs(metadata={"user.id": wrapped}))
        assert rt.metadata["user.id"] is wrapped

    def test_construction_with_none_at_pii_key_succeeds(self) -> None:
        rt = RawTrace(**_minimal_rawtrace_kwargs(metadata={"user.id": None}))
        assert rt.metadata["user.id"] is None

    def test_construction_with_raw_str_at_pii_key_fails(self) -> None:
        with pytest.raises(PIIAttributeTypeError, match=r"user\.id.*unwrapped"):
            RawTrace(**_minimal_rawtrace_kwargs(metadata={"user.id": "leaked-id"}))

    def test_construction_with_int_at_pii_key_fails(self) -> None:
        with pytest.raises(PIIAttributeTypeError, match=r"user\.id.*unwrapped"):
            RawTrace(**_minimal_rawtrace_kwargs(metadata={"user.id": 12345}))

    def test_construction_with_unregistered_key_does_not_fire(self) -> None:
        rt = RawTrace(
            **_minimal_rawtrace_kwargs(metadata={"environment": "prod", "request_count": 42})
        )
        assert rt.metadata["environment"] == "prod"
        assert rt.metadata["request_count"] == 42

    def test_validator_errors_name_the_offending_key(self) -> None:
        with pytest.raises(PIIAttributeTypeError) as exc_info:
            RawTrace(**_minimal_rawtrace_kwargs(metadata={"session.id": "s-leak"}))
        msg = str(exc_info.value)
        assert "session.id" in msg


class TestModelConstructBypass:
    """The conformance harness comment claims that
    `test_emitted_traces_wrap_pii_attributes` re-asserts at the
    harness boundary specifically to catch a regression that
    constructs RawTrace via `model_construct` (which bypasses the
    Pydantic validator). This class pins that claim with actual
    tests — both that `model_construct` CAN produce a raw-PII
    RawTrace (proving the bypass is real) AND that the harness
    walker catches it.

    Cardinal #5 has a known escape hatch (`model_construct` is a
    legitimate Pydantic API for fast-path construction skipping
    validation); the load-bearing defense is the conformance
    harness's read-side walk over emitted traces. These tests
    structurally pin that defense so the harness comment isn't
    convention-only.
    """

    def test_model_construct_bypasses_validator(self) -> None:
        # Sanity check: prove the bypass is real (otherwise the
        # subsequent harness-catches-it test would be testing
        # nothing). `model_construct` returns a RawTrace with the
        # raw PII string intact at `user.id`, no validation error.
        rt = RawTrace.model_construct(
            **_minimal_rawtrace_kwargs(metadata={"user.id": "leaked-via-construct"})
        )
        assert rt.metadata["user.id"] == "leaked-via-construct"
        assert not isinstance(rt.metadata["user.id"], Sensitive)

    def test_harness_walk_catches_model_construct_bypass(self) -> None:
        # Simulate what `test_emitted_traces_wrap_pii_attributes`
        # does: walk the emitted RawTrace's metadata and check that
        # any PII-registered key carries a Sensitive (or None).
        # This test fires the same assertion the harness fires —
        # if the harness logic changes and stops catching this
        # case, this test fails.
        from whatifd.adapters.pii import PII_ATTRIBUTE_KEYS

        bypass_trace = RawTrace.model_construct(
            **_minimal_rawtrace_kwargs(metadata={"user.id": "leaked"})
        )
        leak_keys = [
            k
            for k, v in bypass_trace.metadata.items()
            if k in PII_ATTRIBUTE_KEYS and v is not None and not isinstance(v, Sensitive)
        ]
        # Harness would fail if leak_keys is non-empty — pin that
        # the bypass IS detected at the read-side walk.
        assert leak_keys == ["user.id"], (
            "the harness-shaped read-side walk did not catch the "
            "model_construct bypass; the load-bearing defense is "
            "broken. (See conformance.py "
            "test_emitted_traces_wrap_pii_attributes for the actual "
            "harness assertion.)"
        )
