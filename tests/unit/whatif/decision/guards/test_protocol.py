"""Tests for the `Guard` Protocol + `run_guards` chain composer."""

from __future__ import annotations

from collections.abc import Sequence

from whatif.decision.guards import Guard, run_guards
from whatif.decision.guards.improvement_observation import improvement_observation_guard
from whatif.decision.guards.practical_delta import practical_delta_guard
from whatif.types.cohort import CohortResult
from whatif.types.finding import DecisionFinding
from whatif.types.policy import DecisionPolicy
from whatif.types.primitives import DecimalString


def _failure_cohort(median_delta: str | None = "0.310") -> CohortResult:
    return CohortResult(
        name="failure",
        selected=10,
        replayed=10,
        scored=10,
        ci_available=True,
        ci_unavailable_reason=None,
        median_delta=DecimalString(median_delta) if median_delta is not None else None,
        ci_lower=None,
        ci_upper=None,
        floor_passed=True,
    )


class TestGuardProtocol:
    def test_practical_delta_guard_satisfies_protocol(self) -> None:
        # A plain function with the right signature passes `isinstance`
        # against a runtime-checkable protocol. Without runtime_checkable,
        # `isinstance` won't work at runtime — but the type system still
        # accepts it. We assert by assignment.
        g: Guard = practical_delta_guard
        assert callable(g)

    def test_improvement_observation_guard_satisfies_protocol(self) -> None:
        g: Guard = improvement_observation_guard
        assert callable(g)


class TestRunGuards:
    def test_empty_chain_returns_empty_list(self) -> None:
        result = run_guards([], [_failure_cohort()], DecisionPolicy())
        assert result == []

    def test_findings_are_concatenated_in_registration_order(self) -> None:
        # Guard 1 emits "improvement_observed" (failure delta 0.31 > 0.05).
        # Guard 2 (custom) emits a second info finding.
        # Order in output should match registration order.
        from whatif.decision.finding_codes import make_decision_finding

        def custom_info_guard(
            cohort_results: Sequence[CohortResult], policy: DecisionPolicy
        ) -> list[DecisionFinding]:
            return [
                make_decision_finding(
                    "improvement_observed",
                    message="custom",
                    details={"median_delta": "0.999"},
                )
            ]

        cohorts = [_failure_cohort("0.310")]
        result = run_guards(
            [improvement_observation_guard, custom_info_guard],
            cohorts,
            DecisionPolicy(),
        )
        assert len(result) == 2
        # First finding from improvement_observation_guard, second from custom
        assert result[0].details["median_delta"] == "0.310"
        assert result[1].details["median_delta"] == "0.999"

    def test_returns_fresh_list_each_call(self) -> None:
        # Caller may mutate the returned list without affecting future calls.
        cohorts = [_failure_cohort("0.310")]
        first = run_guards([improvement_observation_guard], cohorts, DecisionPolicy())
        first.clear()
        second = run_guards([improvement_observation_guard], cohorts, DecisionPolicy())
        assert len(second) == 1, "subsequent call must not see prior mutation"

    def test_guard_that_emits_zero_findings_contributes_nothing(self) -> None:
        # No failure cohort → both guards emit nothing → empty list
        result = run_guards(
            [practical_delta_guard, improvement_observation_guard],
            [],  # no cohorts
            DecisionPolicy(),
        )
        assert result == []
