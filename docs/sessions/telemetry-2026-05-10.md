---
session_id: telemetry-2026-05-10
type: milestone-telemetry
covers: Phase J — determinism widening (PR #95, merged 30512d9)
---

# Telemetry — 2026-05-10 (Phase J merge)

Phase J was the last structural-correctness phase before v0.2.0 release packaging. It widened cardinal #4 from top-level-only to per-field opt-in, with cross-platform CI byte-equality enforcement. Two doctrine-bot iterations; merged at iter 2 of 4 cap.

## Went well

- **Pre-PR design record discipline.** The user pushed back on my initial Phase J description ("confirm this was discussed in the plan") — caught that I was inventing scope from a 2-sentence roadmap entry. Writing `2026-05-10-phase-j-design-record.md` *before* code surfaced the four design choices (dataclass attribute vs `Annotated[]`, schema-generator descent placement, extractor descent shape, CI matrix shape) for explicit user review. Each implementation decision traced back to a written alternative-considered. Worth repeating for any future phase whose roadmap entry is shorter than the implementation.

- **Three-layer structural enforcement.** Dataclass `_DETERMINISTIC_FIELDS` ClassVar → schema generator descent → extractor descent. Convention-only deterministic claims (the pre-Phase-J docstring on `RunManifest`) now break CI if violated. The `test_runtime_subfield_annotations_match_dataclass_optin` drift test catches the case where one of the three layers is updated without the other two.

- **Held the line on Cardinal #1 vs typed-exception push.** Doctrine bot iter-2 wanted `SchemaMissingPhaseJAnnotationsError` raised. Declined: a typed `DeterministicSubsetWarning` class with structured fallback IS the failure-as-data shape. Raising would force every caller into try/except for a path whose correct fallback is exactly what we already do. The user's standing rule ("no workarounds, no pushback without honest reason") cut both directions — declined with rationale, didn't capitulate.

- **Empirical disagreement on bot's CI-version claim.** The bot insisted `actions/checkout@v6` etc. don't exist; declined with grep evidence from `main`'s `ci.yml`. Cross-platform CI ran green on the merged commit, vindicating the call.

## Went wrong

- **Iter-1 commit silently failed.** First `git commit && git push` chain showed "Everything up-to-date" because pre-commit hooks (ruff SIM117 on nested `with`) blocked the commit and the chained `git push` ran against the unchanged tree. Wasted a doctrine-bot review cycle on the pre-iter-1 state. Discipline note: when committing through pre-commit hooks, verify with `git log --oneline -1` before assuming the push happened.

- **Schema dual-load slipped through iter-1 self-review.** `_runtime_deterministic_subfields` opened the schema file a second time independently of `_schema_properties()`'s cache. The bot caught it; iter-2 consolidated into a single `_schema_document()` cache. Should have noticed at write time — the function literally reconstructed the path the cache already had.

- **Generator unit test was missing in iter-1.** The schema-drift test catches generator regressions only after regeneration. A direct unit test for `_dataclass_to_schema` opt-in vs non-opt-in paths was a one-screen addition I skipped. Added in iter-2 when the bot flagged it.

## Risks carried forward

- **Generic descent on `_DETERMINISTIC_FIELDS` deferred as YAGNI.** The extractor hardcodes the `runtime` field name. The moment a second dataclass opts in, the hardcoded path silently skips it — `test_runtime_subfield_annotations_match_dataclass_optin` covers `RunManifest` only. Need a parametrized version + extractor walker the moment a second consumer arrives.

- **Cross-platform matrix is single-fixture.** `_emit_determinism_artifact.py` runs `scenario_clean_ship` only. A platform-specific bug that surfaces only in the regression-check or insufficient-sample fixtures wouldn't be caught. Acceptable for v0.2 (the four Phase 9A fixtures are structurally similar at the determinism-subset level), but a future phase could matrix the fixtures themselves.

- **`environment.dependencies` ordering.** Out of scope for Phase J. Pip-resolution-order is build-host-dependent; if a future tool starts consuming `RunManifest.environment` for cross-run comparison, the ordering nondeterminism resurfaces.

## Next

Phase L (release packaging) is the only remaining v0.2.0 critical-path phase. Scope (proposed):

1. **Version bump** across the three packages: `whatifd`, `whatifd-langfuse`, `whatifd-phoenix` from `0.1.x` → `0.2.0`. Coordinate with the version-source pattern fixed in PR #76.
2. **CHANGELOG** finalization — flatten `[Unreleased]` into `[0.2.0]` with all of Phases A–E.2 + I + J, dated 2026-05-10.
3. **README pass** — surface v0.2 additions (regression-check shape, Phoenix adapter, paired-percentile bootstrap, cross-platform determinism guarantee).
4. **Schema URL freeze** — confirm `https://whatifd.codes/schema/report/v0.2.json` resolves to the committed schema file before publishing.
5. **PyPI publication** — three packages, in dependency order. Smoke-test in a clean venv.
6. **Release notes** on the GitHub release page.

Decision needed before Phase L starts: does v0.2.0 ship `whatif diff` (CASCADE-032 from the v0.1 plan) or defer to v0.3? Per memory, the v0.1 plan recommended including; check whether it shipped in any of A–E.2.
