# Doctrine

The trust-first design philosophy that shapes every whatifd decision.

## The deepest principle

> **whatifd's product is not the experiment. It is the verdict's defensibility.**

The experiment is the mechanism. The defensibility is the deliverable. This reframes "what is whatifd?" cleanly: it's not an experiment runner that happens to produce a report. It's a defensibility-producing system that uses experiments as evidence.

## The motto

> **whatifd does not fail silently. If a trace cannot be replayed, scored, or trusted, the report says so. If enough traces cannot be trusted, the verdict must downgrade to Inconclusive.**

The last sentence prevents "warning theater." A report can technically disclose a problem and still mislead reviewers if the warning is buried while the verdict reads "Ship." Disclosure is necessary; downgrade is what makes disclosure honest.

## The decision test

> **If a design flaw would mislead a reviewer, it is a correctness bug. If it only slows or inconveniences the reviewer, it is an optimization or UX issue.**

This is the disambiguator for trade-offs. Examples:

| Situation | Classification | Action |
|---|---|---|
| 5/20 traces skipped but verdict still says Ship | Misleading | Must downgrade or clearly reduce verdict |
| Import takes 400ms | Inconvenient | Optimize later |
| Scorer cache used but not disclosed | Misleading | Must disclose cache hit/miss status |
| Baseline missing but report still says Ship | Misleading | Inconclusive or limited verdict |
| No async support for runner | Inconvenient | Accept for v0.1 if documented |
| Bootstrap CI omitted for tiny sample | Potentially misleading | Disclose "CI unavailable: sample too small" |
| LLM judge has 5% variance run-to-run | Inherent (not misleading if disclosed) | Document, cache, never pretend to fix |

## The three failure categories

Contributors will sometimes try to "fix" inherent limitations by hiding them, which converts inherent into misleading. Naming the category prevents this.

- **Misleading** — hides truth from reviewer. Fix structurally.
- **Inconvenient** — slows or annoys reviewer. Optimize when capacity allows.
- **Inherent** — limitation of the underlying tools (LLM judge variance, scorer cost, missing tool outputs in old traces). Disclose, never pretend to fix.

## Defensible AND actionable

The doctrine has two audiences, and they pull in different directions.

> **A whatifd run produces output that is both *credible* (a reviewer can defend the verdict from the evidence) and *actionable* (an engineer can act on the verdict in five minutes). Credibility without actionability creates skim-and-ignore patterns. Actionability without credibility creates false confidence. Either failure mode undermines the tool.**

Concretely:
- **PR reviewer with 3 minutes** reads the 30-line summary and forms an opinion.
- **Engineer with 30 minutes** reads the full report, drills into evidence, fixes the regression.

Same JSON, three rendered formats:

1. **1-line CI status** (GitHub check display) — must communicate verdict + headline finding in ~80 characters.
2. **30-line summary** (top of Markdown report) — must let the 3-min reviewer form an opinion without scrolling.
3. **Full report** (entire Markdown + JSON) — must let the engineer act.

The compact-Ship case is the degenerate where the 30-line summary IS the entire report. No separate template; same renderer producing a shorter result when there's nothing to elaborate on.

## Trust floor: evidence existence, not evidence quality

> **The trust floor is about evidence existence, not evidence quality. Below the floor, there is insufficient evidence to evaluate any verdict. Above the floor, evidence exists but its quality (statistical power, CI width, sample representativeness) is a policy concern. Floor failures produce Inconclusive. Quality failures produce Don't Ship or Inconclusive depending on policy.**

Floor: replay validity ratio, scored count, selected count, replayed count. The minimum below which no verdict can be rendered.

Policy: CI computability, CI width, baseline coverage ratio, regression thresholds. Configurable, can be made stricter than the floor, never weaker.

Why this split matters: configuration cannot bypass the floor. A user who sets `min_replay_validity: 0.1` cannot produce a junk-evidence Ship verdict because the floor structurally refuses below 0.50 (the v0.1 default, provisional, marked for revision after first 10 production runs).

## v0.1 doctrine vs tool doctrine

