"""Phase 7.1c — walkthrough structural fidelity tests.

For each of the six `docs/walkthroughs/0X-*.md` scenarios, build a
`ReportV01` matching the scenario's "Underlying state" and assert
the rendered output is structurally consistent across the three
formats:

  - `render_ci_status` produces the verdict glyph + label expected
    by the README's "CI status line" entry.
  - `render_summary` produces the verdict header + key cohort
    counts.
  - `render_full_report` produces the verdict header + sections +
    anchors.

## Why structural fidelity instead of byte-equality

The original Phase 7 gate per `phases.md` is byte-equality with
the committed walkthroughs. Several walkthrough features are
deferred from v0.1:

- Per-trace evidence schema (scenarios 2, 3) — cascade-tracked
  for v0.2.
- Multi-cause fix-suggestion templating (scenario 3) — current
  registry is single-template per code.
- Floor table with PASSING rules surfaced (scenario 4) — current
  `CohortResult.floor_failures` only carries failures.

Phase 7.1c ships STRUCTURAL fidelity now. The fixtures in
`_walkthrough_fixtures.py` are concrete enough to drive byte-
equality tests when the deferred features land — tests then add
`docs/walkthroughs/*.md` byte-equal assertions without rebuilding
the fixture surface.

## What's pinned

- Each scenario's verdict_state matches the walkthrough's
  documented verdict.
- Each scenario renders without raising in all three formats.
- Three-format consistency: the verdict label appears in all
  three formats; key cohort counts appear in summary + full
  report.
"""

from __future__ import annotations

import pytest

from whatifd.decision.fix_suggestions import FIX_SUGGESTION_REGISTRY
from whatifd.render import (
    render_ci_status,
    render_full_report,
    render_summary,
)
from whatifd.render._constants import VERDICT_LABEL

from ._walkthrough_fixtures import SCENARIOS

_SCENARIO_IDS = [f"scenario_{n}_{s.name}" for n, s in SCENARIOS.items()]
_SCENARIO_PARAMS = list(SCENARIOS.items())


@pytest.fixture(
    scope="module",
    params=_SCENARIO_PARAMS,
    ids=_SCENARIO_IDS,
)
def scenario(request):
    # `scope="module"`: each Scenario.builder() runs ONCE per module
    # rather than per-test, cutting ~54 builds (6 scenarios x 9 tests)
    # to 6. Reports are frozen dataclasses so cross-test mutation isn't
    # a concern.
    n, s = request.param  # s: Scenario NamedTuple — see _walkthrough_fixtures.
    return {
        "n": n,
        "name": s.name,
        "expected_verdict_state": s.expected_verdict_state,
        "report": s.builder(),
    }


# ---------------------------------------------------------------------------
# Verdict-state fidelity
# ---------------------------------------------------------------------------


class TestVerdictFidelity:
    def test_verdict_state_matches_walkthrough(self, scenario) -> None:
        assert scenario["report"].verdict_state == scenario["expected_verdict_state"], (
            f"Scenario {scenario['n']} ({scenario['name']}): expected "
            f"verdict_state={scenario['expected_verdict_state']!r}, got "
            f"{scenario['report'].verdict_state!r}"
        )


# ---------------------------------------------------------------------------
# All three formats render without raising
# ---------------------------------------------------------------------------


class TestAllFormatsRender:
    def test_ci_status_renders(self, scenario) -> None:
        line = render_ci_status(scenario["report"])
        assert isinstance(line, str)

    def test_summary_renders(self, scenario) -> None:
        out = render_summary(scenario["report"])
        assert isinstance(out, str)
        assert out.startswith("# whatifd verdict:")

    def test_full_report_renders(self, scenario) -> None:
        out = render_full_report(scenario["report"])
        assert isinstance(out, str)
        assert out.startswith("# whatifd verdict:")


# ---------------------------------------------------------------------------
# CI-status-specific format contract
# ---------------------------------------------------------------------------


class TestCIStatusFormat:
    """CI-status-specific format properties.

    Separated from TestAllFormatsRender because the 80-char ceiling
    is a CI-status format contract, not a property shared with
    summary or full report. Future CI-status format pins (e.g.,
    ASCII-only or no embedded newlines) belong here.
    """

    def test_ci_status_within_80_char_budget(self, scenario) -> None:
        line = render_ci_status(scenario["report"])
        assert len(line) <= 80, f"CI status line {len(line)} chars: {line!r}"


