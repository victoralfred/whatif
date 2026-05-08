"""Tests for `whatifd.types.verdict` — Phase 1.4 verdict types.

Three verdict states (sealed union) with the witness-token guard on Ship:
- Ship requires a FloorPassedProof; type system + closure-capture in
  decision/floor.py enforce that the proof can only come from
  evaluate_floor().
- DontShip requires blocking_findings to all have severity == "blocks_ship".
- Inconclusive requires blocking_findings to have severity in
  {"blocks_ship", "blocks_all"}.

Match-statement exhaustiveness over the Verdict union is checked by
mypy strict at the type-check layer; this file covers runtime invariants.
"""

from __future__ import annotations

import dataclasses

import pytest

from whatifd.decision.floor import FloorPassedProof, evaluate_floor
from whatifd.types import (
    CohortResult,
    DecimalString,
    DecisionFinding,
    DontShip,
    FloorFailure,
    Inconclusive,
    Ship,
    TrustFloor,
    Verdict,
)

# --- Fixtures -----------------------------------------------------------


def _passing_cohort(name: str = "failure") -> CohortResult:
    return CohortResult(
        name=name,
        selected=20,
        replayed=20,
        scored=20,
        ci_computable=True,
        ci_unavailable_reason=None,
        median_delta=DecimalString("0.310"),
        ci_lower=DecimalString("0.180"),
        ci_upper=DecimalString("0.440"),
        floor_passed=True,
    )


def _proof() -> FloorPassedProof:
    """A genuine FloorPassedProof from evaluate_floor()."""
    p = evaluate_floor(
        [_passing_cohort("failure"), _passing_cohort("baseline")],
        TrustFloor(),
        ("failure", "baseline"),
    )
    assert isinstance(p, FloorPassedProof)
    return p


def _info_finding(code: str = "improvement_observed") -> DecisionFinding:
    return DecisionFinding(code=code, severity="info", message="test")


def _blocks_ship_finding(code: str = "baseline_regression_above_threshold") -> DecisionFinding:
    return DecisionFinding(code=code, severity="blocks_ship", message="test")


def _blocks_all_finding(code: str = "cache_corruption_detected") -> DecisionFinding:
    return DecisionFinding(code=code, severity="blocks_all", message="test")


# --- Ship ---------------------------------------------------------------


class TestShip:
    def test_construction_with_genuine_proof(self) -> None:
        ship = Ship(
            proof=_proof(),
            cohort_results=[_passing_cohort("failure"), _passing_cohort("baseline")],
            findings=[_info_finding()],
        )
        assert isinstance(ship.proof, FloorPassedProof)
        assert len(ship.cohort_results) == 2

    def test_frozen(self) -> None:
        ship = Ship(proof=_proof(), cohort_results=[], findings=[])
        with pytest.raises(dataclasses.FrozenInstanceError):
            ship.findings = []  # type: ignore[misc]

    def test_proof_is_required(self) -> None:
        # Construction without proof= is a TypeError at the dataclass level.
        with pytest.raises(TypeError):
            Ship(cohort_results=[], findings=[])  # type: ignore[call-arg]


# --- DontShip -----------------------------------------------------------


class TestDontShip:
    def test_construction_with_blocking_findings(self) -> None:
        f = _blocks_ship_finding()
        ds = DontShip(
            cohort_results=[_passing_cohort("baseline")],
            findings=[f],
            blocking_findings=[f],
        )
        assert ds.blocking_findings == [f]

    def test_construction_with_no_blocking_findings(self) -> None:
        # A DontShip with empty blocking_findings is structurally permitted
        # but semantically odd — the decision pipeline would not produce
        # one in practice. The type doesn't enforce non-empty here; that's
        # an integration-test concern at the pipeline layer.
        ds = DontShip(cohort_results=[], findings=[], blocking_findings=[])
        assert ds.blocking_findings == []

    def test_blocks_all_finding_in_blocking_findings_raises(self) -> None:
        # blocks_all → Inconclusive, not DontShip. Validate severity at
        # construction time.
        f = _blocks_all_finding()
        with pytest.raises(ValueError, match="severity='blocks_ship'"):
            DontShip(cohort_results=[], findings=[f], blocking_findings=[f])

    def test_info_finding_in_blocking_findings_raises(self) -> None:
        f = _info_finding()
        with pytest.raises(ValueError, match="severity='blocks_ship'"):
            DontShip(cohort_results=[], findings=[f], blocking_findings=[f])

    def test_frozen(self) -> None:
        ds = DontShip(cohort_results=[], findings=[], blocking_findings=[])
        with pytest.raises(dataclasses.FrozenInstanceError):
            ds.findings = []  # type: ignore[misc]


