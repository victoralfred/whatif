"""Tests for `whatifd.decision.verdict.compute_verdict` — Phase 2.6a.

Cardinal-#2 verdict integration: floor evaluation + guard chain →
Ship | DontShip | Inconclusive. The trust chain at runtime mirrors
the type-level chain documented on `Ship.proof`.
"""

from __future__ import annotations

from whatifd.decision.verdict import compute_verdict
from whatifd.types.cohort import CohortResult
from whatifd.types.policy import DecisionPolicy, TrustFloor
from whatifd.types.primitives import DecimalString
from whatifd.types.verdict import DontShip, Inconclusive, Ship


def _passing_failure_cohort(
    *,
    median_delta: str = "0.310",
    improved: int = 8,
    unchanged: int = 2,
    regressed: int = 0,
) -> CohortResult:
    """Failure cohort that satisfies floor + clean primary endpoints."""
    scored = improved + unchanged + regressed
    return CohortResult(
        name="failure",
        selected=max(scored, 10),
        replayed=max(scored, 10),
        scored=max(scored, 10),
        ci_computable=True,
        ci_unavailable_reason=None,
        median_delta=DecimalString(median_delta),
        ci_lower=DecimalString("0.180"),
        ci_upper=DecimalString("0.440"),
        floor_passed=True,
        improved_count=improved,
        unchanged_count=unchanged,
        regressed_count=regressed,
    )


def _passing_baseline_cohort(
    *,
    improved: int = 2,
    unchanged: int = 8,
    regressed: int = 0,
    ci_computable: bool = True,
) -> CohortResult:
    scored = improved + unchanged + regressed
    return CohortResult(
        name="baseline",
        selected=max(scored, 10),
        replayed=max(scored, 10),
        scored=max(scored, 10),
        ci_computable=ci_computable,
        ci_unavailable_reason=None if ci_computable else "sample_too_small",
        median_delta=DecimalString("0.000"),
        ci_lower=DecimalString("-0.020") if ci_computable else None,
        ci_upper=DecimalString("0.020") if ci_computable else None,
        floor_passed=True,
        improved_count=improved,
        unchanged_count=unchanged,
        regressed_count=regressed,
    )


# ---------------------------------------------------------------------------
# Ship branch
# ---------------------------------------------------------------------------


class TestComputeVerdictShip:
    def test_clean_run_produces_ship(self) -> None:
        """Floor passes; no blocking findings; verdict is Ship.

        The proof field on the returned Ship is the FloorPassedProof
        from evaluate_floor — the witness that proves cardinal #2 was
        satisfied at runtime.
        """
        verdict = compute_verdict(
            [_passing_failure_cohort(), _passing_baseline_cohort()],
            TrustFloor(),
            DecisionPolicy(),
        )
        assert isinstance(verdict, Ship)
        assert verdict.proof is not None
        # Improvement is observed but it's info-severity, not blocking.
        info_codes = [f.code for f in verdict.findings if f.severity == "info"]
        assert "improvement_observed" in info_codes

    def test_ship_carries_cohort_results(self) -> None:
        cohorts = [_passing_failure_cohort(), _passing_baseline_cohort()]
        verdict = compute_verdict(cohorts, TrustFloor(), DecisionPolicy())
        assert isinstance(verdict, Ship)
        assert len(verdict.cohort_results) == 2


# ---------------------------------------------------------------------------
# DontShip branch
# ---------------------------------------------------------------------------


class TestComputeVerdictDontShip:
    def test_baseline_regression_produces_dont_ship(self) -> None:
        """Baseline regressed beyond threshold → DontShip with the
        baseline_regression_above_threshold finding as blocking."""
        cohorts = [
            _passing_failure_cohort(),
            # 3/10 = 0.30 regression > 0.10 default threshold
            _passing_baseline_cohort(improved=4, unchanged=3, regressed=3),
        ]
        verdict = compute_verdict(cohorts, TrustFloor(), DecisionPolicy())
        assert isinstance(verdict, DontShip)
        codes = [f.code for f in verdict.blocking_findings]
        assert "baseline_regression_above_threshold" in codes
        # All blocking findings must be blocks_ship severity.
        for f in verdict.blocking_findings:
            assert f.severity == "blocks_ship"

    def test_failure_improvement_too_low_produces_dont_ship(self) -> None:
        """Failure cohort improvement below threshold → DontShip."""
        cohorts = [
            # 3/10 = 0.30 improvement < 0.50 default threshold
            _passing_failure_cohort(improved=3, unchanged=4, regressed=3),
            _passing_baseline_cohort(),
        ]
        verdict = compute_verdict(cohorts, TrustFloor(), DecisionPolicy())
        assert isinstance(verdict, DontShip)
        codes = [f.code for f in verdict.blocking_findings]
        assert "failure_improvement_below_threshold" in codes

    def test_practical_delta_below_epsilon_produces_dont_ship(self) -> None:
        """Magnitude in noise floor → DontShip even if rate is fine."""
        cohorts = [
            # Rate is fine (8/10 = 0.80 > 0.50) but median delta 0.020
            # is below epsilon 0.050 → magnitude layer blocks.
            _passing_failure_cohort(median_delta="0.020", improved=8, unchanged=2, regressed=0),
            _passing_baseline_cohort(),
        ]
        verdict = compute_verdict(cohorts, TrustFloor(), DecisionPolicy())
        assert isinstance(verdict, DontShip)
        codes = [f.code for f in verdict.blocking_findings]
        assert "practical_delta_below_threshold" in codes


