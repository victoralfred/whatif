"""Tests for `whatifd.diff` — Phase 8.4.

This module is also the load-bearing coverage for **walkthrough 06
(rerun-after-fix / diff)** under Phase 9A.2's coverage map. The
cascade-catalog entry "Phase 9A walkthrough scenario coverage"
defers walkthrough 06 from the integration suite to this file:
reproducing the diff path through `run_pipeline` would mostly re-
test what the cases below already pin (verdict transitions, cohort
deltas, findings added/removed, no-changes sentinel). If you remove
or weaken cases here, update that cascade entry to match — or add
the integration coverage and close the deferral.

Pinned properties:

1. `load_report` raises `DiffError` for missing file, unreadable
   file, malformed JSON, and non-mapping JSON. Genuine reports
   round-trip.
2. `compute_diff` surfaces verdict transitions, schema-version
   transitions, failure-count deltas, per-cohort row deltas, and
   findings added/removed (keyed on (code, severity)).
3. `render_diff_markdown` produces a Markdown body that ends with
   a single trailing newline; the verdict-unchanged + nothing-else
   case emits the "(No changes detected.)" sentinel; the
   verdict-changed case emits a `prev → new` arrow.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from whatifd.diff import (
    CohortDelta,
    DiffError,
    DiffReport,
    FindingDelta,
    compute_diff,
    load_report,
    render_diff_markdown,
)


def _base_report(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "verdict_state": "ship",
        "schema_version": "v0.1",
        "cohort_results": [],
        "decision_findings": [],
        "failures": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# load_report
# ---------------------------------------------------------------------------


class TestLoadReport:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(DiffError, match="not found"):
            load_report(tmp_path / "missing.json")

    def test_malformed_json(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not json{", encoding="utf-8")
        with pytest.raises(DiffError, match="JSON parse error"):
            load_report(p)

    def test_non_mapping_root(self, tmp_path: Path) -> None:
        p = tmp_path / "list.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(DiffError, match="must parse to a mapping"):
            load_report(p)

    def test_unreadable_file_raises_diff_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Cardinal #1: OSError at the file-read boundary surfaces as
        # typed DiffError, not a raw OSError. Mock-based because
        # producing a real unreadable file portably (chmod 000) is
        # flaky under test-runner privileges.
        #
        # The class-level monkeypatch is safe: pytest's `monkeypatch`
        # fixture is function-scoped and auto-reverts at teardown,
        # and pytest runs tests sequentially within a process by
        # default (pytest-xdist isolates via separate processes, not
        # concurrent threads). Per-instance scoping isn't practical
        # for `Path.read_text`: `pathlib.PurePath` uses `__slots__`,
        # so `monkeypatch.setattr(p, "read_text", ...)` raises
        # `AttributeError: 'PosixPath' object attribute 'read_text'
        # is read-only`. Class-level patch is the only option;
        # parallelism concerns are addressed by pytest-xdist's
        # process isolation above.
        p = tmp_path / "ok.json"
        p.write_text(json.dumps(_base_report()), encoding="utf-8")

        def _raise(*args: object, **kwargs: object) -> str:
            raise OSError("simulated read failure")

        monkeypatch.setattr(Path, "read_text", _raise)
        with pytest.raises(DiffError, match="cannot read"):
            load_report(p)

    def test_round_trip(self, tmp_path: Path) -> None:
        p = tmp_path / "ok.json"
        p.write_text(json.dumps(_base_report()), encoding="utf-8")
        data = load_report(p)
        assert data["verdict_state"] == "ship"


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiff:
    def test_verdict_and_failures(self) -> None:
        prev = _base_report(verdict_state="dont_ship", failures=[{"code": "x"}])
        new = _base_report(verdict_state="ship")
        report = compute_diff(prev, new)
        assert report.verdict_state_prev == "dont_ship"
        assert report.verdict_state_new == "ship"
        assert report.failures_prev == 1
        assert report.failures_new == 0

    def test_cohort_deltas_keyed_by_name(self) -> None:
        prev = _base_report(
            cohort_results=[
                {
                    "name": "failure",
                    "selected": 10,
                    "scored": 8,
                    "improved_count": 2,
                    "regressed_count": 1,
                    "unchanged_count": 5,
                    "median_delta": "+0.05",
                }
            ]
        )
        new = _base_report(
            cohort_results=[
                {
                    "name": "failure",
                    "selected": 10,
                    "scored": 9,
                    "improved_count": 5,
                    "regressed_count": 0,
                    "unchanged_count": 4,
                    "median_delta": "+0.10",
                }
            ]
        )
        report = compute_diff(prev, new)
        assert len(report.cohorts) == 1
        c = report.cohorts[0]
        assert c.name == "failure"
        assert (c.improved_prev, c.improved_new) == (2, 5)
        assert (c.median_delta_prev, c.median_delta_new) == ("+0.05", "+0.10")

    def test_findings_added_and_removed(self) -> None:
        prev = _base_report(
            decision_findings=[{"code": "A", "severity": "warning", "message": "old"}]
        )
        new = _base_report(
            decision_findings=[{"code": "B", "severity": "blocking", "message": "new"}]
        )
        report = compute_diff(prev, new)
        directions = {(f.code, f.direction) for f in report.findings}
        assert ("A", "removed") in directions
        assert ("B", "added") in directions


# ---------------------------------------------------------------------------
# render_diff_markdown
# ---------------------------------------------------------------------------


class TestRenderDiffMarkdown:
    def _empty_report(self, **kw: object) -> DiffReport:
        defaults: dict[str, object] = {
            "verdict_state_prev": "ship",
            "verdict_state_new": "ship",
            "schema_version_prev": "v0.1",
            "schema_version_new": "v0.1",
            "failures_prev": 0,
            "failures_new": 0,
            "cohorts": (),
            "findings": (),
        }
        defaults.update(kw)
        return DiffReport(**defaults)  # type: ignore[arg-type]

    def test_trailing_newline(self) -> None:
        out = render_diff_markdown(self._empty_report())
        assert out.endswith("\n")
        assert not out.endswith("\n\n")

    def test_no_changes_sentinel(self) -> None:
        out = render_diff_markdown(self._empty_report())
        assert "(No changes detected.)" in out
        assert "(unchanged)" in out

    def test_verdict_transition_arrow(self) -> None:
        report = self._empty_report(verdict_state_prev="dont_ship", verdict_state_new="ship")
        out = render_diff_markdown(report)
        assert "Don't Ship" in out
        assert "→" in out

    def test_cohort_table_renders(self) -> None:
        report = self._empty_report(
            cohorts=(
                CohortDelta(
                    name="failure",
                    selected_prev=10,
                    selected_new=10,
                    scored_prev=8,
                    scored_new=9,
                    improved_prev=2,
                    improved_new=5,
                    regressed_prev=1,
                    regressed_new=0,
                    unchanged_prev=5,
                    unchanged_new=4,
                    median_delta_prev="+0.05",
                    median_delta_new="+0.10",
                ),
            ),
        )
        out = render_diff_markdown(report)
        assert "## Cohorts" in out
        assert "| failure" in out
        # Changed cells render as prev→new (delta); unchanged as bare value.
        assert "8→9" in out
        assert "+0.05→+0.10" in out

    def test_schema_only_change_is_not_no_change(self) -> None:
        # Pin: schema-version-only delta MUST NOT co-render with the
        # "(No changes detected.)" sentinel. Without the schema check
        # in _verdict_unchanged_and_nothing_else, the renderer emits
        # the schema line AND the sentinel — contradictory output.
        report = self._empty_report(schema_version_prev="v0.1", schema_version_new="v0.2")
        out = render_diff_markdown(report)
        assert "v0.1" in out and "v0.2" in out
        assert "(No changes detected.)" not in out

    def test_unchanged_count_shift_is_not_no_change(self) -> None:
        # Pin: a cohort where only `unchanged_count` shifts (e.g.,
        # rebalancing between unchanged and improved missed the
        # improved counter) MUST NOT emit "(No changes detected.)".
        report = self._empty_report(
            cohorts=(
                CohortDelta(
                    name="failure",
                    selected_prev=10,
                    selected_new=10,
                    scored_prev=8,
                    scored_new=8,
                    improved_prev=2,
                    improved_new=2,
                    regressed_prev=1,
                    regressed_new=1,
                    unchanged_prev=5,
                    unchanged_new=4,
                    median_delta_prev=None,
                    median_delta_new=None,
                ),
            ),
        )
        out = render_diff_markdown(report)
        assert "(No changes detected.)" not in out

    def test_failures_line_suppressed_when_unchanged(self) -> None:
        # Aligns with the Schema-line suppression policy: when the
        # failure count is unchanged, no Failures line surfaces.
        # The verdict line stays (load-bearing per cardinal #10).
        report = self._empty_report(verdict_state_prev="dont_ship", verdict_state_new="ship")
        out = render_diff_markdown(report)
        assert "**Failures:**" not in out

    def test_failures_line_emitted_when_changed(self) -> None:
        report = self._empty_report(failures_prev=2, failures_new=5)
        out = render_diff_markdown(report)
        assert "**Failures:** 2 → 5 (+3)" in out

    def test_pair_str_both_none_renders_single_na(self) -> None:
        # Pin the deliberate invariant from `_pair_str` docstring:
        # both-None medians render as a single `n/a` (unchanged),
        # NOT `n/a→n/a`. Exercised end-to-end via the cohort row.
        report = self._empty_report(
            verdict_state_prev="dont_ship",  # force render past no-changes guard
            verdict_state_new="ship",
            cohorts=(
                CohortDelta(
                    name="failure",
                    selected_prev=10,
                    selected_new=10,
                    scored_prev=8,
                    scored_new=8,
                    improved_prev=2,
                    improved_new=2,
                    regressed_prev=1,
                    regressed_new=1,
                    unchanged_prev=5,
                    unchanged_new=5,
                    median_delta_prev=None,
                    median_delta_new=None,
                ),
            ),
        )
        out = render_diff_markdown(report)
        assert "n/a→n/a" not in out
        assert "| n/a |" in out

    def test_findings_section(self) -> None:
        report = self._empty_report(
            findings=(
                FindingDelta(code="A", severity="warning", direction="removed", message="old"),
                FindingDelta(code="B", severity="blocking", direction="added", message="new"),
            )
        )
        out = render_diff_markdown(report)
        assert "## Findings" in out
        assert "`A`" in out
        assert "`B`" in out
        assert "**+**" in out and "**-**" in out
