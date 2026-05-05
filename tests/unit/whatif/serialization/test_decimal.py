"""Tests for `parse_decimal_string` (early-shipped Phase 5 helper)."""

from __future__ import annotations

import warnings

import pytest

from whatif.exceptions import InvariantViolationError
from whatif.serialization.decimal import FieldLabel, parse_decimal_string
from whatif.types.primitives import DecimalString

# Convenience: most tests use a fixed label; some use a specific one.
_LABEL = FieldLabel("x")


class TestParseDecimalStringCanonical:
    """Canonical inputs — fixed-precision decimal with required decimal point."""

    def test_parses_positive_decimal(self) -> None:
        assert parse_decimal_string(DecimalString("0.310"), field=_LABEL) == 0.310

    def test_parses_negative_decimal(self) -> None:
        assert parse_decimal_string(DecimalString("-0.050"), field=_LABEL) == -0.050

    def test_parses_zero(self) -> None:
        assert parse_decimal_string(DecimalString("0.000"), field=_LABEL) == 0.0

    def test_canonical_input_does_not_warn(self) -> None:
        # Hard error if any warning fires on canonical input.
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            assert parse_decimal_string(DecimalString("0.310"), field=_LABEL) == 0.310


class TestParseDecimalStringNonCanonicalWarns:
    """Non-canonical-but-parseable inputs warn instead of raising.

    Phase 5 will flip these tests from `pytest.warns` to `pytest.raises`
    when `format_decimal_string` codifies the canonical shape and parse
    tightens to match.
    """

    def test_warns_on_integer_form(self) -> None:
        # `"42"` parses (`float()` accepts), but lacks a decimal point —
        # not the fixed-precision shape `format_decimal_string` will emit.
        with pytest.warns(FutureWarning, match="non-canonical"):
            result = parse_decimal_string(DecimalString("42"), field=_LABEL)
        assert result == 42.0

    def test_warns_on_scientific_notation(self) -> None:
        with pytest.warns(FutureWarning, match="non-canonical"):
            result = parse_decimal_string(DecimalString("1e-3"), field=_LABEL)
        assert result == 0.001

    def test_warning_message_includes_field_label(self) -> None:
        with pytest.warns(FutureWarning, match="median_delta"):
            parse_decimal_string(
                DecimalString("42"),
                field=FieldLabel("CohortResult.median_delta"),
            )

    def test_warning_message_includes_offending_value(self) -> None:
        with pytest.warns(FutureWarning, match="1e-3"):
            parse_decimal_string(DecimalString("1e-3"), field=_LABEL)

    def test_warning_mentions_phase_5_tightening(self) -> None:
        with pytest.warns(FutureWarning, match="Phase 5"):
            parse_decimal_string(DecimalString("42"), field=_LABEL)

    def test_future_warning_surfaces_under_library_context_filters(self) -> None:
        # Visibility pin: in production library use, Python's default
        # filters silence DeprecationWarning outside __main__.
        # FutureWarning is shown by default. This test simulates the
        # library-context filter set and confirms FutureWarning surfaces
        # — the empirical justification for choosing FutureWarning over
        # DeprecationWarning. If this test fails, library users won't
        # see the soft-warn drift signal and Phase 5's flip surface
        # widens silently.
        with warnings.catch_warnings(record=True) as recorded:
            # Library-context: silence DeprecationWarning, default-show FutureWarning.
            warnings.resetwarnings()
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            warnings.filterwarnings("default", category=FutureWarning)
            parse_decimal_string(DecimalString("42"), field=_LABEL)

        future_warnings = [w for w in recorded if issubclass(w.category, FutureWarning)]
        assert future_warnings, (
            "FutureWarning must surface under library-context filter set "
            "(DeprecationWarning ignored). If this fails, library users miss "
            "the soft-warn drift signal — see "
            "cascade-catalog `parse_decimal_string` permissiveness entry."
        )


class TestParseDecimalStringRaisesOnMalformed:
    def test_raises_on_non_numeric(self) -> None:
        with pytest.raises(InvariantViolationError, match="parseable as a number"):
            parse_decimal_string(DecimalString("not-a-number"), field=_LABEL)

    def test_error_message_includes_field_label(self) -> None:
        with pytest.raises(InvariantViolationError, match=r"CohortResult\.median_delta"):
            parse_decimal_string(
                DecimalString("garbage"),
                field=FieldLabel("CohortResult.median_delta"),
            )

    def test_error_message_includes_offending_value(self) -> None:
        with pytest.raises(InvariantViolationError, match="garbage"):
            parse_decimal_string(DecimalString("garbage"), field=_LABEL)

    def test_chains_underlying_value_error(self) -> None:
        with pytest.raises(InvariantViolationError) as exc_info:
            parse_decimal_string(DecimalString("garbage"), field=_LABEL)
        assert isinstance(exc_info.value.__cause__, ValueError)

    def test_raises_on_empty_string(self) -> None:
        with pytest.raises(InvariantViolationError):
            parse_decimal_string(DecimalString(""), field=_LABEL)
