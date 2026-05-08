# Walkthrough Scenarios

Six rendered Markdown outputs that pressure-test the design. The walkthroughs are the empirical reviewer — every architectural decision gets validated against whether it produces engineer-readable output for these scenarios.

These are the **first deliverable** in Phase 0, before any code or schema work. They surface gaps the deliberation cannot.

## How to use this file

This file holds the canonical rendered output for each scenario, plus the underlying JSON outline. When designing the renderer (Phase 7), the test suite asserts each scenario's actual rendered output matches the canonical version here.

Each scenario has four parts:

1. **Setup** — what's happening (one paragraph)
2. **Underlying state** — key facts about the experiment that produce this output
3. **CI status line** — the ~80-char one-liner shown in GitHub check display
4. **Markdown report** — the full file an engineer would read

When a walkthrough surfaces a gap (missing CLI command, missing fix template, missing data field), file it in `references/cascade-catalog.md` and resolve before schema freeze.

## Scenario 1: Clean Ship

**Setup:** A prompt update meant to fix a small set of failed traces. Failures cohort improved 14/20; baseline stable; no operational issues.

**Underlying state:**
- Failure cohort: 20 selected, 20 replayed, 20 scored, 14 improved, 4 unchanged, 2 regressed
- Baseline cohort: 20 selected, 20 replayed, 20 scored, 3 improved, 16 unchanged, 1 regressed
- Cache: 38 hits, 2 misses, 0 stale
- All floor rules pass; all policy rules pass

**CI status line:**
```
✓ whatif: Ship — failures 14/20 ↑, baseline 17/20 stable
```

**Markdown report (compact form — degenerate case where summary IS the entire report):**

```markdown
# whatif verdict: Ship

**Failures (20):**   improved 14   unchanged 4   regressed 2   median Δ +0.31  CI [+0.18, +0.44]
**Baseline (20):**   improved 3    unchanged 16  regressed 1   median Δ +0.02  CI [-0.01, +0.05]

All floor rules passed. All policy rules passed.
Replay validity: 40/40 traces. Cache: 38 hits, 2 misses.

**Top improvement:** trace `t_4a91f` — agent now correctly handles ambiguous date input
**Top regression:** trace `t_8c33b` — slight wordiness increase in greeting

[Full evidence ↓](#evidence) · [Manifest →](manifest.json)
```

**Design pressure surfaced:** The compact form is ~12 lines including blank lines. Below the 30-line budget. The two trace mentions at the bottom are the "evidence" — minimal but present, so reviewers see at least one improvement and one regression even in the clean case. This prevents the clean-Ship template from being a rubber stamp.

---

## Scenario 2: Don't Ship (regression)

**Setup:** A prompt update fixes 14/20 failures but causes a 30% regression on baseline traces. Classic silent-regression case whatif exists to catch.

**Underlying state:**
- Failure cohort: 20 selected, 20 replayed, 20 scored, 14 improved, 3 unchanged, 3 regressed
- Baseline cohort: 20 selected, 20 replayed, 20 scored, 1 improved, 13 unchanged, 6 regressed (median Δ -0.18)
- Cache: 39 hits, 1 miss
- Floor: all pass
- Policy: `max_baseline_regression_ratio: 0.10` violated (6/20 = 30%)

**CI status line:**
```
✗ whatif: Don't Ship — baseline regressed 6/20 (median Δ -0.18)
```

**Markdown report (full form):**

