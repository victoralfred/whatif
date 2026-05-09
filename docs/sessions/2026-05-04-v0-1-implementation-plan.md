---
session_id: 2026-05-04-v0-1-implementation-plan
started_at: 2026-05-04T19:00:00Z
---

## Session start

**User request:** Develop a v0.1 implementation plan in plan mode, following the whatifd-design skill guidelines.

**Skill files read:**
- .claude/skills/whatifd-design/SKILL.md
- .claude/skills/whatifd-design/doctrine.md
- .claude/skills/whatifd-design/phases.md
- .claude/skills/whatifd-design/walkthroughs.md
- .claude/skills/whatifd-design/type-model.md
- .claude/skills/whatifd-design/references/cascade-catalog.md

(Read across this and earlier sessions today; doctrine, phases, type-model, and walkthroughs all read recently. Cascade catalog re-checked for current open-cascade count.)

**Cardinal rules cited:**
- Rule #1 (failure-as-data): the plan must structure every expected failure mode as data, not as ad-hoc handling. Drives the failure code registry, finding code registry, and fix-suggestion registry phases.
- Rule #2 (trust floor cannot be bypassed): the plan must put the witness-token enforcement (Phase 1.4 + Phase 2.1) before any code that constructs Ship.
- Rule #4 (determinism opt-in): drives Phase 5's schema-tag infrastructure.
- Rule #5 (Sensitive[T] wrapped): drives Phase 1.2 → Phase 4 (adapter wrapping) → Phase 5 (graph walk).
- Rule #6 (public schema hand-written): drives the public-vs-internal model split as a constraint across Phase 1, 5, and 9.
- Rule #8 (Inconclusive must be actionable): drives the fix-suggestion registry as a Phase 2 deliverable, not a renderer afterthought.
- Rule #9 (orchestration not compute): rejects any "scale this with Ray" suggestions that may surface during planning.

Rule #10 (statistical claims) is in the skill update queue (SKILL_UPDATE_PLAN.md Phase 1) but not yet adopted in the live skill. The plan must account for the skill update as a precondition for some downstream phases.

**Clarifying questions asked:**
- (None yet — clarifying questions for the project owner are part of the plan output, not preconditions to writing the plan.)

**Phase plan position (per references/phases.md):**
- Phase: 0 (Walkthroughs and conceptual model)
- Sub-item: 0.2 (conceptual model document) is next; 0.1 (walkthroughs) is done.
- Prerequisites status: Phase 0.1 walkthroughs committed (`f0d5bed`); SKILL_UPDATE_PLAN.md Phase 1 not yet started.

## Session end

**Artifacts produced:**
- `/home/voseghale/.claude/plans/golden-swimming-globe.md`: v0.1 implementation plan (approved by user; auto mode active afterwards)
- `~/projects/self_dev/.claude/skills/whatifd-design/SKILL.md`, `doctrine.md`, `practices.md`, `contracts.md`, `type-model.md`, `statistical-defaults.md` (new): direct replacements per Phase A.1 of SKILL_UPDATE_PLAN.md
- `~/projects/self_dev/.claude/skills/whatifd-design/type-model.md`: `methodology: MethodologyDisclosure` field manually added to `ReportV01` (the update author's known omission)
- `~/projects/self_dev/.claude/skills/whatifd-design/references/cascade-catalog.md`: three-way merge — 28 open + 22 deferred + 1 template
- `~/projects/self_dev/.claude/skills/whatifd-design/enforcement.md`: 3 new structural-claim rows (methodology disclosure, causal-claim scope, per-trace inference)
- `~/projects/self_dev/.claude/skills/whatifd-design/phases.md`: Phase 1.7 statistical types, Phase 2.5 primary_endpoint_guard + clustering.py, Phase 5.1 methodology field, Phase 7.1 methodology block rendering
- `~/projects/self_dev/.claude/skills/whatifd-design/references/V0_1_DECISION_RECORD.md`: cardinal #10 addendum
- `~/projects/self_dev/SKILL_UPDATE_PLAN.md`: status updated to "Phase A.1 done; A.3 doctrine-layer done; A.2 paused"
- `project/docs/concepts.md` (new): Phase 0.2 conceptual model document — eight sections plus glossary

**Cascade catalog items:**
- Updated: 6 new "open" cascades added (Paired-delta as atomic unit, Predeclared cohort-level primary endpoints, Methodology disclosure required, Reliability/validity/calibration/bias disclosed-as-unmeasured, Cluster bootstrap conditional on real cluster keys, Causal-claim scope enforced) + 12 new "deferred" cascades (cluster bootstrap implementation, stratified sampling, MDE warnings, Holm correction, judge repeat reliability, position-bias mitigation, sequential testing, active selection, calibration sets, HTE analysis, Bayesian panel, causal claims rejected)
- Opened: none new this session — these all came from the skill update package
- Resolved: none — Phase A.1 and A.3-doctrine put the doctrinal layer in place but no cascade items move to "resolved" until implementation lands

**Gaps surfaced:**
- Phase A.2 (walkthrough revision to add methodology blocks) is the empirical pressure-test of cardinal #10 against rendered output. Pending explicit user confirmation; the walkthroughs are now Phase 7 renderer test fixtures. A test of cardinal #10 itself.
- Phase 0.3 audience-distribution decision (failure-rescue scope vs include `regression_check`) needs project owner answer before Phase 1 type-model finalizes the `cohort` field.
- The CASCADE_CATALOG.md snapshot in `references/CASCADE_CATALOG.md` is now stale relative to the live `cascade-catalog.md`. It's a snapshot — re-sync deferred until next milestone.

**Doctrine moments:**
- Decided to proceed with Phase A.1 + A.3-doctrine without pausing because they're mechanical and the plan explicitly classifies them as low-risk.
- Decided to pause Phase A.2 (walkthrough revision) despite auto mode being active, because the plan explicitly says "Requires explicit user confirmation before touching project/docs/walkthroughs/" — auto mode minimizes interruptions but does not override explicit confirmation gates the user defined in their own plan.
- Wrote concepts.md in pre-cardinal-#10 form for the most part (the methodology block reference is in §6 but the doc doesn't yet quote the methodology shape exactly because that lands once A.2 walkthroughs settle).

**Notes for the next session:**
- Awaiting confirmation to proceed with Phase A.2 (walkthrough revision adding methodology blocks).
- Awaiting answer to Phase 0.3 audience-distribution question.
- Phase 0.4 enforcement audit can run after A.2 and A.3 settle — most of the audit is now positive (every structural claim has a paired mechanism in enforcement.md), but I haven't done the formal cross-reference audit pass yet.
- After Phase 0 gate clears, Phase 1 begins with `whatifd/types/primitives.py` — the smallest possible starting move.
