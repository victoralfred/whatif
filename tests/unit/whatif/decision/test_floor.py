"""Tests for `whatif.decision.floor` — Phase 1.4 witness-token pattern.

Cardinal rule #2: trust floor cannot be bypassed. The witness-token
pattern enforces this at the type level — Ship requires a
FloorPassedProof; only `evaluate_floor()` can produce one (closure-
captured token).

These tests cover:
- Positive: `evaluate_floor()` produces a valid proof.
- Adversarial (basic): direct construction with a fabricated token raises.
- Adversarial (advanced): __closure__ introspection IS a real bypass;
  this is documented as a known v0.1 limit and resolved in v1.0 by
  cohort-hash binding (CASCADE-205, deferred).
- Immutability: proofs cannot be mutated after construction.
- Equality: proofs with the same metadata are structurally equal.
- FloorFailureSet: alternative branch type for the union return.
"""

from __future__ import annotations

import pytest

from whatif.decision.floor import (
    FloorFailureSet,
    FloorPassedProof,
    evaluate_floor,
)
from whatif.types import FloorFailure


class TestEvaluateFloorProducesValidProof:
    def test_returns_floor_passed_proof(self) -> None:
        result = evaluate_floor()
        assert isinstance(result, FloorPassedProof)

    def test_proof_carries_floor_version(self) -> None:
        proof = evaluate_floor()
        assert isinstance(proof, FloorPassedProof)
        assert proof.floor_version == "v1"

    def test_proof_carries_evaluated_at_marker(self) -> None:
        # Phase 1.4 stub uses a placeholder string; Phase 2.1 replaces
        # with an ISO timestamp. The shape, not the content, matters here.
        proof = evaluate_floor()
        assert isinstance(proof, FloorPassedProof)
        assert isinstance(proof.evaluated_at, str)
        assert proof.evaluated_at  # non-empty


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
        proof = evaluate_floor()
        assert isinstance(proof, FloorPassedProof)
        with pytest.raises(AttributeError, match="immutable"):
            proof.floor_version = "v2"

    def test_cannot_set_evaluated_at(self) -> None:
        proof = evaluate_floor()
        assert isinstance(proof, FloorPassedProof)
        with pytest.raises(AttributeError, match="immutable"):
            proof.evaluated_at = "forged"

    def test_cannot_add_arbitrary_attribute(self) -> None:
        proof = evaluate_floor()
        with pytest.raises(AttributeError, match="immutable"):
            proof.smuggled = "extra"  # type: ignore[attr-defined]


class TestProofEquality:
    def test_two_proofs_same_metadata_are_equal(self) -> None:
        p1 = evaluate_floor()
        p2 = evaluate_floor()
        # Phase 1.4 stub returns the same metadata each time, so the proofs
        # are structurally equal even though they're different instances.
        assert p1 == p2

    def test_proof_compares_unequal_to_non_proof(self) -> None:
        proof = evaluate_floor()
        assert proof != "FloorPassedProof"
        assert proof != ("v1", "stub")

    def test_proof_is_hashable(self) -> None:
        proof = evaluate_floor()
        # Used in sets / as dict keys for Ship-construction tracking.
        # Two proofs with the same metadata produce the same hash.
        assert hash(proof) == hash(evaluate_floor())


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
