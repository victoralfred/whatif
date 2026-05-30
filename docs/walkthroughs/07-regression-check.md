# whatifd verdict: Ship

**All floor rules passed. All policy rules passed.**

## Stats

**Baseline (20):**   improved 2   unchanged 17   regressed 1   median Δ 0.010   CI [-0.020, 0.040]

<a id="replay-validity"></a>
## Replay validity

**baseline:** 20 selected, 20 replayed (100.0%), 20 scored (100.0%).

<a id="fix"></a>
## Suggested next steps

No actionable findings — the verdict is Ship.

## Methodology

- Unit: paired_trace_delta · Primary metric: faithfulness
- Endpoints: baseline_non_regression
- Cohorts: baseline
- Bootstrap: paired_percentile_bootstrap, B=5000, seed=42 · CI level: 0.95
- Cluster: conversation_id · Multiplicity: none
- Per-trace inference: descriptive_only
- Causal scope: associated_under_cached_tool_replay
- Judge: claude-haiku-4-5 · Cache: enabled (38 hits, 2 misses)
- Practical delta: 0.050 (policy)
- Reliability state: reproducibility=yes, reliability=no, validity=no, calibration=no, bias=no

[Manifest →](manifest.json)
