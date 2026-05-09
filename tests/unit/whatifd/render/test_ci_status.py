"""Tests for `whatifd.render.ci_status.render_ci_status` — Phase 7.3.

Pin properties:

1. Each verdict gets the right glyph + label prefix.
2. Length budget: every produced string ≤ 80 visible chars.
3. Truncation uses `…` and preserves the verdict prefix intact.
4. Ship reason carries the failure / baseline cohort summary.
5. Don't Ship / Inconclusive reason comes from the highest-
   severity decision finding.
6. Inconclusive with no findings but a floor failure surfaces the
   floor rule.
"""

from __future__ import annotations

import dataclasses

import pytest

from whatifd.decision.finding_codes import make_decision_finding
from whatifd.render import render_ci_status
from whatifd.report.projection import project_to_report_v01
from whatifd.types.cohort import FloorFailure

from ..report._fixtures import (
    cache_summary,
    cohort,
    dont_ship,
    inconclusive,
    methodology,
    runtime,
    ship,
)


def _report_for(verdict, *, failures=None, decision_findings=None):
    """Project to a ReportV01 with optional finding override.

    The fixtures' verdict factories carry their own findings; for
    the CI-status tests we sometimes want to inject a specific
    finding to pin the reason path. project_to_report_v01 reads
    the verdict's findings field directly, so override the verdict
    via dataclasses.replace where needed.
    """
    return project_to_report_v01(
        verdict,
        failures=failures or [],
        cache_summary=cache_summary(),
        methodology=methodology(),
        runtime=runtime(),
    )


# ---------------------------------------------------------------------------
# Verdict glyph + label
# ---------------------------------------------------------------------------


class TestVerdictPrefix:
    def test_ship_glyph_and_label(self) -> None:
        line = render_ci_status(_report_for(ship()))
        assert line.startswith("✓ whatifd: Ship —")

    def test_dont_ship_glyph_and_label(self) -> None:
        line = render_ci_status(_report_for(dont_ship()))
        assert line.startswith("✗ whatifd: Don't Ship —")

    def test_inconclusive_glyph_and_label(self) -> None:
        line = render_ci_status(_report_for(inconclusive()))
        assert line.startswith("⚠ whatifd: Inconclusive —")


# ---------------------------------------------------------------------------
# Length budget (≤ 80 chars)
# ---------------------------------------------------------------------------


class TestLengthBudget:
    def test_ship_within_budget(self) -> None:
        line = render_ci_status(_report_for(ship()))
        assert len(line) <= 80, f"Ship line {len(line)} chars: {line!r}"

    def test_dont_ship_within_budget(self) -> None:
        line = render_ci_status(_report_for(dont_ship()))
        assert len(line) <= 80, f"Don't Ship line {len(line)} chars: {line!r}"

    def test_inconclusive_within_budget(self) -> None:
        line = render_ci_status(_report_for(inconclusive()))
        assert len(line) <= 80, f"Inconclusive line {len(line)} chars: {line!r}"

    def test_long_finding_message_truncated_with_ellipsis(self) -> None:
        # A finding with a giant message must produce a within-
        # budget line. Verdict prefix stays intact; reason is
        # truncated with `…`. Severity comes from the registry
        # (cohort_systemic_failure → blocks_all).
        long_message = "x" * 200
        long_finding = make_decision_finding(
            code="cohort_systemic_failure",
            message=long_message,
            details={"cohort": "failure", "percent": 60, "code": "runner_timeout"},
            derived_from_failures=["failure_001"],
        )
        verdict = dataclasses.replace(dont_ship(), findings=(long_finding,))
        line = render_ci_status(_report_for(verdict))

        assert len(line) <= 80
        assert line.startswith("✗ whatifd: Don't Ship — ")
        assert line.endswith("…")


# ---------------------------------------------------------------------------
# Reason source
# ---------------------------------------------------------------------------