These are deliberately disentangled. v0.1 ships with truthful claims; aspirational claims are scoped to v1.0.

**v0.1 doctrine (what ships):**
> whatifd v0.1 produces structured experiment reports for engineers iterating on LLM behavior changes when they have a known failure cohort and a representative baseline. Reports are designed to be reviewable in 5 minutes and reproducible across runs. The verdict is one of Ship, Don't Ship, or Inconclusive based on configurable policy enforced above a structural trust floor.

**Tool doctrine (where it's going):**
> The whatifd project's destination is a pre-merge regression gate that engineers stake their merge button on. v0.1 is the wedge: prove the experiment runner pattern works for one use case, in CI integration form, with structured outputs that downstream tooling can build against. v1.0 expands experiment shapes, adds acceptance mechanisms, and matures the GitHub Action wrapper into a default PR check.

The README leads with v0.1 doctrine. The Path Z page describes tool doctrine. Users with use cases v0.1 doesn't serve see that explicitly and can choose to wait.

## What whatifd is NOT

Stating non-claims protects the doctrine.

- **Not a safety certifier.** whatifd enforces *your* declared policy. It does not certify the absence of bugs, harms, or regressions outside the dimensions you scored.
- **Not a replacement for human review.** It's input to human review. The five-section report shape exists to make that review fast and grounded.
- **Not a substitute for production monitoring.** Production drift is a different problem.
- **Not a benchmark suite.** It evaluates *your* change against *your* traces; it does not produce comparable scores across projects.
- **Not a load test.** Replay is for behavior comparison, not for performance evaluation.

## The cost of this design

Naming the cost prevents future contributors from optimizing it away without understanding what it bought.

> The cost of trust-first design is that whatifd is slower, heavier, and more cautious than a naive implementation — by design. The cost buys the only thing that matters: a verdict an engineer is willing to stake their merge button on.

Slower: scorer cache disclosure overhead, deterministic JSON serialization, two-pass validation (typed input + serialization), structured failure handling.

Heavier: explicit type wrappers (`Sensitive[T]`, witness tokens), graph-walk redaction enforcement, schema validation, golden report tests.

More cautious: floor enforcement (structural via `FloorPassedProof`), baseline-required-for-Ship policy default (`DecisionPolicy.require_baseline=True`; configurable, but the default refuses Ship without baseline), two-affirmation forensic opt-in (structural), scorer cache staleness blocks Ship (structural via finding-code severity).

Each cost is paid in service of the verdict's defensibility. Removing any of them weakens that. If pressure mounts to remove one, ask: which audience are we asking to give up trust — the PR reviewer or the engineer?

## Statistical claims must match the design

> **whatifd's verdict is only as defensible as its sampling, scoring, and uncertainty model.**

This is the math companion to the trust-first frame. The verdict is defensible when sampling is defensible, scoring is defensible, uncertainty is defensible, and methodology is disclosed. If any one of these is hand-waved, the verdict is not defensible — it just looks defensible.

The v0.1 statistical posture, in one paragraph:

> whatifd uses paired trace deltas as the unit of analysis. Verdicts are based on predeclared cohort-level endpoints. Per-trace evidence is descriptive, never inferential. Multiple-comparison correction applies only when the run declares multiple primary endpoints, multiple primary metrics, or inferential subgroup analyses. Methodology is disclosed in every report. Scorer caching addresses reproducibility, not reliability, validity, calibration, or absence of bias. whatifd must not make causal claims beyond "associated regression under cached-tool replay."

The deepest single rule:

> **Endpoint discipline first. Statistical machinery second.**

Multiple-comparison correction is not the foundation. Endpoint discipline is. Defining what counts as a primary endpoint determines whether multiplicity correction even applies. v0.1 ships with one primary metric per cohort, two predeclared endpoints (failure improvement, baseline non-regression), and per-trace evidence framed as descriptive. Under those conditions, no multiplicity correction is needed — and the report says so explicitly.

See `references/practices.md` § "Statistical methodology" for the full mathematical specification, and `references/statistical-defaults.md` for the v0.1 defaults that operationalize it.
