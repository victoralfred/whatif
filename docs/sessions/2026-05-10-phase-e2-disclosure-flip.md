---
session_id: 2026-05-10-phase-e2-disclosure-flip
started_at: 2026-05-10T00:00:00Z
---

## Session start

**User request:** Phase E.2 — pipeline switch (use the Phase E.1 bootstrap algorithm in `_cohort_result_from_bucket`) + `MethodologyDisclosure.bootstrap.method` flip from `"unavailable"` to `"paired_percentile_bootstrap"`. Closes issue #90.

**Phase plan position:** Phase E.2 of v0.2-roadmap.md. Earns v0.2 the right to claim non-`unavailable` methodology disclosure. Doctrine bot has flagged the gap on PRs #82, #86, #88, #89.

## Session end

**Artifacts produced:**
- `src/whatifd/pipeline.py`: `_cohort_result_from_bucket` calls `paired_percentile_bootstrap` (with `BOOTSTRAP_SEED` / `BOOTSTRAP_RESAMPLES` / `BOOTSTRAP_CI_LEVEL` imported from `whatifd.statistical`) and `to_decimal_string` instead of `statistics.quantiles`. `import statistics` dropped — no other call site needs it.
- `src/whatifd/cli.py`: `MethodologyDisclosure.bootstrap` declares `method="paired_percentile_bootstrap"` and consumes `BOOTSTRAP_RESAMPLES` / `BOOTSTRAP_SEED` / `BOOTSTRAP_CI_LEVEL_DECIMAL` directly from `whatifd.statistical` so the disclosure is structurally coupled to the pipeline's actual bootstrap call. No duplicated literals.
- `docs/getting-started.md`: programmatic example flipped + v0.1 "Known limitations" entry marked resolved.
- `.claude/skills/whatifd-design/references/cascade-catalog.md`: Phase E.2 resolved entry.
- `CHANGELOG.md`: Phase E.2 section under [Unreleased].
- `docs/sessions/2026-05-10-phase-e2-disclosure-flip.md`: this file.

**Cascade catalog items:**
- Resolved: "Phase E.2 — pipeline switch + MethodologyDisclosure flip" (2026-05-10).

**Gaps surfaced:**
- The bot's earlier "~125 test references" estimate for the disclosure flip was over-counting. The actual breakage was zero — most `"unavailable"` references in the test surface are testing the type's literal-value support (which still works), not asserting that the production happy path emits it. Walkthrough fixtures #4 and #5 still correctly use `"unavailable"` for genuinely-unavailable cases (sample too small, cache locked); flipping the happy path didn't disturb them.

**Doctrine moments:**
- Considered moving `_BOOTSTRAP_SEED` to a `RunManifest` field or a dedicated stats-layer config. Declined for v0.2: a constant is the simplest reproducibility guarantee, and the cardinal #4 determinism contract is already satisfied. Future surface may parameterize.
- Considered also flipping walkthrough fixtures #4 and #5 to use the new method. Declined: those fixtures depict genuinely-unavailable cases (sample-too-small, cache-locked) where `"unavailable"` is the correct disclosure. The flip is for the happy path only.

**Notes for the next session:**
- Phase E.3 — Holm correction for multiple primary endpoints — is the next step in the statistical-layer chain. Not yet filed.
- Phase E.4 (observed-MDE) and E.5 (pairwise judging) follow.
- For v0.2.0 release: still need Phase I (GitHub Action), Phase J (determinism widening), Phase L (release packaging).
