"""Tests for `practical_delta_guard`."""

from __future__ import annotations

import pytest

from whatifd.decision.guards.practical_delta import practical_delta_guard
from whatifd.exceptions import InvariantViolationError
from whatifd.types.cohort import CohortResult
from whatifd.types.policy import DecisionPolicy
from whatifd.types.primitives import DecimalString

from ._helpers import failure_cohort as _failure_cohort


class TestPracticalDeltaGuardEmits:
    def test_emits_when_median_delta_below_epsilon(self) -> None:
        # 0.030 < default epsilon 0.050
        findings = practical_delta_guard([_failure_cohort("0.030")], DecisionPolicy())
        assert len(findings) == 1
        f = findings[0]
        assert f.code == "practical_delta_below_threshold"
        assert f.severity == "blocks_ship"
        assert f.details["median_delta"] == "0.030"
        assert f.details["threshold"] == "0.050"

    def test_emits_at_exactly_epsilon(self) -> None:
        # Equality is below-threshold per the docstring.
        # 0.050 == default epsilon 0.050 → emit
        findings = practical_delta_guard([_failure_cohort("0.050")], DecisionPolicy())
        assert len(findings) == 1

    def test_emits_for_negative_delta(self) -> None:
        # Negative delta is "below threshold" trivially.
        findings = practical_delta_guard([_failure_cohort("-0.010")], DecisionPolicy())
        assert len(findings) == 1


class TestPracticalDeltaGuardSilent:
    def test_silent_when_above_epsilon(self) -> None:
        # 0.310 > 0.050 → no finding (improvement observed, not below threshold)
        findings = practical_delta_guard([_failure_cohort("0.310")], DecisionPolicy())
        assert findings == []

    def test_silent_when_no_failure_cohort(self) -> None:
        # No cohort named "failure" → guard abstains
        cohorts = [
            CohortResult(
                name="baseline",
                selected=10,
                replayed=10,
                scored=10,
                ci_computable=True,
                ci_unavailable_reason=None,
                median_delta=DecimalString("0.020"),
                ci_lower=None,
                ci_upper=None,
                floor_passed=True,
            )
        ]
        findings = practical_delta_guard(cohorts, DecisionPolicy())
        assert findings == []

    def test_silent_when_median_delta_is_none(self) -> None:
        findings = practical_delta_guard([_failure_cohort(None)], DecisionPolicy())
        assert findings == []

    def test_silent_when_empty_cohort_list(self) -> None:
        findings = practical_delta_guard([], DecisionPolicy())
        assert findings == []


class TestPracticalDeltaGuardThresholdCustom:
    def test_respects_custom_epsilon(self) -> None:
        # Custom policy epsilon=0.20; failure delta 0.150 → below threshold
        policy = DecisionPolicy(practical_delta_epsilon=0.20)
        findings = practical_delta_guard([_failure_cohort("0.150")], policy)
        assert len(findings) == 1
        assert findings[0].details["threshold"] == "0.200"

    def test_respects_custom_epsilon_above_default(self) -> None:
        # With epsilon=0.40, even 0.310 (which would normally pass) is now below
        policy = DecisionPolicy(practical_delta_epsilon=0.40)
        findings = practical_delta_guard([_failure_cohort("0.310")], policy)
        assert len(findings) == 1


class TestPracticalDeltaGuardDoesNotMutate:
    def test_does_not_mutate_inputs(self) -> None:
        # CohortResult is frozen; verifying the guard returns a fresh list
        # rather than touching inputs is a smoke check.
        cohorts = [_failure_cohort("0.030")]
        original_name = cohorts[0].name
        _ = practical_delta_guard(cohorts, DecisionPolicy())
        assert cohorts[0].name == original_name


class TestPracticalDeltaGuardMalformedDelta:
    def test_raises_invariant_violation_on_non_numeric_string(self) -> None:
        # A non-numeric DecimalString is a structural integrity
        # violation upstream — the type contract is "decimal-formatted
        # string". Per cardinal #1, bugs propagate as a typed
        # `InvariantViolationError` (not stdlib `ValueError`) so the call-
        # site intent is legible. PR #23 reviewer flagged the earlier
        # silent-abstention path as tensioning with cardinal #1.
        cohort = CohortResult(
            name="failure",
            selected=10,
            replayed=10,
            scored=10,
            ci_computable=True,
            ci_unavailable_reason=None,
            median_delta=DecimalString("not-a-number"),  # misuse
            ci_lower=None,
            ci_upper=None,
            floor_passed=True,
        )
        with pytest.raises(InvariantViolationError, match="parseable as a number"):
            practical_delta_guard([cohort], DecisionPolicy())

    def test_invariant_violation_chains_underlying_value_error(self) -> None:
        # `raise ... from e` preserves the stdlib ValueError as __cause__
        # so the underlying parse failure is recoverable in tracebacks.
        cohort = CohortResult(
            name="failure",
            selected=10,
            replayed=10,
            scored=10,
            ci_computable=True,
            ci_unavailable_reason=None,
            median_delta=DecimalString("garbage"),
            ci_lower=None,
            ci_upper=None,
            floor_passed=True,
        )
        with pytest.raises(InvariantViolationError) as exc_info:
            practical_delta_guard([cohort], DecisionPolicy())
        assert isinstance(exc_info.value.__cause__, ValueError)
