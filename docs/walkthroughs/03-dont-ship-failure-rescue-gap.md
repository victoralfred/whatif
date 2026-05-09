# whatifd verdict: Don't Ship

**Reason:** the failure cohort improved on only 2/20 traces (10%), below the 50% threshold.
The proposed change does not appear to fix the targeted failures.

Baseline cohort is stable.

[Suggested next steps ↓](#fix) · [Full report ↓](#stats) · [Manifest →](manifest.json)

---

## Stats

**Failures (20):**   improved 2    unchanged 16  regressed 2   median Δ +0.02  CI [-0.04, +0.08]
**Baseline (20):**   improved 1    unchanged 18  regressed 1   median Δ +0.00  CI [-0.02, +0.02]

## Replay validity

Replayed: 20/20 failures, 20/20 baseline.
Cache: 38 hits, 2 misses.

## Suggested next steps

The change does not improve the failure cohort enough to ship. Common causes:

- The change addresses a different failure mode than the failures cohort represents.
  Re-examine the failure traces to identify the actual pattern.
- The scorer rubric ("faithfulness") may not reward the kind of improvement the change targets.
  Try `--score inspect_ai:helpfulness` if the change targets response quality.
- The change is too conservative. Iterate on the prompt and rerun.

## Evidence

### Top improvements (2)

**`t_a1102`** — Δ +0.18
> [...judge rationale...]

**`t_a1187`** — Δ +0.11
> [...judge rationale...]

### Failures that did not improve (sample of 5 of 16)

**`t_a1023`** — Δ +0.02 (essentially unchanged)
> Original failure mode: incorrect handling of multi-turn context.
> Replayed: same failure mode persists.

**`t_a1031`** — Δ -0.01
> [...similar shape...]

[See full trace context in Langfuse →](https://langfuse.example/...)

## Methodology

- **Unit of analysis:** paired trace delta
- **Primary metric:** faithfulness · **Cohorts:** failure, baseline
- **Primary endpoints:** failure improvement, baseline non-regression
- **Bootstrap:** paired percentile, B=5000, seed=42
- **Cluster handling:** conversation_id cluster bootstrap
- **Multiplicity:** none; one primary metric per cohort
- **Per-trace evidence:** descriptive, not inferential. *No per-trace statistical significance is claimed.*
- **Judge:** claude-haiku-4-5 · **Scorer cache:** enabled (38 hits / 2 misses)
- **Practical delta threshold:** 0.05 (source: policy)
- **Reliability:** not measured · **Validity / calibration:** not measured · **Bias audit:** not measured
- **Causal scope:** associated under cached-tool replay (the failure cohort did not improve under this replay; the live behavior may differ)