# --- Inconclusive -------------------------------------------------------


class TestInconclusive:
    def test_construction_due_to_floor_failure(self) -> None:
        floor_fail = FloorFailure(
            rule="min_scored_per_required_cohort",
            observed=3,
            threshold=5,
            severity="blocks_all",
        )
        inc = Inconclusive(
            cohort_results=[_passing_cohort("failure")],
            findings=[],
            floor_failures=[floor_fail],
        )
        assert inc.floor_failures == [floor_fail]
        assert inc.blocking_findings == []

    def test_construction_due_to_blocks_all_finding(self) -> None:
        f = _blocks_all_finding("cache_lock_unavailable")
        inc = Inconclusive(
            cohort_results=[],
            findings=[f],
            blocking_findings=[f],
        )
        assert inc.blocking_findings == [f]

    def test_blocks_ship_finding_allowed_in_blocking(self) -> None:
        # Inconclusive's blocking_findings allows blocks_ship too — useful
        # when a Don't-Ship-eligible finding fires alongside a floor
        # failure (floor wins; the DontShip-flavored finding just
        # contextualizes).
        f = _blocks_ship_finding()
        inc = Inconclusive(cohort_results=[], findings=[f], blocking_findings=[f])
        assert inc.blocking_findings == [f]

    def test_info_finding_in_blocking_raises(self) -> None:
        f = _info_finding()
        with pytest.raises(ValueError, match="severity in"):
            Inconclusive(cohort_results=[], findings=[f], blocking_findings=[f])

    def test_degrades_trust_finding_in_blocking_raises(self) -> None:
        f = DecisionFinding(code="x", severity="degrades_trust", message="test")
        with pytest.raises(ValueError, match="severity in"):
            Inconclusive(cohort_results=[], findings=[f], blocking_findings=[f])


# --- Verdict union ------------------------------------------------------


class TestVerdictUnion:
    def test_ship_is_verdict(self) -> None:
        v: Verdict = Ship(proof=_proof(), cohort_results=[], findings=[])
        assert isinstance(v, Ship)

    def test_dont_ship_is_verdict(self) -> None:
        v: Verdict = DontShip(cohort_results=[], findings=[], blocking_findings=[])
        assert isinstance(v, DontShip)

    def test_inconclusive_is_verdict(self) -> None:
        v: Verdict = Inconclusive(cohort_results=[], findings=[])
        assert isinstance(v, Inconclusive)

    def test_match_statement_dispatches_correctly(self) -> None:
        # Pattern match exhaustiveness is a mypy-strict check; this runtime
        # test pins that match correctly dispatches each variant. Any future
        # verdict state addition (v1.0 Conditionally Ship) would require
        # updating this match — and mypy strict would flag the missing case.
        verdicts: list[Verdict] = [
            Ship(proof=_proof(), cohort_results=[], findings=[]),
            DontShip(cohort_results=[], findings=[], blocking_findings=[]),
            Inconclusive(cohort_results=[], findings=[]),
        ]
        labels: list[str] = []
        for v in verdicts:
            match v:
                case Ship():
                    labels.append("ship")
                case DontShip():
                    labels.append("dont_ship")
                case Inconclusive():
                    labels.append("inconclusive")
        assert labels == ["ship", "dont_ship", "inconclusive"]
