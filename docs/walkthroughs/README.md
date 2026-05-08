# Walkthrough scenarios

Six rendered Markdown reports that pressure-test the design before any code is written.

These files are the **canonical output** Phase 7's renderer must reproduce. The Phase 7 test suite asserts `render_full_report(report)` byte-equals the corresponding file (modulo non-deterministic fields under `manifest.runtime`).

The walkthroughs are also the empirical reviewer for the design. Each scenario surfaces concrete gaps that feed `references/cascade-catalog.md`. Gaps surfaced here must resolve or defer before schema freeze.

## Index

| # | File | Verdict | Pressure tested |
|---|------|---------|-----------------|
| 1 | [01-clean-ship.md](01-clean-ship.md) | Ship | Compact-form trust visibility |
| 2 | [02-dont-ship-regression.md](02-dont-ship-regression.md) | Don't Ship | Per-trace evidence with judge rationale |
| 3 | [03-dont-ship-failure-rescue-gap.md](03-dont-ship-failure-rescue-gap.md) | Don't Ship | Multi-cause fix-suggestion templating |
| 4 | [04-inconclusive-insufficient-sample.md](04-inconclusive-insufficient-sample.md) | Inconclusive | Per-cohort floor table; failure-driven fix text |
| 5 | [05-inconclusive-cache-corruption.md](05-inconclusive-cache-corruption.md) | Inconclusive | Run-scope failure → CLI recovery commands |
| 6 | [06-rerun-after-fix.md](06-rerun-after-fix.md) | Diff | `whatif diff` CLI surface; diff JSON schema |

## Scenario 1: Clean Ship

**Setup:** A prompt update meant to fix a small set of failed traces. Failures cohort improved 14/20; baseline stable; no operational issues.

**Underlying state:**
- Failure cohort: 20 selected, 20 replayed, 20 scored, 14 improved, 4 unchanged, 2 regressed
- Baseline cohort: 20 selected, 20 replayed, 20 scored, 3 improved, 16 unchanged, 1 regressed
- Cache: 38 hits, 2 misses, 0 stale
- All floor rules pass; all policy rules pass

**CI status line:** `✓ whatif: Ship — failures 14/20 ↑, baseline 17/20 stable`

**Design pressure:** ~12 lines of report total. Below 30-line budget. The two trace mentions ("top improvement" / "top regression") at the bottom prevent the clean-Ship template from being a rubber stamp — reviewers see at least one improvement and one regression even when nothing is wrong. **Open question:** the `[Full evidence ↓](#evidence)` link points at a section that doesn't exist in the compact form. See cascade catalog: "Compact-form anchor semantics."

## Scenario 2: Don't Ship (regression)

**Setup:** A prompt update fixes 14/20 failures but causes a 30% regression on baseline traces. The classic silent-regression case whatif exists to catch.

**Underlying state:**
- Failure cohort: 20 selected, 20 replayed, 20 scored, 14 improved, 3 unchanged, 3 regressed
- Baseline cohort: 20 selected, 20 replayed, 20 scored, 1 improved, 13 unchanged, 6 regressed (median Δ -0.18)
- Cache: 39 hits, 1 miss
- Floor: all pass
- Policy: `max_baseline_regression_ratio: 0.10` violated (6/20 = 30%)

**CI status line:** `✗ whatif: Don't Ship — baseline regressed 6/20 (median Δ -0.18)`

**Design pressure:** The judge rationale is what makes the report defensible. Without "agent now refuses requests it previously handled correctly," the reviewer just sees a number and must take it on faith. The Sensitive[T] redaction profile choice matters here — `review` profile shows snippets; `minimal` profile would show only deltas without text. **Schema gap:** the per-trace evidence shape (Original / Replayed / Judge) is not in `CohortResult`, `FailureRecord`, or `DecisionFinding`. See cascade catalog: "Per-trace evidence schema."

## Scenario 3: Don't Ship (failure rescue gap)

**Setup:** The proposed change doesn't actually fix the failures it was supposed to address. Baseline is fine.

**Underlying state:**
- Failure cohort: 20 selected, 20 replayed, 20 scored, 2 improved, 16 unchanged, 2 regressed
- Baseline cohort: 20 selected, 20 replayed, 20 scored, 1 improved, 18 unchanged, 1 regressed
- Floor: all pass
- Policy: `min_failure_improvement_ratio: 0.50` violated (2/20 = 10%)

**CI status line:** `✗ whatif: Don't Ship — failures only 2/20 improved (need 50%)`

