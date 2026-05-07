"""Tests for `whatif.render.markdown.render_full_report` — Phase 7.1a.

Pin properties:

1. Verdict header per state.
2. Anchors `<a id="fix">` and `<a id="replay-validity">` are
   present and resolve the summary's forward-reference links.
3. Methodology block surfaces every required field (cardinal #10);
   the five reliability concepts each appear by name even when
   marked false.
4. Floor evaluation table rendered IFF a floor failure is present;
   clean Ship omits it.
5. Suggested next steps section surfaces blocking findings (7.1a
   placeholder; 7.1b will wire registry templates).
6. Stats section carries median Δ + CI per cohort.
7. Trailing newline; no Markdown lint failures.
"""

from __future__ import annotations

import dataclasses

from whatif.decision.finding_codes import make_decision_finding
from whatif.render import render_full_report
from whatif.report.projection import project_to_report_v01
from whatif.types.cohort import FloorFailure

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


# ---------------------------------------------------------------------------
# Verdict header + structure
# ---------------------------------------------------------------------------


class TestVerdictHeader:
    def test_ship_header(self) -> None:
        out = render_full_report(_report_for(ship()))
        assert out.startswith("# whatif verdict: Ship\n")

    def test_dont_ship_header(self) -> None:
        out = render_full_report(_report_for(dont_ship()))
        assert out.startswith("# whatif verdict: Don't Ship\n")

    def test_inconclusive_header(self) -> None:
        out = render_full_report(_report_for(inconclusive()))
        assert out.startswith("# whatif verdict: Inconclusive\n")

    def test_trailing_newline(self) -> None:
        out = render_full_report(_report_for(ship()))
        assert out.endswith("\n")
        assert not out.endswith("\n\n")  # exactly one


# ---------------------------------------------------------------------------
# Anchors that the summary's forward-reference links resolve to
# ---------------------------------------------------------------------------


class TestAnchors:
    def test_replay_validity_anchor_present_for_all_verdicts(self) -> None:
        for verdict in (ship(), dont_ship(), inconclusive()):
            out = render_full_report(_report_for(verdict))
            assert '<a id="replay-validity"></a>' in out, (
                f"replay-validity anchor missing for {verdict.__class__.__name__}"
            )

    def test_fix_anchor_present_for_all_verdicts(self) -> None:
        # The summary's forward-reference link to #fix must resolve
        # for every verdict, including clean Ship (where the
        # section is a "no actionable findings" placeholder). The
        # summary itself omits the #fix link for Ship, but if a
        # consumer splices summary + full-report and a future Ship
        # variant adds an actionable finding, the anchor must still
        # exist as a stable target.
        for verdict in (ship(), dont_ship(), inconclusive()):
            out = render_full_report(_report_for(verdict))
            assert '<a id="fix"></a>' in out


# ---------------------------------------------------------------------------
# Methodology disclosure (cardinal #10)
# ---------------------------------------------------------------------------


class TestMethodology:
    def test_section_header_present(self) -> None:
        out = render_full_report(_report_for(ship()))
        assert "## Methodology" in out

    def test_five_reliability_concepts_named(self) -> None:
        # Cardinal #10: silence is the failure mode. Each of the
        # five reliability concepts MUST appear by name even when
        # marked false.
        out = render_full_report(_report_for(ship()))
        for concept in (
            "reproducibility",
            "reliability",
            "validity",
            "calibration",
            "bias",
        ):
            assert concept in out, (
                f"reliability concept {concept!r} missing from "
                "Methodology block — cardinal #10 disclosure violation"
            )

    def test_unit_of_analysis_disclosed(self) -> None:
        out = render_full_report(_report_for(ship()))
        assert "paired_trace_delta" in out

    def test_causal_scope_disclosed(self) -> None:
        out = render_full_report(_report_for(ship()))
        assert "associated_under_cached_tool_replay" in out

    def test_per_trace_inference_disclosed(self) -> None:
        out = render_full_report(_report_for(ship()))
        assert "descriptive_only" in out


# ---------------------------------------------------------------------------
# Floor evaluation
# ---------------------------------------------------------------------------