# ---------------------------------------------------------------------------
# Inconclusive branch (floor failures)
# ---------------------------------------------------------------------------


class TestComputeVerdictFloorFails:
    def test_min_scored_below_floor_produces_inconclusive(self) -> None:
        """Floor failure → Inconclusive regardless of guard findings.
        Cardinal #2: floor precedence is absolute."""
        # Baseline scored=3 < floor min 5 → floor fails on baseline.
        cohorts = [
            _passing_failure_cohort(),
            CohortResult(
                name="baseline",
                selected=10,
                replayed=10,
                scored=3,  # floor fails
                ci_computable=True,
                ci_unavailable_reason=None,
                median_delta=DecimalString("0.000"),
                ci_lower=DecimalString("-0.010"),
                ci_upper=DecimalString("0.010"),
                floor_passed=False,
                improved_count=1,
                unchanged_count=2,
                regressed_count=0,
            ),
        ]
        verdict = compute_verdict(cohorts, TrustFloor(), DecisionPolicy())
        assert isinstance(verdict, Inconclusive)
        assert len(verdict.floor_failures) >= 1
        # The min_scored rule should be among the failures.
        rules = [f.rule for f in verdict.floor_failures]
        assert "min_scored_per_required_cohort" in rules

    def test_floor_failure_overrides_clean_findings(self) -> None:
        """Even if guard findings are clean, floor failure forces Inconclusive."""
        cohorts = [
            CohortResult(
                name="failure",
                selected=10,
                replayed=10,
                scored=2,  # floor fails
                ci_computable=True,
                ci_unavailable_reason=None,
                median_delta=DecimalString("0.310"),
                ci_lower=DecimalString("0.180"),
                ci_upper=DecimalString("0.440"),
                floor_passed=False,
                improved_count=2,
                unchanged_count=0,
                regressed_count=0,
            ),
            _passing_baseline_cohort(),
        ]
        verdict = compute_verdict(cohorts, TrustFloor(), DecisionPolicy())
        assert isinstance(verdict, Inconclusive)
        # Inconclusive carries floor_failures; DontShip never does.
        assert verdict.floor_failures

    def test_floor_failure_overrides_blocking_findings(self) -> None:
        """Cardinal #2 floor precedence: when both the floor fails AND
        guards emit blocking findings, the verdict is Inconclusive
        (driven by floor) rather than DontShip (driven by guard).

        This pins the precedence direction explicitly. The clean-findings
        case is in `test_floor_failure_overrides_clean_findings`; this
        test covers the more interesting case where DontShip would be
        the alternative.
        """
        cohorts = [
            # Below floor on scored AND failure-improvement rate too low.
            # Without floor failure, this would be DontShip.
            CohortResult(
                name="failure",
                selected=10,
                replayed=10,
                scored=2,  # floor fails: scored < min 5
                ci_computable=True,
                ci_unavailable_reason=None,
                median_delta=DecimalString("0.020"),  # also magnitude-floor concern
                ci_lower=DecimalString("-0.010"),
                ci_upper=DecimalString("0.050"),
                floor_passed=False,
                improved_count=0,
                unchanged_count=1,
                regressed_count=1,  # 0/2 improvement rate, would block DontShip
            ),
            _passing_baseline_cohort(improved=2, unchanged=4, regressed=4),
            # ^ baseline regression rate also high, would also block DontShip
        ]
        verdict = compute_verdict(cohorts, TrustFloor(), DecisionPolicy())
        # Floor precedence is absolute. Even with blocks_ship findings
        # present in `verdict.findings`, the verdict is Inconclusive
        # because the floor failed.
        assert isinstance(verdict, Inconclusive)
        assert verdict.floor_failures
        # The blocks_ship findings are still in `findings` for the
        # renderer (cardinal #1: failure-as-data; the floor doesn't
        # silence guard observations) — they're just not the structural
        # reason for the verdict.
        codes = [f.code for f in verdict.findings]
        # At least one blocking finding should be present alongside the floor.
        assert any(
            c in codes
            for c in [
                "failure_improvement_below_threshold",
                "baseline_regression_above_threshold",
                "practical_delta_below_threshold",
            ]
        )