```markdown
# whatif verdict: Don't Ship

**Reason:** baseline cohort regressed 6/20 traces (30%), exceeding the 10% threshold.
Median baseline Δ: **-0.18** (CI: [-0.24, -0.12]).

The proposed prompt change improves 14/20 failure cases but introduces regressions
in 30% of previously-correct baseline cases.

[Top regression: `t_492af` ↓](#regression-detail) · [Full report ↓](#stats) · [Manifest →](manifest.json)

---

## Stats

**Failures (20):**   improved 14   unchanged 3   regressed 3   median Δ +0.28  CI [+0.15, +0.41]
**Baseline (20):**   improved 1    unchanged 13  regressed 6   median Δ -0.18  CI [-0.24, -0.12]

## Replay validity

Replayed: 20/20 failures, 20/20 baseline.
Cache: 39 hits, 1 miss (`t_8c33b` — tool output schema changed).

## Baseline integrity

Baseline cohort regression rate: 30% (threshold: 10%) — **POLICY VIOLATION**

## Evidence

### Top improvements (3)

**`t_4a91f`** — Δ +0.45
> Original: "I cannot determine the date you mean."
> Replayed: "Did you mean May 4, 2026 (the upcoming) or May 4, 2025 (the past)?"
> Judge: Replayed handles ambiguity directly, original gave up.

**`t_2bd11`** — Δ +0.41
> [...similar shape...]

**`t_55a08`** — Δ +0.38
> [...similar shape...]

### Top regressions (3)

**`t_492af`** — Δ -0.31
> Original: "I'd be happy to help. What's your account number?"
> Replayed: "I cannot help with account inquiries without verification."
> Judge: Original handled a routine support request; replayed now refuses requests it previously handled correctly.

**`t_771fe`** — Δ -0.28
> [...similar shape...]

**`t_88c40`** — Δ -0.24
> [...similar shape...]

[See full trace context in Langfuse →](https://langfuse.example/...)
```

**Design pressure surfaced:** The judge rationale is what makes the report defensible. Without "agent now refuses requests it previously handled correctly," the reviewer just sees a number and has to take it on faith. The Sensitive[T] redaction profile choice matters here — review profile shows snippets; minimal profile would show only deltas without text.

---

## Scenario 3: Don't Ship (failure rescue gap)

**Setup:** The proposed change doesn't actually fix the failures it was supposed to address. Baseline is fine.

**Underlying state:**
- Failure cohort: 20 selected, 20 replayed, 20 scored, 2 improved, 16 unchanged, 2 regressed
- Baseline cohort: 20 selected, 20 replayed, 20 scored, 1 improved, 18 unchanged, 1 regressed
- Floor: all pass
- Policy: `min_failure_improvement_ratio: 0.50` violated (2/20 = 10%)

**CI status line:**
```
✗ whatif: Don't Ship — failures only 2/20 improved (need 50%)
```

**Markdown report (excerpt of the differing parts):**

```markdown
# whatif verdict: Don't Ship

**Reason:** the failure cohort improved on only 2/20 traces (10%), below the 50% threshold.
The proposed change does not appear to fix the targeted failures.

Baseline cohort is stable.

[Suggested next steps ↓](#fix) · [Full report ↓](#stats) · [Manifest →](manifest.json)

---

## Stats

**Failures (20):**   improved 2    unchanged 16  regressed 2   median Δ +0.02  CI [-0.04, +0.08]
**Baseline (20):**   improved 1    unchanged 18  regressed 1   median Δ +0.00  CI [-0.02, +0.02]

[...]

## Suggested next steps

The change does not improve the failure cohort enough to ship. Common causes:

- The change addresses a different failure mode than the failures cohort represents.
  Re-examine the failure traces to identify the actual pattern.
- The scorer rubric ("faithfulness") may not reward the kind of improvement the change targets.
  Try `--score inspect_ai:helpfulness` if the change targets response quality.
- The change is too conservative. Iterate on the prompt and rerun.
```

**Design pressure surfaced:** Fix suggestions for "failure cohort didn't improve" need to span multiple causes. The template can't be one-size-fits-all. May need cause-specific templates triggered by which guard fired.

---

## Scenario 4: Inconclusive (insufficient sample)

**Setup:** The user is bootstrapping their tracer. Only 3 baseline traces have complete tool outputs. Floor rule violated.

**Underlying state:**
- Failure cohort: 15 selected, 15 replayed, 15 scored, 11 improved, 3 unchanged, 1 regressed
- Baseline cohort: 8 selected, 5 replayed, 3 scored (5 had cache misses; 2 of remaining had schema mismatches)
- Floor: `min_scored_per_required_cohort: 5` violated for baseline (3 < 5)

**CI status line:**
```
⚠ whatif: Inconclusive — baseline cohort below floor (3 < 5 scored)
```

**Markdown report (full form):**

