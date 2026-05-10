---
session_id: 2026-05-10-phase-b-config-score-fn
started_at: 2026-05-10T00:00:00Z
---

## Session start

**User request:** Phase B of the v0.2 roadmap — close the v0.1 setup-failure cliff by making `scorer.adapter: inspect_ai` reachable from `whatifd.config.yaml` (today: programmatic API only).

**Skill files read:**
- `.claude/skills/whatifd-design/SKILL.md` (project guide via CLAUDE.md, prior session)
- (Phase A session covered the doctrine groundwork; Phase B reuses the same boundary placement rules.)

**Cardinal rules cited:**
- #1 (failure-as-data): every config-validation, score-fn-resolution, and adapter-construction failure produces a typed exception, never an unhandled stack trace.
- #6 (boundary discipline): `scorer_loader` is a separate module from `runner_loader` so error messages name the field (`scorer.score_fn` vs `target.runner`) — keeps the cardinal-#6 boundary readable to operators.
- #7 (two-affirmation): unaffected by Phase B; existing CLI tests retargeted from `inspect_ai` (sentinel-failure) to `stub` (sentinel-empty) preserve the cross-surface check coverage.

**Phase plan position (per `v0.2-roadmap.md`):**
- Phase: B — Config-loaded score_fn (closes CLI/Inspect cliff).
- Sub-item: B.1 single PR — `ScorerConfig` extension + `scorer_loader` module + `build_scorer` wiring + tests.
- Prerequisites status: Phase A merged (`d0f7e29`), main clean.

## Session end

**Artifacts produced:**
- `src/whatifd/config.py`: extended `ScorerConfig` with `score_fn`, `judge_provider`, `judge_model_id`, `judge_model_snapshot`, `rubric_id`, `rubric_text`, `scoring_parameters`. Cross-field `model_validator` enforces all five required fields when `adapter='inspect_ai'`.
- `src/whatifd/scorer_loader.py` (new): `load_score_fn(reference: str) -> Callable` with typed `ScorerLoadError`. Mirrors `runner_loader` shape exactly.
- `src/whatifd/adapters/factory.py`: `build_scorer` adapter='inspect_ai' branch now resolves `score_fn` via `scorer_loader` and instantiates `InspectAIScorer` with all config fields.
- Tests: new `tests/unit/whatifd/test_scorer_loader.py` (12 tests covering happy path, structural errors, import failures). Existing `tests/unit/whatifd/test_config.py` and `tests/unit/whatifd/test_cli.py` fixtures retargeted from `inspect_ai` to `stub`. `test_build_scorer_inspect_ai_raises_actionable` retired; replaced by `test_build_scorer_inspect_ai_missing_score_fn_blocked_by_validator` (validator-time) and `test_build_scorer_inspect_ai_with_real_score_fn_returns_inspect_scorer` (happy-path integration).
- `CHANGELOG.md`: Phase B entry under [Unreleased].
- `.claude/skills/whatifd-design/references/cascade-catalog.md`: Resolved cascade entry "Phase B — Scorer score_fn config-loadable; inspect_ai reachable from YAML."
- `docs/sessions/2026-05-10-phase-b-config-score-fn.md`: this file.

**Cascade catalog items:**
- Resolved: "Phase B — Scorer score_fn config-loadable; inspect_ai reachable from YAML" (2026-05-10).

**Gaps surfaced:**
- Docs in `whatifd-docs/` (separate repo) still carry v0.1 caveat admonitions on inspect-ai.md, langfuse.md, workflow.md, first-experiment.md, live-langfuse.md, config.md. Filed as a follow-up: docs PR should land after this code PR merges so the prose reflects published behavior.
- The validator-time enforcement of `inspect_ai` required fields rendered the `score_fn is None` branch in `build_scorer` unreachable. Kept as belt-and-suspenders for a future contributor who bypasses the validator. If that path becomes load-bearing again, the cascade entry documents the design.

**Doctrine moments:**
- Considered sharing a single `_python_ref_loader` helper between `runner_loader` and `scorer_loader`. Declined: error messages name the config field, and threading the field name through every error string adds complexity for no wire-shape benefit. Two near-identical modules with different field-name strings is the right amount of duplication for the cardinal-#6 boundary.
- Considered putting the inspect_ai required-fields check in the factory rather than the validator. Moved it to the validator: failures should surface at config-load time so operators see "your YAML is incomplete" before any adapter machinery starts up. Cardinal #1: structured failure as close to the user input as possible.
- Re-targeted existing test fixtures from `adapter: inspect_ai` (which was a v0.1 sentinel-failure) to `adapter: stub` (sentinel-empty). The behavior the tests pin — "two-affirmation reaches dispatcher → setup-failure exit 2" — is preserved because the stub source's empty trace list also produces a setup-failure outcome. The change is in WHICH layer fails, not THAT it fails.

**Notes for the next session:**
- Phase C is the verdict-policy branch on `experiment_shape`. Walkthrough fixture #7 (regression-check shape) needs to land before Phase C ships.
- Follow-up docs PR in `whatifd-docs/`: drop v0.1 caveat admonitions; replace YAML examples that use `adapter: stub` (with caveat note) with the now-working `adapter: inspect_ai` form.
