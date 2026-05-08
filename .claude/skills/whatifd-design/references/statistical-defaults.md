# Statistical Defaults for v0.1

These defaults operationalize cardinal rule #10. They are intentionally modest. Each can be overridden by `whatif.config.yaml`, but the defaults are what ships when the user doesn't configure.

The frame is fixed: **endpoint discipline first, statistical machinery second.**

## Score scale

Default v0.1 scorer output is treated as continuous on `[0, 1]`.

Other score types are deferred to v0.2:

- ordinal (e.g., {-2, -1, 0, +1, +2})
- categorical (e.g., refusal/help/escalate)
- binary pass/fail
- pairwise preference (A wins, B wins, tie)

If a scorer adapter produces a non-continuous score, the adapter must convert to `[0, 1]` for v0.1 (e.g., binary pass/fail → 0.0/1.0; ordinal → linear scaling). Adapter authors are responsible for documenting the conversion in `JudgeMethodDisclosure`.

## Judge mode

Default v0.1 judge mode is **independent scoring per output** — the judge scores the original output and the replayed output separately, on the same rubric. The delta is computed by whatif core, not by the judge.

Pairwise judging (the judge directly compares two outputs) is deferred. It is more sensitive but introduces position bias, which requires order randomization or dual-order judging — both of which double scoring cost. v0.2 may add it as opt-in.

## Primary metric count

v0.1 supports **one primary quality metric per run**.

