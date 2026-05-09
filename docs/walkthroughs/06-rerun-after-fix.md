# whatifd diff: 2026-05-03-prompt-v3 → 2026-05-04-prompt-v4

**Verdict change:** Don't Ship → Ship

## Cohort comparison

| Cohort | Metric | v3 | v4 | Change |
|--------|--------|----|----|--------|
| failure | improved | 14 | 14 | unchanged |
| failure | regressed | 3 | 2 | -1 |
| baseline | improved | 1 | 3 | +2 |
| baseline | regressed | 6 | 1 | **-5** |
| baseline | median Δ | -0.18 | +0.02 | +0.20 |

## Findings change

**Resolved findings (in v3, gone in v4):**
- `baseline_regression_above_threshold` — baseline regression rate dropped from 30% to 5%.

**New findings (in v4, not in v3):**
(none)

## Trace-level differences

5 baseline traces that regressed in v3 but not in v4:
- `t_492af` (was Δ -0.31, now Δ +0.04)
- `t_771fe` (was Δ -0.28, now Δ +0.02)
- `t_88c40` (was Δ -0.24, now Δ -0.01)
- `t_a1234` (was Δ -0.21, now Δ +0.05)
- `t_b5567` (was Δ -0.18, now Δ +0.03)

The fix appears to have specifically addressed the over-refusal pattern identified
in v3's evidence section.

## Methodology

**Unchanged across runs:** unit of analysis (paired trace delta), primary metric (faithfulness), bootstrap (paired percentile, B=5000, seed=42), cluster handling (conversation_id), multiplicity (none), per-trace evidence framing (descriptive), judge (claude-haiku-4-5), practical delta threshold (0.05), causal scope (associated under cached-tool replay).

**Differences:**
- Cache state: v3 had 39 hits / 1 miss; v4 has 40 hits / 0 misses (the change does not invalidate cached scores).
- Reliability/validity/calibration/bias: still not measured in either run.

A diff between two runs is only meaningful when methodology is identical or its differences are disclosed. The verdict change (Don't Ship → Ship) is attributable to the prompt change because the methodology held constant.