**Design pressure:** Fix suggestions for "failure cohort didn't improve" need to span multiple causes. The current `FixSuggestion` shape (one template + list of generic suggestions) is right for floor rules but doesn't capture the *enumerated multiple-causes* pattern this scenario uses. See cascade catalog: "Multi-cause fix-suggestion templating."

## Scenario 4: Inconclusive (insufficient sample)

**Setup:** The user is bootstrapping their tracer. Only 3 baseline traces have complete tool outputs. Floor rule violated.

**Underlying state:**
- Failure cohort: 15 selected, 15 replayed, 15 scored, 11 improved, 3 unchanged, 1 regressed
- Baseline cohort: 8 selected, 5 replayed, 3 scored (5 had cache misses; 2 of remaining had schema mismatches)
- Floor: `min_scored_per_required_cohort: 5` violated for baseline (3 < 5)

**CI status line:** `⚠ whatif: Inconclusive — baseline cohort below floor (3 < 5 scored)`

**Design pressure:** Two things land here.
1. The fix text is not generic — it enumerates the specific causes from failure records ("5 traces had cache misses for tool `search`"). The renderer queries failure records, groups by code, and produces per-code text. Confirms the `FIX_SUGGESTION_REGISTRY` design but adds a new requirement: templates must be able to reference aggregated failure data, not just the threshold values.
2. The floor evaluation table renders all eight rules including the passing ones with checkmarks. `CohortResult.floor_failures` only carries failures. Either track passing rules too, or have the renderer iterate over `TrustFloor` rules and check membership. See cascade catalog: "Floor table rendering — passing rules."

## Scenario 5: Inconclusive (cache corruption)

**Setup:** The scorer cache lock file is corrupted from an interrupted previous run. The current run cannot acquire the lock.

**Underlying state:**
- Run cannot start scoring stage
- `CacheLockedError` raised; converted to run-scope `FailureRecord(code="cache_lock_unavailable", scope="run")`
- Verdict: Inconclusive (run-scope failure)

**CI status line:** `⚠ whatif: Inconclusive — scorer cache locked by stale process`

**Design pressure:** Three CLI commands are referenced (`whatif cache rebuild --force`, `whatif cache unlock`, `whatif cache verify`). None are in the v0.1 CLI surface yet. If they aren't in v0.1 scope, scenario 5's recovery message is a lie. See cascade catalog: "CLI cache subcommands for v0.1."

## Scenario 6: Rerun-after-fix (diff mode)

**Setup:** After scenario 2 (Don't Ship: baseline regression), the engineer fixes the prompt and reruns. They want to compare report A (before fix) to report B (after fix).

**Underlying state:**
- Two runs against the same trace fixture
- Run A produced Don't Ship; Run B produced Ship
- User wants to see what changed

**CLI invocation (proposed):** `whatif diff reports/2026-05-03-prompt-v3/report.json reports/2026-05-04-prompt-v4/report.json`

**Design pressure:** Whether `whatif diff` is in v0.1 scope is a real question. Arguments for: it's the most natural engineer workflow after iterating on a fix. Arguments against: it's a separate CLI surface that doubles renderer complexity and requires its own JSON output schema. See cascade catalog: "CLI `whatif diff` for v0.1."

## What the walkthroughs prove together

1. The 30-line summary budget is achievable. Scenarios 1, 2, 3, 5 fit. Scenarios 4 and 6 (with structured tables) push the boundary but remain readable.
2. Fix suggestions need cause-specific templates, not generic ones. Scenarios 3, 4, 5 each need different fix text driven by which finding fired and which underlying failures contributed.
3. The CLI surface needs `cache rebuild`, `cache unlock`, `cache verify`, and `diff`. Scenarios 5 and 6 reveal these as required for v0.1 to be usable.
4. The judge rationale is the load-bearing element of evidence. Scenarios 2 and 3 are defensible only because the judge text quotes the actual change in agent behavior.
5. Per-cohort floor breakdown in the report is essential. Scenario 4's table format is the right shape — readable and structured.
6. The Sensitive[T] redaction profile choice is visible to users. What appears in the evidence section depends on `reporting.profile`. The rendered report should disclose which profile produced it.

These six observations are filed as cascade entries. None are surprising; all are concrete; all are resolvable before schema freeze.

## How to read these scenarios

- The six `.md` files are the **canonical rendered output**. Phase 7's renderer test asserts byte-equality against them.
- This README is the **context** — setup, underlying state, CI status line, design pressure observed.
- The skill reference at `.claude/skills/whatifd-design/walkthroughs.md` is the **upstream source** for these files. When the skill changes, this directory updates.
- Cascade entries surfaced by these scenarios live in `.claude/skills/whatifd-design/references/cascade-catalog.md` under "Open cascades."
