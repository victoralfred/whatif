# whatifd verdict: Inconclusive

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
   to 20+ in `whatifd.config.yaml` to give more headroom.

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

## Methodology

- **Unit of analysis:** paired trace delta
- **Primary metric:** faithfulness · **Cohorts:** failure, baseline
- **Primary endpoints:** failure improvement, baseline non-regression (NOT evaluated; baseline cohort below floor)
- **Bootstrap:** paired percentile, B=5000, seed=42 (applied to failure cohort; *unavailable* for baseline — sample too small)
- **Cluster handling:** conversation_id cluster bootstrap (applied where bootstrap ran)
- **Multiplicity:** none; one primary metric per cohort
- **Per-trace evidence:** descriptive, not inferential. *No per-trace statistical significance is claimed.*
- **Judge:** claude-haiku-4-5 · **Scorer cache:** enabled
- **Practical delta threshold:** 0.05 (source: policy)
- **Reliability:** not measured · **Validity / calibration:** not measured · **Bias audit:** not measured
- **Causal scope:** associated under cached-tool replay
- **Why Inconclusive:** the trust floor is about evidence existence, not evidence quality. Below the floor, no verdict can be rendered. Fix the cohort sample size and rerun.
