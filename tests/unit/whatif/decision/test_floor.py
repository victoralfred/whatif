"""Tests for `whatif.decision.floor` — Phase 1.4 witness + Phase 2.1 evaluator.

Cardinal rule #2: trust floor cannot be bypassed. The witness-token
pattern enforces this at the type level — Ship requires a
FloorPassedProof; only `evaluate_floor()` can produce one (closure-
captured token).

Phase 2.1 replaces the no-arg stub with a real evaluator over
`Sequence[CohortResult]` and `TrustFloor`, plus the per-cohort helper
`compute_cohort_floor_failures`.

These tests cover:
- Positive: `evaluate_floor(...)` over passing cohorts produces a valid proof.
- Adversarial (basic): direct construction with a fabricated token raises.
- Adversarial (advanced): __closure__ introspection IS a real bypass;
  this is documented as a known v0.1 limit and resolved in v1.0 by
  cohort-hash binding (CASCADE-205, deferred).
- Immutability: proofs cannot be mutated after construction.
- Equality: proofs with the same metadata are structurally equal.
- FloorFailureSet: alternative branch type for the union return.
- Per-cohort rule evaluation: each rule trips at its boundary.
- Aggregation: failures across cohorts collected; missing cohorts emit
  `required_cohort_present`.
- Timestamp: `evaluated_at` is a real ISO 8601 string from the injected clock.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from whatif.decision.floor import (
    FloorFailureSet,
    FloorPassedProof,
    compute_cohort_floor_failures,
    evaluate_floor,
)
from whatif.types import CohortResult, FloorFailure, TrustFloor


def _passing_cohort(name: str = "failure") -> CohortResult:
    """Build a CohortResult that passes the default TrustFloor."""
    return CohortResult(
        name=name,
        selected=10,
        replayed=10,
        scored=10,
        ci_computable=True,
        ci_unavailable_reason=None,
        median_delta=None,
        ci_lower=None,
        ci_upper=None,
        floor_passed=True,
    )


def _passing_pair() -> list[CohortResult]:
    return [_passing_cohort("failure"), _passing_cohort("baseline")]


_FIXED_NOW = lambda: datetime(2026, 5, 3, 12, 0, 0, tzinfo=UTC)  # noqa: E731


class TestEvaluateFloorProducesValidProof:
    def test_returns_floor_passed_proof(self) -> None:
        result = evaluate_floor(
            _passing_pair(), TrustFloor(), ("failure", "baseline"), now=_FIXED_NOW
        )
        assert isinstance(result, FloorPassedProof)

    def test_proof_carries_floor_version(self) -> None:
        proof = evaluate_floor(
            _passing_pair(), TrustFloor(), ("failure", "baseline"), now=_FIXED_NOW
        )
        assert isinstance(proof, FloorPassedProof)
        assert proof.floor_version == "v1"

    def test_proof_carries_iso_8601_evaluated_at(self) -> None:
        proof = evaluate_floor(
            _passing_pair(), TrustFloor(), ("failure", "baseline"), now=_FIXED_NOW
        )
        assert isinstance(proof, FloorPassedProof)
        assert proof.evaluated_at == "2026-05-03T12:00:00+00:00"
        # Round-trips back through fromisoformat without raising.
        assert datetime.fromisoformat(proof.evaluated_at) == _FIXED_NOW()

    def test_proof_uses_floor_version_from_argument(self) -> None:
        proof = evaluate_floor(
            _passing_pair(),
            TrustFloor(version="v2-experimental"),
            ("failure", "baseline"),
            now=_FIXED_NOW,
        )
        assert isinstance(proof, FloorPassedProof)
        assert proof.floor_version == "v2-experimental"

    def test_default_clock_produces_real_timestamp(self) -> None:
        # Without injecting `now`, the proof carries a real wall-clock UTC
        # ISO 8601 string. We can't pin the value, but we can pin the shape.
        before = datetime.now(UTC)
        proof = evaluate_floor(_passing_pair(), TrustFloor(), ("failure", "baseline"))
        after = datetime.now(UTC)
        assert isinstance(proof, FloorPassedProof)
        parsed = datetime.fromisoformat(proof.evaluated_at)
        assert before <= parsed <= after


class TestExternalConstructionBlocked:
    def test_object_token_raises(self) -> None:
        # The most obvious bypass: pass a fresh object() as the token.
        with pytest.raises(TypeError, match="cannot be constructed externally"):
            FloorPassedProof(
                _token=object(),
                floor_version="v1",
                evaluated_at="forged",
            )

    def test_none_token_raises(self) -> None:
        with pytest.raises(TypeError, match="cannot be constructed externally"):
            FloorPassedProof(
                _token=None,  # type: ignore[arg-type]
                floor_version="v1",
                evaluated_at="forged",
            )

    def test_string_token_raises(self) -> None:
        with pytest.raises(TypeError, match="cannot be constructed externally"):
            FloorPassedProof(
                _token="any string",
                floor_version="v1",
                evaluated_at="forged",
            )


class TestKnownIntrospectionBypass:
    """Document the known v0.1 limit.

    Closure-capture is bypassable by Python introspection — adversarial
    code can extract the captured token from `__closure__[N].cell_contents`
    and pass it to `FloorPassedProof.__init__`. The point of these tests
    is NOT to claim the bypass is impossible, but to document it
    explicitly as a known limit.

    The v0.1 defense layers:
    1. Type-level: closure-capture (this module). Catches accidental
       bypasses (e.g., a contributor refactor that adds a non-floor
       construction site).
    2. Code-review-level: any code that does `__closure__` introspection
       is visibly adversarial.
    3. Property-test-level (Phase 2 gate): "no DecisionPolicy
       configuration produces Ship when evaluate_floor returns
       FloorFailureSet" — catches policy-coverage gaps.

    The v1.0 hardening (CASCADE-205) adds `_cohort_results_hash` to the
    proof and verifies in `Ship.__post_init__` that the hash matches the
    actual cohort_results. Then introspection-extracted tokens still
    produce valid proofs, but those proofs don't match any concrete
    Ship's cohort results — the hash check fails.
    """

    def test_closure_introspection_is_a_real_bypass(self) -> None:
        # Extract the captured token via __closure__. This is the documented
        # bypass path. The test pins that it works in v0.1; v1.0 cohort-hash
        # binding closes it at the Ship.__post_init__ layer.
        closure = FloorPassedProof.__init__.__closure__  # type: ignore[attr-defined]
        assert closure is not None, "expected closure cells from _build_floor_machinery"

        # Find the cell containing the token. The token is `object()`, not
        # a primitive, so we identify it as the cell whose contents are an
        # instance of `object` and not a closure cell of any other type.
        token = None
        for cell in closure:
            value = cell.cell_contents
            if type(value) is object:
                token = value
                break

        assert token is not None, "expected to find the closure-captured token"

        # Use the extracted token to construct a "valid" proof externally.
        # This succeeds in v0.1 — that's the known limit.
        forged = FloorPassedProof(
            _token=token,
            floor_version="v1",
            evaluated_at="introspection-bypass",
        )
        assert isinstance(forged, FloorPassedProof)
        assert forged.evaluated_at == "introspection-bypass"


class TestImmutability:
    def test_cannot_set_floor_version(self) -> None:
        proof = evaluate_floor(
            _passing_pair(), TrustFloor(), ("failure", "baseline"), now=_FIXED_NOW
        )
        assert isinstance(proof, FloorPassedProof)
        with pytest.raises(AttributeError, match="immutable"):
            proof.floor_version = "v2"

    def test_cannot_set_evaluated_at(self) -> None:
        proof = evaluate_floor(
            _passing_pair(), TrustFloor(), ("failure", "baseline"), now=_FIXED_NOW
        )
        assert isinstance(proof, FloorPassedProof)
        with pytest.raises(AttributeError, match="immutable"):
            proof.evaluated_at = "forged"

    def test_cannot_add_arbitrary_attribute(self) -> None:
        proof = evaluate_floor(
            _passing_pair(), TrustFloor(), ("failure", "baseline"), now=_FIXED_NOW
        )
        with pytest.raises(AttributeError, match="immutable"):
            proof.smuggled = "extra"  # type: ignore[attr-defined]


class TestProofEquality:
    def test_two_proofs_same_metadata_are_equal(self) -> None:
        p1 = evaluate_floor(_passing_pair(), TrustFloor(), ("failure", "baseline"), now=_FIXED_NOW)
        p2 = evaluate_floor(_passing_pair(), TrustFloor(), ("failure", "baseline"), now=_FIXED_NOW)
        # Same fixed clock → same evaluated_at → structural equality.
        assert p1 == p2

    def test_proof_compares_unequal_to_non_proof(self) -> None:
        proof = evaluate_floor(
            _passing_pair(), TrustFloor(), ("failure", "baseline"), now=_FIXED_NOW
        )
        assert proof != "FloorPassedProof"
        assert proof != ("v1", "stub")

    def test_proof_is_hashable(self) -> None:
        proof = evaluate_floor(
            _passing_pair(), TrustFloor(), ("failure", "baseline"), now=_FIXED_NOW
        )
        twin = evaluate_floor(
            _passing_pair(), TrustFloor(), ("failure", "baseline"), now=_FIXED_NOW
        )
        assert hash(proof) == hash(twin)


class TestFloorFailureSet:
    def test_empty_construction(self) -> None:
        s = FloorFailureSet()
        assert len(s) == 0
        assert not s

    def test_with_failures(self) -> None:
        s = FloorFailureSet(
            failures=[
                FloorFailure(
                    rule="min_scored_per_required_cohort",
                    observed=3,
                    threshold=5,
                    severity="blocks_all",
                ),
            ]
        )
        assert len(s) == 1
        assert bool(s) is True

    def test_iteration(self) -> None:
        f1 = FloorFailure(rule="r1", observed=0, threshold=1, severity="blocks_all")
        f2 = FloorFailure(rule="r2", observed=0, threshold=1, severity="blocks_ship")
        s = FloorFailureSet(failures=[f1, f2])
        assert list(s) == [f1, f2]

    def test_failure_set_does_not_need_token(self) -> None:
        # Construction is unguarded — anyone can build a FloorFailureSet.
        # That's intentional: the failure branch carries no privilege.
        # Adversarial code constructing a FloorFailureSet can only force
        # the run into Inconclusive, not into Ship.
        s = FloorFailureSet(failures=[])
        assert s is not None


# ---------------------------------------------------------------------------
# Phase 2.1: per-cohort evaluation + aggregation
# ---------------------------------------------------------------------------


def _cohort(
    *,
    name: str = "failure",
    selected: int = 10,
    replayed: int = 10,
    scored: int = 10,
) -> CohortResult:
    return CohortResult(
        name=name,
        selected=selected,
        replayed=replayed,
        scored=scored,
        ci_computable=True,
        ci_unavailable_reason=None,
        median_delta=None,
        ci_lower=None,
        ci_upper=None,
        floor_passed=True,
    )


class TestComputeCohortFloorFailures:
    def test_passing_cohort_yields_no_failures(self) -> None:
        assert compute_cohort_floor_failures(_cohort(), TrustFloor()) == []

    def test_below_min_selected_emits_blocks_all(self) -> None:
        cohort = _cohort(selected=4)
        failures = compute_cohort_floor_failures(cohort, TrustFloor())
        rules = {f.rule for f in failures}
        assert "min_selected_per_required_cohort" in rules
        sel = next(f for f in failures if f.rule == "min_selected_per_required_cohort")
        assert sel.observed == 4
        assert sel.threshold == 5
        assert sel.severity == "blocks_all"

    def test_below_min_replayed_emits_blocks_all(self) -> None:
        cohort = _cohort(replayed=2)
        failures = compute_cohort_floor_failures(cohort, TrustFloor())
        rep = next(f for f in failures if f.rule == "min_replayed_per_required_cohort")
        assert rep.observed == 2
        assert rep.severity == "blocks_all"

    def test_below_min_scored_emits_blocks_all(self) -> None:
        cohort = _cohort(scored=1)
        failures = compute_cohort_floor_failures(cohort, TrustFloor())
        scd = next(f for f in failures if f.rule == "min_scored_per_required_cohort")
        assert scd.observed == 1
        assert scd.severity == "blocks_all"

    def test_below_validity_ratio_emits_blocks_ship(self) -> None:
        # 10 selected, 2 replayed → ratio 0.20 < default 0.50.
        cohort = _cohort(selected=10, replayed=2, scored=2)
        failures = compute_cohort_floor_failures(cohort, TrustFloor())
        ratio = next(
            f for f in failures if f.rule == "min_replay_validity_ratio_per_required_cohort"
        )
        assert ratio.observed == "0.200"
        assert ratio.threshold == 0.50
        assert ratio.severity == "blocks_ship"

    def test_validity_ratio_at_threshold_passes(self) -> None:
        # 10 selected, 5 replayed → ratio 0.50 == threshold 0.50.
        cohort = _cohort(selected=10, replayed=5, scored=5)
        failures = compute_cohort_floor_failures(cohort, TrustFloor())
        ratio_failures = [
            f for f in failures if f.rule == "min_replay_validity_ratio_per_required_cohort"
        ]
        assert ratio_failures == []

    def test_zero_selected_skips_ratio_rule(self) -> None:
        # selected=0 → min_selected fails (blocks_all); ratio rule must not
        # divide by zero or emit a redundant blocks_ship failure.
        cohort = _cohort(selected=0, replayed=0, scored=0)
        failures = compute_cohort_floor_failures(cohort, TrustFloor())
        rules = [f.rule for f in failures]
        assert "min_replay_validity_ratio_per_required_cohort" not in rules
        # The three count rules all fail.
        assert "min_selected_per_required_cohort" in rules
        assert "min_replayed_per_required_cohort" in rules
        assert "min_scored_per_required_cohort" in rules

    def test_at_threshold_count_passes(self) -> None:
        # Exactly at threshold (5) is a pass, not a failure.
        cohort = _cohort(selected=5, replayed=5, scored=5)
        assert compute_cohort_floor_failures(cohort, TrustFloor()) == []

    def test_custom_floor_thresholds_apply(self) -> None:
        floor = TrustFloor(min_scored_per_required_cohort=20)
        cohort = _cohort(scored=10)  # passes default 5, fails custom 20
        failures = compute_cohort_floor_failures(cohort, floor)
        scd = next(f for f in failures if f.rule == "min_scored_per_required_cohort")
        assert scd.observed == 10
        assert scd.threshold == 20


class TestEvaluateFloorAggregation:
    def test_all_required_passing_yields_proof(self) -> None:
        result = evaluate_floor(
            [_cohort(name="failure"), _cohort(name="baseline")],
            TrustFloor(),
            ("failure", "baseline"),
            now=_FIXED_NOW,
        )
        assert isinstance(result, FloorPassedProof)

    def test_one_failing_cohort_blocks_run(self) -> None:
        result = evaluate_floor(
            [_cohort(name="failure"), _cohort(name="baseline", scored=1)],
            TrustFloor(),
            ("failure", "baseline"),
            now=_FIXED_NOW,
        )
        assert isinstance(result, FloorFailureSet)
        rules = [f.rule for f in result]
        assert rules == ["min_scored_per_required_cohort"]

    def test_failures_aggregated_across_cohorts(self) -> None:
        result = evaluate_floor(
            [
                _cohort(name="failure", selected=2),  # min_selected fails
                _cohort(name="baseline", scored=1),  # min_scored fails
            ],
            TrustFloor(),
            ("failure", "baseline"),
            now=_FIXED_NOW,
        )
        assert isinstance(result, FloorFailureSet)
        rules = [f.rule for f in result]
        assert "min_selected_per_required_cohort" in rules
        assert "min_scored_per_required_cohort" in rules

    def test_missing_required_cohort_emits_present_failure(self) -> None:
        # Only "failure" cohort provided; baseline is required but absent.
        result = evaluate_floor(
            [_cohort(name="failure")],
            TrustFloor(),
            ("failure", "baseline"),
            now=_FIXED_NOW,
        )
        assert isinstance(result, FloorFailureSet)
        assert len(result) == 1
        only = next(iter(result))
        assert only.rule == "required_cohort_present"
        assert only.observed == "absent"
        assert only.severity == "blocks_all"

    def test_extra_non_required_cohorts_ignored(self) -> None:
        # A cohort outside `required_cohorts` should not affect the verdict.
        result = evaluate_floor(
            [
                _cohort(name="failure"),
                _cohort(name="baseline"),
                _cohort(name="exploratory", scored=0),  # would fail if required
            ],
            TrustFloor(),
            ("failure", "baseline"),
            now=_FIXED_NOW,
        )
        assert isinstance(result, FloorPassedProof)

    def test_empty_required_cohorts_is_structural_failure(self) -> None:
        # Cardinal #2: a misconfigured policy with no required cohorts must
        # not produce a vacuous proof. The floor refuses with a structured
        # `required_cohorts_nonempty` failure (cardinal #1: structured
        # data, not an exception).
        result = evaluate_floor([], TrustFloor(), (), now=_FIXED_NOW)
        assert isinstance(result, FloorFailureSet)
        assert len(result) == 1
        only = next(iter(result))
        assert only.rule == "required_cohorts_nonempty"
        assert only.observed == 0
        assert only.threshold == 1
        assert only.severity == "blocks_all"

    def test_empty_required_cohorts_blocks_even_with_results(self) -> None:
        # Even when cohort results are present, empty required_cohorts is
        # a structural failure — a policy that demands no required cohorts
        # is the bypass scenario cardinal #2 prevents.
        result = evaluate_floor(_passing_pair(), TrustFloor(), (), now=_FIXED_NOW)
        assert isinstance(result, FloorFailureSet)
        assert next(iter(result)).rule == "required_cohorts_nonempty"