class TestReasonSource:
    def test_ship_reason_summarizes_cohorts(self) -> None:
        line = render_ci_status(_report_for(ship()))
        # The ship() fixture's cohorts produce a "failures X/Y ↑,
        # baseline Z/Y stable" tail. Pin the structural shape, not
        # exact numbers (which are fixture-dependent).
        assert " ↑, baseline " in line
        assert "stable" in line

    def test_dont_ship_reason_uses_highest_severity_finding(self) -> None:
        # Two findings: one info (lowest) and one blocks_ship
        # (higher). Renderer must pick the blocks_ship message.
        # Severity is registry-driven; we pick codes for their
        # registered severity, not pass severity directly.
        f_low = make_decision_finding(
            code="improvement_observed",  # severity=info
            message="LOW-SEVERITY MESSAGE",
            details={"median_delta": "0.250", "threshold": "0.05"},
        )
        f_high = make_decision_finding(
            code="baseline_regression_above_threshold",  # severity=blocks_ship
            message="HIGH",
            details={"observed": "0.150", "threshold": "0.10"},
        )
        verdict = dataclasses.replace(dont_ship(), findings=(f_low, f_high))
        line = render_ci_status(_report_for(verdict))
        assert "HIGH" in line
        assert "LOW-SEVERITY MESSAGE" not in line


# ---------------------------------------------------------------------------
# Floor-failure fallback
# ---------------------------------------------------------------------------


class TestFloorFailureFallback:
    def test_inconclusive_with_floor_failure_surfaces_rule(self) -> None:
        # An Inconclusive whose findings list is empty must surface
        # the top floor-failure rule. Build a cohort with a floor
        # failure and inject it into an inconclusive verdict that
        # has no findings.
        floor_failure = FloorFailure(
            rule="min_scored_per_required_cohort",
            observed=3,
            threshold=5,
            severity="blocks_all",
        )
        c = dataclasses.replace(
            cohort("baseline"),
            floor_passed=False,
            floor_failures=[floor_failure],
        )
        verdict = dataclasses.replace(
            inconclusive(),
            cohort_results=(c,),
            findings=(),
        )
        line = render_ci_status(_report_for(verdict))
        # The floor-failure path produces a "<cohort> cohort below
        # floor (...)" reason. The exact rule name may be truncated
        # by the 80-char budget; assert the structural prefix +
        # observed/threshold numbers (which are short and survive).
        assert "baseline cohort below floor" in line
        assert "(3 < 5" in line


# ---------------------------------------------------------------------------
# Defensive boundary
# ---------------------------------------------------------------------------


class TestShipFallback:
    def test_ship_with_non_standard_cohort_names_lists_each(self) -> None:
        # Pin the generic per-cohort fallback: when cohort_results
        # is non-empty but contains neither 'failure' nor
        # 'baseline' (e.g., a future v0.2 regression_check shape
        # using 'control'/'treatment'), the renderer falls back to
        # listing each cohort's improved/scored separately. Format:
        # `<name> <improved>/<scored> ↑, <name> <improved>/<scored> ↑`.
        c_a = dataclasses.replace(cohort("control"), improved_count=7, scored=10)
        c_b = dataclasses.replace(cohort("treatment"), improved_count=8, scored=10)
        verdict = dataclasses.replace(ship(), cohort_results=(c_a, c_b))
        line = render_ci_status(_report_for(verdict))

        assert line.startswith("✓ whatifd: Ship — ")
        # Each cohort named, with improved/scored summary.
        assert "control 7/10 ↑" in line
        assert "treatment 8/10 ↑" in line
        # The standard failure/baseline phrasing must NOT appear.
        assert "stable" not in line

    def test_ship_with_empty_cohort_results_uses_no_cohorts_string(self) -> None:
        # The Ship-reason builder has a "no cohorts" fallback for
        # the case where neither `failure` nor `baseline` cohorts
        # are present. The witness-token path normally guarantees
        # non-empty cohort_results, but the renderer is a leaf
        # function — test the fallback directly via a constructed
        # report so a future refactor that drops the branch
        # surfaces here.
        report = _report_for(ship())
        report = dataclasses.replace(report, cohort_results=[])
        line = render_ci_status(report)
        assert line == "✓ whatifd: Ship — no cohorts"


