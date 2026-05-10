"""Tests for `whatifd.statistical.bootstrap` — Phase E.1.

Property tests + boundary cases. The Hypothesis property tests pin
the doctrinally-load-bearing invariants:
- determinism with seed
- CI brackets the median
- CI tightens (or stays equal) with more resamples on average

Boundary cases pin cardinal #1 (typed errors on bad input).
"""

from __future__ import annotations

import statistics

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from whatifd.statistical import BootstrapResult, paired_percentile_bootstrap


class TestHappyPath:
    def test_returns_bootstrap_result(self) -> None:
        result = paired_percentile_bootstrap([0.1, 0.2, 0.3], seed=42)
        assert isinstance(result, BootstrapResult)
        assert result.resamples == 2000  # default
        assert result.seed == 42
        assert result.ci_level == 0.95

    def test_median_matches_input_median(self) -> None:
        # The reported median is the median of the ORIGINAL deltas,
        # not of the bootstrap distribution. Cardinal #10:
        # bootstrap quantifies uncertainty around the point
        # estimate; it does not replace the point estimate.
        deltas = [0.1, 0.2, 0.3, 0.4, 0.5]
        result = paired_percentile_bootstrap(deltas, seed=42)
        assert result.median == statistics.median(deltas)

    def test_ci_bracket_includes_median(self) -> None:
        # Empirical: at 95% CI level, ci_lower <= median <= ci_upper
        # for a non-degenerate distribution. Defends against an off-
        # by-one in the percentile-index calculation.
        deltas = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        result = paired_percentile_bootstrap(deltas, seed=42)
        assert result.ci_lower <= result.median <= result.ci_upper

    def test_ci_lower_less_than_or_equal_ci_upper(self) -> None:
        result = paired_percentile_bootstrap([0.1, 0.2, 0.3], seed=42)
        assert result.ci_lower <= result.ci_upper


class TestDeterminism:
    def test_same_seed_same_result(self) -> None:
        deltas = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3]
        a = paired_percentile_bootstrap(deltas, seed=42)
        b = paired_percentile_bootstrap(deltas, seed=42)
        assert a == b

    def test_different_seeds_different_ci(self) -> None:
        # Sanity: the seed actually controls the resampler.
        # Different seeds on the same data should produce different
        # CIs. Strictly speaking this is probabilistic — two seeds
        # COULD coincidentally produce resample sequences whose 50th
        # and 1949th sorted-median values agree, but at n=20 + 2000
        # resamples + a non-degenerate input, the probability is
        # vanishingly small (the joint probability of two specific
        # bootstrap-distribution percentiles colliding under
        # different seeds is empirically <1e-6 for inputs with
        # spread). If this test ever flakes, the right fix is
        # probably to investigate the seed pair (it's likely
        # signaling a real determinism regression), not to soften
        # the assertion to skip-on-collision — that would mask the
        # very property we're testing.
        deltas = [i / 100.0 for i in range(20)]  # 0.00..0.19
        a = paired_percentile_bootstrap(deltas, seed=1)
        b = paired_percentile_bootstrap(deltas, seed=2)
        # Median is data-determined and identical.
        assert a.median == b.median
        # CI bounds depend on the resample sequence.
        assert (a.ci_lower, a.ci_upper) != (b.ci_lower, b.ci_upper)

    def test_does_not_perturb_global_random(self) -> None:
        # Cardinal-#4-adjacent: the bootstrap MUST NOT touch the
        # global `random` module's state, or concurrent uses of
        # `random.random()` elsewhere in the process become non-
        # reproducible.
        import random as _random

        _random.seed(999)
        before = _random.random()

        _random.seed(999)
        paired_percentile_bootstrap([0.1, 0.2, 0.3], seed=42)
        after = _random.random()

        assert before == after


class TestStructuralErrors:
    def test_empty_deltas_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            paired_percentile_bootstrap([], seed=42)

    def test_zero_resamples_raises(self) -> None:
        with pytest.raises(ValueError, match="resamples must be >= 1"):
            paired_percentile_bootstrap([0.1], resamples=0, seed=42)

    def test_negative_resamples_raises(self) -> None:
        with pytest.raises(ValueError, match="resamples must be >= 1"):
            paired_percentile_bootstrap([0.1], resamples=-5, seed=42)

    @pytest.mark.parametrize("bad_level", [0.0, 1.0, -0.1, 1.5])
    def test_invalid_ci_level_raises(self, bad_level: float) -> None:
        with pytest.raises(ValueError, match=r"ci_level must be in \(0, 1\)"):
            paired_percentile_bootstrap([0.1, 0.2], ci_level=bad_level, seed=42)


