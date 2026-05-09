# whatifd verdict: Ship

**Failures (20):**   improved 14   unchanged 4   regressed 2   median Δ +0.31  CI [+0.18, +0.44]
**Baseline (20):**   improved 3    unchanged 16  regressed 1   median Δ +0.02  CI [-0.01, +0.05]

All floor rules passed. All policy rules passed.
Replay validity: 40/40 traces. Cache: 38 hits, 2 misses.

**Top improvement:** trace `t_4a91f` — agent now correctly handles ambiguous date input
**Top regression:** trace `t_8c33b` — slight wordiness increase in greeting

## Methodology
- Unit: paired trace delta · Bootstrap: paired percentile, B=5000, seed=42
- Primary metric: faithfulness · Endpoints: failure improvement + baseline non-regression
- Cluster: conversation_id · Multiplicity: none · Per-trace evidence: descriptive
- Judge: claude-haiku-4-5 · Cache: enabled · Practical delta: 0.05 (policy)
- Reliability/validity/calibration/bias: not measured · Causal scope: associated under cached-tool replay

[Manifest →](manifest.json)