```markdown
# whatif verdict: Inconclusive

**Reason:** the baseline cohort has only 3 successfully-scored traces (floor requires 5).
There is insufficient evidence to evaluate this change against silent regression.

The failure cohort looks promising (11/15 improved), but a Ship verdict requires
a credibly-evaluated baseline.

[Suggested next steps ↓](#fix) · [Replay details ↓](#replay-validity) · [Manifest →](manifest.json)

---

## Suggested next steps

The baseline cohort had 8 selected traces but only 3 reached scoring. Causes:

1. **5 traces had tool-cache misses** (tool outputs not recorded in original traces).
   Fix: ensure your tracer is logging tool outputs. For Langfuse, see
   https://langfuse.com/docs/tracing-features/tool-tracing.

2. **2 traces had schema mismatches** (trace format differs from current).
   Fix: re-record traces with the current agent version, or update the adapter
   to handle the older schema.

3. **Selection limit may be too low.** Try increasing `selection.baseline_cohort.limit`
   to 20+ in `whatif.config.yaml` to give more headroom.

After addressing these, rerun the experiment.

## Replay validity

Failures: 15/15 replayed (100%), 15/15 scored (100%).
Baseline: 8 selected, 5 replayed (62.5%), 3 scored (37.5%).

Skipped traces:
- `t_b1023`, `t_b1024`, `t_b1025`, `t_b1027`, `t_b1031` — cache miss for tool `search`
- `t_b1029`, `t_b1030` — schema mismatch (missing `output_format` field)

## Stats

(Computed only for cohorts with sufficient samples.)

**Failures (15):**   improved 11   unchanged 3   regressed 1   median Δ +0.34  CI [+0.21, +0.47]
**Baseline (3):**    improved 2    unchanged 1   regressed 0   median Δ +0.05  (CI not computed: sample too small)

## Floor evaluation

| Rule | Cohort | Observed | Threshold | Status |
|------|--------|----------|-----------|--------|
| min_selected_per_required_cohort | failure | 15 | 5 | ✓ |
| min_replayed_per_required_cohort | failure | 15 | 5 | ✓ |
| min_scored_per_required_cohort | failure | 15 | 5 | ✓ |
| min_replay_validity_ratio_per_required_cohort | failure | 1.00 | 0.50 | ✓ |
| min_selected_per_required_cohort | baseline | 8 | 5 | ✓ |
| min_replayed_per_required_cohort | baseline | 5 | 5 | ✓ |
| **min_scored_per_required_cohort** | **baseline** | **3** | **5** | **✗** |
| min_replay_validity_ratio_per_required_cohort | baseline | 0.375 | 0.50 | ✗ |
```

**Design pressure surfaced:** The fix-suggestion text needs to be specific to which floor rules failed. A generic "increase your sample" isn't actionable. The text needs to enumerate the specific causes from the failure records. This means the renderer queries failure records, groups by code, and produces per-code text. Confirms the `FIX_SUGGESTION_REGISTRY` design.

---

## Scenario 5: Inconclusive (cache corruption)

**Setup:** The scorer cache lock file is corrupted from an interrupted previous run. The current run cannot acquire the lock.

**Underlying state:**
- Run cannot start scoring stage
- `CacheLockedError` raised; converted to run-scope `FailureRecord`
- Verdict: Inconclusive (run-scope failure)

**CI status line:**
```
⚠ whatif: Inconclusive — scorer cache locked by stale process
```

**Markdown report (focused excerpt):**

```markdown
# whatif verdict: Inconclusive

**Reason:** could not acquire scorer cache lock at `.whatif/cache/scorer/.lock`.
A previous run may have terminated abnormally, leaving the lock file orphaned.

[Suggested next steps ↓](#fix) · [Manifest →](manifest.json)

---

## Suggested next steps

The cache lock file shows:
- PID: 12345 (recorded)
- Hostname: ci-runner-7
- Started: 2026-04-30T14:22:00Z (4 days ago)

To recover:

1. **If you know the previous run is no longer running:**
   `whatif cache rebuild --force`
   This will rebuild the cache from scratch (slower next run, but safe).

2. **If you want to clear just the lock without rebuilding:**
   `whatif cache unlock`
   Use only if you're certain no other whatif process is using this cache.

3. **If you suspect file corruption:**
   `whatif cache verify`
   Reads all entries, reports any with checksum mismatches, optionally repairs.

This run produced no verdict. Rerun after recovery.
```