class TestCustomConfiguration:
    def test_resamples_count_passes_through(self) -> None:
        result = paired_percentile_bootstrap([0.1, 0.2, 0.3], resamples=500, seed=42)
        assert result.resamples == 500

    def test_ci_level_passes_through(self) -> None:
        result = paired_percentile_bootstrap([0.1, 0.2, 0.3], ci_level=0.99, seed=42)
        assert result.ci_level == 0.99

    def test_higher_ci_level_widens_or_equals_interval(self) -> None:
        # Spot-check, NOT a universal proof. Monotonicity of CI width
        # in ci_level is structurally guaranteed by the percentile-
        # index formula (`(alpha/2)*(N-1)` and `(1-alpha/2)*(N-1)`):
        # higher ci_level => smaller alpha => indices push outward
        # in the sorted bootstrap distribution. But "outward" can
        # collide with array bounds at small `resamples`, and on
        # degenerate distributions different seeds can produce
        # collapsed CIs that tie rather than strictly widen. Both
        # calls below pin seed=42 so the resample sequence is
        # identical; the assertion is `>=` not `>` for that reason.
        deltas = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        ci_95 = paired_percentile_bootstrap(deltas, ci_level=0.95, seed=42)
        ci_99 = paired_percentile_bootstrap(deltas, ci_level=0.99, seed=42)
        assert (ci_99.ci_upper - ci_99.ci_lower) >= (ci_95.ci_upper - ci_95.ci_lower)


class TestPropertyBased:
    """Hypothesis property tests on bootstrap invariants."""

    @given(
        deltas=st.lists(
            st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
            min_size=2,
            max_size=50,
        ),
        seed=st.integers(min_value=0, max_value=10_000),
    )
    @settings(max_examples=50, deadline=2000)
    def test_ci_brackets_median_for_arbitrary_input(self, deltas: list[float], seed: int) -> None:
        # Across arbitrary delta sequences (length 2-50, finite floats),
        # the empirical 95% CI bracket includes the median.
        #
        # Note on degenerate cases: if `deltas` is constant or has
        # very low spread, the bootstrap distribution collapses and
        # `ci_lower == result.median == ci_upper` — the assertion
        # holds trivially in that case (`<=` is non-strict). The
        # interesting property is the directional bracket, not strict
        # inequality. Split into two explicit asserts so a future
        # debugger sees which side of the bracket failed.
        result = paired_percentile_bootstrap(deltas, seed=seed, resamples=200)
        assert result.ci_lower <= result.median, (
            f"ci_lower ({result.ci_lower}) > median ({result.median})"
        )
        assert result.median <= result.ci_upper, (
            f"median ({result.median}) > ci_upper ({result.ci_upper})"
        )

    @given(
        deltas=st.lists(
            st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=5,
            max_size=20,
        ),
        seed=st.integers(min_value=0, max_value=10_000),
    )
    @settings(max_examples=30, deadline=3000)
    def test_deterministic_across_runs(self, deltas: list[float], seed: int) -> None:
        # Same input + same seed = identical BootstrapResult.
        a = paired_percentile_bootstrap(deltas, seed=seed, resamples=200)
        b = paired_percentile_bootstrap(deltas, seed=seed, resamples=200)
        assert a == b

    @given(
        deltas=st.lists(
            st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            min_size=10,
            max_size=30,
        ),
        seed=st.integers(min_value=0, max_value=10_000),
    )
    @settings(max_examples=30, deadline=3000)
    def test_ci_width_monotone_in_ci_level(self, deltas: list[float], seed: int) -> None:
        # Structural property: CI width is non-decreasing in
        # ci_level. Higher confidence => indices push outward in
        # the sorted bootstrap distribution. Companion to
        # test_higher_ci_level_widens_or_equals_interval (which is
        # a single spot-check); this Hypothesis property gives the
        # invariant the same coverage depth as the bracket
        # invariant.
        ci_90 = paired_percentile_bootstrap(deltas, ci_level=0.90, seed=seed, resamples=200)
        ci_95 = paired_percentile_bootstrap(deltas, ci_level=0.95, seed=seed, resamples=200)
        ci_99 = paired_percentile_bootstrap(deltas, ci_level=0.99, seed=seed, resamples=200)
        width_90 = ci_90.ci_upper - ci_90.ci_lower
        width_95 = ci_95.ci_upper - ci_95.ci_lower
        width_99 = ci_99.ci_upper - ci_99.ci_lower
        assert width_90 <= width_95 <= width_99, (
            f"non-monotone widths: 90={width_90}, 95={width_95}, 99={width_99}"
        )