# ---------------------------------------------------------------------------
# Inconclusive branch (blocks_all from guards)
# ---------------------------------------------------------------------------


class TestComputeVerdictBlocksAll:
    def test_ci_unavailable_on_required_cohort_produces_inconclusive(self) -> None:
        """Floor passes but CI is unavailable on a required cohort →
        ci_availability_guard emits blocks_all → Inconclusive (operational
        catastrophe at the policy level)."""
        cohorts = [
            _passing_failure_cohort(),
            _passing_baseline_cohort(ci_computable=False),
        ]
        verdict = compute_verdict(cohorts, TrustFloor(), DecisionPolicy())
        assert isinstance(verdict, Inconclusive)
        # No floor failures (floor passed); blocking_findings is the policy concern.
        assert verdict.floor_failures == []
        codes = [f.code for f in verdict.blocking_findings]
        assert "ci_unavailable_for_required_cohort" in codes

    def test_blocks_all_overrides_blocks_ship(self) -> None:
        """When both blocks_all and blocks_ship findings fire, the
        verdict is Inconclusive (not DontShip). blocks_all takes
        precedence; the run is operationally untrustworthy."""
        cohorts = [
            # CI unavailable on baseline → blocks_all
            # AND failure improvement below threshold → blocks_ship
            _passing_failure_cohort(improved=3, unchanged=4, regressed=3),
            _passing_baseline_cohort(ci_computable=False),
        ]
        verdict = compute_verdict(cohorts, TrustFloor(), DecisionPolicy())
        assert isinstance(verdict, Inconclusive)
        # Both findings should be present in blocking_findings.
        codes = sorted(f.code for f in verdict.blocking_findings)
        assert "ci_unavailable_for_required_cohort" in codes
        assert "failure_improvement_below_threshold" in codes


# ---------------------------------------------------------------------------
# Cardinal-#2 trust-chain pin
# ---------------------------------------------------------------------------


class TestCardinalTwoTrustChain:
    """The witness-token contract pinned at the verdict-computation layer.

    `Ship` requires a `FloorPassedProof`. `compute_verdict` is the only
    function that can produce a `Ship` because:
    - It calls `evaluate_floor` (which produces the proof).
    - It threads the proof into `Ship(proof=...)`.
    - No other branch consumes the proof.
    """

    def test_ship_carries_proof_from_evaluate_floor(self) -> None:
        from datetime import datetime

        verdict = compute_verdict(
            [_passing_failure_cohort(), _passing_baseline_cohort()],
            TrustFloor(),
            DecisionPolicy(),
        )
        assert isinstance(verdict, Ship)
        # Proof's metadata reflects the floor we passed in.
        assert verdict.proof.floor_version == "v1"
        # evaluated_at is a real ISO 8601 timestamp from the floor's
        # clock — round-tripping through fromisoformat() is the strict
        # check (a string containing 'T' isn't enough).
        parsed = datetime.fromisoformat(verdict.proof.evaluated_at)
        assert parsed.tzinfo is not None  # UTC timestamp from evaluate_floor's default clock

    def test_dont_ship_does_not_construct_with_proof(self) -> None:
        """DontShip has no `proof` field — confirmed at the type level
        (`whatifd.types.verdict.DontShip` doesn't accept proof). This
        test pins runtime behavior: when guards block but floor passes,
        the verdict layer constructs DontShip via the no-proof branch.
        """
        cohorts = [
            _passing_failure_cohort(improved=3, unchanged=4, regressed=3),
            _passing_baseline_cohort(),
        ]
        verdict = compute_verdict(cohorts, TrustFloor(), DecisionPolicy())
        assert isinstance(verdict, DontShip)
        assert not hasattr(verdict, "proof")


# ---------------------------------------------------------------------------
# Custom guard chain
# ---------------------------------------------------------------------------


class TestComputeVerdictCustomGuards:
    def test_custom_empty_guards_produces_ship_when_floor_passes(self) -> None:
        """With no guards configured, only the floor decides — clean
        floor pass produces Ship even if defaults would have flagged."""
        # This cohort would normally trigger practical_delta_below_threshold
        # (median 0.020 <= epsilon 0.050) but with no guards configured,
        # no findings emit.
        cohorts = [
            _passing_failure_cohort(median_delta="0.020", improved=8, unchanged=2),
            _passing_baseline_cohort(),
        ]
        verdict = compute_verdict(cohorts, TrustFloor(), DecisionPolicy(), guards=())
        assert isinstance(verdict, Ship)
        assert verdict.findings == []