**Design pressure surfaced:** Three CLI commands are referenced (`cache rebuild --force`, `cache unlock`, `cache verify`). If these aren't in v0.1 scope, scenario 5 fails. **Cascade catalog item:** add `whatif cache <subcommand>` family to v0.1 CLI surface, with at least the three subcommands above.

---

## Scenario 6: Rerun-after-fix (diff mode)

**Setup:** After scenario 2 (Don't Ship: baseline regression), the engineer fixes the prompt and reruns. They want to compare report A (before fix) to report B (after fix).

**Underlying state:**
- Two runs against the same trace fixture
- Run A produced Don't Ship; Run B produced Ship
- User wants to see what changed

**CLI invocation (proposed):**
```
whatif diff reports/2026-05-03-prompt-v3/report.json reports/2026-05-04-prompt-v4/report.json
```

**Output (proposed):**

```markdown
# whatif diff: 2026-05-03-prompt-v3 → 2026-05-04-prompt-v4

**Verdict change:** Don't Ship → Ship

## Cohort comparison

| Cohort | Metric | v3 | v4 | Change |
|--------|--------|----|----|--------|
| failure | improved | 14 | 14 | unchanged |
| failure | regressed | 3 | 2 | -1 |
| baseline | improved | 1 | 3 | +2 |
| baseline | regressed | 6 | 1 | **-5** |
| baseline | median Δ | -0.18 | +0.02 | +0.20 |

## Findings change

**Resolved findings (in v3, gone in v4):**
- `baseline_regression_above_threshold` — baseline regression rate dropped from 30% to 5%.

**New findings (in v4, not in v3):**
(none)

## Trace-level differences

5 baseline traces that regressed in v3 but not in v4:
- `t_492af` (was Δ -0.31, now Δ +0.04)
- `t_771fe` (was Δ -0.28, now Δ +0.02)
- `t_88c40` (was Δ -0.24, now Δ -0.01)
- `t_a1234` (was Δ -0.21, now Δ +0.05)
- `t_b5567` (was Δ -0.18, now Δ +0.03)

The fix appears to have specifically addressed the over-refusal pattern identified
in v3's evidence section.
```

**Design pressure surfaced:** Whether `whatif diff` is in v0.1 scope is a real question. Arguments for: it's the most natural engineer workflow after iterating on a fix. Arguments against: it's a separate feature surface that doubles the CLI complexity and requires its own renderer.

**Cascade catalog item:** Decision on `whatif diff` for v0.1. Recommend: include it in v0.1 because the rerun-after-fix workflow is core to the failure-rescue use case. Without it, engineers iterate by reading two reports side-by-side, which is the kind of friction that drives them to skim.

---

## What the walkthroughs prove

After all six are written and the underlying JSON shape is consistent across them:

1. **The 30-line summary budget is achievable.** Scenarios 1, 2, 3 fit. Scenario 5 fits. Scenarios 4 and 6 (with structured tables) push the boundary.

2. **Fix suggestions need cause-specific templates, not generic ones.** Scenarios 3, 4, 5 each need different fix text driven by which finding fired.

3. **The CLI surface needs `cache rebuild`, `cache unlock`, `cache verify`, and `diff`.** Scenarios 5 and 6 reveal these as required for v0.1 to be usable.

4. **The judge rationale is the load-bearing element of evidence.** Scenarios 2 and 3 are defensible only because the judge text quotes the actual change in agent behavior.

5. **Per-cohort floor breakdown in the report is essential.** Scenario 4's table format is the right shape — readable and structured.

6. **The Sensitive[T] redaction profile choice is visible to users.** What appears in the evidence section depends on `reporting.profile`. Document this trade-off explicitly.

These six gaps feed the cascade catalog. None are surprising; all are concrete; all are resolvable before schema freeze.

The walkthroughs have done their job: they've moved the design from "internally coherent" to "empirically validated against engineer reading patterns."