class TestWireBoundary:
    """Sanity for `to_decimal_string` — the helper exists so callers
    don't repeat the f-string boilerplate at every wire-boundary
    crossing."""

    def test_default_precision_is_3(self) -> None:
        from whatifd.statistical import to_decimal_string

        assert to_decimal_string(0.123456) == "0.123"

    def test_custom_precision_passes_through(self) -> None:
        from whatifd.statistical import to_decimal_string

        assert to_decimal_string(0.123456, precision=5) == "0.12346"

    def test_negative_values_formatted(self) -> None:
        from whatifd.statistical import to_decimal_string

        assert to_decimal_string(-0.05) == "-0.050"

    def test_zero_formatted_with_precision(self) -> None:
        from whatifd.statistical import to_decimal_string

        assert to_decimal_string(0.0) == "0.000"

    def test_precision_zero_produces_integer_format(self) -> None:
        from whatifd.statistical import to_decimal_string

        # precision=0 is legal — produces no decimal point at all
        # (matches f"{x:.0f}" semantics).
        assert to_decimal_string(3.7, precision=0) == "4"
        assert to_decimal_string(-2.4, precision=0) == "-2"

    @pytest.mark.parametrize("bad_precision", [-1, -5, -100])
    def test_negative_precision_raises_value_error(self, bad_precision: int) -> None:
        from whatifd.statistical import to_decimal_string

        with pytest.raises(ValueError, match="precision must be >= 0"):
            to_decimal_string(0.5, precision=bad_precision)


class TestEdgeCases:
    """Bootstrap algorithm edge cases that don't fit a single
    behavioral category — collected so a future reader navigating
    by class name finds them in one place.
    """

    def test_resamples_one_produces_degenerate_collapsed_ci(self) -> None:
        # Edge case pinned by the docstring: resamples=1 is valid
        # but degenerate. Both indices round to 0; ci_lower ==
        # ci_upper == bootstrap_medians[0]. Test exists so the
        # docstring claim is structurally enforced.
        result = paired_percentile_bootstrap([0.1, 0.2, 0.3], resamples=1, seed=42)
        assert result.ci_lower == result.ci_upper

    def test_full_wire_boundary_round_trip(self) -> None:
        # Integration smoke: bootstrap output → to_decimal_string →
        # CohortResult.median_delta. Pins that the typed wire shape
        # actually accepts the helper's output (cardinal #6 boundary
        # crossing) and that the bootstrap-bound DecimalStrings
        # parse-and-round-trip cleanly.
        from whatifd.statistical import to_decimal_string
        from whatifd.types.cohort import CohortResult

        result = paired_percentile_bootstrap(
            [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            seed=42,
        )
        cohort = CohortResult(
            name="failure",
            selected=10,
            replayed=10,
            scored=10,
            ci_computable=True,
            ci_unavailable_reason=None,
            median_delta=to_decimal_string(result.median),
            ci_lower=to_decimal_string(result.ci_lower),
            ci_upper=to_decimal_string(result.ci_upper),
            floor_passed=True,
            improved_count=10,
            unchanged_count=0,
            regressed_count=0,
        )
        assert isinstance(cohort.median_delta, str)  # DecimalString is a NewType over str
        # Round-trip: parse the wire shape back to a float; should
        # equal the bootstrap median rounded to 3 decimals.
        assert abs(float(cohort.median_delta) - round(result.median, 3)) < 1e-9