The primary metric is configured via `scorer.rubric` in `whatif.config.yaml`. v0.1 default: `faithfulness` (per Inspect AI's standard rubric). Other primary metrics (e.g., helpfulness, accuracy) are valid choices but only one can be primary in v0.1.

Multiple primary metrics with Holm correction is deferred to v0.2. Until then, secondary metrics may be reported descriptively but cannot drive verdicts.

## Primary endpoints

v0.1 default endpoints (one per cohort):

- **failure cohort**: `improvement_above_threshold` — `P(delta > epsilon)` exceeds configured threshold
- **baseline cohort**: `non_regression_below_threshold` — `P(delta < -epsilon)` stays below configured threshold

Both must pass for Ship. Either failing produces Don't Ship.

## Practical-delta threshold

Default `epsilon = 0.05` on the `[0, 1]` scale.

This is a **policy default**, not an empirically calibrated value. The methodology block records `practical_delta_source: "policy"` to make this explicit. Until judge noise floor is empirically measured (v0.3+), `epsilon` cannot be claimed as calibrated against measurement noise.

If `epsilon` is configured below the judge's noise floor (when calibration data exists), the report warns. Without calibration data, the report neither confirms nor refutes the threshold's appropriateness.

## Bootstrap method

Default: **paired percentile bootstrap.**

- Method: `paired_percentile_bootstrap`
- Resamples: B = 5000
- Seed: 42 (overridable; recorded in manifest)
- Sample unit: `paired_trace_delta`
- CI level: 0.95

If the cohort meets the trust floor for selected, replayed, and scored traces but the bootstrap cannot be computed (e.g., zero variance, insufficient distinct values), the methodology block records `method: "unavailable"` with `unavailable_reason`, and the cohort cannot drive a Ship verdict.

## Cluster handling

Default: **`auto`** with `fallback_behavior: warn`.

Resolution order (most to least granular):

1. `conversation_id`
2. `session_id`
3. `user_id`
4. None (i.i.d. assumption)

The most granular available cluster key is selected. If none is available, the report discloses:

> Cluster handling: none. CIs assume trace-level independence and may be optimistic if traces are correlated.

For high-trust CI environments, set `clustering.fallback_behavior: refuse` to block Ship when no cluster key is available.

The cluster-bootstrap *implementation* is deferred to v0.2; v0.1 declares the structural commitment but uses i.i.d. bootstrap with explicit disclosure.

## Baseline sampling

Default: **seeded random sampling** within the baseline cohort filter.

- Sampling: random
- Seed: 42 (overridable; recorded in manifest)
- Selection limit: configured via `selection.baseline_cohort.limit` (default 20)

Stratified sampling by user-supplied strata keys (e.g., language, request type, account segment) is deferred to v0.2. Embedding-cluster strata are explicitly rejected for confirmatory verdicts in any version (unstable across runs).

## Failure-cohort sampling

Default: **all matching traces up to limit**, no sampling within filter.

The failure cohort is typically defined by an explicit filter (e.g., `tag:incident-2026-04` or `quality_score < 0.3`). Within that filter, v0.1 takes the most recent N up to `selection.failure_cohort.limit` (default 20).

If the failure cohort filter matches more than the limit, the report discloses the truncation and the selection method.

## Underpowered runs

v0.1 blocks **only below the structural trust floor**.

Above the floor, low statistical power produces warnings, not automatic blocking. v0.1 lacks empirical `sigma_delta` data to compute meaningful power; v0.2 can add observed-MDE warnings once realistic experiments accumulate.

The default behavior:

- Below floor: `Inconclusive`, exit code 2.
- Above floor but underpowered (judged by reviewer): warning in report, no automatic block.
- Above floor and well-powered: verdict determined by primary endpoints.

## Judge configuration

v0.1 defaults:

- Judge model: `claude-haiku-4-5` (fast, cheap, sufficient for `faithfulness` rubric)
- Scorer cache: enabled in CI environments, mode=`auto` interactively
- Scorer cache profile: `normalized_result_only` (no full prompts/outputs cached)
- Reliability subset: not measured
- Validity / calibration: not measured
- Bias audit: not measured

The methodology block discloses each of these. Future versions may expand defaults; v0.1's stance is "address reproducibility, disclose unmeasured properties."

## Calibration

Human-labeled calibration sets are **not required** in v0.1.

Reports must not claim judge validity or calibration unless a calibration set is configured and evaluated. The methodology block's `validity_measured` and `calibration_measured` fields default to `false`.

v0.3 supports user-supplied calibration sets and applies isotonic or Platt scaling to judge outputs. Until then, judge confidence values (when provided) are passed through without recalibration.

## Cost reduction

Sequential testing and active trace selection are deferred. v0.1 optimizes for defensibility over cost.

Concretely:

- Replay: every selected trace, no early stopping
- Scoring: every replayed trace, no active selection
- Bootstrap: full B=5000 every run

If cost becomes a barrier to adoption, sequential testing (v0.3) and active selection with confirmatory holdout (v0.3) are the planned interventions. Both require careful design to avoid biasing verdicts.

## What this implies for `whatif.config.yaml`

The minimal v0.1 config that takes all defaults:

```yaml
source:
  adapter: langfuse
  project: my-project

target:
  module: my_agent.replay
  function: run

selection:
  failure_cohort:
    limit: 20
    filter: "your-failure-filter"
  baseline_cohort:
    limit: 20
    sampling: random
    seed: 42

change:
  system_prompt: prompts/v3.txt

scorer:
  adapter: inspect_ai
  rubric: faithfulness
  # All other scorer options take v0.1 defaults
```

This produces a run that:
- Uses paired bootstrap with B=5000 and seed=42
- Treats `faithfulness` as the single primary metric
- Requires baseline non-regression and failure improvement for Ship
- Uses `epsilon = 0.05` as the practical-delta threshold
- Resolves cluster keys automatically from the Langfuse adapter
- Discloses reliability/validity/calibration/bias as unmeasured
- Caches scorer outputs for reproducibility

The methodology block in the resulting report fully describes what statistical claims the verdict is allowed to make. A reviewer who reads the methodology block can answer every question listed in `references/type-model.md` § "What this enables in the report".

## When to override defaults

The defaults are conservative. Override when you have specific reasons:

| Default | Override when |
|---|---|
| `epsilon = 0.05` | Your scoring rubric has a known different noise floor |
| Seed = 42 | You want different randomness; CI repeatability still works because the seed is recorded in manifest |
| Bootstrap B = 5000 | Profile data shows bootstrap is hot; lower to 2000 for speed (acceptable; CI confidence levels still hold) |
| `clustering.fallback_behavior: warn` | Your CI environment requires cluster keys (set to `refuse`) |
| `selection.baseline_cohort.limit: 20` | Sample size analysis suggests larger N needed for adequate power |

Each override is recorded in the manifest. Reviewers can see what was changed from defaults and ask why.