class TestFloorEvaluation:
    def test_clean_ship_omits_floor_table(self) -> None:
        # Clean Ship has no floor failures; the section is omitted.
        out = render_full_report(_report_for(ship()))
        assert "## Floor evaluation" not in out

    def test_floor_table_rendered_when_failure_present(self) -> None:
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
        verdict = dataclasses.replace(inconclusive(), cohort_results=(c,), findings=())
        out = render_full_report(_report_for(verdict))
        assert "## Floor evaluation" in out
        assert "min_scored_per_required_cohort" in out
        assert "**baseline**" in out
        assert "**3**" in out
        assert "**5**" in out


# ---------------------------------------------------------------------------
# Suggested next steps (7.1a placeholder; 7.1b wires templates)
# ---------------------------------------------------------------------------


class TestSuggestedNextSteps:
    def test_ship_has_no_actionable_findings_paragraph(self) -> None:
        out = render_full_report(_report_for(ship()))
        assert "## Suggested next steps" in out
        assert "No actionable findings" in out

    def test_registered_template_summary_and_steps_rendered(self) -> None:
        # Each blocking finding renders the registered FixSuggestion's
        # summary as an h3 + numbered steps.
        from whatif.decision.fix_suggestions import FIX_SUGGESTION_REGISTRY

        f = make_decision_finding(
            code="baseline_regression_above_threshold",
            message="x",
            details={"observed": "0.150", "threshold": "0.10"},
        )
        verdict = dataclasses.replace(dont_ship(), findings=(f,))
        out = render_full_report(_report_for(verdict))

        template = FIX_SUGGESTION_REGISTRY["baseline_regression_above_threshold"]
        # h3 summary line
        assert f"### {template.summary}" in out
        # First step rendered as numbered list item
        assert f"1. {template.steps[0]}" in out
        # Total steps preserved
        assert f"{len(template.steps)}. {template.steps[-1]}" in out

    def test_placeholder_text_removed_in_7_1b(self) -> None:
        # The 7.1a placeholder must be gone now that 7.1b wires
        # real templates. A future regression that re-introduces
        # the placeholder would fail this test.
        f = make_decision_finding(
            code="baseline_regression_above_threshold",
            message="x",
            details={"observed": "0.150", "threshold": "0.10"},
        )
        verdict = dataclasses.replace(dont_ship(), findings=(f,))
        out = render_full_report(_report_for(verdict))
        assert "Fix-suggestion templates land in Phase 7.1b" not in out

    def test_multiple_blocking_findings_sorted_by_severity(self) -> None:
        # Two blocking findings: blocks_ship + blocks_all. The
        # blocks_all template renders FIRST (highest severity).
        f_ship = make_decision_finding(
            code="baseline_regression_above_threshold",  # blocks_ship
            message="x",
            details={"observed": "0.150", "threshold": "0.10"},
        )
        f_all = make_decision_finding(
            code="cohort_systemic_failure",  # blocks_all
            message="x",
            details={
                "cohort": "failure",
                "percent": 60,
                "code": "runner_timeout",
            },
            derived_from_failures=["failure_001"],
        )
        verdict = dataclasses.replace(dont_ship(), findings=(f_ship, f_all))
        out = render_full_report(_report_for(verdict))

        from whatif.decision.fix_suggestions import FIX_SUGGESTION_REGISTRY

        all_summary = FIX_SUGGESTION_REGISTRY["cohort_systemic_failure"].summary
        ship_summary = FIX_SUGGESTION_REGISTRY["baseline_regression_above_threshold"].summary

        # blocks_all (cohort_systemic_failure) appears BEFORE
        # blocks_ship (baseline_regression_above_threshold) — index
        # in the rendered string proves order.
        idx_all = out.index(all_summary)
        idx_ship = out.index(ship_summary)
        assert idx_all < idx_ship

    def test_unregistered_code_fallback_does_not_crash(self) -> None:
        # Defensive: an unregistered finding code surfaces the
        # fallback "(no registered template)" string rather than
        # crashing the renderer with KeyError.
        from whatif.decision.finding_codes import FINDING_CODE_REGISTRY
        from whatif.decision.fix_suggestions import FIX_SUGGESTION_REGISTRY
        from whatif.types.finding import DecisionFinding

        # Find a finding code that exists in FINDING_CODE_REGISTRY
        # but NOT in FIX_SUGGESTION_REGISTRY (an info-severity code
        # would qualify but isn't blocking; we forge a blocking-
        # severity finding directly to exercise the fallback).
        # Use a hand-built DecisionFinding with severity=blocks_ship
        # and code that's intentionally unregistered.
        unregistered_code = "test_unregistered_blocking_code"
        assert unregistered_code not in FIX_SUGGESTION_REGISTRY
        # Confirm the test premise: the code is also not in the
        # finding registry (any registered code MUST have a fix
        # suggestion per cardinal #8 coverage).
        assert unregistered_code not in FINDING_CODE_REGISTRY

        forged = DecisionFinding(
            code=unregistered_code,
            severity="blocks_ship",
            message="forged finding for fallback test",
        )
        verdict = dataclasses.replace(dont_ship(), findings=(forged,))
        # No raise — fallback string appears.
        out = render_full_report(_report_for(verdict))
        assert f"`{unregistered_code}` (no registered template)" in out


