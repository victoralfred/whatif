# Concepts

This page is the conceptual model behind whatif. Two pages plus glossary. If you read nothing else about the project, read this.

## 1. Product: defensible verdicts

> **whatif's product is the verdict's defensibility.**

The verdict is one of `Ship`, `Don't Ship`, or `Inconclusive`. The product is not the verdict itself — it's the property that the verdict is defensible: a reviewer can read the report, follow the reasoning, see the evidence, identify the assumptions, and either trust the verdict or know exactly which assumption to challenge. Every design decision in whatif is judged against whether it makes the verdict more defensible. Features that increase defensibility belong early. Features that don't belong nowhere.

A corollary that resolves day-to-day disputes:

> **If a design flaw would mislead a reviewer, it is a correctness bug. If it only slows or inconveniences the reviewer, it is an optimization or UX issue.**

## 2. Non-claims

Stating non-claims protects the doctrine. whatif is:

- **Not a safety certifier.** whatif enforces *your* declared policy. It does not certify the absence of bugs, harms, or regressions outside the dimensions you scored.
- **Not a replacement for human review.** It is input to human review. The report shape exists to make that review fast and grounded, not to replace it.
- **Not a substitute for production monitoring.** Production drift is a different problem.
- **Not a benchmark suite.** It evaluates *your* change against *your* traces; it does not produce comparable scores across projects.
- **Not a load test.** Replay is for behavior comparison, not for performance evaluation.
- **Not a causal estimator beyond replay association.** Cached-tool replay is a known biased estimator of true production effect. whatif claims "associated regression under cached-tool replay," not "caused production regression."

## 3. Verdict states

Three states. Closed set for v0.1; adding a state requires a major schema bump.

- **`Ship`** — every primary endpoint passed; trust floor passed; no blocking findings. The change can ship.
- **`Don't Ship`** — at least one primary endpoint failed (e.g., baseline regression rate above policy threshold; failure cohort didn't improve). Floor passed. The change cannot ship as-is.
- **`Inconclusive`** — either the trust floor failed (insufficient evidence to evaluate) OR a `blocks_all` finding fired (e.g., scorer cache locked, scoring stage couldn't run). The verdict is unknown until the underlying issue is resolved.

`Conditionally Ship` and acceptance mechanisms are deferred to v1.0 as a coherent unit.

## 4. Trust floor and decision policy

These are two distinct layers and the distinction is load-bearing:

- **Trust floor** — about *evidence existence*. Below the floor, there is insufficient evidence to evaluate any verdict. Floor failures produce `Inconclusive`. The floor cannot be overridden by configuration. Encoded structurally via the `FloorPassedProof` witness token: `Ship` requires a proof that only `evaluate_floor()` produces.
- **Decision policy** — about *evidence quality*. Above the floor, evidence exists but its quality (statistical power, CI width, regression thresholds, baseline coverage ratio) is a configurable concern. Policy can be made stricter than the floor; never weaker.

Why the split matters: a user who configures `min_replay_validity: 0.1` cannot produce a junk-evidence Ship verdict because the floor structurally refuses below 0.50.

## 5. Failure-as-data

> **whatif does not fail silently. If a trace cannot be replayed, scored, or trusted, the report says so. If enough traces cannot be trusted, the verdict must downgrade to Inconclusive.**

Two layered types:

- **`FailureRecord`** — the operational fact. One per event (cache miss, runner timeout, scorer error, schema mismatch). Adapter emits trace-scope; core emits cohort-scope and run-scope after aggregation. No `verdict_impact` field — that's a policy projection.
- **`DecisionFinding`** — the policy conclusion. One per conclusion. Aggregates across `FailureRecord`s where applicable. Carries severity (`info | degrades_trust | blocks_ship | blocks_all`).

The bright-line rule: `FailureRecord` is what happened, `DecisionFinding` is what it means. Aggregation happens in the finding, not by mutating records.

## 6. Evidence and audit bundle

A whatif run produces an `ArtifactBundle` on disk. Profile-driven layout:

- **`minimal`** — `report.md`, `report.json`, `manifest.json`, `hashes.json`. Smallest defensible bundle.
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

## 8. Examples of misleading outputs whatif must never produce

These are the failure modes the architecture exists to prevent. Each is a correctness bug, not a UX issue:

- **Verdict `Ship` with 20% replay validity.** The structural floor refuses below 0.50; configuration cannot lower it.
- **Missing baseline hidden in a footnote.** Baseline is required for `Ship`; absence forces `Inconclusive` or `Don't Ship`.
- **Scorer cache disabled in CI without disclosure.** `cache_summary` is a required field on `ReportV01`; schema validation refuses reports without it.
- **Raw production traces included by default.** Default profile is `review` (no full prompts); `forensic` requires two-affirmation opt-in disclosed in the manifest.
- **Per-trace p-values without multiplicity correction.** Per-trace evidence is descriptive only — `MethodologyDisclosure.per_trace_inference: Literal["descriptive_only"]` is sealed at the type level.
- **"Caused production regression" claim.** `MethodologyDisclosure.causal_claim_scope: Literal["associated_under_cached_tool_replay"]` is sealed for v0.1.
- **A confidence interval emitted without method/sample-unit/seed disclosure.** Schema validation requires `BootstrapMethodDisclosure` to be populated.
- **A verdict downgrade silently buried.** Severe trust failures must affect the verdict, not just appear in a footnote (per disclosure-not-sufficient doctrine).

The architecture's trust-first cost is real: slower than a naive implementation, heavier on type wrappers and graph walks, more cautious about what the verdict is allowed to claim. The cost buys the only thing that matters — a verdict an engineer is willing to stake their merge button on.

---

## Glossary

- **Verdict** — `Ship | Don't Ship | Inconclusive`. The terminal output of a run.
- **Trust** — the property that the report's claims match its evidence. Maintained structurally, not by convention.
- **Baseline** — the cohort of representative production traces used to detect silent regression. Required for `Ship`.
- **Cohort** — a labeled subset of traces. v0.1 supports `failure` and `baseline`. Cohort-level primary endpoints are the unit of statistical inference.
- **Condition** — an above-floor concern that can be configured but not weakened below the floor (e.g., regression threshold, CI width).
- **Failure** (`FailureRecord`) — an operational event: something went wrong. Layer-pure; no verdict implications baked in.
- **Finding** (`DecisionFinding`) — a policy conclusion. Carries severity. May reference one or more failures.
- **Floor** — the structural minimum below which no verdict can be rendered. Encoded via `FloorPassedProof` witness token.
- **Policy** — user-configurable rules that layer on top of the floor. Stricter than floor, never weaker.
- **Manifest** (`RunManifest`) — the audit anchor. Captures everything needed to reproduce a run: floor version, policy, environment, redaction state, sensitive-unwrap log.
- **Audit** — the property that every claim in the report is traceable to its evidence. Grep-able for `Sensitive[T]` unwraps; signed by `cache_summary` content; disclosed via `MethodologyDisclosure`.
- **Defensible** — a reviewer can defend the verdict from the evidence in the report.
- **Actionable** — an engineer can act on the verdict in five minutes. Inconclusive verdicts must include a registered fix suggestion.

## Where to go from here

- The runner contract: [runner-contract.md](runner-contract.md) (Phase 10)
- The walkthrough scenarios that pressure-tested this design: [walkthroughs/README.md](walkthroughs/README.md)
- The full design rationale: [DESIGN.md](../DESIGN.md)
- The long-term destination: [path-z.md](path-z.md) (Phase 10) — describes the tool doctrine separately from v0.1 doctrine.