class TestGlyphCodePointStability:
    def test_glyph_label_keys_match_verdict_states(self) -> None:
        # Pin the closed set of verdict states the renderer
        # accepts. A future verdict (e.g., Phase v0.2 "ConditionallyShip")
        # would need new entries in BOTH _GLYPH and _LABEL — this
        # test fails until both are updated, surfacing the
        # extension point explicitly.
        from whatifd.render.ci_status import _GLYPH, _LABEL

        expected_states = {"ship", "dont_ship", "inconclusive"}
        assert set(_GLYPH.keys()) == expected_states
        assert set(_LABEL.keys()) == expected_states

    def test_glyphs_are_single_code_point(self) -> None:
        # Pin the docstring's claim that visible width == len(string).
        # Each glyph is one code point; the rest of the format is
        # ASCII. A future contributor adding a multi-codepoint
        # glyph (e.g., a flag emoji built from two regional
        # indicators) would silently break the 80-char width
        # assumption — this test catches that.
        from whatifd.render.ci_status import _GLYPH

        for state, glyph in _GLYPH.items():
            assert len(glyph) == 1, (
                f"glyph for {state!r} is {len(glyph)} code points: {glyph!r}. "
                "ci_status.py docstring claims visible width == len(string); "
                "multi-codepoint glyphs break that assumption."
            )


class TestDefensiveFallback:
    def test_inconclusive_with_no_findings_and_no_floor_failures(self) -> None:
        # Pin the defensive contract-violation string. The decision
        # pipeline guarantees a non-Ship verdict has at least one
        # finding or floor failure (cardinal #2 + #8), but the
        # renderer is a leaf — engineering a verdict that violates
        # this upstream contract surfaces the violation as a
        # recognizable string rather than raising. A future
        # refactor that changes the string would fail this test,
        # forcing explicit review.
        c = dataclasses.replace(
            cohort("baseline"),
            floor_passed=True,  # no floor failures
            floor_failures=[],
        )
        verdict = dataclasses.replace(
            inconclusive(),
            cohort_results=(c,),
            findings=(),
        )
        line = render_ci_status(_report_for(verdict))
        assert line == (
            "⚠ whatifd: Inconclusive — (no finding available — contract violation upstream)"
        )


class TestSeverityRankCoverage:
    def test_severity_rank_covers_all_severity_literal_arms(self) -> None:
        # Pin that the rank table covers every value in the
        # `Severity` Literal. A future contributor adding a
        # severity to the type without updating the rank would
        # fail this test, surfacing the omission BEFORE render-
        # time KeyError appears in production.
        from typing import get_args

        from whatifd.render._constants import SEVERITY_RANK
        from whatifd.types.finding import Severity

        literal_arms = set(get_args(Severity))
        assert literal_arms == set(SEVERITY_RANK.keys()), (
            f"SEVERITY_RANK keys {set(SEVERITY_RANK.keys())} do not match "
            f"Severity Literal arms {literal_arms}. A new severity was "
            "added without updating whatifd/render/_constants.py."
        )


class TestSeverityStrictness:
    def test_unknown_severity_raises_keyerror(self) -> None:
        # `Severity` is a closed Literal; a value outside it
        # arriving at the renderer is schema drift (e.g., a Phase
        # v0.2 addition that didn't update _SEVERITY_RANK).
        # Surface the drift loudly rather than silently demoting
        # to below info — which would produce a wrong CI status if
        # the new severity is meant to be the highest.
        from whatifd.types.finding import DecisionFinding

        bogus = DecisionFinding(
            code="bogus",
            severity="bogus_severity",  # type: ignore[arg-type]
            message="x",
        )
        verdict = dataclasses.replace(dont_ship(), findings=(bogus,))
        with pytest.raises(KeyError):
            render_ci_status(_report_for(verdict))


class TestDefensiveBoundary:
    def test_unknown_verdict_state_raises_keyerror(self) -> None:
        # A `verdict_state` outside the closed Literal would have
        # been rejected at projection time, but pin the renderer's
        # behavior under direct mutation to ensure we don't
        # silently emit a bogus glyph. The KeyError surfaces the
        # contract violation rather than producing a garbage line.
        report = _report_for(ship())
        report = dataclasses.replace(report, verdict_state="bogus")  # type: ignore[arg-type]
        with pytest.raises(KeyError):
            render_ci_status(report)
