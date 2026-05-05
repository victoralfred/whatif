# Cascade Catalog

Every design decision ripples. The catalog enumerates the ripples. This is a **live document** — update it whenever a decision is made or a new consequence is discovered. Schema freeze cannot happen until every cascade item has a resolution: implementation done, test in place, or explicit deferral with rationale.

## How to use this catalog

1. Before making a schema-affecting decision, scan this catalog for related ripples.
2. After making a decision, list its ripples here.
3. When implementing a ripple, mark it resolved with the commit / test that closes it.
4. Before schema freeze, audit: every entry must be resolved or deferred.

Format per entry:

```
### [TITLE]

**Source decision:** [link or quote]
**Rippled to:** [list of code/doc/test changes needed]
**Status:** [open | in_progress | resolved | deferred]
**Resolution:** [link to PR/commit/test, or rationale for deferral]
```

## Open cascades (must resolve before schema freeze)

### Verdict-impact removal from FailureRecord

**Source decision:** `FailureRecord` is operational fact only; verdict consequences live on `DecisionFinding`. See `references/type-model.md`.

**Rippled to:**
- Every "warn-loud" event needs a registered finding code in `FINDING_CODE_REGISTRY`.
- Renderers must look up finding for an event, not read impact off the failure.
- Adapter authors need clear docs on what NOT to do (don't try to set verdict_impact on records).
- Migration: any prototype code using `failure.verdict_impact` must move to finding-based logic.

**Status:** open

**Resolution:** Catalog finding codes (see "Finding code registry" cascade); update renderer logic.

### Finding code registry

**Source decision:** Every blocking event needs a registered finding code with severity, fix suggestion, required details keys.

**Rippled to:**
- `whatif/decision/finding_codes.py` — registry module
- `whatif/decision/fix_suggestions.py` — suggestion templates
- CI test enumerates registry, asserts every floor rule and blocking finding code has a registered fix
- Renderer queries registry for fix text in Inconclusive/Don't Ship reports

**Status:** open

**Resolution:** Registry implementation in Phase 2 (decision pipeline). Walkthrough scenarios surface missing entries.

Initial registry (catalog from doctrine):

```
# Floor-related (blocks_all)
- replay_validity_below_floor
- replayed_count_below_floor
- selected_count_below_floor
- scored_count_below_floor

# Policy-related (blocks_ship)
- baseline_regression_above_threshold
- failure_cohort_no_improvement
- ci_uncomputable_for_required_cohort

# Operational (degrades_trust)
- stale_cache_hit_above_threshold
- cache_corruption_detected
- redaction_profile_downgraded
- network_retry_exhausted
- schema_mismatch_above_threshold
- ci_width_above_threshold

# Acceptance (v1.0+)
- condition_persistently_accepted
- acceptance_count_above_threshold
```

### CI availability moved from floor to policy

**Source decision:** CI availability is a policy concern, not a floor concern. Bootstrap-uncomputable is a feature limit, not a trust failure.

**Rippled to:**
- `evaluate_floor()` no longer checks CI availability.
- New policy guard `ci_availability_guard` produces `DecisionFinding(code="ci_uncomputable_for_required_cohort")`.
- `--accept-no-ci` flag is a policy override, not a floor override.
- Doctrine docs updated: floor is about evidence existence, not evidence quality.
- Cohort propagation: `CohortResult.ci_available` populated by stats stage, consumed by policy guard.

**Status:** open

**Resolution:** Phase 2 (decision pipeline) implementation.

### Cohort propagation throughout

**Source decision:** Floors and policies apply per-required-cohort, not just globally. `CohortResult` is the canonical per-cohort artifact.

**Rippled to:**
- Schema: `ReportV01.cohort_results: list[CohortResult]` — each cohort produces one
- `evaluate_floor()` operates per-cohort, returns per-cohort failures
- Decision policy guards operate per-cohort
- Renderer: stats section breaks out per-cohort, replay validity per-cohort
- Adapter: `FailureRecord.cohort` populated for trace-scope and cohort-scope records
- Tests: golden reports include multi-cohort cases

**Status:** open

**Resolution:** Phase 1 (types) defines `CohortResult`; Phase 2 (decision pipeline) implements per-cohort evaluation.

### Sensitive[T] redaction default

**Source decision:** All user content from adapters wrapped in `Sensitive[T]`. Unwrapping requires `.unwrap(reason: str)` call which audit-logs.

**Rippled to:**
- `whatif/types/sensitive.py` — wrapper implementation with __repr__, __str__, __format__, __reduce__ overrides
- `whatif/serialization/encoder.py` — custom JSONEncoder that raises on unwrapped Sensitive
- `whatif/serialization/graph_walk.py` — `assert_no_unredacted_sensitive(obj)` pre-write hook
- Banned-import lint: `json.dumps` only allowed in `whatif/serialization/`
- Reference adapters need audit: every place that produces user-content fields wraps in Sensitive
- Manifest: `runtime.sensitive_unwraps` field captures audit log
- Tests: redaction snapshot tests, graph-walk tests, encoder tests

**Status:** open

**Resolution:** Phase 1 (types) implements wrapper; Phase 4 (adapters) wraps adapter outputs; Phase 5 (serialization) implements graph walk.

### Witness-token pattern for Ship

**Source decision:** `Ship` cannot be constructed without `FloorPassedProof` token; only `evaluate_floor()` produces tokens.

**Rippled to:**
- `whatif/decision/floor.py` — `evaluate_floor()` and `_FLOOR_INTERNAL_TOKEN`
- `whatif/types/verdict.py` — `Ship`, `DontShip`, `Inconclusive` with witness requirement on `Ship`
- Property test: no policy config produces `Ship` when `evaluate_floor()` returns `FloorFailure`
- Cascade item for v1.0: `_cohort_results_hash` on proof, `Ship.__post_init__` verification, or closure-capture variant

**Status:** open

**Resolution:** Phase 2 (decision pipeline).

### Determinism opt-in default

**Source decision:** New schema fields are non-deterministic by default. Opting in requires explicit `x-deterministic: true` annotation.

**Rippled to:**
- JSON Schema for `ReportV01` includes `x-deterministic` annotations
- Determinism CI test introspects schema, builds deterministic-field set, diffs only that subset
- Numeric fields in determinism budget use `DecimalString` not float
- Python interpreter version pinned in determinism test
- Documentation: schema authors guide on when to mark deterministic

**Status:** open

**Resolution:** Phase 5 (serialization) implements; schema freeze validates.

### Two-affirmation forensic profile

**Source decision:** Forensic profile requires both config block (`reporting.forensic_acknowledgment`) AND CLI flag (`--profile forensic`).

**Rippled to:**
- Config validation rejects single-affirmation attempts
- CLI validation rejects single-affirmation attempts
- Manifest discloses both affirmations
- Test: single-affirmation attempts fail
- Docs: forensic profile usage requires both

**Status:** open

**Resolution:** Phase 6 (CLI/config).

### Public-vs-internal model split

**Source decision:** `ReportV01` and friends are hand-written public models. Internal types refactor freely. Projection functions translate.

**Rippled to:**
- `whatif/report/models_v01.py` — public, versioned
- `whatif/internal/` — internal types
- `whatif/report/projection.py` — translation
- `whatif/report/schema/v0.1.schema.json` — generated from `ReportV01`, committed
- CI tests: no internal imports in public; schema matches models; golden reports validate

**Status:** open

**Resolution:** Phase 1 (types) starts; Phase 5 (serialization) completes.

### Cohort-systemic detection rule

**Source decision:** Cohort-scope `FailureRecord`s are emitted by core when ≥50% of cohort traces fail with the same code.

**Rippled to:**
- Aggregation logic in `whatif/decision/aggregation.py`
- Trace records marked `aggregated_into: <cohort_record_id>` when folded
- Heterogeneous-failure case: rule applies per code; multiple cohort-scope records possible
- Walkthrough scenarios 4 and 5 surface edge cases

**Status:** open (rule is provisional; walkthroughs may refine)

**Resolution:** Phase 2 (decision pipeline) implements; walkthroughs may bump the threshold.

### Floor stale-window justification

**Source decision:** Cache lock takes 24-hour stale window before takeover.

**Rippled to:**
- Documentation: explain layering — OS-level `fcntl` is primary, stale-window is fallback for OS-lock-failure cases (kernel crash, NFS corruption)
- Config: `cache.lock.stale_after_seconds` default 86400, override allowed
- Warning in docs: values below 300 risk false-takeover during long bootstrap CI runs

**Status:** open

**Resolution:** Phase 3 (cache) — document layering, default 24h, parametrize.

### Cache disclosure content spec

**Source decision:** `cache_summary` is required field on `ReportV01`; `CacheSummary` is itself a typed object with required fields.

**Rippled to:**
- `CacheSummary` type definition with all required fields (mode, profile, hits, misses, writes, stale_hits, corrupted_entries, schema_version, key_version, models_distribution, policy)
- Schema validation enforces presence and content
- Renderer surfaces cache state in detail section
- Tests: schema invalid if cache_summary missing or incomplete

**Status:** open

**Resolution:** Phase 5 (serialization), Phase 7 (renderer).

### Audit log for .unwrap() reasons

**Source decision:** Every `Sensitive.unwrap()` call audit-logs with reason; log appears in manifest.

**Rippled to:**
- `whatif/types/sensitive.py` — `_audit_log` module-private structlog logger
- `manifest.runtime.sensitive_unwraps: list[SensitiveUnwrap]` (non-deterministic ordering)
- Renderer surfaces unwrap count in audit profile
- Schema: `sensitive_unwraps` annotated `x-deterministic: false`

**Status:** open

**Resolution:** Phase 1 (types) implements; Phase 5 (serialization) wires to manifest.

### CLI cache subcommands for v0.1 (`cache rebuild`, `cache unlock`, `cache verify`)

**Source decision:** Scenario 5 (cache corruption) recovery message instructs the user to run `whatif cache rebuild --force`, `whatif cache unlock`, or `whatif cache verify`. None are in the v0.1 CLI surface. Phase 8.2 lists `whatif cache rebuild` as conditional on Phase 0 surfacing it; Phase 0 has now surfaced it. The other two (`unlock`, `verify`) are not yet anywhere in the plan.

**Rippled to:**
- `whatif/cli.py` — three new subcommands under a `cache` group
- `whatif/cache/recovery.py` (new) — implementations: rebuild deletes `.whatif/cache/entries/` and reports counts; unlock removes `.whatif/cache/.lock` after PID-alive check; verify walks entries computing checksums against stored hashes
- Each subcommand needs its own exit-code semantics (success vs partial repair vs unrepairable)
- Docs: cache recovery section in `docs/getting-started.md` or a new `docs/cache.md`
- Tests: each subcommand tested with corrupted-cache fixtures
- The `unlock` command is structurally dangerous (could clobber a live lock); should it require two-affirmation per cardinal #7? Probably not — a CLI flag like `--i-am-sure` is sufficient since it's a recovery path, not an opt-in to a sensitive capability

**Status:** open

**Resolution:** Phase 8 (CLI) — bundle all three subcommands. Without scenario 5's recovery message is non-actionable.

### CLI `whatif diff` for v0.1

**Source decision:** Scenario 6 (rerun-after-fix) shows `whatif diff <prev-report.json> <new-report.json>` producing a verdict-change summary plus cohort-comparison table plus trace-level differences. Not in any phase plan.

**Rippled to:**
- `whatif/cli.py` — `diff` subcommand
- `whatif/diff/` (new) — diff computation over two `ReportV01` instances
- `whatif/render/diff_markdown.py` (new) — Markdown renderer for diff output
- Diff also needs a JSON output shape (for downstream tooling); requires its own schema versioning decision (`DiffV01`?)
- Tests: diff round-trip; verdict-change matrix (Ship→Ship, Ship→DontShip, DontShip→Ship, Inconclusive→Ship, etc., 9 cells)
- Decision: ship in v0.1 or defer to v0.2?
  - Pro: rerun-after-fix is the most natural engineer workflow after iterating on a fix; without it engineers iterate by reading two reports side-by-side, which is the friction-pattern that drives skim
  - Pro: cardinal #8 (Inconclusive must be actionable) extends to "Don't Ship must be iterable" — diff makes the iteration concrete
  - Con: it's a separate CLI surface with its own renderer and its own schema version
- Recommendation: include in v0.1. The failure-rescue use case is fundamentally iterative, and the diff mode is what makes the iteration legible

**Status:** open (decision pending)

**Resolution:** Phase 8 (CLI) decision; if accepted, becomes Phase 8.5 (diff). If deferred to v0.2, scenario 6's design pressure remains unresolved and the README must remove the CLI invocation example.

### Per-trace evidence schema (top improvements / regressions with judge rationale)

**Source decision:** Scenarios 2 and 3 render top-N improvement and regression traces with structured Original / Replayed / Judge-rationale fields per trace. The current `ReportV01` types (`CohortResult`, `FailureRecord`, `DecisionFinding`) do not carry this data. Without a typed shape for it, the renderer has nothing to render.

**Rippled to:**
- New type in `whatif/types/evidence.py`:
  ```python
  @dataclass(frozen=True, slots=True)
  class TraceEvidence:
      trace_id: str
      cohort: str
      delta: DecimalString
      original_excerpt: Sensitive[str]   # snippet, not full trace
      replayed_excerpt: Sensitive[str]
      judge_rationale: Sensitive[str]
  ```
- New field on `ReportV01`: `evidence: ReportEvidence` containing `top_improvements: list[TraceEvidence]` and `top_regressions: list[TraceEvidence]` (per cohort)
- The N (how many to include) is a `reporting.evidence_top_n` config field; default 3
- Excerpts are `Sensitive[str]` per cardinal #5; the renderer unwraps with reason `"render_evidence_section"`; the unwraps appear in `manifest.runtime.sensitive_unwraps`
- Adapter responsibility: extract excerpts at adapter boundary, wrap as Sensitive
- Tests: evidence section renders for scenarios 2, 3; redacts entirely under `minimal` profile
- Cardinal #5 implication: under `minimal` profile, the entire evidence section either shows redacted markers or is suppressed — needs explicit decision, not silent

**Status:** open

**Resolution:** Phase 1 (types) adds `TraceEvidence`; Phase 5 (serialization) wires the field; Phase 7 (renderer) renders the section.

### CI unavailability reason on CohortResult

**Source decision:** Scenario 4 renders `(CI not computed: sample too small)` inline in the stats line for the baseline cohort. The current `CohortResult.ci_available: bool` flag captures *whether* CI was computed but not *why*. Without the reason, the renderer can't produce the right phrase — it can only say "CI not available" generically.

**Rippled to:**
- Extend `CohortResult` with `ci_unavailable_reason: Literal["sample_too_small", "zero_variance", "computation_failed", None]` (None when `ci_available=True`)
- Stats stage populates the reason when computation skips
- Renderer uses the reason to produce specific text: "sample too small" → "CI not computed: sample too small"; "zero_variance" → "CI not computed: all samples identical"; "computation_failed" → "CI computation failed; see manifest for details"
- The `computation_failed` case also emits a `DecisionFinding(code="ci_computation_failed", severity="degrades_trust")`
- Tests: each reason produces correct rendered text

**Status:** open

**Resolution:** Phase 1 (types) extends `CohortResult`; Phase 2 (decision pipeline) populates in stats stage; Phase 7 (renderer) consumes.

### Floor table rendering — passing rules need to be enumerable

**Source decision:** Scenario 4 renders an 8-row table including all floor rules (passing AND failing) with checkmarks/X for status. `CohortResult.floor_failures: list[FloorFailure]` only carries failures — the renderer has no list of *what could have failed*.

**Rippled to:**
Two design options:
1. **Track passes too:** add `floor_passes: list[FloorPass]` to `CohortResult` symmetric with `floor_failures`. Pros: self-contained data. Cons: doubles cohort-result size; passes are derivable from `(TrustFloor rules) - (failures)`.
2. **Renderer iterates floor:** the renderer has access to the `TrustFloor` instance and iterates its known rules, checking membership in `floor_failures` for each. Pros: no schema bloat. Cons: introduces an asymmetry where the floor-rule list lives in code, not in the report data.

Recommendation: option 2. Keep `CohortResult` lean; the floor rule list is a `TrustFloor.rule_names() -> list[str]` classmethod. Renderer iterates per cohort.

**Rippled to (option 2):**
- `TrustFloor` exposes `@classmethod rule_names() -> list[str]` returning the canonical floor rule order
- Renderer template iterates rule_names × cohorts × (FloorFailure lookup)
- Tests: floor table renders correctly for scenarios with all passes (scenario 1), some failures (scenario 4), all failures (synthetic edge case)

**Status:** open

**Resolution:** Phase 1 (types) adds `rule_names()` classmethod; Phase 7 (renderer) implements table.

### Multi-cause fix-suggestion templating

**Source decision:** Scenario 3 (failure rescue gap) and scenario 4 (insufficient sample) both render fix text with multiple enumerated causes. Scenario 3's "Common causes" lists 3 generic reasons; scenario 4's "Causes:" enumerates specific reasons derived from underlying `FailureRecord`s ("5 traces had tool-cache misses", "2 traces had schema mismatches"). The current `FixSuggestion(template, suggestions=[...])` shape from the existing "Finding code registry" cascade handles the generic case but not the data-driven case.

**Rippled to:**
- Extend `FixSuggestion` shape with an optional `causes_from_failures: Callable[[list[FailureRecord]], list[str]] | None` that derives cause text from underlying failures grouped by code
- Renderer queries the registry, gets the FixSuggestion, calls `causes_from_failures(finding.derived_from_failures)` if present, falls back to static `suggestions=[...]` list otherwise
- Each cause in the derived list is rendered as a numbered item with the cause description and a fix action
- Tests: scenario 3 renders generic three-bullet list; scenario 4 renders the data-driven enumerated list with correct trace counts grouped by failure code
- Cardinal #8 implication: actionability is now a structural requirement on the fix-suggestion entry, not just on whether the entry exists. CI test extends from "registry has entries for all codes" to "every entry produces actionable text against test fixtures"

**Status:** open

**Resolution:** Phase 2 (decision pipeline) extends `FixSuggestion`; Phase 7 (renderer) wires the data-driven path. Refines existing "Finding code registry" cascade.

### Compact-form anchor semantics (suppressed sections)

**Source decision:** Scenario 1 (clean Ship, compact form) renders the link `[Full evidence ↓](#evidence)` but the compact form does not contain an Evidence section. The link is dead.

**Rippled to:**
- Decide: in compact form, suppress the link entirely (preferred — dead links erode trust), OR render the same anchor links and accept that they're no-ops, OR move the inline "Top improvement" / "Top regression" sentences into a tiny named Evidence section so the anchor resolves
- Recommendation: suppress the link. Compact form's value is brevity; a dead link is friction.
- Renderer rule: anchor links are emitted only when the target section exists in the rendered output
- Tests: scenario 1 rendered output has no `[Full evidence ↓]` link; full-form scenarios render the link
- This rule applies symmetrically to all summary-section links: `[Suggested next steps ↓]`, `[Replay details ↓]`, `[Stats ↓]` — emit only if the target section is present

**Status:** open (decision needed; recommendation above)

**Resolution:** Phase 7 (renderer) — renderer emits anchor links conditionally based on which sections will appear in the final output.

### Profile disclosure in rendered Markdown

**Source decision:** Scenario 2 shows judge-rationale text snippets in the Evidence section. This content only appears under `reporting.profile in {review, audit, forensic}`. Under `minimal` profile, the snippets would be redacted or absent. The walkthrough doesn't disclose which profile produced it. A reviewer cannot tell whether they're seeing the full evidence or a redacted view.

**Rippled to:**
- Renderer adds a small profile-disclosure marker either at the top of the report (in the front-matter / header line) or in the manifest reference link
- Recommended placement: footer-ish, near the manifest link, e.g., `[Manifest →](manifest.json) · profile: review`
- Suppressed-content sections render an explicit notice instead of disappearing silently: `> Evidence section suppressed under profile=minimal. Use --profile review or higher to see judge rationale.`
- Cardinal #3 implication: silent suppression is misleading by burial. Explicit suppression-notice is disclosure-and-downgrade discipline.
- Tests: each profile produces the right disclosure marker; suppressed sections render the notice

**Status:** open

**Resolution:** Phase 7 (renderer) — profile marker in footer; explicit suppression notices for absent sections.

### Dashboard SKILL_DIR resolution — skill location vs project repo

**Source decision:** The Layer 4 telemetry dashboard (`scripts/skill-dashboard.sh`) computes paths like `$SKILL_DIR/SKILL.md` and `$SKILL_DIR/references/cascade-catalog.md`. `SKILL_DIR` is hardcoded to `.claude/skills/whatif-design` *relative to the project repo root*. But in this workspace the canonical skill lives at `~/projects/self_dev/.claude/skills/whatif-design/` — one level above the project repo, alongside the deliberation drafts. The dashboard cannot find it.

**Rippled to:**
- Layer 4 "Reference file usage" table prints `(skill not found at .claude/skills/whatif-design)` instead of per-file read counts.
- Layer 4 "Cascade catalog" section prints "Cascade catalog not found" instead of open/in-progress/resolved/deferred counts.
- Layers 1, 2, 3 are unaffected (transcript copy, agent self-report, benchmark prompts don't depend on `SKILL_DIR`).

**Resolution options:**
1. **Co-locate the skill in the project repo**: copy or symlink `~/projects/self_dev/.claude/skills/whatif-design/` into `project/.claude/skills/whatif-design/`. Pros: dashboard works zero-config; the skill ships with the code. Cons: two source-of-truth copies that need sync; the deliberation drafts and the project repo evolve at different rates.
2. **Resolution walk**: dashboard walks up the directory tree from `$PWD` looking for `.claude/skills/whatif-design/`. Stops at `$HOME` or `/`. Pros: zero-config; supports either layout. Cons: more script complexity.
3. **Env var override**: caller sets `WHATIF_SKILL_DIR=...` before invoking the dashboard. Pros: explicit, simple. Cons: not zero-config; muscle-memory mistake risk.
4. **Status quo + graceful degradation**: keep the hardcoded path; the dashboard's skill-related sections print informative "not found" messages. Layers 1–3 fully usable; Layer 4 partial.

**Recommendation:** option 2 (resolution walk). Single small script change, no duplication, no env-var ceremony. Falls back to option 4's degradation if the walk finds nothing.

**Status:** resolved (2026-05-05) — adopted option 1.

**Resolution:** the canonical skill now lives in the project repo at `.claude/skills/whatif-design/` (curated set: SKILL.md + 9 reference files including this catalog). The deliberation drafts and the v0.1 decision record are deliberately kept private at the parent-workspace level; only files contributors should see on a clean clone are committed. Layer 4 dashboard works zero-config against the in-repo path; the resolution-walk option becomes unnecessary.

### Paired-delta as atomic unit

**Source decision:** The unit of statistical analysis is the paired trace delta. Original and replayed scores must not be analyzed as independent samples. See `references/practices.md` § "Statistical methodology".

**Rippled to:**
- `TraceDelta` internal type (float arithmetic) and `TraceDeltaReportV01` public type (DecimalString)
- Analysis API in `whatif/internal/stats.py` accepts `Sequence[TraceDelta]`, never separate score arrays
- Bootstrap operates on delta values, preserving pairing
- Effect size measures use paired forms (`d_z`, paired probabilities)

**Status:** required for v0.1

**Resolution:** Phase 1 (types) implements `TraceDelta`; Phase 2 (decision pipeline) implements paired bootstrap.

### Predeclared cohort-level primary endpoints

**Source decision:** Verdicts derive from predeclared cohort-level primary endpoints. Per-trace evidence is descriptive, not inferential. This is the foundation that determines whether multiplicity correction applies.

**Rippled to:**
- `DecisionPolicy` includes `primary_endpoints` as a required field for v0.1
- v0.1 default: failure-cohort improvement, baseline-cohort non-regression
- Single primary metric per cohort (multiple-metric support deferred to v0.2 with Holm correction)
- Renderer marks per-trace evidence with the disclaimer: "No per-trace statistical significance is claimed. Evidence examples are descriptive."

**Status:** required for v0.1

**Resolution:** Phase 2 (decision pipeline); rendered output verified in Phase 7 walkthroughs.

### Methodology disclosure required in every report

**Source decision:** Every `ReportV01` includes a `MethodologyDisclosure` with bootstrap method, multiplicity stance, judge state, effect-size policy, per-trace-inference scope, and causal-claim scope. Schema validation enforces presence; required-field validation enforces content.

**Rippled to:**
- `ReportV01.methodology: MethodologyDisclosure` (required field)
- All five sub-disclosures (`BootstrapMethodDisclosure`, `MultiplicityDisclosure`, `JudgeMethodDisclosure`, `EffectSizeDisclosure`, plus the parent) defined in `references/type-model.md`
- Renderer surfaces methodology block in the full report
- Schema validation test asserts methodology presence
- Walkthroughs include methodology block in expected output

**Status:** required for v0.1

**Resolution:** Phase 1 (types), Phase 5 (serialization), Phase 7 (renderer).

### Reliability/validity/calibration/bias disclosed-as-unmeasured

**Source decision:** v0.1 addresses reproducibility (scorer cache, deterministic seed, sorted JSON). Reliability, validity, calibration, and bias are NOT measured by default. They must be explicitly marked unmeasured in `JudgeMethodDisclosure`.

**Rippled to:**
- `JudgeMethodDisclosure` has explicit booleans for each: `reproducibility_addressed`, `reliability_measured`, `validity_measured`, `calibration_measured`, `bias_audit_measured`
- Default values for v0.1: `reproducibility_addressed=True`, others `False`
- Renderer shows unmeasured properties in methodology block — does NOT silently omit them
- Doctrine: scorer caching freezes a judge sample; it does not estimate judge reliability, validity, calibration, or bias

**Status:** required for v0.1

**Resolution:** Phase 1 (types), Phase 7 (renderer).

### Cluster bootstrap conditional on real cluster keys

**Source decision:** When tracer adapters provide real cluster keys, whatif uses cluster bootstrap. When not available, whatif assumes i.i.d. and discloses the assumption. Fabricating cluster structure for confirmatory verdicts is forbidden in v0.1.

**Rippled to:**
- `TraceSource.cluster_key_support()` method on the protocol
- `ClusterKeySupport`, `ClusterSelection`, `ClusteringPolicy` types
- `resolve_cluster_key()` resolver function
- Resolved choice recorded in `RunManifest` and `MethodologyDisclosure.bootstrap.cluster_key`
- `whatif-langfuse` adapter declares its real cluster keys
- Forbidden: k-means on embeddings or other unstable heuristics for confirmatory verdicts

**Status:** required for v0.1 (declaration); cluster bootstrap implementation deferred to v0.2

**Resolution:** Phase 1 (types) and Phase 4 (adapters) implement declaration; Phase 2 cluster bootstrap implementation deferred.

### Causal-claim scope enforced

**Source decision:** whatif is allowed to claim "associated regression under cached-tool replay." It is NOT allowed to claim "caused production regression." This is enforced via the `causal_claim_scope` literal field on `MethodologyDisclosure`.

**Rippled to:**
- `MethodologyDisclosure.causal_claim_scope: Literal["associated_under_cached_tool_replay"]` (sealed; v0.1 has only this value)
- Renderer uses "associated under cached-tool replay" phrasing throughout
- Doctrine in `references/practices.md` § "Causal language" enforces this verbally
- Future expansion (e.g., `"validated_against_holdout"`) is a v0.2+ minor schema bump

**Status:** required for v0.1

**Resolution:** Phase 1 (types), Phase 7 (renderer).

### `_AuditLog` process-singleton vs ContextVar isolation

**Source decision:** Phase 1.2 (`whatif/types/sensitive.py`) ships `_audit_log` as a thread-safe but module-level singleton. Records from concurrent runs in the same process share the buffer. This is acceptable for v0.1's expected pattern (one whatif fork per process), but breaks if a long-lived process orchestrates multiple sequential runs without explicit `drain()` between them, or if concurrent runs share a process.

**Rippled to:**
- `whatif/types/sensitive.py` — current implementation
- Phase 6 (replay pipeline) — when concurrent unwrap calls happen across `ThreadPoolExecutor` workers, all writes go to the same singleton; correct because of the `threading.Lock`, but only because all workers share the SAME run
- Embedding scenarios (CI orchestrators that reuse a process) — would need explicit `drain()` between runs

**Status:** open

**Resolution options:**
1. **Status quo + discipline**: each run drains the audit log into its manifest before the next run begins. Document in the runner contract.
2. **`contextvars.ContextVar`**: each run owns its own audit buffer via the context. More robust against accidental cross-run contamination. Costs a context lookup per `.unwrap()` call (negligible).
3. **Explicit `AuditContext` instance passed through the call graph**: most explicit, most invasive — would change the `Sensitive.unwrap()` signature.

Recommend option 2 (ContextVar) when concurrent or embedded runs become a real use case. Filed by PR #13 reviewer feedback.

**Trigger for resolution:** v0.1 ships option 1 with documented discipline. Move to ContextVar when first multi-run-in-process use case lands.

## Deferred cascades (v1.0+, explicit)

### FloorPassedProof binds to specific cohort results

**Source decision:** v0.1 ships token without cohort-results hash; v1.0 strengthens.

**Rationale for deferral:** Over-engineering for v0.1. Property test catches reuse in practice; the hardened version (closure-capture or hash-binding) is a v1.0 concern when audit requirements tighten.

**Trigger for resolution:** v1.0 implementation when audit/compliance pressure justifies the complexity.

### Conditional verdict state (Conditionally Ship / Requires Acceptance)

**Source decision:** v0.1 stays at three verdicts. Acceptance mechanism (run-scoped vs persistent) is v1.0 design.

**Rationale for deferral:** Coherent design unit needing its own deliberation. Single-flag escape (`--accept-no-ci`) is the v0.1 placeholder.

**Trigger for resolution:** v1.0 implementation; design pass on acceptance mechanism.

### Multi-cohort beyond failure/baseline

**Source decision:** v0.1 is failure-rescue only. Schema uses `cohort: str` (not Literal) so future expansion is non-breaking.

**Rationale for deferral:** Audience-distribution data shapes priority. Schema flexibility preserves the option without front-loading the cost.

**Trigger for resolution:** v0.2; depends on observed user shapes.

### Async runner first-class support

**Source decision:** v0.1 supports SyncRunner; AsyncRunner Protocol is defined but reference adapters are sync.

**Rationale for deferral:** Sync covers most users; async runners need additional concurrency design (cancellation, batching, error propagation).

**Trigger for resolution:** v0.2 with proper async design.

### Multi-tenant cache directories

**Source decision:** v0.1 cache is single-directory; multi-tenant CI needs more thought.

**Rationale for deferral:** Most v0.1 users are single-team; multi-tenant is enterprise CI feature.

**Trigger for resolution:** v0.3.

### Cluster bootstrap implementation

**Source decision:** v0.1 declares cluster-key support via `TraceSource.cluster_key_support()` and resolves cluster keys via `resolve_cluster_key()`. The actual cluster-bootstrap *computation* (resampling clusters rather than traces) is deferred to v0.2.

**Rationale for deferral:** v0.1 makes the structural commitments — adapter declares, policy resolves, methodology block discloses — but defaults to i.i.d. bootstrap with explicit disclosure when no cluster key is available, and uses i.i.d. bootstrap even when keys ARE available. The cluster-resampling math is a v0.2 implementation that doesn't change the public schema (the disclosure fields are already there).

**Trigger for resolution:** v0.2 implementation. No schema change required.

### Stratified sampling

**Source decision:** v0.1 uses seeded random sampling within failure and baseline cohorts. Stratified sampling (by request type, language, account segment, length bucket) is deferred.

**Rationale for deferral:** Stratified sampling is the right tool when the population is heterogeneous and you care about representativeness. v0.1 doesn't yet have user-facing strata configuration or empirical evidence that strata matter for verdict quality. Embedding-cluster strata are explicitly rejected (unstable across runs, manufactured rather than declared).

**Trigger for resolution:** v0.2 with explicit user-provided strata keys. v0.3 may explore embedding-cluster strata for *exploratory* (non-verdict-gating) analysis.

### Power / minimum-detectable-effect warnings

**Source decision:** v0.1 has structural floors (min_replayed_per_required_cohort = 5) that act as evidence-existence floors but not evidence-quality floors. Power analysis based on observed `sigma_delta` is deferred.

**Rationale for deferral:** v0.1 lacks pilot data to estimate `sigma_delta` reliably. Reporting power without empirical variance estimates would be theater. v0.2 can collect variance estimates from initial production runs and report observed minimum detectable effect.

**Trigger for resolution:** v0.2 once enough realistic experiments have been run to estimate typical `sigma_delta` for common scoring rubrics. Reports observed MDE; warns when underpowered for configured `practical_delta`. Does NOT auto-block above floor — only warns.

### Multiple-metric correction (Holm)

**Source decision:** v0.1 supports one primary metric per cohort. Multiple primary metrics with Holm correction is deferred.

**Rationale for deferral:** Single-metric design avoids multiplicity correction entirely. Multi-metric support adds genuine complexity (which correction, which family-wise error rate, how to combine cohort-level decisions) that benefits from real user demand to shape it.

**Trigger for resolution:** v0.2 when users demonstrate need for multi-metric primary endpoints. Correction default: Holm. Configurable via `decision.multiplicity` policy block.

### Judge repeat reliability

**Source decision:** v0.1 caches scorer outputs (reproducibility). Repeated judging on a subset to estimate inter-rater reliability is deferred.

**Rationale for deferral:** Doubles or triples scorer cost on selected cases. v0.2 can make this opt-in (`scorer.reliability_subset_ratio: 0.10` re-scores 10% of cases independently). v0.1's stance: explicitly disclose reliability as unmeasured rather than measure it badly.

**Trigger for resolution:** v0.2 with opt-in subset re-scoring. Reports test-retest reliability metric (Krippendorff's alpha or ICC) in methodology block.

### Position-bias mitigation for pairwise judges

**Source decision:** v0.1 uses independent-scoring judge mode (each output scored on its own). Pairwise judging (compare original vs replayed directly) is deferred.

**Rationale for deferral:** Pairwise is more sensitive but introduces position bias (judges prefer whichever output is listed first). Mitigation requires order randomization or dual-order judging, which doubles cost. Defer until pairwise mode is shown to add value beyond independent scoring.

**Trigger for resolution:** v0.2 with pairwise mode opt-in. Order randomization seeded; dual-order option available for high-stakes runs.

### Sequential testing with predeclared stopping

**Source decision:** v0.1 replays all selected traces before evaluating. Sequential testing with early stopping (SPRT, alpha-spending, group sequential) is deferred.

**Rationale for deferral:** Real cost-reduction opportunity (~50% on obvious-Ship and obvious-Don't-Ship cases) but only valid with predeclared stopping rules, randomized trace order, and predeclared looks. Adds significant design complexity — the kind of thing that should ship after v0.1 endpoint discipline is solid.

**Trigger for resolution:** v0.3 with full design pass on predeclared stopping rules.

### Active trace selection with confirmatory holdout

**Source decision:** v0.1 selects traces via seeded random sampling within cohort filters. Active learning (uncertainty sampling, expected error reduction) is deferred.

**Rationale for deferral:** Active selection biases estimates if used for verdict gating without correction. Safe design: active for *exploratory* selection plus a held-out random/stratified confirmatory sample for verdict. v0.3 can implement this two-track design.

**Trigger for resolution:** v0.3 with confirmatory holdout discipline.

### Calibration against human-labeled sets

**Source decision:** v0.1 does not measure judge validity or calibration. Configuring a human-labeled calibration set is deferred.

**Rationale for deferral:** Validity and calibration require external labels — humans evaluating a held-out set of traces against the same rubric the judge uses. This is real annotation work that v0.1 cannot promise. v0.3 supports user-supplied calibration sets and applies isotonic/Platt calibration to judge outputs.

**Trigger for resolution:** v0.3 with calibration-set support. Without a calibration set, the methodology block continues to mark validity and calibration as unmeasured.

### Subgroup / heterogeneous treatment effect analysis

**Source decision:** v0.1 reports cohort-level aggregates only. Subgroup analysis (e.g., "the change improves average behavior but regresses on a specific input pattern") is deferred.

**Rationale for deferral:** HTE estimation typically needs much more data than a single whatif run provides. v0.3 can implement causal forests or simpler HTE methods if sample sizes warrant. Subgroup findings are exploratory unless promoted to inferential primary endpoints with multiplicity correction.

**Trigger for resolution:** v0.3 if sample sizes and use cases support it. Default treatment: exploratory, BH-FDR corrected, labeled as exploratory in report.

### Bayesian decision panel

**Source decision:** v0.1 ships frequentist output exclusively. Bayesian framing (`P(regression rate > threshold | observed evidence)`) is deferred and may remain optional indefinitely.

**Rationale for deferral:** Bayesian output requires priors. Priors are politically sensitive in CI tooling — a skeptical user can ask "why did your prior say this prompt change was safe?" Frequentist output has cleaner political legibility for a CI gate. Bayesian framing is best as an internal research tool until the doctrine matures around prior elicitation.

**Trigger for resolution:** v0.3 optional output panel, if at all. Frequentist remains the default.

### Causal claims beyond replay association (rejected, not deferred)

**Source decision:** whatif is allowed to claim "associated regression under cached-tool replay" and forbidden from claiming "caused production regression." This is a permanent restriction.

**Rationale for non-resolution:** The replay setup is a known biased estimator of true causal effect. Cached tool outputs pin the original agent's decisions; the changed agent might trigger different downstream behaviors that replay cannot observe. Claiming "caused" would be overclaim. The `MethodologyDisclosure.causal_claim_scope` field is sealed at `"associated_under_cached_tool_replay"` for v0.1.

**Trigger for resolution:** None as a rejection. v0.2+ may add additional valid scopes (e.g., `"validated_against_holdout"` if a live-replay validation pipeline is built), but the v0.1 scope cannot be weakened to "caused."

### Tamper-evident report bundles (cryptographic signing)

**Source decision:** v0.1 ships hash file; cryptographic signing deferred.

**Rationale for deferral:** Hash file detects accidental tampering. Cryptographic signing requires PKI infrastructure decisions out of scope for v0.1.

**Trigger for resolution:** v1.0 in regulated environments.

### Vectorized bootstrap CI computation (NumPy)

**Source decision:** v0.1 ships pure-Python bootstrap. NumPy reserved for if/when profiling justifies the dependency.

**Rationale for deferral:** Bootstrap on ~40 floats × 1000 resamples is sub-millisecond in pure Python. NumPy is a 50MB dependency that would add ~50ms to the import budget and yield negligible absolute time savings on typical runs. The schema is unchanged either way (`DecimalString` output is identical), so this is a pure internal refactor when the time comes.

**Trigger for resolution:** Profile data showing bootstrap as a non-trivial fraction of runtime on realistic experiments (≥5% wall-clock). Likely v0.2 if it happens at all.

### `orjson` for serialization (GIL-releasing JSON)

**Source decision:** v0.1 ships stdlib `json` via the custom `WhatifJSONEncoder`. `orjson` is reserved for if/when serialization shows up in profile.

**Rationale for deferral:** Stdlib `json` is acceptable for typical report sizes (under 1MB). `orjson` releases the GIL during serialization and is 5–10× faster, but the absolute time for a 100-trace report is sub-100ms either way. The custom encoder semantics (sorted keys, `Sensitive`-rejection, custom `default()`) are preservable over `orjson` without changing behavior.

**Trigger for resolution:** Profile data showing JSON serialization as a non-trivial fraction of runtime on realistic experiments. Likely v0.2 for very large reports (1000+ traces).

### Workload-classification policy (no CPU-optimization tools)

**Source decision:** whatif is orchestration, not compute. Generic high-performance Python tools (Ray, ProcessPool for replay, MKL, SIMD vectorization, BF16/INT8 precision, Numba `@njit`, ONNX Runtime, OpenVINO, shared-memory IPC) are explicitly rejected for the core. They conflict with one or more trust-first guarantees: structural typing, runner contract simplicity, determinism, redaction enforcement, import budget. See `references/practices.md` § "What this workload is NOT".

**Rationale for deferral / non-resolution:** This is a permanent rejection, not a deferral. It is captured here because future contributors will propose these tools and the rejection rationale must survive the conversation. The cascade entry exists so the question is closed, not re-opened.

**Trigger for resolution:** None. If a future workload class actually requires compute (e.g., a v2.0 feature that does local model inference inside whatif), this decision is revisited as part of that feature's design — not as an optimization of v0.1's existing pipeline.

### Schema migration tooling beyond v0.1.x

**Source decision:** v0.1 ships `whatif report-migrate` as a no-op stub for v0.1.x patches. Real migration logic kicks in at v0.2.

**Rationale for deferral:** No real migrations needed within v0.1.x.

**Trigger for resolution:** v0.2 first minor release.

### `CohortResult` rate-count partition — tighten `<=` to `==` at Phase 2.6

**Source decision:** PR #24 lands the rate-count partition (`improved_count`, `unchanged_count`, `regressed_count`) on `CohortResult` with `__post_init__` enforcing `improved + unchanged + regressed <= scored`. The lenient `<=` constraint preserves backward compatibility with pre-Phase-2.5b construction sites (test fixtures, the floor evaluator) that default rate counts to 0.

**Rippled to:**
- `whatif/types/cohort.py::CohortResult.__post_init__` — change the invariant from `count_sum > self.scored` to `count_sum != self.scored` once Phase 2.6's projection layer populates the partition exhaustively for every required cohort.
- `tests/unit/whatif/types/test_cohort.py::TestRateCountInvariant` — `test_partial_population_passes` flips from a positive test to a `pytest.raises(InvariantViolationError)` test. `test_default_zero_counts_pass` either flips too OR is removed (Phase 2.6 should never produce `scored > 0` with all-zero partition; a structural failure in projection).
- `tests/unit/whatif/decision/guards/_helpers.py::failure_cohort` and `baseline_cohort` — auto-resolve `_resolve_scored = max(default, sum)` becomes `_resolve_scored = sum if sum > 0 else default`. Phase 2.6 tests should pass exhaustive partitions explicitly.
- The `<=` lenient form lets a pathological "scored=10 with all-zero partition" pass both the floor (`min_scored_per_required_cohort: 5` is satisfied) AND the rate guards (silent abstain on zero total). PR #24's findings agent flagged this as a misleading-class concern in F1 option 3; the resolution is Phase 2.6 exhaustive partition.

**Status:** open

**Resolution:** Phase 2.6 verdict computation PR — projection layer populates the rate-count partition exhaustively; `__post_init__` invariant tightens to `==`; the lenient default-0 path is removed.

**Trigger for resolution:** Phase 2.6 verdict computation PR (verdict computation reads from `CohortResult` rate counts and depends on them being exhaustive).

**Related Phase 5 ripple:** when `ReportV01` lands in Phase 5 (public schema; hand-written per cardinal #6), the rate-count fields need a projection mapping from internal `CohortResult` to the public report shape. PR #24 reviewer noted: an end-to-end serialization test that a `CohortResult` with non-zero rate counts round-trips through `ReportV01` should land alongside the projection. That test belongs to the Phase 5 serialization PR, not this one.

### Phase 2.5 deferred guards — dependency map

**Source decision:** Phase 2.5 (PR #23) lands the `Guard` Protocol, the `run_guards` chain composer, and two guards (`practical_delta_guard`, `improvement_observation_guard`). Five remaining guards are intentionally deferred — each blocks on a specific upstream change. Documented here so the dependency chain is discoverable from the catalog rather than buried in a PR body.

**Rippled to:**
- `baseline_regression_guard` — blocked on `CohortResult` rate-count fields (`improved_count`, `unchanged_count`, `regressed_count`). Emits `baseline_regression_above_threshold`.
- `failure_improvement_guard` — same dependency. Emits `failure_improvement_below_threshold`.
- `ci_availability_guard` — blocked on adding `ci_unavailable_for_required_cohort` to `FINDING_CODE_REGISTRY`. The corresponding failure code (operational fact, emitted by stats) already exists; the finding code (policy conclusion) does not.
- `cache_staleness_guard` — blocked on Phase 3 cache subsystem (cache metadata: `last_modified_at`, `cache_key_version`).
- `primary_endpoint_guard` (cardinal #10) — blocked on Phase 2.6 verdict-computation logic; the multiple-endpoint resolution shape is co-designed with the verdict layer.

**Status:** open (each tracked individually below)

**Resolution plan:**
1. ~~PR after #23: extend `CohortResult` with rate-count fields → land `baseline_regression_guard` + `failure_improvement_guard` together~~ → **resolved by Phase 2.5b**: both rate-based guards landed alongside the `improved_count`/`unchanged_count`/`regressed_count` extension on `CohortResult`. Framing cleanup applied: `practical_delta_guard`'s docstring now cross-references `failure_improvement_guard` as the load-bearing primary endpoint.
2. PR adding `ci_unavailable_for_required_cohort` to `FINDING_CODE_REGISTRY` + `FIX_SUGGESTION_REGISTRY` → land `ci_availability_guard`.
3. Phase 3 cache subsystem PRs → cache metadata reaches `CohortResult` via projection layer → land `cache_staleness_guard`.
4. Phase 2.6 verdict computation PR → `primary_endpoint_guard` lands as part of the multi-endpoint resolution. (Framing cleanup is no longer pending — Phase 2.5b applied it inline when the rate-based guards landed.)

### Guard pre-parse caching — Phase 2.6 verdict computation

**Source decision:** PR #23 ships two guards (`practical_delta_guard`, `improvement_observation_guard`) that each independently call `parse_decimal_string(failure.median_delta, ...)`. When both run on the same cohort the parse happens twice. Phase 2.5 keeps each guard self-contained for testability and reasoning; the redundancy is acceptable at v0.1 scale (microseconds per call).

**Rippled to:**
- `whatif/decision/guards/improvement_observation.py` — docstring marks the redundant parse with reference to this cascade entry.
- Phase 2.6 verdict computation introduces a context object (or a pre-parsed `cohort_results_parsed` view) that pre-parses `median_delta` once per cohort and passes the float to guards alongside the `CohortResult`.
- Guard signatures may evolve from `(cohorts, policy)` to `(cohorts, policy, parsed)` or similar; the `Guard` Protocol updates accordingly.
- Existing guards retain a thin parse-fallback path so they remain self-contained when called outside the verdict pipeline (tests, ad-hoc usage).

**Status:** open

**Resolution:** Phase 2.6 — verdict computation pre-parses cohort numerics once and threads the parsed values to every guard. Cardinal #1 invariant (parse-on-failure raises `InvariantViolationError`) moves to the pre-parse step; guards then read floats directly.

**Trigger for resolution:** Phase 2.6 PR.

### `parse_decimal_string` permissiveness — soft warn now, tighten at Phase 5

**Source decision:** PR #23 ships `parse_decimal_string` early (one half of the Phase 5 serialization helper pair) so Phase 2.5 guards can validate `CohortResult.median_delta`. The current implementation accepts anything `float()` parses but emits a `DeprecationWarning` on inputs that violate the committed canonical shape (no decimal point, scientific notation). Phase 5 will flip the warning to a hard `InvariantViolationError` and pin exact precision per field.

**Rippled to:**
- `whatif/serialization/decimal.py` — replace the `FutureWarning` branch with `raise InvariantViolationError(...)`. The canonical regex (`_CANONICAL_DECIMAL_RE`) becomes the gate.
- `tests/unit/whatif/serialization/test_decimal.py::TestParseDecimalStringNonCanonicalWarns` — flips from `pytest.warns(FutureWarning)` to `pytest.raises(InvariantViolationError)` for every test in that class.
- **Flip-test list synchronization (PR #23 reviewer note):** as more callers adopt `parse_decimal_string` (each subsequent guard, the verdict layer, the renderer), every test that uses `pytest.warns(FutureWarning, match=...)` against a non-canonical input becomes part of the Phase 5 flip surface. Phase 5's PR must grep for `pytest.warns(FutureWarning` across `tests/` and update each occurrence in lockstep. Today there's only one location; the count grows.
- `format_decimal_string` (new in Phase 5) pins per-field precision. The current canonical shape is `^-?\d+\.\d+$`; Phase 5 may narrow further (e.g., exactly 3 fractional digits for ratios).
- **Phase 5 helper-adoption ripple (PR #24 reviewer note):** when `format_decimal_string` lands, the inline `format(rate, '.3f')` calls in `whatif/decision/guards/{baseline_regression,failure_improvement}.py` (and the symmetric `format(threshold, '.3f')` in both files) should switch to the helper. Today's two sites are bounded; the helper-extraction prevents drift if a third rate-based guard adds the same pattern. Tests for the two `TestSubPrecisionThresholdDivergence` cases (in `test_failure_improvement.py`) will need to flip from "documented divergence pinned" to "round-trip equality pinned" once the canonical shape is enforced.
- **Float-equality stability (PR #23 reviewer note):** the `practical_delta_guard` boundary check `median_delta_float <= policy.practical_delta_epsilon` relies on `float("0.050") == 0.05` round-tripping exactly. When `format_decimal_string` lands with a guarantee that policy thresholds round-trip through `format(value, '.3f')` to identical bytes, this concern dissolves. The Phase 5 PR should pin a boundary-stability test asserting `parse(format(x)) == x` for the canonical thresholds.

**Status:** open — soft-warning phase active.

**Resolution:** Phase 5 — `format_decimal_string` lands and pins the canonical shape; `parse_decimal_string` tightens warning → error. The two functions become a round-trip pair: `parse(format(x)) == x` for every numeric x in the determinism budget.

**Trigger for resolution:** Phase 5 serialization layer PR.

## Resolved cascades

### Fresh-list-per-guard contract — convention, not enforcement (resolved 2026-05-05)

**Source decision:** PR #23 went through three reviewer iterations on whether `run_guards` should structurally enforce that each guard returns a fresh list (not a class-level mutable shared across guards). Iterations: add `id()`-based check → upgrade to `is`-comparison with strong references → drop the check entirely. Final state: convention documented in `whatif/decision/guards/__init__.py`'s discipline note + `whatif/decision/guards/protocol.py` `run_guards` docstring; no runtime check.

**Rationale:** The fresh-list contract is a coding-pattern claim, not a structural claim about verdict integrity (which would belong in `references/enforcement.md`). Per the enforcement-strength hierarchy, convention-with-documentation is the appropriate mechanism for non-structural claims. The trust-floor witness pattern (`FloorPassedProof`) is for structural claims; the runtime check would have been belt-and-suspenders that didn't pay rent.

**Recovery path:** if a real shared-list bug ever surfaces, the response is a targeted regression test for that specific failure mode, NOT re-introducing blanket runtime enforcement. The doctrine: defense-in-depth must earn its rent in observed bugs, not hypothetical ones.

**Resolved by:** PR #23, commit `064154c` (final state).



## Audit checklist for schema freeze

Before publishing v0.1 JSON Schema:

- [ ] Every cascade in "Open cascades" has status `resolved` or `deferred`
- [ ] Every "structural" claim in the codebase appears in `references/enforcement.md` with a mechanism
- [ ] Every floor rule has a registered fix suggestion
- [ ] Every blocking finding code has a registered fix suggestion
- [ ] Generated schema diff against committed schema is empty
- [ ] Six golden reports validate against schema
- [ ] Determinism CI test passes (same input twice → byte-identical deterministic subset)
- [ ] Property test passes: no policy config produces `Ship` when floor fails
- [ ] Property test passes: synthetic adversarial inputs all produce structured reports
- [ ] Walkthrough scenarios produce rendered output that matches expectations
- [ ] Conceptual model document approved
