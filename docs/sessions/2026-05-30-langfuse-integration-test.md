---
session_id: 2026-05-30-langfuse-integration-test
started_at: 2026-05-30T00:00:00Z
---

## Session start

**User request:** Test whatifd against a real Langfuse instance scored by an auto-scorer (the result "wasn't as expected"), write a production-grade implementation, run it, and give a verdict. Then sketch the correct end-to-end wiring and fix the findings surfaced.

**Skill files read:**
- .claude/skills/whatifd-design/references/cascade-catalog.md (entry: "Run-level FloorFailure projection")
- CLAUDE.md (cardinal rules, scope discipline, telemetry protocol)

**Cardinal rules cited:**
- Rule #8 (Inconclusive must be actionable): the live run produced a bare `verdict_state="inconclusive"` with `decision_findings: []` — the core fix.
- Rule #2 (trust floor cannot be bypassed): the missing-cohort Inconclusive is floor-driven; the new finding is a disclosure layer on top, not a new verdict path.
- Rule #3 (disclosure necessary but not sufficient): justified choosing `decision_findings` (actionable) over a `floor_failures` wire field (pure disclosure).
- Rule #6 (public schema hand-written): the chosen fix adds no wire field, leaving the published v0.2 schema untouched.
- Rule #10 (statistical claims match design): diagnosed that the operator's data had zero score variance + tautological evaluator inputs → no defensible verdict possible; whatifd's Inconclusive was correct.

**Clarifying questions asked:**
- Which cascade resolution to implement for the missing-cohort fix — `decision_findings` only vs a `floor_failures` wire field vs both. Owner chose `decision_findings` only.

**Phase plan position (per references/phases.md):**
- Post-v0.2.0 hardening (branch `v0.2.1-hardening`, PR #110). This is a cardinal-#8 fix discovered via real-world integration testing.
- Prerequisites status: none outstanding for this fix.

## Session end

**Artifacts produced:**
- src/whatifd/decision/finding_codes.py: added `required_cohort_absent` FindingCodeSpec (blocks_all, `required_details=("cohort",)`, `derived_from_failures_expectation="never"`).
- src/whatifd/decision/fix_suggestions.py: added paired `required_cohort_absent` FixSuggestion pointing the operator upstream (classifier / data / experiment_shape).
- src/whatifd/decision/verdict.py: `compute_verdict` derives absent required cohorts and emits one `required_cohort_absent` finding per absent cohort, appended before the severity partition.
- tests/unit/whatifd/decision/test_verdict.py: `test_absent_required_cohort_emits_actionable_finding` + negative pin `test_present_required_cohorts_emit_no_absent_finding`.
- tests/unit/whatifd/decision/test_finding_codes.py: carved out `_FLOOR_DERIVED_BLOCKS_ALL` exception + `test_floor_derived_blocks_all_codes_do_not_expect_failure_derivation`.
- .claude/skills/whatifd-design/references/cascade-catalog.md: "Run-level FloorFailure projection" → resolved (decision_findings path).
- CHANGELOG.md: "Live-integration finding (2026-05-30)" entry under [Unreleased] → Fixed.
- (consumer-side, outside the repo) /home/voseghale/DEV/whatif/: corrected `production_langfuse_run.py`, `CORRECT_WIRING.md` (role-swap sketch), recon probes.

**Cascade catalog items:**
- Resolved: "Run-level FloorFailure projection" — missing-cohort Inconclusive made actionable via `decision_findings` (`required_cohort_absent`); no wire-schema change. Trigger (first real missing-cohort report + operator confusion) fired this session.
- Updated: noted the deferred Phase-7 renderer treatment of run-level vs per-cohort floor failures remains open as a separate concern.

**Gaps surfaced:**
- `whatifd-langfuse` ships only a `TraceSource`, no `Scorer`. Operators with an existing Langfuse LLM-judge cannot reuse it to score replayed outputs (whatifd re-scores both sides with one ruler per cardinal #10). A `LangfuseScorer` adapter that wraps the Langfuse evaluation config is a real feature gap — to be filed/implemented as its own branch after PR #110 merges (sequential-branch discipline).
- Full suite after the fix: 1347 passed, 1 skipped.

**Doctrine moments:**
- Applied the misleading-vs-inconvenient test to the verdict surface: a bare Inconclusive with no findings is *misleading* (reads as "nothing to report") rather than merely inconvenient. That made the fix mandatory under cardinal #8, not optional polish.
- Chose `decision_findings` over a new wire field by ranking cardinal #8 (actionability) above cardinal #3 (disclosure): a footnote field discloses but does not act; the findings channel is what renderers surface.

**Notes for the next session:**
- PR #110 (`v0.2.1-hardening`) now carries this fix locally — not yet committed/pushed (awaiting owner go-ahead).
- Second finding (LangfuseScorer reuse) is a feature, deferred to its own branch off updated main after #110 merges, per sequential-branch rule.
- The operator's data itself is degenerate (tautological evaluator inputs: response == reference byte-identical across 24/24; 1–5 rubric mis-extracted to score=1). Upstream evaluator fixes (reference ≠ response; correct scale extraction) are in `projects/trading`, not whatifd — captured in `/home/voseghale/DEV/whatif/CORRECT_WIRING.md`.
