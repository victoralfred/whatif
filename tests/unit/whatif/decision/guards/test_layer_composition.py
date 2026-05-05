"""Cardinal #10 layer composition test — Phase 2.5b integration.

Pins the end-to-end behavior of the three cardinal-#10 guards
running together via `run_guards`:

- `failure_improvement_guard` (primary endpoint, load-bearing)
- `baseline_regression_guard` (symmetric non-regression endpoint)
- `practical_delta_guard` (supplementary magnitude layer)

Per cardinal #10, these three guards form the verdict's statistical-
claims layer for v0.1. They MUST compose cleanly: each reads only
its own cohort's data, run_guards concatenates findings in
registration order, and the verdict layer (Phase 2.6) selects
Ship/DontShip/Inconclusive from the resulting findings.

This test does NOT call the verdict layer (that's Phase 2.6); it
asserts the pre-verdict guard composition is correct on realistic
cohort scenarios.
"""

from __future__ import annotations

from whatif.decision.guards import (
    baseline_regression_guard,
    failure_improvement_guard,
    practical_delta_guard,
    run_guards,
)
from whatif.types.policy import DecisionPolicy

from ._helpers import baseline_cohort, failure_cohort

# Standard cardinal-#10 layer ordering: primary endpoints first
# (rate-based), magnitude layer last (supplementary). This is the
# expected order Phase 2.6 verdict computation will register.
_LAYER = (failure_improvement_guard, baseline_regression_guard, practical_delta_guard)


class TestCardinal10LayerComposition:
    def test_clean_ship_scenario_emits_no_blocking_findings(self) -> None:
        # Failure cohort: 8/10 improved, median delta well above epsilon.
        # Baseline cohort: 0/10 regressed.
        # All three layers should pass; result should be empty (Ship-eligible).
        cohorts = [
            failure_cohort(median_delta="0.310", improved=8, unchanged=2, regressed=0),
            baseline_cohort(improved=2, unchanged=8, regressed=0),
        ]
        findings = run_guards(_LAYER, cohorts, DecisionPolicy())
        assert findings == [], f"clean Ship scenario should emit no findings, got {findings}"

    def test_failure_improvement_below_threshold_only(self) -> None:
        # Failure rescue rate too low (3/10 = 0.30 < 0.50 default).
        # Baseline is fine; magnitude is fine.
        # Expect exactly one finding: failure_improvement_below_threshold.
        cohorts = [
            failure_cohort(median_delta="0.250", improved=3, unchanged=4, regressed=3),
            baseline_cohort(improved=2, unchanged=8, regressed=0),
        ]
        findings = run_guards(_LAYER, cohorts, DecisionPolicy())
        assert len(findings) == 1
        assert findings[0].code == "failure_improvement_below_threshold"
        # Cardinal #2: severity drives verdict. Pin it explicitly so a
        # registry-level severity regression can't slip past.
        assert findings[0].severity == "blocks_ship"

    def test_baseline_regression_above_threshold_only(self) -> None:
        # Baseline regression too high (3/10 = 0.30 > 0.10 default).
        # Failure rescue is good; magnitude is fine.
        cohorts = [
            failure_cohort(median_delta="0.310", improved=8, unchanged=2, regressed=0),
            baseline_cohort(improved=4, unchanged=3, regressed=3),
        ]
        findings = run_guards(_LAYER, cohorts, DecisionPolicy())
        assert len(findings) == 1
        assert findings[0].code == "baseline_regression_above_threshold"
        assert findings[0].severity == "blocks_ship"

    def test_magnitude_below_epsilon_only(self) -> None:
        # Failure rescue rate is fine (8/10 > 0.50). Baseline is fine.
        # But median delta 0.020 <= epsilon 0.050 → magnitude floor blocks.
        # Demonstrates the magnitude layer's supplementary role: catches
        # cases where rate-only would ship a noise-floor win.
        cohorts = [
            failure_cohort(median_delta="0.020", improved=8, unchanged=2, regressed=0),
            baseline_cohort(improved=2, unchanged=8, regressed=0),
        ]
        findings = run_guards(_LAYER, cohorts, DecisionPolicy())
        assert len(findings) == 1
        assert findings[0].code == "practical_delta_below_threshold"
        assert findings[0].severity == "blocks_ship"

    def test_all_three_layers_fire_simultaneously(self) -> None:
        # Catastrophe scenario: failure rescue too low AND baseline regressed
        # AND magnitude in noise floor. All three blocking findings should
        # surface so the verdict layer (Phase 2.6) can render the full picture.
        #
        # Order matters: `run_guards` documents registration-order
        # concatenation. `_LAYER` is registered as
        # (failure_improvement, baseline_regression, practical_delta), so
        # findings must come back in that exact order.
        cohorts = [
            failure_cohort(median_delta="0.020", improved=2, unchanged=4, regressed=4),
            baseline_cohort(improved=3, unchanged=4, regressed=3),
        ]
        findings = run_guards(_LAYER, cohorts, DecisionPolicy())
        codes = [f.code for f in findings]
        assert codes == [
            "failure_improvement_below_threshold",
            "baseline_regression_above_threshold",
            "practical_delta_below_threshold",
        ], f"findings should arrive in registration order; got {codes}"
        # Cardinal #2: every finding emitted by these guards is
        # blocks_ship — pinned so a registry-level severity regression
        # in any of the three codes can't slip past unnoticed.
        severities = [f.severity for f in findings]
        assert severities == ["blocks_ship"] * 3, (
            f"all cardinal-#10 layer findings must be blocks_ship; got {severities}"
        )

    def test_layer_independence_under_composition(self) -> None:
        # Pin that running all three guards together produces the same
        # findings as running each individually + concatenating. Catches
        # any future regression where guards accidentally interact via
        # shared mutable state.
        cohorts = [
            failure_cohort(median_delta="0.020", improved=2, unchanged=4, regressed=4),
            baseline_cohort(improved=3, unchanged=4, regressed=3),
        ]
        policy = DecisionPolicy()

        composed = run_guards(_LAYER, cohorts, policy)
        composed_codes = [f.code for f in composed]

        # Individual concatenation in the SAME order as _LAYER registration.
        individual = (
            failure_improvement_guard(cohorts, policy)
            + baseline_regression_guard(cohorts, policy)
            + practical_delta_guard(cohorts, policy)
        )
        individual_codes = [f.code for f in individual]

        # Order-preserving equality (not just sorted equality): pins that
        # `run_guards` matches manual concatenation in registration order.
        assert composed_codes == individual_codes, (
            "composition via run_guards must match running guards individually "
            f"in registration order; got {composed_codes} vs {individual_codes}"
        )

    def test_only_failure_cohort_present_does_not_break_composition(self) -> None:
        # Realistic edge case: only failure cohort populated (e.g., baseline
        # cohort below floor). baseline_regression_guard abstains; the
        # other two evaluate normally.
        cohorts = [
            failure_cohort(median_delta="0.310", improved=8, unchanged=2, regressed=0),
        ]
        findings = run_guards(_LAYER, cohorts, DecisionPolicy())
        # No blocking findings: failure_improvement passes (8/10 > 0.50),
        # practical_delta passes (0.310 > 0.050), baseline_regression
        # silently abstains.
        assert findings == []
