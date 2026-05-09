# Phase 0.4 — Enforcement Audit

**Date**: 2026-05-05
**Status**: ✅ complete
**Source**: `.claude/skills/whatifd-design/phases.md` § 0.4
**Closes**: Phase 0 gate (Phase 0.1 ✅, 0.2 ✅, 0.3 ✅, 0.4 ✅ — Phase 1 unblocked)

## What this audit checked

Per `phases.md` § 0.4: for each "structural" claim across the codebase plan, confirm

1. The claim appears in `references/enforcement.md` with a paired mechanism.
2. The mechanism is implementable with v0.1 tooling.
3. The test that proves the mechanism is in the phase plan.

Method: grep for "structural" / "structurally" across all skill files (`SKILL.md`, `doctrine.md`, `type-model.md`, `contracts.md`, `practices.md`, `statistical-defaults.md`, `walkthroughs.md`, `phases.md`, `enforcement.md`, `references/cascade-catalog.md`, `references/V0_1_DECISION_RECORD.md`); classify each instance; cross-reference real claims against `enforcement.md`.

## Inventory of "structural" mentions

### Real structural CLAIMS — must have an enforcement.md row

| Claim | Source | Enforcement.md row | Status |
|---|---|---|---|
| Floor cannot be bypassed | doctrine.md, type-model.md, statistical-defaults.md, multiple | "Floor cannot be overridden" | ✅ |
| Sensitive[T] redaction | type-model.md, practices.md, multiple | "Sensitive fields cannot be written without redaction" | ✅ |
| Single-writer cache | type-model.md, contracts.md | "Single-writer cache access" | ✅ |
| Determinism opt-in | type-model.md, contracts.md, doctrine.md | "Same inputs → byte-identical JSON" | ✅ |
| Cache disclosure required | type-model.md, contracts.md | "Cache disclosure cannot be disabled" | ✅ |
| Failures-as-data (no silent crashes) | doctrine.md, practices.md, walkthroughs.md | "Failures-as-data (no silent crashes)" | ✅ |
| Inconclusive must be actionable | doctrine.md (cardinal #8), V0_1_DECISION_RECORD.md | "Inconclusive must be actionable" | ✅ |
| Public schema hand-written | type-model.md, contracts.md | "Public schema is hand-written" | ✅ |
| Two-affirmation forensic | doctrine.md, type-model.md, contracts.md | "Two-affirmation for forensic profile" | ✅ |
| Verdict-state space sealed | type-model.md | "Verdict-state space is closed" | ✅ |
| Methodology disclosure required | doctrine.md, type-model.md (cardinal #10) | "Methodology disclosure cannot be omitted" | ✅ (added Phase A.3) |
| Causal-claim scope sealed | doctrine.md, type-model.md (cardinal #10) | "Causal-claim scope cannot be exceeded" | ✅ (added Phase A.3) |
| Per-trace inference descriptive only | doctrine.md, type-model.md (cardinal #10) | "Per-trace inference is descriptive only" | ✅ (added Phase A.3) |
| **Paired-delta is the unit of analysis** | **type-model.md:398 ("Pairing is structural")** | **(was missing; added by this audit)** | ✅ (added Phase 0.4) |

### Meta-mentions (about the audit concept itself, not specific claims)

These are not claims requiring enforcement; they are documentation of the audit pattern. No action.

- `SKILL.md` § "How to use this skill" (mentions `references/enforcement.md` as a reference file)
- `SKILL.md` cardinal-rules block (uses "structural" as a property, not a claim)
- `SKILL.md` § "When in doubt, ask the right question" (uses "structural" as a question)
- `enforcement.md` itself (the audit-trail document)
- `practices.md` § "Style" / "What good looks like" (meta-mentions the audit)
- `phases.md` § 0.4 (defines this audit)
- `practices.md` § "What this workload is NOT" (uses "structural typing" to refer to Python `Protocol` — different sense of word)
- `contracts.md` § "Adapter protocols" (same — "structural typing" = Python `Protocol`)

### Cascade-tracked gaps (already known, not new findings)

These are real structural concerns with known gaps already filed in `references/cascade-catalog.md`:

- `_FLOOR_INTERNAL_TOKEN` is convention-via-underscore-prefix → **CASCADE-010** (FloorPassedProof witness-token strengthening; v0.1 keeps the underscore pattern, v1.0 adds closure-capture or hash-binding)
- Cache disclosure was structural-by-presence, not content → **CASCADE-020** (cache disclosure content spec; resolution in Phase 5)
- Cluster bootstrap "structurally committed but not implemented in v0.1" → CASCADE entry "Cluster bootstrap implementation" (deferred to v0.2; v0.1 declares the structure with i.i.d. fallback + explicit disclosure)

These are tracked, not gaps in the audit.

### Wording cleanup applied by this audit

| File:line | Original | Reframed |
|---|---|---|
| `doctrine.md:101` | "baseline-required-for-Ship structural rule" | "baseline-required-for-Ship policy default" — `DecisionPolicy.require_baseline=True` is configurable; the default refuses Ship without baseline but it's not structural |

## Enforcement table — current state after Phase 0.4

The `enforcement.md` table now contains **14 rows** (10 baseline + 3 added in Phase A.3 for cardinal #10 + 1 added in Phase 0.4 for paired-delta).

Every row:
1. ✅ Pairs a structural claim with a specific enforcement mechanism (type-level / pre-write hook / property test / schema validation).
2. ✅ Mechanism is implementable with v0.1 tooling (mypy strict, Pydantic schema validation, fcntl, pytest property tests via Hypothesis).
3. ✅ Has a corresponding test gate in `phases.md` (Phase 1 for type-level, Phase 2 for floor evaluator, Phase 3 for cache lock, Phase 5 for serialization, Phase 7 for renderer assertions, Phase 9 for end-to-end integration).

## Cascade catalog cross-reference

Open cascades that touch enforcement-table rows (will resolve as those test gates land):

| Cascade | Resolution phase |
|---|---|
| Witness-token pattern for Ship | Phase 2 (decision pipeline) |
| Sensitive[T] redaction default | Phase 1 (types) + Phase 4 (adapters) + Phase 5 (serialization) |
| Determinism opt-in default | Phase 5 (serialization) |
| Two-affirmation forensic profile | Phase 8 (CLI/config) |
| Public-vs-internal model split | Phase 1 starts; Phase 5 completes |
| Cohort-systemic detection rule | Phase 2 (aggregation logic) |
| Floor stale-window justification | Phase 3 (cache) |
| Cache disclosure content spec | Phase 5 (serialization) + Phase 7 (renderer) |
| Audit log for .unwrap() reasons | Phase 1 (types) + Phase 5 (serialization) |
| Methodology disclosure required | Phase 1 (types) + Phase 5 (serialization) + Phase 7 (renderer) |
| Reliability/validity/calibration/bias disclosed-as-unmeasured | Phase 1 (types) + Phase 7 (renderer) |
| Cluster bootstrap conditional on real cluster keys | Phase 1 (types) + Phase 4 (adapters) |
| Causal-claim scope enforced | Phase 1 (types) + Phase 7 (renderer) |
| Paired-delta as atomic unit | Phase 1 (types — `whatifd/types/statistical.py`) + Phase 2 (decision pipeline — bootstrap on deltas) |
| Predeclared cohort-level primary endpoints | Phase 2 (decision pipeline — `primary_endpoint_guard`) |
| Finding code registry | Phase 2 (decision pipeline) |
| CI availability moved from floor to policy | Phase 2 (decision pipeline) |
| Cohort propagation throughout | Phase 1 (types) + Phase 2 (decision pipeline) |
| CLI cache subcommands for v0.1 (rebuild, unlock, verify) | Phase 8 (CLI) |
| CLI `whatifd diff` for v0.1 | Phase 8 (CLI) + Phase 7 (renderer) |
| Per-trace evidence schema | Phase 1 (types) + Phase 5 (serialization) + Phase 7 (renderer) |
| CI unavailability reason on CohortResult | Phase 1 (types) + Phase 2 (decision pipeline) + Phase 7 (renderer) |
| Floor table rendering — passing rules need to be enumerable | Phase 1 (types — `TrustFloor.rule_names()`) + Phase 7 (renderer) |
| Multi-cause fix-suggestion templating | Phase 2 (decision pipeline) + Phase 7 (renderer) |
| Compact-form anchor semantics | Phase 7 (renderer) |
| Profile disclosure in rendered Markdown | Phase 7 (renderer) |
| Dashboard SKILL_DIR resolution | Out-of-band (Layer 4 dashboard polish) |

All open cascades are accounted for in `phases.md`. No orphan cascades.

## Phase 0 gate status

| Phase 0 sub-item | Status |
|---|---|
| 0.1 Walkthrough scenarios (six rendered Markdown) | ✅ committed (`f0d5bed`); methodology blocks added (`3bde7b2`) |
| 0.2 Conceptual model document (`docs/concepts.md`) | ✅ committed (`3bde7b2`) |
| 0.3 Audience-distribution decision | ✅ recorded in `V0_1_DECISION_RECORD.md` addendum 2026-05-05; ship `failure_rescue` only, ROADMAP `regression_check` for v0.2 |
| 0.4 Enforcement audit | ✅ this document; two findings resolved in-line |
| Cascade catalog has zero open structural-without-mechanism items | ✅ all open cascades have mechanisms in `enforcement.md` or are deferred with rationale |

**Phase 0 gate: GREEN.** Phase 1 unblocked.

## What unblocks next

Phase 1 (type model): smallest possible code start is `src/whatifd/types/primitives.py` with `DecimalString` and `JsonPrimitive` types. After Phase 1 tests are green, Phase 2 (decision pipeline) begins.

The `methodology` field on `ReportV01` (cardinal #10) will land in Phase 5 (public report model). The `cohort: str` schema flexibility (per Phase 0.3 decision) is preserved by typing `cohort` as `str` rather than `Literal["failure", "baseline"]`, with v0.1 runtime accepting only `"failure"` and `"baseline"` values.
