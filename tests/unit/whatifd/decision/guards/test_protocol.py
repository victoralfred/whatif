"""Tests for the `Guard` Protocol + `run_guards` chain composer."""

from __future__ import annotations

from collections.abc import Sequence

from whatifd.decision.finding_codes import make_decision_finding
from whatifd.decision.guards import Guard, run_guards
from whatifd.decision.guards.improvement_observation import improvement_observation_guard
from whatifd.decision.guards.practical_delta import practical_delta_guard
from whatifd.types.cohort import CohortResult
from whatifd.types.finding import DecisionFinding
from whatifd.types.policy import DecisionPolicy

from ._helpers import failure_cohort as _failure_cohort


class TestGuardProtocol:
    def test_practical_delta_guard_satisfies_protocol(self) -> None:
        # `Guard` is a typing.Protocol — NOT `@runtime_checkable`. The
        # signature contract is enforced by mypy strict at type-check
        # time (the assignment below would fail mypy if the function
        # didn't match). At runtime there's nothing to assert beyond
        # callability; the type system is the contract.
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
        # Guard A emits info; Guard B emits blocks_ship. The two guards
        # produce findings with different codes AND different severities
        # so the order assertion can't pass on a details-payload
        # coincidence — registration order is verified by
        # finding-identity, not by content matching.

        def info_guard_a(
            cohort_results: Sequence[CohortResult], policy: DecisionPolicy
        ) -> list[DecisionFinding]:
            return [
                make_decision_finding(
                    "improvement_observed",
                    message="from A",
                    details={"median_delta": "0.500", "threshold": "0.050"},
                )
            ]

        def blocks_ship_guard_b(
            cohort_results: Sequence[CohortResult], policy: DecisionPolicy
        ) -> list[DecisionFinding]:
            return [
                make_decision_finding(
                    "practical_delta_below_threshold",
                    message="from B",
                    details={"median_delta": "0.020", "threshold": "0.050"},
                )
            ]

        result = run_guards(
            [info_guard_a, blocks_ship_guard_b],
            [_failure_cohort("0.500")],
            DecisionPolicy(),
        )
        assert len(result) == 2

        # First finding is from A: info severity, improvement_observed code.
        assert result[0].code == "improvement_observed"
        assert result[0].severity == "info"
        assert result[0].message == "from A"

        # Second finding is from B: blocks_ship severity, different code.
        assert result[1].code == "practical_delta_below_threshold"
        assert result[1].severity == "blocks_ship"
        assert result[1].message == "from B"

        # Reverse the registration order; assert the output flips.
        flipped = run_guards(
            [blocks_ship_guard_b, info_guard_a],
            [_failure_cohort("0.500")],
            DecisionPolicy(),
        )
        assert flipped[0].code == "practical_delta_below_threshold"
        assert flipped[1].code == "improvement_observed"

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

    def test_passes_same_cohort_results_object_to_every_guard(self) -> None:
        # Pin the no-mutation contract structurally: run_guards must
        # pass the SAME cohort_results object (by `is` identity) to
        # every guard. If a future implementation accidentally
        # rebound or copied the input mid-loop, callers expecting
        # shared state would see drift.
        received: list[Sequence[CohortResult]] = []

        def spy_guard(
            cohort_results: Sequence[CohortResult], policy: DecisionPolicy
        ) -> list[DecisionFinding]:
            received.append(cohort_results)
            return []

        cohorts = [_failure_cohort()]
        run_guards([spy_guard, spy_guard, spy_guard], cohorts, DecisionPolicy())
        assert len(received) == 3
        assert all(r is cohorts for r in received), (
            "every guard must receive the SAME cohort_results object identity"
        )

    def test_passes_same_policy_object_to_every_guard(self) -> None:
        # Symmetric to the cohort_results check.
        received: list[DecisionPolicy] = []

        def spy_guard(
            cohort_results: Sequence[CohortResult], policy: DecisionPolicy
        ) -> list[DecisionFinding]:
            received.append(policy)
            return []

        policy = DecisionPolicy()
        run_guards([spy_guard, spy_guard], [_failure_cohort()], policy)
        assert len(received) == 2
        assert all(r is policy for r in received)
