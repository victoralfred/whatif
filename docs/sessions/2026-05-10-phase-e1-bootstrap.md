---
session_id: 2026-05-10-phase-e1-bootstrap
started_at: 2026-05-10T00:00:00Z
---

## Session start

**User request:** Phase E of the v0.2 roadmap — statistical layer upgrade. Real cluster bootstrap (replaces i.i.d./empirical bootstrap; `bootstrap.method` stops being `"unavailable"`), Holm correction, observed-MDE warnings.

Decision at scope time: split into Phase E.1 (algorithm + tests, this PR) and Phase E.2 (pipeline switch + disclosure flip + walkthrough regeneration, follow-up). Splitting keeps each PR independently reviewable; bundling would touch ~125 test references for review.

**Phase plan position:** Phase E of v0.2-roadmap.md. Phase A, B, C (+ #84 completion), D shipped.

## Session end

**Artifacts produced:**
- `src/whatifd/statistical/__init__.py` (new) — public surface (`BootstrapResult`, `paired_percentile_bootstrap`).
- `src/whatifd/statistical/bootstrap.py` (new) — algorithm + dataclass. Pure-Python, seed-required, local `random.Random`.
- `tests/unit/whatifd/statistical/__init__.py` (new, empty).
- `tests/unit/whatifd/statistical/test_bootstrap.py` (new) — 19 tests across happy-path, determinism, structural errors, custom configuration, and Hypothesis property tests.
- `CHANGELOG.md`: Phase E.1 section under [Unreleased].
- `.claude/skills/whatifd-design/references/cascade-catalog.md`: Phase E.1 resolved entry with explicit Phase E.2 follow-up scope.
- `docs/sessions/2026-05-10-phase-e1-bootstrap.md`: this file.

**Cascade catalog items:**
- Resolved: "Phase E.1 — paired-percentile bootstrap algorithm + property tests" (2026-05-10).

**Gaps surfaced:**
- Phase E.2 must flip the pipeline-side `_cohort_result_from_bucket` to use `paired_percentile_bootstrap`, update the CLI's `MethodologyDisclosure` construction to declare `bootstrap.method = "paired_percentile_bootstrap"`, and regenerate the six committed walkthrough golden fixtures whose methodology blocks currently encode `"unavailable"`. The cascade-catalog entry pins this as the explicit follow-up.
- Holm correction for multiple primary endpoints + observed-MDE power warnings + pairwise judging are listed in the v0.2 roadmap under Phase E. Each is independently doctrinally valuable; whichever lands next probably gets its own PR (Phase E.3, E.4, ...).

**Doctrine moments:**
- Considered shipping algorithm + pipeline switch + walkthrough regeneration in one PR. Declined: the bootstrap-algorithm-correctness review and the walkthrough-fixture-regen review are two separable cognitive surfaces. Bundling makes both reviews worse.
- Considered defaulting `seed` to a fixed constant. Declined: seed-required is the cardinal-#4 contract. A caller who genuinely doesn't care about reproducibility can pass `seed=0`; that's an explicit choice, not a silent default.
- Considered using `numpy.random.choice` for vectorized resampling. Declined per cardinal #9 (orchestration not compute). Cascade-catalog entry notes the NumPy variant as a v0.3 optimization gated on profile data.

**Notes for the next session:**
- Phase E.2 is the natural next step: pipeline switch + disclosure flip + walkthrough regen. ~125 test references will likely need touching; the diff size is the point of the split.
- After E.2 stabilizes, Phase E.3 candidates: Holm correction, observed-MDE power warnings, pairwise judging. Each independently doctrinally valuable.