# ---------------------------------------------------------------------------
# Three-format consistency: verdict label appears in all three
# ---------------------------------------------------------------------------


class TestThreeFormatConsistency:
    def test_verdict_label_appears_in_all_formats(self, scenario) -> None:
        report = scenario["report"]
        # Source of truth for the verdict label is in
        # `whatifd.render._constants.VERDICT_LABEL`. Importing it
        # here avoids drift if a future label change updates the
        # render module without touching test expectations.
        label = VERDICT_LABEL[report.verdict_state]
        ci = render_ci_status(report)
        summary = render_summary(report)
        full = render_full_report(report)

        assert label in ci
        assert label in summary
        assert label in full

    def test_cohort_counts_consistent_summary_vs_full(self, scenario) -> None:
        # If the report has cohort_results, the summary's per-cohort
        # `(N):` count and the full report's `(N):` count must match.
        # (Both source from `CohortResult.scored`.)
        #
        # Scoped to `({scored}):` (with trailing colon) rather than
        # bare `({scored})` — the colon is part of the cohort-line
        # format `**Label (N):**` and avoids spurious matches when
        # the integer string `(0)` could appear elsewhere in the
        # rendered output (e.g., a future "Cache: 0 misses" line).
        report = scenario["report"]
        if not report.cohort_results:
            pytest.skip("scenario has no cohort_results")
        summary = render_summary(report)
        full = render_full_report(report)
        for c in report.cohort_results:
            count_marker = f"({c.scored}):"
            assert count_marker in summary, (
                f"cohort {c.name!r} count marker {count_marker!r} missing from summary"
            )
            assert count_marker in full, (
                f"cohort {c.name!r} count marker {count_marker!r} missing from full report"
            )


# ---------------------------------------------------------------------------
# Per-scenario structural pins
# ---------------------------------------------------------------------------


class TestScenarioStructure:
    """Per-scenario structural pins.

    Note: these tests deliberately do NOT consume the shared
    `scenario` fixture. They each target ONE specific scenario by
    importing its builder directly so the assertion can pin
    scenario-specific shape (e.g., scenario 4's floor table,
    scenario 5's cache_lock fix-suggestion summary). This excludes
    them from the parameterized cross-format run, which is the
    intended trade-off — the parameterized tests in the classes
    above cover the cross-format properties; this class covers
    per-scenario specifics.
    """

    def test_scenario_2_dont_ship_regression_surfaces_baseline_regression(
        self,
    ) -> None:
        # The Don't Ship regression scenario MUST surface the
        # baseline-regression finding's message in summary + full.
        from ._walkthrough_fixtures import scenario_2_dont_ship_regression

        report = scenario_2_dont_ship_regression()
        summary = render_summary(report)
        full = render_full_report(report)
        assert "baseline cohort regressed" in summary
        assert "baseline cohort regressed" in full

    def test_scenario_4_inconclusive_renders_floor_table(self) -> None:
        # The insufficient-sample scenario has a floor failure;
        # the full report renders the floor-evaluation table.
        from ._walkthrough_fixtures import (
            scenario_4_inconclusive_insufficient_sample,
        )

        report = scenario_4_inconclusive_insufficient_sample()
        full = render_full_report(report)
        assert "## Floor evaluation" in full
        assert "min_scored_per_required_cohort" in full
        assert "**baseline**" in full
        assert "**3**" in full

    def test_scenario_5_inconclusive_renders_cache_lock_finding(self) -> None:
        from ._walkthrough_fixtures import (
            scenario_5_inconclusive_cache_corruption,
        )

        report = scenario_5_inconclusive_cache_corruption()
        full = render_full_report(report)
        # The cache_lock_unavailable fix-suggestion template is
        # registered; verify its summary line appears in the
        # rendered full report.
        template = FIX_SUGGESTION_REGISTRY["cache_lock_unavailable"]
        assert f"### {template.summary}" in full

    def test_clean_ship_no_fix_section_content(self) -> None:
        # Clean Ship's Suggested-next-steps section is the "no
        # actionable findings" placeholder (NOT a registry
        # template). Pin this explicitly so a future regression
        # that emits a template for clean Ship surfaces here.
        from ._walkthrough_fixtures import scenario_1_clean_ship

        report = scenario_1_clean_ship()
        full = render_full_report(report)
        assert "No actionable findings" in full