# ---------------------------------------------------------------------------
# Type-input contract
# ---------------------------------------------------------------------------
#
# `compute_verdict` types its `floor` parameter as `TrustFloor` directly;
# mypy strict catches wrong-type calls at compile time. No runtime
# isinstance check — per the enforcement-strength hierarchy in
# `references/enforcement.md`, type-level prevention is stronger than
# runtime defense. There is intentionally no `test_non_trust_floor_input_raises`.


# ---------------------------------------------------------------------------
# Phase C — regression_check experiment shape
# ---------------------------------------------------------------------------


class TestRegressionCheckShape:
    """Phase C: regression_check shape has only a `baseline` cohort
    (no failure cohort). The verdict layer must:
    1. Skip the failure-cohort guards (practical_delta, improvement_observation).
    2. Override required_cohorts to ('baseline',) — failure cohort
       absent must not trigger a floor-failure for missing cohort.
    3. Still run primary_endpoint + ci_availability guards on the
       baseline.
    """

    def test_clean_baseline_only_run_produces_ship(self) -> None:
        # Pins the GUARD-side: _REGRESSION_CHECK_GUARDS does not emit
        # any blocks_ship finding against a passing baseline. Companion
        # test `test_failure_cohort_not_required_under_regression_check`
        # pins the FLOOR-side override; both halves together confirm
        # "regression_check + clean baseline = Ship."
        verdict = compute_verdict(
            cohort_results=[_passing_baseline_cohort()],
            floor=TrustFloor(),
            policy=DecisionPolicy(),
            experiment_shape="regression_check",
        )
        assert isinstance(verdict, Ship)
        # Findings list is empty: improvement_observation_guard is
        # excluded from _REGRESSION_CHECK_GUARDS so no info-finding
        # appears here either.
        assert verdict.findings == []

    def test_baseline_regression_produces_dont_ship(self) -> None:
        # 30% baseline regression > policy.max_baseline_regression_ratio
        # (default 0.10) → primary_endpoint guard emits blocks_ship.
        regressing_baseline = _passing_baseline_cohort(improved=2, unchanged=5, regressed=3)
        verdict = compute_verdict(
            cohort_results=[regressing_baseline],
            floor=TrustFloor(),
            policy=DecisionPolicy(),
            experiment_shape="regression_check",
        )
        assert isinstance(verdict, DontShip)

    def test_missing_baseline_produces_inconclusive(self) -> None:
        # No baseline cohort → floor failure, regardless of shape.
        verdict = compute_verdict(
            cohort_results=[],
            floor=TrustFloor(),
            policy=DecisionPolicy(),
            experiment_shape="regression_check",
        )
        assert isinstance(verdict, Inconclusive)

    def test_failure_cohort_not_required_under_regression_check(self) -> None:
        # Pins the FLOOR-side override: policy.required_cohorts
        # defaults to ("failure", "baseline"), but
        # _required_cohorts_for_shape("regression_check", policy)
        # returns ("baseline",). Without that override, this run
        # would be Inconclusive(floor_failures=[required_cohort_missing
        # for "failure"]). Companion test
        # `test_clean_baseline_only_run_produces_ship` pins the
        # GUARD-side (no spurious findings).
        verdict = compute_verdict(
            cohort_results=[_passing_baseline_cohort()],
            floor=TrustFloor(),
            policy=DecisionPolicy(),  # .required_cohorts == ("failure", "baseline")
            experiment_shape="regression_check",
        )
        assert isinstance(verdict, Ship)

    def test_failure_rescue_still_requires_failure_cohort(self) -> None:
        # Sanity: the v0.1 default shape is unchanged. Baseline-only
        # under failure_rescue is still a floor failure.
        verdict = compute_verdict(
            cohort_results=[_passing_baseline_cohort()],
            floor=TrustFloor(),
            policy=DecisionPolicy(),
            experiment_shape="failure_rescue",
        )
        assert isinstance(verdict, Inconclusive)

    def test_default_shape_is_failure_rescue(self) -> None:
        # Back-compat: callers that don't pass experiment_shape get
        # the v0.1 default behavior.
        verdict = compute_verdict(
            cohort_results=[_passing_baseline_cohort()],
            floor=TrustFloor(),
            policy=DecisionPolicy(),
        )
        assert isinstance(verdict, Inconclusive)
