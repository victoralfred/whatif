# Concepts

This page is the conceptual model behind whatifd. Two pages plus glossary. If you read nothing else about the project, read this.

## 1. Product: defensible verdicts

> **whatifd's product is the verdict's defensibility.**

The verdict is one of `Ship`, `Don't Ship`, or `Inconclusive`. The product is not the verdict itself — it's the property that the verdict is defensible: a reviewer can read the report, follow the reasoning, see the evidence, identify the assumptions, and either trust the verdict or know exactly which assumption to challenge. Every design decision in whatifd is judged against whether it makes the verdict more defensible. Features that increase defensibility belong early. Features that don't belong nowhere.

A corollary that resolves day-to-day disputes:

> **If a design flaw would mislead a reviewer, it is a correctness bug. If it only slows or inconveniences the reviewer, it is an optimization or UX issue.**

## 2. Non-claims

Stating non-claims protects the doctrine. whatifd is:

- **Not a substitute for production monitoring.** Production drift is a different problem.
- **Not a benchmark suite.** It evaluates *your* change against *your* traces; it does not produce comparable scores across projects.
- **Not a load test.** Replay is for behavior comparison, not for performance evaluation.
- **Not a causal estimator beyond replay association.** Cached-tool replay is a known biased estimator of true production effect. whatifd claims "associated regression under cached-tool replay," not "caused production regression."
- **Not a judge-quality validator.** Scorer caching addresses reproducibility, not validity. Whether the judge measures the right thing is the user's calibration concern, disclosed via `MethodologyDisclosure.judge_state`.

## 3. The three verdicts

Every run produces exactly one of:

- **`Ship`** — the change passed every floor rule and every above-floor policy guard. The structural witness token `FloorPassedProof` is required to construct a `Ship`; only `evaluate_floor()` produces one. The `Ship` verdict carries observational findings (information-severity), but no `blocks_ship` or `blocks_all` finding can coexist with it — `compute_verdict` would have downgraded the verdict otherwise.
- **`Don't Ship`** — at least one above-floor guard emitted a `blocks_ship` finding (e.g., baseline regression rate above threshold, failure improvement rate below threshold, practical-delta below epsilon). The floor passed; the change is structurally evaluable but doesn't meet policy.
- **`Inconclusive`** — either the floor failed (insufficient evidence to evaluate any verdict) or a `blocks_all` finding fired (operational catastrophe such as required-cohort CI uncomputable). The verdict is not a "soft no" — it is a refusal to render a verdict at all. Inconclusive must always include a registered fix suggestion (per cardinal #8).

The order of precedence is fixed: `blocks_all` > `blocks_ship` > `info`. Floor failures take absolute priority — no policy configuration can produce `Ship` from a below-floor run.

## 4. Trust floor vs decision policy

whatifd separates two concerns that are conflated in most CI tools.

- **Trust floor** — about *evidence existence*. Below the floor, there is insufficient evidence to evaluate any verdict. Floor failures produce `Inconclusive`. The floor cannot be overridden by configuration. Encoded structurally via the `FloorPassedProof` witness token: `Ship` requires a proof that only `evaluate_floor()` produces. Floor rules: minimum selected/replayed/scored traces per required cohort, minimum replay-validity ratio, structural CI computability (`ci_computable`). The floor is *versioned* and sticky in the manifest — existing runs validate against the floor version they were built against; v0.2 may bump to floor v2. Sticky-manifest scope: at write time, `evaluate_floor()` records the active floor version into the manifest; at report-read time (the serialization layer that loads `ReportV01`, plus the `whatifd report-migrate` command), the reader validates that the recorded version is recognized and refuses to render verdicts from manifests with unknown floor versions. The guarantee is end-to-end, not just write-side.
- **Decision policy** — about *evidence quality*. Configurable thresholds that gate `Ship`/`Don't Ship` decisions ABOVE the floor. Policy can be stricter than floor, never weaker. Stricter is enforced by the guard chain at evaluation time; weaker is prevented because the floor is structural and policy never gets asked about below-floor cases. Examples: `max_baseline_regression_ratio`, `min_failure_improvement_ratio`, `practical_delta_epsilon`, `max_ci_width` (the lever for accepting wider but computable CIs).

Why the split matters: a user who configures `min_replay_validity: 0.1` cannot produce a junk-evidence Ship verdict because the floor structurally refuses below 0.50. Per the closing decision (`V0_1_DECISION_RECORD.md` §6), there is no `--accept-no-ci` flag — CI unavailability stays `blocks_all` and forces Inconclusive; `policy.max_ci_width` is the only lever for accepting wider CIs, and it operates on the policy side of the boundary.

## 5. Failure-as-data

> **whatifd does not fail silently. If a trace cannot be replayed, scored, or trusted, the report says so. If enough traces cannot be trusted, the verdict must downgrade to Inconclusive.**

Two layered types:

- **`FailureRecord`** — the operational fact. One per event (cache miss, runner timeout, scorer error, schema mismatch). Adapter emits trace-scope; core emits cohort-scope and run-scope after aggregation. No `verdict_impact` field — that's a policy projection.
- **`DecisionFinding`** — the policy conclusion. One per conclusion. Aggregates across `FailureRecord`s where applicable. Carries severity (`info | degrades_trust | blocks_ship | blocks_all`).

The bright-line rule: `FailureRecord` is what happened, `DecisionFinding` is what it means. Aggregation happens in the finding, not by mutating records. The `≥50%` cohort-systemic rule emits a cohort-scope record that links to the per-trace records it summarizes via `aggregated_into`.

## 6. Evidence and audit bundle

Every run writes an artifact bundle alongside the report. The bundle's content is controlled by a `storage_profile`:

- **`minimal`** — `report.json`, `report.md`, `manifest.json` only.
- **`review`** — adds `cache-summary.json`, `trace-selection.json`. Default for interactive use.
- **`audit`** — adds `config.resolved.yaml`, `dependencies.json`. Default in CI.
- **`forensic`** — adds raw evidence (full prompts, full outputs, full judge rationale). Two-affirmation opt-in only: requires both a config block AND a CLI flag; both disclosed in the manifest.

The report renders in three formats from the same JSON:

1. **1-line CI status** (~80 chars) — what GitHub Actions shows in the check display.
2. **30-line summary** — the top of the Markdown report; what the PR reviewer with 3 minutes reads.
3. **Full report** — Markdown with five sections (Verdict, Stats, Replay validity, Baseline integrity, Evidence) plus a Methodology block. What the engineer with 30 minutes reads.

The Methodology block is required in every report. It discloses bootstrap method, multiplicity stance, judge state, effect-size policy, per-trace-inference scope, and causal-claim scope. A reviewer who reads only the methodology can answer: what was the unit of analysis? what primary endpoints drove the verdict? has the judge been validated against ground truth? what magnitude threshold was used? what's the maximum claim the report is allowed to make?

## 7. Privacy and redaction

User content from adapters is wrapped in `Sensitive[T]` at the boundary. Three layers of defense:

1. **Type-level (mypy strict)** — adapters return `Sensitive[str]`; core types accept `Sensitive[str]` for sensitive fields.
2. **Pre-serialization graph walk** — `assert_no_unredacted_sensitive(report)` walks the full object graph before any artifact is written; raises on any `Sensitive` instance.
3. **Encoder fallback** — `WhatifJSONEncoder.default()` raises `UnredactedSensitiveError` if a `Sensitive` reaches it.

Audit becomes grep-able: instead of "audit every serialization path," audit becomes "grep for `.unwrap(`." Every unwrap is a reviewable call site with a logged reason that lands in `manifest.runtime.sensitive_unwraps`.

## 8. Examples of misleading outputs whatifd must never produce

These are the failure modes the architecture exists to prevent. Each is a correctness bug, not a UX issue:

- **Verdict `Ship` with 20% replay validity.** The structural floor refuses below 0.50; configuration cannot lower it.
- **Missing baseline hidden in a footnote.** Baseline is required for `Ship`; absence forces `Inconclusive` or `Don't Ship`.
- **Scorer cache disabled in CI without disclosure.** `cache_summary` is a required field on `ReportV01`; schema validation refuses reports without it.
- **Raw production traces included by default.** Default profile is `review` (no full prompts); `forensic` requires two-affirmation opt-in disclosed in the manifest.
- **Per-trace p-values without multiplicity correction.** Per-trace evidence is descriptive only — `MethodologyDisclosure.per_trace_inference: Literal["descriptive_only"]` is sealed at the type level.
- **"Caused production regression" claim.** `MethodologyDisclosure.causal_claim_scope: Literal["associated_under_cached_tool_replay"]` is sealed for v0.1.
- **A confidence interval emitted without method/sample-unit/seed disclosure.** Schema validation requires `BootstrapMethodDisclosure` to be populated.
- **A verdict downgrade silently buried.** Severe trust failures must affect the verdict, not just appear in a footnote (per disclosure-not-sufficient doctrine).
- **A `Ship` verdict with structurally uncomputable CI on a required cohort.** `ci_computable=False` on a required cohort emits `blocks_all`, forcing Inconclusive. There is no escape-hatch flag.

The architecture's trust-first cost is real: slower than a naive implementation, heavier on type wrappers and graph walks, more cautious about what the verdict is allowed to claim. The cost buys the only thing that matters — a verdict an engineer is willing to stake their merge button on.

---

## Glossary

- **Verdict** — `Ship | Don't Ship | Inconclusive`. The terminal output of a run.
- **Trust** — the property that the report's claims match its evidence. Maintained structurally, not by convention.
- **Baseline** — the cohort of representative production traces used to detect silent regression. Required for `Ship`.
- **Cohort** — a labeled subset of traces. v0.1 supports `failure` and `baseline`. Cohort-level primary endpoints are the unit of statistical inference.
- **Primary endpoint** — a predeclared cohort-level claim that drives the verdict (e.g., "failure cohort improvement rate ≥ 50%"). Per cardinal rule #10, per-trace observations are descriptive, not inferential.
- **Condition** — an above-floor concern that can be configured but not weakened below the floor (e.g., regression threshold, CI width).
- **Failure** (`FailureRecord`) — an operational event: something went wrong. Layer-pure; no verdict implications baked in.
- **Finding** (`DecisionFinding`) — a policy conclusion. Carries severity. May reference one or more failures.
- **Floor** — the structural minimum below which no verdict can be rendered. Encoded via `FloorPassedProof` witness token.
- **Policy** — user-configurable rules that layer on top of the floor. Stricter than floor, never weaker.
- **`ci_computable`** — bootstrap CI was successfully computed. Structural concern; floor-equivalent severity (`blocks_all`).
- **`ci_meaningful`** — the computed CI is narrow enough to be actionable (width below `policy.max_ci_width`). Policy-quality concern; deferred Phase 3 wiring.
- **Manifest** (`RunManifest`) — the audit anchor. Captures everything needed to reproduce a run: floor version, policy, environment, redaction state, sensitive-unwrap log.
- **Audit** — the property that every claim in the report is traceable to its evidence. Grep-able for `Sensitive[T]` unwraps; signed by `cache_summary` content; disclosed via `MethodologyDisclosure`.
- **Defensible** — a reviewer can defend the verdict from the evidence in the report.
- **Actionable** — an engineer can act on the verdict in five minutes. Inconclusive verdicts must include a registered fix suggestion.

## Where to go from here

- The runner contract: [runner-contract.md](runner-contract.md) (Phase 10)
- The walkthrough scenarios that pressure-tested this design: [walkthroughs/README.md](walkthroughs/README.md)
- The full design rationale: [DESIGN.md](../DESIGN.md)
- The long-term destination: [path-z.md](path-z.md) (Phase 10) — describes the tool doctrine separately from v0.1 doctrine.
