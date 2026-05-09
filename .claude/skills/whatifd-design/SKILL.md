---
name: whatifd-design
description: Design and implement `whatifd`, a trust-first LLM experiment runner that produces defensible verdicts (Ship / Don't Ship / Inconclusive) from forked production traces, replayed against a proposed change, scored, and reported. Use this skill whenever the user asks to design, architect, implement, plan, or build any part of whatifd — including the runner contract, trust floor, failure taxonomy, scorer cache, JSON schema, decision policy, report rendering, GitHub Action wrapper, or any milestone of the v0.1 → v1.0 trajectory. Also use this skill when discussing similar trust-first experiment-runner systems, CI-grade verdict tooling for LLM behavior changes, or any architectural question about replay-based regression testing for AI agents.
---

# whatifd: Trust-First Experiment Runner

## What this skill is for

`whatifd` is an open-source experiment runner for LLM behavior changes. The user changes a prompt, model, or tool; whatifd forks production traces, replays them with the change, scores the diff, and emits a verdict report defensible enough to block a PR.

This skill encodes the design doctrine, type model, enforcement mechanisms, and bottom-up phased plan for building it. Use this skill any time you're working on whatifd's architecture, implementation, documentation, or scope decisions.

## The one principle that controls everything

> **whatifd's product is the verdict's defensibility. Every design decision is judged by whether it makes the verdict more defensible. If a feature increases defensibility, it belongs early. If it doesn't, no amount of cleverness justifies its inclusion.**

A corollary that resolves day-to-day disputes:

> **If a design flaw would mislead a reviewer, it is a correctness bug. If it only slows or inconveniences the reviewer, it is an optimization or UX issue.**

These two sentences are the test for every disagreement. Cite them.

## How to use this skill

The skill body below is a router. The actual content lives in `references/`. Read the reference file relevant to what you're working on. Do not try to hold all of this in working memory at once.

Reference files, in the order you typically need them:

1. **`references/doctrine.md`** — the trust-first principles, the motto, the three-format report system, the misleading-vs-inconvenient test. Read this first if you're new to the project. Read it again whenever you're tempted to weaken a structural guarantee.

2. **`references/type-model.md`** — the canonical type list (`TrustFloor`, `FailureRecord`, `DecisionFinding`, `Verdict`, `CohortResult`, `RunManifest`, `ReportV01`, `ArtifactBundle`), the two-type scope rule for failures vs findings, the witness-token pattern for `Ship`, the `Sensitive[T]` redaction wrapper. Read this when designing or implementing any data structure.

3. **`references/enforcement.md`** — the enforcement table that pairs every "structural" claim with the mechanism that makes it true. Read this when you find yourself writing the word "structural" — make sure the claim has a paired mechanism.

4. **`references/contracts.md`** — the runner contract (the user-supplied function), the adapter protocols (tracer, scorer), the report JSON schema versioning rules, the public-vs-internal model split. Read this when working at any boundary between whatifd and another system.

5. **`references/cascade-catalog.md`** — the live document tracking follow-on consequences of design decisions. Every change ripples; the catalog enumerates the ripples. Read this before any schema-affecting change. Update it as new cascades are discovered.

6. **`references/phases.md`** — the bottom-up phased implementation plan with test gates at each phase. Read this when planning the next chunk of work or deciding what's in scope for which milestone.

7. **`references/practices.md`** — coding decisions, design patterns, library choices, performance discipline, statistical methodology, observability hooks. Read this when writing code for the first time on a new module. **Read the "What this workload is NOT" section before reaching for any performance tool** (Ray, NumPy, ProcessPool, ONNX, Numba, MKL, etc.) — most generic high-performance Python advice is wrong for whatifd and adopting it would break the trust-first guarantees. **Read the "Statistical methodology" section before any decision touching uncertainty, effect size, primary endpoints, or per-trace inference** — see also #9 below for the v0.1 defaults.

8. **`references/walkthroughs.md`** — six rendered scenario outputs (Clean Ship, Don't Ship regression, Don't Ship failure-rescue gap, Inconclusive insufficient sample, Inconclusive cache corruption, Rerun-after-fix). Read this when designing UI/UX, the renderer, or fix-suggestion templates. Walkthroughs are the empirical reviewer.

9. **`references/statistical-defaults.md`** — the v0.1 statistical defaults that operationalize cardinal rule #10. Read this when configuring scorer adapters, setting cohort thresholds, or deciding what to put in `whatifd.config.yaml`. Defaults are intentionally modest: one primary metric per cohort, paired bootstrap with B=5000, `epsilon=0.05`, reliability/validity/calibration/bias disclosed as unmeasured. Override only with stated reasons; overrides are recorded in the manifest.

## What to do at the start of any whatifd work session

1. **Read the doctrine.** `references/doctrine.md`. Two minutes. Re-anchors the trust-first frame.
2. **Identify the artifact you're producing.** Code module? Schema field? Documentation section? UX scenario? The artifact determines which reference files matter.
3. **Read the relevant references.** Don't skim all nine every time.
4. **Check the cascade catalog.** Does your change ripple? If yes, list the ripples before starting.
5. **Identify the test gate.** Phase plans tie every implementation chunk to a test that proves it works. Find the gate before writing the code.

## Project status (as of design close)

- v0.1 scope: **failure-rescue experiment type only**, with a known failure cohort and a representative baseline. Other experiment shapes (regression-check, A/B comparison, latency optimization) are deferred to v0.2 with proper design.
- Schema freeze is **blocked** until: cohort propagation is complete, failure/finding two-type model is implemented, floor-vs-acceptance precedence is committed in code.
- Implementation order: walkthroughs → enforcement audit → conceptual model document → schema freeze → integration fixtures → code.
- The deliberation has converged. Further pre-implementation refinement does not improve the design more than the walkthroughs will. **The next action is empirical, not analytical.**

## Cardinal rules (non-negotiable)

These survive every design dispute. If a proposal violates one of these, it is rejected regardless of how clever the rationale.

1. **Failure-as-data.** Every expected failure (cache miss, malformed trace, runner exception, scorer timeout, replay mismatch, missing baseline) appears as structured data in the JSON report. No silent crashes. No generic "failed" buckets. Unhandled exceptions are bugs in whatifd itself.

2. **Trust floor cannot be bypassed.** Floor failures produce `Inconclusive` regardless of policy configuration. The floor is enforced at the type level via the `FloorPassedProof` witness token, not by convention or by property test alone. See `references/enforcement.md`.

3. **Disclosure is necessary but not sufficient.** A report can technically disclose a problem and still mislead by burying the warning. Severe trust failures must affect the verdict, not just appear in a footnote.

4. **Determinism is opt-in per field, default off.** New schema fields are non-deterministic by default. Opting into the determinism budget requires explicit `x-deterministic: true` annotation. See `references/contracts.md`.

5. **Sensitive data is wrapped, never raw.** Any user content entering whatifd is wrapped as `Sensitive[T]` at the adapter boundary. Unwrapping requires explicit `.unwrap(reason: str)` calls that audit-log. Core's serializer refuses unwrapped sensitive values via pre-serialization graph walk. See `references/type-model.md`.

6. **Public schema is hand-written; internal types can refactor.** `ReportV01` and friends are hand-written models with explicit projection functions from internal types. Internal refactors do not break the public contract. See `references/contracts.md`.

7. **Two-affirmation rule for dangerous capabilities.** Forensic profile, persistent acceptance (v1.0), or any future structurally-dangerous flag requires both a config block AND a CLI flag. One alone is insufficient. The pattern generalizes.

8. **Inconclusive must be actionable.** Every floor rule and every blocking finding code has a registered fix-suggestion template. CI test enumerates the registry and asserts coverage. A user reading an Inconclusive verdict must see a concrete next step.

9. **whatifd is orchestration, not compute.** The workload is I/O-bound (LLM API latency, tracer fetch, disk cache). It is NOT a CPU-bound AI compute workload. Generic "high-performance Python" advice (Ray, ProcessPool for replay, NumPy throughout, MKL, SIMD, BF16/INT8 precision, Numba, ONNX Runtime, shared-memory IPC) is **wrong for whatifd** even when correct for its actual domain. Adopting that advice breaks the trust-first guarantees: ProcessPool breaks the runner contract, NumPy breaks `DecimalString` determinism, shared memory breaks `Sensitive[T]` redaction, Ray blows the import budget. Profile first, classify the bottleneck, then pick a tool. The bottleneck will be I/O. See `references/practices.md` § "What this workload is NOT".

10. **Statistical claims must match the design.** whatifd uses paired trace deltas as the unit of analysis, predeclared cohort-level endpoints as the basis for verdict, and descriptive (not inferential) framing for per-trace evidence. Multiple-comparison correction applies only to multiple primary endpoints, not to per-trace observations. Methodology is disclosed in every report. Scorer caching addresses reproducibility — NOT reliability, validity, calibration, or absence of bias; if those are not measured, the methodology block must say so. whatifd must not make causal claims beyond "associated regression under cached-tool replay." See `references/practices.md` § "Statistical methodology", `references/type-model.md` § "Statistical types", and `references/statistical-defaults.md`.

## When in doubt, ask the right question

The trust-first frame produces a useful disambiguator for design questions. When stuck:

- "Would this make the verdict more defensible?" — primary question.
- "Would a reviewer be misled, or merely inconvenienced?" — disambiguator for trade-offs.
- "Does this require a floor (structural) or a policy (configurable) defense?" — for guarantee questions.
- "Is this v0.1 doctrine or tool doctrine?" — for scope questions.
- "Can the structural claim be enforced at type level, or is it convention with a strong adjective?" — for enforcement questions.
- "What does the profile show is the bottleneck?" — for performance questions. If the answer isn't "I have profile data," the optimization is premature. CPU is not the bottleneck for whatifd; if a tool's value depends on whatifd being CPU-bound, it's the wrong tool.
- "Is this a primary endpoint or descriptive evidence?" — for statistical questions. If it's descriptive, no inferential claim. If it's a primary endpoint, declare it before evaluation. Multiple primary endpoints require multiplicity correction.

If you cannot answer the primary question, the design is not yet ready. Stop and clarify before writing code or schema.