# ---------------------------------------------------------------------------
# Stats section
# ---------------------------------------------------------------------------


class TestStats:
    def test_section_header_present(self) -> None:
        out = render_full_report(_report_for(ship()))
        assert "## Stats" in out

    def test_failure_and_baseline_lines_present(self) -> None:
        out = render_full_report(_report_for(ship()))
        assert "**Failures (" in out
        assert "**Baseline (" in out

    def test_ci_string_when_bounds_present(self) -> None:
        # The fixture's cohort produces ci_lower / ci_upper
        # populated; pin the `CI [lower, upper]` shape.
        out = render_full_report(_report_for(ship()))
        assert "CI [" in out

    def test_ci_not_computed_fallback(self) -> None:
        # Engineer a cohort with neither CI bounds nor an
        # unavailable_reason; the fallback string must appear.
        c = dataclasses.replace(
            cohort("failure"),
            ci_lower=None,
            ci_upper=None,
            ci_unavailable_reason=None,
        )
        verdict = dataclasses.replace(
            ship(),
            cohort_results=(c, *[r for r in ship().cohort_results if r.name != "failure"]),
        )
        out = render_full_report(_report_for(verdict))
        assert "(CI not computed)" in out

    def test_ci_unavailable_reason_renders_in_string(self) -> None:
        # Three-way CI coverage: bounds present (covered by
        # test_ci_string_when_bounds_present), bounds absent +
        # reason present (this test), bounds absent + reason
        # absent (test_ci_not_computed_fallback above).
        c = dataclasses.replace(
            cohort("failure"),
            ci_lower=None,
            ci_upper=None,
            ci_unavailable_reason="sample_too_small",
        )
        verdict = dataclasses.replace(
            ship(),
            cohort_results=(c, *[r for r in ship().cohort_results if r.name != "failure"]),
        )
        out = render_full_report(_report_for(verdict))
        assert "(CI not computed: sample_too_small)" in out


# ---------------------------------------------------------------------------
# Replay validity edge cases
# ---------------------------------------------------------------------------


class TestReplayValidityZeroSelected:
    def test_zero_selected_does_not_zero_divide(self) -> None:
        # Defensive pin: a cohort with selected=0 (degenerate, but
        # possible if a future selection policy yields nothing for
        # one cohort) must NOT crash the renderer with a
        # ZeroDivisionError. The percentage falls back to "n/a".
        c = dataclasses.replace(
            cohort("failure"),
            selected=0,
            replayed=0,
            scored=0,
        )
        verdict = dataclasses.replace(
            ship(),
            cohort_results=(c, *[r for r in ship().cohort_results if r.name != "failure"]),
        )
        # No raise.
        out = render_full_report(_report_for(verdict))
        # The zero-selected cohort's replay-validity line uses
        # "n/a" for percentages.
        assert "**failure:** 0 selected, 0 replayed (n/a)" in out


# ---------------------------------------------------------------------------
# Replay validity
# ---------------------------------------------------------------------------


class TestReplayValidity:
    def test_section_header_present(self) -> None:
        out = render_full_report(_report_for(ship()))
        assert "## Replay validity" in out

    def test_per_cohort_counts_rendered(self) -> None:
        out = render_full_report(_report_for(ship()))
        # Each cohort surfaces selected/replayed/scored counts.
        assert "selected," in out
        assert "replayed (" in out
        assert "scored (" in out
