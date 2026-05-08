"""Tests for `whatifd.render.summary.render_summary` — Phase 7.2.

Pin properties:

1. Verdict header per state.
2. Reason block: clean Ship gets all-passed line; non-Ship uses
   highest-severity finding's message; floor-failure fallback
   when no findings.
3. Cohort stats lines for failure / baseline; generic per-cohort
   lines for non-standard names.
4. Replay validity line summarizing replay + cache.
5. Jump-link bar with `#fix` for non-Ship; omits it for clean Ship
   (compact-Ship degenerate case).
6. Output ≤30 lines (budget enforced; raises if exceeded).
"""

from __future__ import annotations

import dataclasses

from whatifd.decision.finding_codes import make_decision_finding
from whatifd.render import render_summary
from whatifd.report.projection import project_to_report_v01

from ..report._fixtures import (
    cache_summary,
    cohort,
    dont_ship,
    inconclusive,
    methodology,
    runtime,
    ship,
)


def _report_for(verdict, *, failures=None):
    return project_to_report_v01(
        verdict,
        failures=failures or [],
        cache_summary=cache_summary(),
        methodology=methodology(),
        runtime=runtime(),
    )


def _line_count(rendered: str) -> int:
    return rendered.count("\n")


# ---------------------------------------------------------------------------
# Verdict header + line budget
# ---------------------------------------------------------------------------


class TestVerdictHeader:
    def test_ship_header(self) -> None:
        out = render_summary(_report_for(ship()))
        assert out.startswith("# whatif verdict: Ship\n")

    def test_dont_ship_header(self) -> None:
        out = render_summary(_report_for(dont_ship()))
        assert out.startswith("# whatif verdict: Don't Ship\n")

    def test_inconclusive_header(self) -> None:
        out = render_summary(_report_for(inconclusive()))
        assert out.startswith("# whatif verdict: Inconclusive\n")


class TestLineBudget:
    def test_ship_within_budget(self) -> None:
        out = render_summary(_report_for(ship()))
        assert _line_count(out) <= 30

    def test_dont_ship_within_budget(self) -> None:
        out = render_summary(_report_for(dont_ship()))
        assert _line_count(out) <= 30

    def test_inconclusive_within_budget(self) -> None:
        out = render_summary(_report_for(inconclusive()))
        assert _line_count(out) <= 30


# ---------------------------------------------------------------------------
# Compact-Ship degenerate case
# ---------------------------------------------------------------------------


class TestCompactShip:
    def test_clean_ship_omits_fix_link(self) -> None:
        # The "Suggested next steps" jump link is only meaningful
        # for verdicts with actionable findings. Clean Ship omits
        # it; the trailing bar holds only Replay details + Manifest.
        out = render_summary(_report_for(ship()))
        assert "[Suggested next steps ↓](#fix)" not in out
        assert "[Replay details ↓](#replay-validity)" in out
        assert "[Manifest →](manifest.json)" in out

    def test_clean_ship_reason_is_all_passed(self) -> None:
        out = render_summary(_report_for(ship()))
        assert "All floor rules passed. All policy rules passed." in out

    def test_clean_ship_is_compact(self) -> None:
        # Pin the compact-Ship form is short — well under the 30-
        # line budget. Catches a regression that adds verbose
        # sections to the clean path.
        out = render_summary(_report_for(ship()))
        assert _line_count(out) <= 12, (
            f"clean Ship rendered {_line_count(out)} lines; expected ≤12 "
            "for the compact-Ship degenerate case"
        )


# ---------------------------------------------------------------------------
# Non-Ship: jump links + finding reason
# ---------------------------------------------------------------------------


class TestNonShip:
    def test_dont_ship_includes_fix_link(self) -> None:
        out = render_summary(_report_for(dont_ship()))
        assert "[Suggested next steps ↓](#fix)" in out

    def test_inconclusive_includes_fix_link(self) -> None:
        out = render_summary(_report_for(inconclusive()))
        assert "[Suggested next steps ↓](#fix)" in out

    def test_dont_ship_reason_uses_highest_severity_finding(self) -> None:
        f_low = make_decision_finding(
            code="improvement_observed",
            message="LOW",
            details={"median_delta": "0.250", "threshold": "0.05"},
        )
        f_high = make_decision_finding(
            code="baseline_regression_above_threshold",
            message="THE-HIGH-MESSAGE",
            details={"observed": "0.150", "threshold": "0.10"},
        )
        verdict = dataclasses.replace(dont_ship(), findings=(f_low, f_high))
        out = render_summary(_report_for(verdict))
        assert "**THE-HIGH-MESSAGE**" in out
        assert "LOW" not in out


# ---------------------------------------------------------------------------
# Stats block
# ---------------------------------------------------------------------------


class TestStats:
    def test_failure_and_baseline_lines(self) -> None:
        # The ship() fixture produces both cohorts with known
        # numbers. Pin the structural shape, not the exact numbers.
        out = render_summary(_report_for(ship()))
        assert "**Failures (" in out
        assert "**Baseline (" in out
        assert "improved " in out
        assert "regressed " in out
        assert "median Δ " in out

    def test_extra_cohort_appears_after_known_ones(self) -> None:
        # Non-standard cohort names land via the generic per-
        # cohort path; appear with their literal name.
        extra = dataclasses.replace(cohort("control"), scored=10)
        verdict = dataclasses.replace(
            ship(),
            cohort_results=(*ship().cohort_results, extra),
        )
        out = render_summary(_report_for(verdict))
        assert "**control (10):**" in out


# ---------------------------------------------------------------------------
# Replay validity line
# ---------------------------------------------------------------------------


class TestReplayValidity:
    def test_validity_line_present(self) -> None:
        out = render_summary(_report_for(ship()))
        assert "Replay validity:" in out
        assert "Cache:" in out
        assert "hits" in out
        assert "misses" in out
