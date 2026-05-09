# whatifd verdict: Don't Ship

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

## Methodology

- **Unit of analysis:** paired trace delta
- **Primary metric:** faithfulness · **Cohorts:** failure, baseline
- **Primary endpoints:** failure improvement, baseline non-regression
- **Bootstrap:** paired percentile, B=5000, seed=42
- **Cluster handling:** conversation_id cluster bootstrap
- **Multiplicity:** none; one primary metric per cohort
- **Per-trace evidence:** descriptive, not inferential. *No per-trace statistical significance is claimed.*
- **Judge:** claude-haiku-4-5 · **Scorer cache:** enabled (39 hits / 1 miss)
- **Practical delta threshold:** 0.05 (source: policy)
- **Reliability:** not measured · **Validity / calibration:** not measured · **Bias audit:** not measured
- **Causal scope:** associated regression under cached-tool replay (NOT "caused production regression")
