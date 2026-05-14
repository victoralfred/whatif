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

### `whatifd.adapters` package introduced (Phase 4A.1)

**Source decision:** Phase 4A.1 (PR #57) introduces `src/whatifd/adapters/` with `TraceSource` / `Scorer` Protocols, `RawTrace` / `JudgeResult` Pydantic models (Sensitive[str] user-content fields per cardinal #5), `AdapterMetadata` frozen dataclass, and a re-exported `ClusterKeySupport`. Lazy-load contract: core modules (`whatifd.cli`, `whatifd.diff`, `whatifd.config`, `whatifd.contract`, `whatifd.cache`, `whatifd.render`) MUST NOT import `whatifd.adapters`; the subprocess test in `tests/unit/whatifd/adapters/test_protocols.py::TestLazyLoad` is the enforcement.

**Rippled to:**
- **Phase 4A.2** (next sub-phase) — parameterized conformance harness in `tests/adapters/test_conformance.py`. Single source of truth for "what makes an adapter valid"; runs against the stub at 4A.3 and against real adapters at 4B.
- **Phase 4A.3** (synthetic stub) — `src/whatifd/adapters/stub.py`. Must satisfy the conformance harness; lazy-load test extended to also check the stub isn't pulled by core.
- **Phase 4B real adapters** — `whatifd-langfuse`, `whatifd-inspect-ai` separate packages. Implement the protocols; pass conformance; consume `RunManifest.adapters` surface.
- **`RunManifest.adapters` surface** — adapter identity (id / package version / SDK version) flows from `AdapterMetadata` into `RunManifest` for audit. Phase 1.6 manifest types may need a small extension to carry one entry per adapter (trace source + scorer); this entry tracks the decision when 4B lands.
- **Adapter→core typed-boundary review** — `RawTrace.tool_spans`, `RawTrace.metadata`, `JudgeResult.metadata` are typed `dict[str, Any]` to mirror existing `whatifd.contract` shapes (`TraceInput.metadata`, `ReplayOutput.tool_spans`). Cardinal #6 in the project's CLAUDE.md governs the public report schema, NOT the adapter↔core internal boundary, so this is intentional. If/when the contract grows a typed `ToolSpan` model (deferred to v0.2), the adapter projection updates in lockstep.
- **Transitive import cost of `whatifd.adapters` import** — `whatifd/adapters/__init__.py` re-exports `ClusterKeySupport` from `whatifd.types.statistical`, so `import whatifd.adapters` pulls in `whatifd.types.statistical` at module load. Adapter-package authors targeting minimal import footprints should be aware: importing the adapter package eagerly loads the statistical types. The lazy-load contract only protects core (`import whatifd`) — it does not bound the cost of loading the adapter package itself.

**Phase 4A.2 conformance harness checklist** (registered here so a future refactor of the protocol module doesn't orphan the inline TODOs in `protocols.py`):

- [x] Harness invokes `TraceSource.iter_traces`, `adapter_metadata`, `cluster_key_support` with realistic inputs and asserts return shape (Phase 4A.2, PR #58).
- [x] Harness invokes `Scorer.score`, `cache_key_components`, `adapter_metadata`; asserts `score.rationale` is `Sensitive[str]`; asserts `cache_key_components(...)` returns a valid `CacheKeyComponents` (Phase 4A.2, PR #58).
- [x] Harness asserts `RawTrace.user_message` and `original_response` are `Sensitive[str]` for every emitted trace (Phase 4A.2, PR #58).
- [x] Harness exercises the `score=None` structural-failure path via `StructuralFailureScorerConformance` (Phase 4A.2, PR #58).
- [x] Harness runs against the synthetic stub at 4A.3 and is green (`tests/adapters/test_stub_conformance.py`, this PR).
- [ ] Same harness re-runs against `whatifd-langfuse` and `whatifd-inspect-ai` at 4B.

**Status:** Phase 4A complete (4A.1 / 4A.2 / 4A.3 all landed). 4B real adapters remaining.

**Resolution:** closes when 4B real adapters ship and the conformance harness is green against both real adapters in addition to the stub.

### Monorepo workspace + `whatifd-langfuse` distribution (Phase 4B.1)

**Source decision:** Phase 4B.1 (PR #65) ships `packages/whatifd-langfuse/` as a sibling distribution under a uv workspace (`[tool.uv.workspace] members = ["packages/whatifd-langfuse"]` at the root `pyproject.toml`). Industry-standard monorepo layout (cf. OpenTelemetry Python, AWS CDK, pytest plugins). Library version pinning is lower-bound + major-cap (`langfuse>=4.5.1,<5.0`).

**Rippled to:**
- **Phase 4B.2** — `packages/whatifd-inspect-ai/` joins the workspace as a second sibling. Same pinning convention; same separate-distribution rule (lazy-loaded by core, never imported transitively).
- **Lazy-load contract** extended at the workspace level: `tests/unit/whatifd/adapters/test_protocols.py::TestLazyLoad::test_core_modules_do_not_load_real_adapter_packages` now scans for `whatifd_langfuse` and `whatifd_inspect_ai` in `sys.modules` after importing `whatifd.cli` / `whatifd.diff` / `whatifd.config` / `whatifd.contract` / `whatifd.cache` / `whatifd.render`. Adding a third sibling MUST extend this scan in the same PR.
- **Conformance harness reuse** — `packages/whatifd-langfuse/tests/conftest.py` adds the parent's `tests/adapters/` directory to `sys.path` so `from conformance import TraceSourceConformance` works. If this seam grows brittle (Phase 4B.2 hits the same friction; out-of-tree adapters can't reach into the parent), promote `tests/adapters/conformance.py` to a public `whatifd.testing.adapter_conformance` per `whatifd-features` entry #1. Until then, the conftest tweak is the documented bridge.
- **Cassette discipline** — recorded-smoke tests under `pytest-recording` MUST scrub user content from response bodies AND credentials from request headers AND echoed identifiers from response bodies. Header filtering alone is insufficient (Langfuse echoes `public_key` inside trace metadata). The pattern: a `before_record_response` hook that walks the JSON shape and replaces `input` / `output` / `metadata` / `name` / `projectId` / per-trace `id` with deterministic placeholders. Phase 4B.2 (`whatifd-inspect-ai`) inherits this discipline; any new adapter cassette is reviewed for content leakage before commit.
- **`packages/` test collection** — root `[tool.pytest.ini_options] testpaths = ["tests", "packages"]`. Adding a third package extends the glob; adding a non-package directory requires a more selective testpaths value.

**Phase 4B.2 reviewer checklist** (must be satisfied before 4B.2 PR merges):

- [ ] `packages/whatifd-inspect-ai/` exists with its own `pyproject.toml`, `src/whatifd_inspect_ai/`, and tests.
- [ ] Workspace registration: `[tool.uv.workspace] members` extended; `[tool.uv.sources]` adds `whatifd-inspect-ai = { workspace = true }`; `[dependency-groups] workspace` includes the new package.
- [ ] `tests/unit/whatifd/adapters/test_protocols.py::test_core_modules_do_not_load_real_adapter_packages`: the `# TODO(4B.2): drop this comment when whatifd_inspect_ai is workspace-registered.` line is removed AND the surrounding "false-green note" prose is removed. Failing to remove the marker is a code-review gate; grep `TODO(4B.2)` across the repo at PR review time.
- [ ] Conformance harness reuse seam: `packages/whatifd-inspect-ai/tests/conftest.py` either copies the `sys.path` workaround from `whatifd-langfuse` OR (if friction surfaces) the harness gets promoted to `whatifd.testing.adapter_conformance` per `whatifd-features` entry #1 in the same PR.
- [ ] Recorded smoke (if Inspect AI has a hosted scoring API surface): same `pytest-recording` discipline + cassette scrub patterns; cassette reviewed for user-content leakage before commit.

**Status:** open (4B.1 landed; 4B.2 + 9B remaining).

**Resolution:** closes when Phase 4B.2 ships the second sibling AND Phase 9B's real-adapter smoke covers both.

### Deterministic-subset extractor (Phase 9A.3)

**Source decision:** Phase 9A.3 (PR #62) introduces `whatifd.serialization.determinism.extract_deterministic_subset`. The function reads `v0.1.schema.json` via `importlib.resources.files` (zipimport-safe), keeps only top-level fields tagged `x-deterministic: true`, and warns via `DeterministicSubsetWarning` when input keys aren't in the schema (drift detection). The integration test `tests/integration/test_determinism.py` re-runs each Phase 9A scenario twice and asserts byte-equality on the subset via `canonical_json_bytes`.

**Rippled to:**
- **CI gate (future):** the determinism comparison surface is now a known artifact. A future Phase 9B / Phase 10 CI check that diffs deterministic subsets across runs (e.g., on PRs that touch the pipeline) should reuse `extract_deterministic_subset` rather than re-implement the schema lookup.
- **Schema-bump migrations (v0.2+):** when the schema adds a new top-level field with `x-deterministic: true`, `test_deterministic_field_set_matches_schema` MUST be updated in the same PR so the byte-equality assertion covers the new field. Producer-ahead-of-consumer drift surfaces as `DeterministicSubsetWarning` at runtime; missing schema-extractor sync surfaces as a test failure.
- **Banned-import discipline:** the test file routes its re-encode through `canonical_json_bytes` (in `whatifd.serialization`); any future helper that encodes for byte-comparison MUST live in the serialization package per the project's `json.dumps`-only-inside-`whatifd/serialization/` lint rule. The lint rule itself is one layer of cardinal #5's three-layer defense (it prevents bypassing `WhatifJSONEncoder`'s Sensitive-rejection check), but the immediate governing rule is the banned-import discipline, not cardinal #5 itself.

**Status:** open (extractor shipped; CI diff gate is downstream work).

**Owner / tracking:** the CI diff gate is the natural fit for the **Phase 10 release-prep CI hardening PR** (`.github/workflows/release.yml` or a new `determinism-diff.yml`). When that PR opens it MUST link this entry. If Phase 9B (real-adapter smoke) needs an earlier checkpoint, it can claim the work first by linking here from the 9B PR description; whichever PR consumes the extractor first owns the resolution. Until one of those PRs claims it, no GitHub issue exists — when one does, replace this paragraph with the issue number.

### Phase 9A walkthrough scenario coverage (4 of 6 in 9A.1+9A.2)

**Source decision:** Phase 9A.1 + 9A.2 cover walkthroughs 1–4 (Clean Ship, Don't Ship × 2, Inconclusive insufficient sample) end-to-end through `whatifd.pipeline.run_pipeline` against the synthetic stub. Walkthroughs 5 (cache corruption) and 6 (rerun-after-fix / diff) are deliberately deferred.

**Rippled to:**
- **Walkthrough 5 (cache corruption)** — recovery-path scenario already exercised by `tests/unit/whatifd/cache/test_recovery.py` and the `whatifd cache verify` CLI surface. Surfacing it through `run_pipeline` requires a parallel CLI integration harness (the cache-corruption signal flows via `whatifd cache verify` exit codes + the `cache_summary.policy_violations` field, not through the per-trace stream). Phase 9A.4 (failure injection) is the right home — it runs every `FAILURE_CODE_REGISTRY` entry through a CLI-level harness.
- **Walkthrough 6 (rerun-after-fix / diff)** — fully exercised by `tests/unit/whatifd/test_diff.py` against synthetic reports. The pipeline that produces the inputs IS exercised here (scenario 1 produces "before-fix"; downstream scenarios produce "after-fix"); the diff itself is tested at its own seam. Reproducing through `run_pipeline` would mostly re-test what `test_diff.py` already covers.

**Status:** open (4 of 6 covered; 5 and 6 tracked as deferred).

**Resolution:** closes when Phase 9A.4 lands the CLI failure-injection harness (covers walkthrough 5) and a Phase 9A.5 cross-pipeline+diff smoke test or explicit decision marks walkthrough 6 satisfied by `test_diff.py`.

### TODO: Sweep this catalog at Phase 4B and Phase 9B closure

**Source decision:** Phase 4 and Phase 9 each split into a structural half (4A/9A) and a real-adapter half (4B/9B). See `references/phases.md`.

**Rippled to:** every entry below whose Status mentions "Phase 4" or "Phase 9" without a sub-letter. Splitting the phases changes the granularity at which downstream cascades resolve — an entry previously blocked on "Phase 4" may now be load-bearing on 4B specifically, or may already be satisfied by 4A. The split does NOT auto-resolve any catalog entries; the reviewer must walk them.

**Status:** open (sweep procedure, not a resolvable cascade).

**Resolution:** when Phase 4B is formally gated as complete, walk this catalog top-to-bottom and update every entry whose Status references "Phase 4" — re-target to 4A or 4B as appropriate, or mark resolved if the structural half closed it. Repeat the sweep at Phase 9B closure. Leave this entry in place across both sweeps; remove it only when both 4B and 9B are merged AND the catalog has been walked end-to-end. Do not silently skip — the prose-only instruction in `phases.md` is not enforcement; this entry is the enforcement.

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
- `whatifd/decision/finding_codes.py` — registry module
- `whatifd/decision/fix_suggestions.py` — suggestion templates
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
- Per V0_1_DECISION_RECORD §6 (and 2026-05-05 skill-alignment addendum), `--accept-no-ci` is removed; `policy.max_ci_width` is the lever for accepting wider CIs.
- Doctrine docs updated: floor is about evidence existence, not evidence quality.
- Cohort propagation: `CohortResult.ci_computable` populated by stats stage, consumed by policy guard.

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
- `whatifd/types/sensitive.py` — wrapper implementation with __repr__, __str__, __format__, __reduce__ overrides
- `whatifd/serialization/encoder.py` — custom JSONEncoder that raises on unwrapped Sensitive
- `whatifd/serialization/graph_walk.py` — `assert_no_unredacted_sensitive(obj)` pre-write hook
- Banned-import lint: `json.dumps` only allowed in `whatifd/serialization/`
- Reference adapters need audit: every place that produces user-content fields wraps in Sensitive
- Manifest: `runtime.sensitive_unwraps` field captures audit log
- Tests: redaction snapshot tests, graph-walk tests, encoder tests

**Status:** open

**Resolution:** Phase 1 (types) implements wrapper; Phase 4 (adapters) wraps adapter outputs; Phase 5 (serialization) implements graph walk.

### Artifact-write call-site sequencing for graph walk

**Source decision:** `assert_no_unredacted_sensitive(report)` is layer (b) of cardinal #5 and MUST run at every artifact-write site BEFORE `encode_report_v01(report)`. The encoder's `default()` raise is the last-line fallback, not the primary defense — bypassing the graph walk reduces the three-layer guarantee to two.

**Rippled to:**
- `whatifd/cli.py` — `whatifd fork` artifact-write path (Phase 8) calls `assert_no_unredacted_sensitive` immediately before `encode_report_v01`
- Any future artifact-write site (cache-entry persistence, diff output, replay-snapshot dump) follows the same sequence
- Integration test (Phase 9): inject an unwrapped Sensitive into a stub report graph and assert the artifact-write fails at the graph walk, NOT the encoder fallback (proves layer (b) is wired, not skipped)
- Doc: `docs/runner-contract.md` (Phase 10) names the sequence so adapter authors don't reinvent the call site

**Status:** open

**Resolution:** Phase 8 wires the CLI call site; Phase 9 integration test pins the sequencing.

### Schema-file artifact contract (generated, drift-tested)

**Source decision:** `src/whatifd/report/schema/v0.1.schema.json` is a derived artifact mirroring `whatifd/report/models_v01.py::ReportV01`. The committed bytes match the output of `scripts/generate_schema.py`; a drift test (`tests/unit/whatifd/report/test_schema.py::TestSchemaDrift`) re-runs the generator and asserts byte equality. Cardinal #6 ("public schema hand-written") is satisfied by hand-writing the Python dataclass; the JSON file follows mechanically.

**Rippled to:**
- `whatifd/report/models_v01.py` — every field shape change requires a regenerate. The drift test fails CI otherwise.
- `whatifd/report/projection.py` — projection output must match the generated schema (encoded fixture key-coverage test pins it).
- Phase 6 replay pipeline — produces `ReplaySuccess`/`ReplayFailure` that flow into `cohort_results` / `failures`; any new field surfaces here as a schema bump.
- Phase 8 CLI — `whatifd report-migrate` stub references the committed schema as the v0.1 baseline; v0.2 migration logic reads the file at the published URI.
- Phase 9 integration — full `jsonschema`-library validation of golden reports (the unit-level smoke test only checks required-key coverage).
- Phase 10 release — schema published at `https://whatif.codes/schema/report/v0.1.json`; `$id` in the file already points at this URI.

**Status:** open

**Resolution:** drift test in place from Phase 5.5. Phase 9 adds `jsonschema`-library validation. Phase 10 publishes to the public URI. Schema-version bump (v0.1 → v0.2) requires regenerating into `v0.2.schema.json` plus a `whatifd report-migrate` stub.

### Per-trace ThreadPoolExecutor + leaked-thread-on-timeout pattern

**Source decision:** Phase 6.3a (PR #44) `whatifd.replay.kernel.replay_one_trace` enforces a wall-clock timeout via `ThreadPoolExecutor(max_workers=1)` + `Future.result(timeout=...)`. Python provides no portable way to kill a running thread, so on timeout the kernel calls `executor.shutdown(wait=False)` and returns immediately — the runner thread keeps running until the runner returns naturally. v0.1 accepts this with documented constraint that runners must be timeout-aware via inner I/O timeouts.

**Rippled to:**
- `whatifd/replay/kernel.py` (Phase 6.3a) — fresh executor per call, manual lifecycle (no `with` block — `with` would block in `__exit__` defeating the timeout). The test `test_slow_runner_produces_runner_timeout` asserts kernel returns within 10× the timeout budget.
- Phase 6.3b streaming pipeline (PR #45) — landed with double-executor pattern that is safe by construction. Outer `ThreadPoolExecutor(max_workers=N)` submits kernel CALLS; each kernel internally spawns its own `ThreadPoolExecutor(max_workers=1)` for runner timeout. The kernel returns synchronously even on timeout via `shutdown(wait=False)` on the inner executor and detaching the leaked runner thread. So the outer streaming pool's `shutdown(wait=True)` only waits for kernel RETURNS (fast), NOT for leaked runner threads. Timeouts do not serialize because kernel-return doesn't block on the leak. Peak threads = 2 * max_workers (one outer + one inner per concurrent kernel).
- Phase 6.3c async runner path (PR #46) — landed. `replay_one_trace_async` uses `asyncio.wait_for(coro, timeout=...)`; on expiry the task is cancelled cleanly via `CancelledError` and the runner's `try/finally` / `async with` cleanup runs at the next `await` boundary. Test `test_cancellation_runs_runner_cleanup` pins synchronous (within Python 3.11+ `wait_for` semantics) cleanup completion. `AsyncRunner` Protocol added in `whatifd.contract` as a runtime-checkable sibling to `Runner`. NO leaked-thread workaround on the async path; this gap is now closed for v0.1.
- v0.2 hardening candidate: subprocess pool for runners. Subprocesses CAN be killed (`Process.terminate`), so timeout enforcement becomes real. Trade-off: serialization overhead per trace (the runner state has to round-trip via pickle). Out of v0.1 scope.
- Documentation: `docs/runner-contract.md` (Phase 10) must spell out the inner-I/O-timeout requirement so runner authors know the wall-clock backstop is best-effort.

**Status:** open (acceptable for v0.1 with documented constraint).

**Resolution:** v0.2 subprocess-pool hardening, OR v0.2 stays on threads but documents more aggressively. Trigger condition: a real production user hits a runner-hang scenario where the leaked thread accumulates measurable resource pressure across many traces.

### Render subpackage boundary (`whatifd.render`)

**Source decision:** Phase 7 introduces a dedicated `whatifd.render` subpackage producing three Markdown / text formats from the same `ReportV01`:

  - **CI status** — ≤80-char one-line summary (Phase 7.3, PR #47, ✅).
  - **Summary section** — ≤30-line compact Markdown block (Phase 7.2).
  - **Full report** — five-section Markdown with anchored jump links + methodology block per cardinal #10 (Phase 7.1).

Each format is a pure function `(ReportV01) -> str`. Walkthrough-match tests against the committed `docs/walkthroughs/*.md` fixtures are the Phase 7 gate.

**Rippled to:**
- `whatifd/render/ci_status.py` (Phase 7.3) — verdict glyph + label + reason; severity-ranked finding selection; floor-failure fallback; defensive fallback for contract-violation upstream.
- `whatifd/render/summary.py` (Phase 7.2, PR #48) — 30-line block; degenerate compact-Ship form; anchored jump links to full-report sections (`#fix`, `#replay-validity`, `manifest.json`). The summary's forward-reference jump links are the **canonical splice point for Phase 8 CLI**: `whatifd fork` produces both summary (for PR-comment posting) and full-report (for `report.md` artifact); when concatenated with the full report, the forward references become live in-document navigation. Phase 8 must NOT rewrite the summary's anchor targets — Phase 7.1 will produce `<a id="fix">` / `<a id="replay-validity">` headings the summary points at.
- `whatifd/render/markdown.py` (Phase 7.1, 7.1a landed in PR #49) — `render_full_report(report) -> str` is the canonical full-report surface and the Phase 8 CLI splice partner for `render_summary`. 7.1a ships eight sections (Verdict header, Reason, Stats, Replay validity with `<a id="replay-validity">` anchor, Floor evaluation conditional on failure, Suggested next steps with `<a id="fix">` anchor, Methodology with all five reliability concepts named per cardinal #10, Manifest pointer). Outstanding: 7.1b wires `FIX_SUGGESTION_REGISTRY` templates per blocking finding (placeholder text held in 7.1a, pinned by `test_phase_7_1b_placeholder_message`); 7.1c walkthrough-match tests for all six `docs/walkthroughs/*.md` scenarios (Phase 7 gate). Phase 8 CLI consumes `render_summary` + `render_full_report` and concatenates; the summary's forward-reference jump links resolve to the anchors `render_full_report` produces.
- `whatifd/render/templates/` — one file per fix-suggestion code; placeholder consistency lint per phases.md.
- Three-format consistency test (Phase 7 gate) — no contradiction across CI status / summary / full report.
- Phase 9 integration — render the six golden `ReportV01` fixtures, assert byte-equal to `docs/walkthroughs/*.md`.

**Status:** open. 7.3 ✅ landed; 7.1 + 7.2 + walkthrough-match tests outstanding.

**Resolution:** Phase 7 closes when all three formats render and the six walkthroughs round-trip byte-equal.

### CLI must enforce two-affirmation before forensic-path code

**Source decision:** Phase 8.1 (PR #52) `whatifd/config.py::assert_two_affirmation(cfg, *, cli_profile)` enforces the cardinal-#7 cross-surface match between `reporting.profile` and the `--profile` CLI flag. The function is a leaf — it raises if the surfaces disagree; it does NOT short-circuit profile resolution on its own.

**Rippled to:**
- `whatifd/cli.py` (Phase 8.2) — the `whatifd fork` entry point MUST call `assert_two_affirmation(cfg, cli_profile=<--profile flag value>)` IMMEDIATELY after `load_config` returns and BEFORE any code path that resolves the redaction profile or constructs the artifact bundle. A failure to call leaves the CLI half of cardinal #7 unenforced; a `--profile forensic` invocation against a non-forensic config (or vice versa) would silently take the dangerous path.
- Phase 8 integration test — wires up a CLI invocation with mismatched surfaces and asserts non-zero exit + `ForensicAffirmationError` message.
- v1.0 generalization — additional dangerous flags (persistent acceptance, etc.) follow the same two-affirmation pattern; the CLI has a single chokepoint where all such checks fire before any dangerous capability activates.

**Status:** open (Phase 8.2 is the gate).

**Resolution:** Phase 8.2 wires the `assert_two_affirmation` call at the CLI's earliest pre-action point. `# TODO(cardinal #7)` comment at the call site so a future refactor that moves it sees the marker.

### `whatifd cache rebuild --strict` (deferred from v0.1)

**Source decision:** Phase 8.3 (PR #54) `rebuild` counts non-directory paths under `entries/` (stray files that shouldn't normally exist) via `RebuildResult.non_bucket_skipped` rather than erroring. The CLI prints the count; an operator running `whatifd cache rebuild` sees the anomaly. v0.1 chose the count-and-continue pattern over a hard error because:

1. The count is sufficient feedback for operator inspection.
2. A real user encountering frequent stray files is the trigger for the hard-error variant; without that signal, defaulting to error would surface false alarms (e.g., a `.DS_Store` macOS artifact).

**Rippled to (deferred):**
- `whatifd/cache/recovery.py::rebuild` would gain a `strict: bool = False` parameter; when True and `non_bucket_skipped > 0`, return a result with `error="stray_files_present"`.
- `whatifd/cli.py` `cache rebuild` would gain a `--strict` flag that wires through to the parameter.
- Test coverage for both branches.

**Status:** open (deferred).

**Resolution:** trigger is a real user encountering stray files often enough to want hard-error semantics. Until then, the count-and-continue default is correct. The `TODO(future)` marker at `rebuild`'s `non_bucket_skipped` branch points back to this entry.

### Walkthrough scenario 6 fixture delegation

**Source decision:** Phase 7.1c (PR #51) `tests/unit/whatifd/render/_walkthrough_fixtures.py::scenario_6_rerun_after_fix` delegates entirely to `scenario_1_clean_ship()` and only overrides `runtime.experiment_id`. Walkthrough 06 (`docs/walkthroughs/06-rerun-after-fix.md`) currently has identical stats to walkthrough 01; the delegation captures that equivalence directly.

**Risk:** if walkthrough 06 later diverges from 01 in stats (e.g., post-fix counts differ from the original clean-Ship counts), the delegation silently produces stale data — tests pass against scenario 1's stats, not scenario 6's. The builder's docstring carries the warning, but a reader skimming the SCENARIOS map won't see it.

**Resolution:** when scenario 6's walkthrough diverges, replace the delegation with explicit per-field overrides (or a fresh builder). The drift shows up as soon as any structural fidelity test fails; until then the delegation is the most-faithful representation of "scenario 6 == scenario 1 + recovery context".

**Status:** open (acceptable while walkthroughs 01 and 06 share stats).

### Replay subpackage boundary (`whatifd.replay`)

**Source decision:** Phase 6 introduces a dedicated `whatifd.replay` subpackage with a sealed-union typed result (`ReplayResult = ReplaySuccess | ReplayFailure`) as the per-trace pipeline output. `ReplayFailure` is the lightweight in-pipeline shape (registry-validated `code` with `stage="replay"`); the report-level `FailureRecord` is produced at aggregation via `make_failure_record`, which assigns the stable `id` and enforces required-details. Cardinal #1 boundary lives at `ReplayFailure.__post_init__`.

**Rippled to:**
- `whatifd/replay/result.py` (Phase 6.1) — sealed union + registry validation. Frozen, slotted, ReplayOutput referenced via TYPE_CHECKING to keep import cheap.
- `whatifd/replay/tool_cache.py` (Phase 6.2) — `ToolCache.from_trace(...)` raises `CacheMissError` which the pipeline converts to `ReplayFailure(code="tool_cache_miss")`. The exception is module-private; it never escapes the replay subpackage.
- `whatifd/replay/pipeline.py` (Phase 6.3) — generator chain consuming `Iterator[RawTrace]`, producing `Iterator[ScoreCase | ReplayFailure]`. Timeout / runner exception → `ReplayFailure(code="runner_timeout"|"runner_exception")`. Bounded concurrency (ThreadPoolExecutor for sync, asyncio.gather + semaphore for async).
- `whatifd/decision/aggregation.py` (Phase 2.7) — projects the `ReplayFailure` stream into `list[FailureRecord]` for `ReportV01.failures`. Required-details validation runs here (via `make_failure_record`), not at construction.
- `whatifd/decision/failure_codes.py` — adding a new replay-stage code requires (a) registering with `stage="replay"`, (b) updating `ReplayFailure` callers to construct it. The `__post_init__` registry check catches mismatches at the call site.
- Phase 9 integration — pipeline + aggregation tests pin the projection contract end-to-end.

**Status:** open

**Resolution:** 6.1 (sealed union) ✅. 6.2 (tool_cache + CacheMissError) and 6.3 (pipeline + concurrency + timeouts) close the subpackage. Phase 2.7 aggregation closes the projection contract; Phase 9 pins it via integration test on golden fixtures.

### Witness-token pattern for Ship

**Source decision:** `Ship` cannot be constructed without `FloorPassedProof` token; only `evaluate_floor()` produces tokens.

**Rippled to:**
- `whatifd/decision/floor.py` — `evaluate_floor()` and `_FLOOR_INTERNAL_TOKEN`
- `whatifd/types/verdict.py` — `Ship`, `DontShip`, `Inconclusive` with witness requirement on `Ship`
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
- `whatifd/report/models_v01.py` — public, versioned
- `whatifd/internal/` — internal types
- `whatifd/report/projection.py` — translation
- `whatifd/report/schema/v0.1.schema.json` — generated from `ReportV01`, committed
- CI tests: no internal imports in public; schema matches models; golden reports validate

**Status:** open

**Resolution:** Phase 1 (types) starts; Phase 5 (serialization) completes.

### Cohort-systemic detection rule

**Source decision:** Cohort-scope `FailureRecord`s are emitted by core when ≥50% of cohort traces fail with the same code.

**Rippled to:**
- Aggregation logic in `whatifd/decision/aggregation.py`
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
- `whatifd/types/sensitive.py` — `_audit_log` module-private structlog logger
- `manifest.runtime.sensitive_unwraps: list[SensitiveUnwrap]` (non-deterministic ordering)
- Renderer surfaces unwrap count in audit profile
- Schema: `sensitive_unwraps` annotated `x-deterministic: false`

**Status:** open

**Resolution:** Phase 1 (types) implements; Phase 5 (serialization) wires to manifest.

### CLI cache subcommands for v0.1 (`cache rebuild`, `cache unlock`, `cache verify`)

**Source decision:** Scenario 5 (cache corruption) recovery message instructs the user to run `whatifd cache rebuild --force`, `whatifd cache unlock`, or `whatifd cache verify`. None are in the v0.1 CLI surface. Phase 8.2 lists `whatifd cache rebuild` as conditional on Phase 0 surfacing it; Phase 0 has now surfaced it. The other two (`unlock`, `verify`) are not yet anywhere in the plan.

**Rippled to:**
- `whatifd/cli.py` — three new subcommands under a `cache` group
- `whatifd/cache/recovery.py` (new) — implementations: rebuild deletes `.whatifd/cache/entries/` and reports counts; unlock removes `.whatifd/cache/.lock` after PID-alive check; verify walks entries computing checksums against stored hashes
- Each subcommand needs its own exit-code semantics (success vs partial repair vs unrepairable)
- Docs: cache recovery section in `docs/getting-started.md` or a new `docs/cache.md`
- Tests: each subcommand tested with corrupted-cache fixtures
- The `unlock` command is structurally dangerous (could clobber a live lock); should it require two-affirmation per cardinal #7? Probably not — a CLI flag like `--i-am-sure` is sufficient since it's a recovery path, not an opt-in to a sensitive capability

**Status:** open

**Resolution:** Phase 8 (CLI) — bundle all three subcommands. Without scenario 5's recovery message is non-actionable.

### CLI `whatifd diff` for v0.1

**Source decision:** Scenario 6 (rerun-after-fix) shows `whatifd diff <prev-report.json> <new-report.json>` producing a verdict-change summary plus cohort-comparison table plus trace-level differences. Not in any phase plan.

**Rippled to:**
- `whatifd/cli.py` — `diff` subcommand
- `whatifd/diff/` (new) — diff computation over two `ReportV01` instances
- `whatifd/render/diff_markdown.py` (new) — Markdown renderer for diff output
- Diff also needs a JSON output shape (for downstream tooling); requires its own schema versioning decision (`DiffV01`?)
- Tests: diff round-trip; verdict-change matrix (Ship→Ship, Ship→DontShip, DontShip→Ship, Inconclusive→Ship, etc., 9 cells)
- Decision: ship in v0.1 or defer to v0.2?
  - Pro: rerun-after-fix is the most natural engineer workflow after iterating on a fix; without it engineers iterate by reading two reports side-by-side, which is the friction-pattern that drives skim
  - Pro: cardinal #8 (Inconclusive must be actionable) extends to "Don't Ship must be iterable" — diff makes the iteration concrete
  - Con: it's a separate CLI surface with its own renderer and its own schema version
- Recommendation: include in v0.1. The failure-rescue use case is fundamentally iterative, and the diff mode is what makes the iteration legible

**Status:** resolved — shipped in v0.1 as Phase 8.4 (PR #55).

**Resolution:** `whatifd diff <prev.json> <new.json>` lives at `src/whatifd/diff.py` (single module, not a subpackage — no `whatifd/render/diff_markdown.py` separation; the renderer is `render_diff_markdown` in the same file). v0.1 scope: verdict-state transitions, cohort row deltas, decision_findings added/removed (keyed on `(code, severity)`), failure-count delta. Renderer emits Markdown only — no `DiffV01` JSON output schema in v0.1 (downstream tooling reads the Markdown or re-runs `compute_diff` against the raw JSON). `whatifd/diff.py::load_report` deliberately reads raw dicts rather than reconstructing `ReportV01` so cross-version comparisons during migration don't fail spuriously.

**Deferred to v0.2:**
- Per-trace evidence diff (which traces newly improved / regressed) — **hard dependency edge** on the "Per-trace evidence schema (top improvements / regressions with judge rationale)" entry directly below. The diff cannot land before that schema does, because there is no typed shape to diff over. Any v0.2 milestone that schedules per-trace evidence diff MUST schedule the schema entry first or in the same PR.
- `DiffV01` JSON output shape — only motivated when downstream tooling appears that wants structured diff data.
- Verdict-change matrix tests (Ship→Ship, Ship→DontShip, … 9 cells) — current tests pin the load-bearing transitions; full matrix becomes useful when the renderer grows verdict-specific guidance.

### Per-trace evidence schema (top improvements / regressions with judge rationale)

**Source decision:** Scenarios 2 and 3 render top-N improvement and regression traces with structured Original / Replayed / Judge-rationale fields per trace. The current `ReportV01` types (`CohortResult`, `FailureRecord`, `DecisionFinding`) do not carry this data. Without a typed shape for it, the renderer has nothing to render.

**Rippled to:**
- New type in `whatifd/types/evidence.py`:
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

**Source decision:** Scenario 4 renders `(CI not computed: sample too small)` inline in the stats line for the baseline cohort. The `ci_computable: bool` flag captures *whether* CI was computed but not *why*. Without the reason, the renderer can't produce the right phrase — it can only say "CI not available" generically.

**Rippled to:**
- Extend `CohortResult` with `ci_unavailable_reason: Literal["sample_too_small", "zero_variance", "computation_failed", None]` (None when `ci_computable=True`)
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

**Source decision:** The Layer 4 telemetry dashboard (`scripts/skill-dashboard.sh`) computes paths like `$SKILL_DIR/SKILL.md` and `$SKILL_DIR/references/cascade-catalog.md`. `SKILL_DIR` is hardcoded to `.claude/skills/whatifd-design` *relative to the project repo root*. But in this workspace the canonical skill lives at `~/projects/self_dev/.claude/skills/whatifd-design/` — one level above the project repo, alongside the deliberation drafts. The dashboard cannot find it.

**Rippled to:**
- Layer 4 "Reference file usage" table prints `(skill not found at .claude/skills/whatifd-design)` instead of per-file read counts.
- Layer 4 "Cascade catalog" section prints "Cascade catalog not found" instead of open/in-progress/resolved/deferred counts.
- Layers 1, 2, 3 are unaffected (transcript copy, agent self-report, benchmark prompts don't depend on `SKILL_DIR`).

**Resolution options:**
1. **Co-locate the skill in the project repo**: copy or symlink `~/projects/self_dev/.claude/skills/whatifd-design/` into `project/.claude/skills/whatifd-design/`. Pros: dashboard works zero-config; the skill ships with the code. Cons: two source-of-truth copies that need sync; the deliberation drafts and the project repo evolve at different rates.
2. **Resolution walk**: dashboard walks up the directory tree from `$PWD` looking for `.claude/skills/whatifd-design/`. Stops at `$HOME` or `/`. Pros: zero-config; supports either layout. Cons: more script complexity.
3. **Env var override**: caller sets `WHATIF_SKILL_DIR=...` before invoking the dashboard. Pros: explicit, simple. Cons: not zero-config; muscle-memory mistake risk.
4. **Status quo + graceful degradation**: keep the hardcoded path; the dashboard's skill-related sections print informative "not found" messages. Layers 1–3 fully usable; Layer 4 partial.

**Recommendation:** option 2 (resolution walk). Single small script change, no duplication, no env-var ceremony. Falls back to option 4's degradation if the walk finds nothing.

**Status:** resolved (2026-05-05) — adopted option 1.

**Resolution:** the canonical skill now lives in the project repo at `.claude/skills/whatifd-design/` (curated set: SKILL.md + 9 reference files including this catalog). The deliberation drafts and the v0.1 decision record are deliberately kept private at the parent-workspace level; only files contributors should see on a clean clone are committed. Layer 4 dashboard works zero-config against the in-repo path; the resolution-walk option becomes unnecessary.

### Paired-delta as atomic unit

**Source decision:** The unit of statistical analysis is the paired trace delta. Original and replayed scores must not be analyzed as independent samples. See `references/practices.md` § "Statistical methodology".

**Rippled to:**
- `TraceDelta` internal type (float arithmetic) and `TraceDeltaReportV01` public type (DecimalString)
- Analysis API in `whatifd/internal/stats.py` accepts `Sequence[TraceDelta]`, never separate score arrays
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

**Source decision:** When tracer adapters provide real cluster keys, whatifd uses cluster bootstrap. When not available, whatifd assumes i.i.d. and discloses the assumption. Fabricating cluster structure for confirmatory verdicts is forbidden in v0.1.

**Rippled to:**
- `TraceSource.cluster_key_support()` method on the protocol
- `ClusterKeySupport`, `ClusterSelection`, `ClusteringPolicy` types
- `resolve_cluster_key()` resolver function
- Resolved choice recorded in `RunManifest` and `MethodologyDisclosure.bootstrap.cluster_key`
- `whatifd-langfuse` adapter declares its real cluster keys
- Forbidden: k-means on embeddings or other unstable heuristics for confirmatory verdicts

**Status:** required for v0.1 (declaration); cluster bootstrap implementation deferred to v0.2

**Resolution:** Phase 1 (types) and Phase 4 (adapters) implement declaration; Phase 2 cluster bootstrap implementation deferred.

### Causal-claim scope enforced

**Source decision:** whatifd is allowed to claim "associated regression under cached-tool replay." It is NOT allowed to claim "caused production regression." This is enforced via the `causal_claim_scope` literal field on `MethodologyDisclosure`.

**Rippled to:**
- `MethodologyDisclosure.causal_claim_scope: Literal["associated_under_cached_tool_replay"]` (sealed; v0.1 has only this value)
- Renderer uses "associated under cached-tool replay" phrasing throughout
- Doctrine in `references/practices.md` § "Causal language" enforces this verbally
- Future expansion (e.g., `"validated_against_holdout"`) is a v0.2+ minor schema bump

**Status:** required for v0.1

**Resolution:** Phase 1 (types), Phase 7 (renderer).

### `_AuditLog` process-singleton vs ContextVar isolation

**Source decision:** Phase 1.2 (`whatifd/types/sensitive.py`) ships `_audit_log` as a thread-safe but module-level singleton. Records from concurrent runs in the same process share the buffer. This is acceptable for v0.1's expected pattern (one whatifd fork per process), but breaks if a long-lived process orchestrates multiple sequential runs without explicit `drain()` between them, or if concurrent runs share a process.

**Rippled to:**
- `whatifd/types/sensitive.py` — current implementation
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

### `whatifd diff` arrow spacing consistency

**Source decision:** v0.1 ships `whatifd diff` with two arrow styles: the verdict line uses spaced ` → ` (`Don't Ship → Ship`), while cohort-table cells use unspaced `→` (`8→9 (+1)`). The unspaced form is deliberate — cohort cells live inside Markdown table columns where the tight form preserves column budget on narrow viewers; the verdict line is full-width prose where spacing reads cleaner.

**Rationale for deferral:** Cosmetic, not a correctness issue. Aligning would either (a) widen cohort cells (worse for narrow viewers) or (b) tighten the verdict line (worse for readability). The right answer probably involves measuring real PR-comment renders before picking.

**Trigger for resolution:** v0.2 renderer pass — when per-trace evidence diff lands and the cohort table grows, revisit the column-width budget holistically.

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

**Rippled to (Phase 3 lock implications, recorded with PR #33):**
- `whatifd/cache/lock.py` is filesystem-local: `fcntl.flock` + lock-file PID/create_time provenance assume a single-host, single-filesystem cache directory. The module docstring documents this scope and refuses unsupported filesystems (NFS surfaces as `ENOLCK`/`EOPNOTSUPP` with a clear error message).
- Multi-tenant resolution will require either: (a) per-tenant cache subdirectories under a shared root (still filesystem-local — extends naturally from the v0.1 primitive), or (b) a network-coordinated lock (Redis, etcd, or NFS-safe filesystem locking — note that `O_EXLOCK` is BSD/macOS-only and not available on Linux, so a portable NFS-safe path likely means a `lockf`/network-coordinated approach rather than `O_EXLOCK`). Option (a) preserves the v0.1 lock primitive; option (b) replaces it.
- Whichever route, the `LockFileContent` shape (pid + process_start_time + hostname + started_at) generalizes: `hostname` is already recorded for cross-host diagnostics, and a v0.3 multi-tenant entry would add `tenant_id` via the `CacheMeta.extra` forward-compat path.

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

**Rationale for deferral:** HTE estimation typically needs much more data than a single whatifd run provides. v0.3 can implement causal forests or simpler HTE methods if sample sizes warrant. Subgroup findings are exploratory unless promoted to inferential primary endpoints with multiplicity correction.

**Trigger for resolution:** v0.3 if sample sizes and use cases support it. Default treatment: exploratory, BH-FDR corrected, labeled as exploratory in report.

### Bayesian decision panel

**Source decision:** v0.1 ships frequentist output exclusively. Bayesian framing (`P(regression rate > threshold | observed evidence)`) is deferred and may remain optional indefinitely.

**Rationale for deferral:** Bayesian output requires priors. Priors are politically sensitive in CI tooling — a skeptical user can ask "why did your prior say this prompt change was safe?" Frequentist output has cleaner political legibility for a CI gate. Bayesian framing is best as an internal research tool until the doctrine matures around prior elicitation.

**Trigger for resolution:** v0.3 optional output panel, if at all. Frequentist remains the default.

### Causal claims beyond replay association (rejected, not deferred)

**Source decision:** whatifd is allowed to claim "associated regression under cached-tool replay" and forbidden from claiming "caused production regression." This is a permanent restriction.

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

**Source decision:** whatifd is orchestration, not compute. Generic high-performance Python tools (Ray, ProcessPool for replay, MKL, SIMD vectorization, BF16/INT8 precision, Numba `@njit`, ONNX Runtime, OpenVINO, shared-memory IPC) are explicitly rejected for the core. They conflict with one or more trust-first guarantees: structural typing, runner contract simplicity, determinism, redaction enforcement, import budget. See `references/practices.md` § "What this workload is NOT".

**Rationale for deferral / non-resolution:** This is a permanent rejection, not a deferral. It is captured here because future contributors will propose these tools and the rejection rationale must survive the conversation. The cascade entry exists so the question is closed, not re-opened.

**Trigger for resolution:** None. If a future workload class actually requires compute (e.g., a v2.0 feature that does local model inference inside whatifd), this decision is revisited as part of that feature's design — not as an optimization of v0.1's existing pipeline.

### Schema migration tooling beyond v0.1.x

**Source decision:** v0.1 ships `whatifd report-migrate` as a no-op stub for v0.1.x patches. Real migration logic kicks in at v0.2.

**Rationale for deferral:** No real migrations needed within v0.1.x.

**Trigger for resolution:** v0.2 first minor release.

### `CohortResult` rate-count partition — tighten `<=` to `==` at Phase 2.6

**Source decision:** PR #24 lands the rate-count partition (`improved_count`, `unchanged_count`, `regressed_count`) on `CohortResult` with `__post_init__` enforcing `improved + unchanged + regressed <= scored`. The lenient `<=` constraint preserves backward compatibility with pre-Phase-2.5b construction sites (test fixtures, the floor evaluator) that default rate counts to 0.

**Rippled to:**
- `whatifd/types/cohort.py::CohortResult.__post_init__` — change the invariant from `count_sum > self.scored` to `count_sum != self.scored` once Phase 2.6's projection layer populates the partition exhaustively for every required cohort.
- `tests/unit/whatifd/types/test_cohort.py::TestRateCountInvariant` — `test_partial_population_passes` flips from a positive test to a `pytest.raises(InvariantViolationError)` test. `test_default_zero_counts_pass` either flips too OR is removed (Phase 2.6 should never produce `scored > 0` with all-zero partition; a structural failure in projection).
- `tests/unit/whatifd/decision/guards/_helpers.py::failure_cohort` and `baseline_cohort` — auto-resolve `_resolve_scored = max(default, sum)` becomes `_resolve_scored = sum if sum > 0 else default`. Phase 2.6 tests should pass exhaustive partitions explicitly.
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
2. ~~PR adding `ci_unavailable_for_required_cohort` to `FINDING_CODE_REGISTRY` + `FIX_SUGGESTION_REGISTRY` → land `ci_availability_guard`~~ → **resolved by Phase 2.5c**: finding code added (severity=blocks_all, derived_from_failures="always"); fix-suggestion entry added; `ci_availability_guard` lands and emits one finding per affected required cohort. Pending: failure-record plumbing (`derived_from_failures` placeholder used; real wiring in Phase 2.6 / projection layer). Skill-alignment 2026-05-05: the entry's earlier `--accept-no-ci` escape-hatch guidance was removed — V0_1_DECISION_RECORD §6 forbids the flag.
3. Phase 3 cache subsystem PRs → cache metadata reaches `CohortResult` via projection layer → land `cache_staleness_guard`.
4. Phase 2.6 verdict computation PR → `primary_endpoint_guard` lands as part of the multi-endpoint resolution. Also: `ci_availability_guard`'s emitted findings need real `derived_from_failures` wiring once failure records are threaded end-to-end (placeholder `["pending_phase_2_6_plumbing"]` is in place today).
   - **Partial resolution by Phase 2.6b (PR after #26):** `primary_endpoint_guard` lands as a configurable rate-based guard that consolidates the Phase 2.5b `failure_improvement_guard` + `baseline_regression_guard` pair. Reads `policy.primary_endpoints` and dispatches by direction (`improvement_above_threshold`, `non_regression_below_threshold`); emits the existing finding codes (`failure_improvement_below_threshold`, `baseline_regression_above_threshold`) — no registry change. The two hardcoded Phase 2.5b guards are deleted; their tests migrate to `test_primary_endpoint.py`.
   - **Remaining for Phase 2.6c:** real `derived_from_failures` wiring on `ci_availability_guard` (replace `_PHASE_2_6_PLACEHOLDER`). The previously-tracked `accept_no_ci` arithmetic was removed in the 2026-05-05 skill-alignment pass — V0_1_DECISION_RECORD §6 forbids the flag, so 2.6c is just the failure-record plumbing.

### Guard pre-parse caching — Phase 2.6 verdict computation

**Source decision:** PR #23 ships two guards (`practical_delta_guard`, `improvement_observation_guard`) that each independently call `parse_decimal_string(failure.median_delta, ...)`. When both run on the same cohort the parse happens twice. Phase 2.5 keeps each guard self-contained for testability and reasoning; the redundancy is acceptable at v0.1 scale (microseconds per call).

**Rippled to:**
- `whatifd/decision/guards/improvement_observation.py` — docstring marks the redundant parse with reference to this cascade entry.
- Phase 2.6 verdict computation introduces a context object (or a pre-parsed `cohort_results_parsed` view) that pre-parses `median_delta` once per cohort and passes the float to guards alongside the `CohortResult`.
- Guard signatures may evolve from `(cohorts, policy)` to `(cohorts, policy, parsed)` or similar; the `Guard` Protocol updates accordingly.
- Existing guards retain a thin parse-fallback path so they remain self-contained when called outside the verdict pipeline (tests, ad-hoc usage).

**Status:** open

**Resolution:** Phase 2.6 — verdict computation pre-parses cohort numerics once and threads the parsed values to every guard. Cardinal #1 invariant (parse-on-failure raises `InvariantViolationError`) moves to the pre-parse step; guards then read floats directly.

**Trigger for resolution:** Phase 2.6 PR.

### `parse_decimal_string` permissiveness — soft warn now, tighten at Phase 5

**Source decision:** PR #23 ships `parse_decimal_string` early (one half of the Phase 5 serialization helper pair) so Phase 2.5 guards can validate `CohortResult.median_delta`. The current implementation accepts anything `float()` parses but emits a `DeprecationWarning` on inputs that violate the committed canonical shape (no decimal point, scientific notation). Phase 5 will flip the warning to a hard `InvariantViolationError` and pin exact precision per field.

**Rippled to:**
- `whatifd/serialization/decimal.py` — replace the `FutureWarning` branch with `raise InvariantViolationError(...)`. The canonical regex (`_CANONICAL_DECIMAL_RE`) becomes the gate.
- `tests/unit/whatifd/serialization/test_decimal.py::TestParseDecimalStringNonCanonicalWarns` — flips from `pytest.warns(FutureWarning)` to `pytest.raises(InvariantViolationError)` for every test in that class.
- **Flip-test list synchronization (PR #23 reviewer note):** as more callers adopt `parse_decimal_string` (each subsequent guard, the verdict layer, the renderer), every test that uses `pytest.warns(FutureWarning, match=...)` against a non-canonical input becomes part of the Phase 5 flip surface. Phase 5's PR must grep for `pytest.warns(FutureWarning` across `tests/` and update each occurrence in lockstep. Today there's only one location; the count grows.
- `format_decimal_string` (new in Phase 5) pins per-field precision. The current canonical shape is `^-?\d+\.\d+$`; Phase 5 may narrow further (e.g., exactly 3 fractional digits for ratios).
- **Phase 5 helper-adoption ripple (PR #24 reviewer note):** when `format_decimal_string` lands, the inline `format(rate, '.3f')` calls in `whatifd/decision/guards/{baseline_regression,failure_improvement}.py` (and the symmetric `format(threshold, '.3f')` in both files) should switch to the helper. Today's two sites are bounded; the helper-extraction prevents drift if a third rate-based guard adds the same pattern. Tests for the two `TestSubPrecisionThresholdDivergence` cases (in `test_failure_improvement.py`) will need to flip from "documented divergence pinned" to "round-trip equality pinned" once the canonical shape is enforced.
- **Float-equality stability (PR #23 reviewer note):** the `practical_delta_guard` boundary check `median_delta_float <= policy.practical_delta_epsilon` relies on `float("0.050") == 0.05` round-tripping exactly. When `format_decimal_string` lands with a guarantee that policy thresholds round-trip through `format(value, '.3f')` to identical bytes, this concern dissolves. The Phase 5 PR should pin a boundary-stability test asserting `parse(format(x)) == x` for the canonical thresholds.

**Status:** open — soft-warning phase active.

**Resolution:** Phase 5 — `format_decimal_string` lands and pins the canonical shape; `parse_decimal_string` tightens warning → error. The two functions become a round-trip pair: `parse(format(x)) == x` for every numeric x in the determinism budget.

**Trigger for resolution:** Phase 5 serialization layer PR.

### Inconclusive renderer must distinguish floor_failures from blocking_findings

**Source decision:** PR #26 (Phase 2.6a) reviewer F2 noted that the floor-failure-Inconclusive case populates BOTH `Inconclusive.floor_failures` AND `Inconclusive.blocking_findings` from guard outputs. The data structure is honest: the two fields are distinct on the type. But a renderer that prints `blocking_findings` without also surfacing `floor_failures` could mislead a reviewer into thinking the guard finding drove the verdict — when in fact the floor failure is the structural reason.

**Rippled to:**
- `whatifd/render/markdown.py` (Phase 7) — the Inconclusive renderer must:
  1. ALWAYS surface `floor_failures` first (cardinal #2 structural reason takes precedence).
  2. Surface `blocking_findings` SECOND, framed as "guard observations" rather than "verdict drivers".
  3. Never print `blocking_findings` alone for a floor-failure verdict (the misleading-class case).
- `tests/integration/test_walkthroughs.py` (Phase 9) — walkthrough scenario 4 (Inconclusive insufficient sample) is the empirical reviewer for this rendering rule. The committed walkthrough Markdown shows `floor_failures` first; the renderer test must produce identical output.
- Doctrine cross-reference: cardinal #3 ("disclosure necessary but not sufficient") — the renderer is the disclosure surface; if it buries the floor reason, disclosure has been compromised even though the data was honest.

**Status:** open

**Resolution:** Phase 7 (rendering) — Inconclusive renderer reads both fields and orders the output per the rule above. Walkthrough scenario 4 round-trip test pins the contract.

**Trigger for resolution:** Phase 7 renderer PR.

### Direction-keyed finding codes for v0.2 multi-cohort `primary_endpoint_guard`

**Source decision:** PR #27 (Phase 2.6b) introduced `primary_endpoint_guard` reading `policy.primary_endpoints`. The guard reuses Phase 2.3's existing finding codes (`failure_improvement_below_threshold`, `baseline_regression_above_threshold`), which hardcode the v0.1 default cohort identities (`failure`, `baseline`) into the code namespace. The findings agent reviewing PR #27 (F1) flagged that this leaks v0.1 cohort assumptions into the public schema: a v0.2 custom policy declaring `PrimaryEndpoint(cohort="warmup", direction="improvement_above_threshold")` would emit `failure_improvement_below_threshold` even though the cohort is `"warmup"` — code and message would disagree about which cohort is at fault. Reader-facing tooling that filters on finding codes would mis-categorize non-canonical cohort runs.

**Why this is acceptable for v0.1:** v0.1 is failure-rescue-only (Phase 0.3 audience-distribution decision). Default cohorts are `failure` + `baseline` only; the finding-code names are truthful for the default. No v0.1 shipped path exercises the mismatch.

**Rippled to:**
- `src/whatifd/decision/guards/primary_endpoint.py` — dispatch logic emits direction-keyed codes (`primary_improvement_below_threshold`, `primary_non_regression_above_threshold`); the cohort name moves to `details["cohort"]`.
- `src/whatifd/decision/finding_codes.py::FINDING_CODE_REGISTRY` — adds the new codes; deprecates the v0.1 codes (kept for one minor cycle per the schema-versioning promotion-path rules in `references/contracts.md`).
- `src/whatifd/decision/fix_suggestions.py::FIX_SUGGESTION_REGISTRY` — adds matching fix-suggestion entries for the new codes.
- `tests/unit/whatifd/decision/guards/test_primary_endpoint.py` — adds a `TestNonCanonicalCohortNames` class exercising the configurable surface with custom cohort names (e.g. `"warmup"`, `"regression"`); the test would have caught the v0.1 mismatch empirically.
- Doctrine cross-reference: cardinal #6 (public schema is hand-written; internal types refactor freely) — finding codes ARE part of the public schema; the rename is a v0.2 minor bump per the schema versioning rules.

**Sibling concerns folded into this entry (PR #27 bot iter-3):**
- **Per-endpoint thresholds.** `_evaluate_non_regression` reads `policy.max_baseline_regression_ratio` regardless of which cohort the endpoint targets. A v0.2 `PrimaryEndpoint(cohort="warmup", direction="non_regression_below_threshold")` would silently use the baseline threshold. Symmetric for `_evaluate_improvement`. v0.2 should thread the threshold through `PrimaryEndpoint` (e.g., `threshold: float | None = None` falling back to the policy-level default by direction) so per-endpoint thresholds are explicit.
- **`primary_endpoints` cohorts ⊆ `required_cohorts` invariant.** Today both fields are independent on `DecisionPolicy`; no validator enforces the subset relation. A user who declares an endpoint on a non-required cohort sees the endpoint silently abstain when the cohort is missing (the guard's intentional silent-skip + the floor's `required_cohort_present` rule catches missing REQUIRED cohorts only). v0.2 either adds a Pydantic validator on `DecisionPolicy` (ergonomic for misconfiguration) OR documents this as best-effort-by-design. The decision lands with the rest of the multi-cohort surface.

**Status:** open (v0.2 work — not blocking v0.1 schema freeze).

**Resolution:** v0.2 minor release. New direction-keyed codes shipped; v0.1 codes deprecated with one-minor-cycle notice; promotion-path rules in `references/contracts.md` followed.

**Trigger for resolution:** v0.2 minor release PR (concurrent with `regression_check` cohort expansion or other multi-cohort work).

### `ci_meaningful` policy-guard wiring

**Source decision:** Skill-alignment pass (2026-05-05) restored the `CohortResult` CI split per V0_1_DECISION_RECORD §2: `ci_computable` (structural, read by `ci_availability_guard`) vs `ci_meaningful` (policy-quality, defaults True). The width-vs-`policy.max_ci_width` check that populates `ci_meaningful=False` is not yet wired — `max_ci_width` defaults to None today, and there is no guard that consults the field.

**Status note (2026-05-06, post-PR #35):** Phase 3 (cache subsystem) closed without this guard landing. The original entry's "Phase 3 (cache + stats layer)" trigger conflated two distinct subsystems — Phase 3.1–3.5 covered cache only. The stats layer that produces `ci_lower`/`ci_upper`/`median_delta` is implicit in Phase 6 (replay pipeline) or wherever bootstrap CI lands; phases.md does not yet locate it explicitly. Trigger updated below.

**Rippled to:**
- Phase 3 stats layer: when `ci_computable=True`, compute the CI width (`ci_upper - ci_lower`) as float; if `policy.max_ci_width is not None and width > max_ci_width`, set `ci_meaningful=False`.
- New guard `ci_meaningful_guard` (or fold into a generalized `ci_quality_guard`) at policy severity `blocks_ship` (NOT `blocks_all` — meaningfulness is policy quality, not structural). Emits a finding code like `ci_too_wide_for_required_cohort`.
- Finding code + fix-suggestion entries land alongside the guard.
- Cardinal #2 boundary preserved: `ci_computable` stays at `blocks_all` (Inconclusive); `ci_meaningful` stops at `blocks_ship` (DontShip).

**Status:** open

**Resolution:** the stats layer that produces `ci_lower`/`ci_upper` wires the width computation when `ci_computable=True`; the policy guard lands in the same PR or immediately after. Test: a cohort with `ci_computable=True, ci_meaningful=False` produces `DontShip`, not `Inconclusive`. The stats layer's phase-plan home is TBD — currently implicit in Phase 6 replay pipeline; phases.md should pin this explicitly when Phase 4/5/6 sequencing is finalized.

**Trigger for resolution:** the PR that introduces bootstrap CI computation (wherever in the phase plan that lands).

### Run-level FloorFailure projection

**Source decision:** Phase 5.2 projection (PR #38) flattens internal `Verdict` into `ReportV01`. The internal `Inconclusive` carries `floor_failures: list[FloorFailure]` aggregating run-level structural failures (including run-scope failures like "required cohort missing" that have no per-cohort home). v0.1 `ReportV01` has no top-level `floor_failures` field; per-cohort failures travel through `cohort_results[].floor_failures`, but the run-level aggregate is dropped on the wire.

**v0.1 design choice:** drop the run-level aggregate. Pinned by `tests/unit/whatifd/report/test_projection.py::TestFloorFailuresProjection`. For most run shapes this is information-preserving (the failures appear under their cohort). For the missing-cohort case, the floor failure is lost from the wire — readers see `verdict_state="inconclusive"` and an empty cohort list with no structured explanation of what was missing.

**Rippled to (v0.2 schema decision):**
- Adding `ReportV01.floor_failures: list[FloorFailure]` is patch-level per `references/contracts.md` §"Schema versioning" (new optional field with default).
- Projection updates: `_flatten_verdict` returns the run-level aggregate; `project_to_report_v01` stamps it into the new field.
- Tests in `test_projection.py` update to assert the field is populated for missing-cohort cases.
- Phase 7 renderer surfaces run-level vs per-cohort floor failures distinctly (the missing-cohort case currently renders awkwardly with no cohort to anchor the failure under).

**Status:** open

**Resolution:** v0.2 minor (or v0.1.x patch since it's purely additive). The decision is whether the missing-cohort case is rare enough to keep dropping (and surface via `decision_findings` only) or worth a dedicated wire field.

**Trigger for resolution:** the first user-facing report that exhibits a missing-cohort case AND the operator complains about the loss of structured floor-failure data, OR the v0.2 schema-bump cycle that revisits ReportV01 fields.

### Serialization ↔ report ↔ cache import cycle

**Source decision:** Phase 5.3 (PR #39) lands `WhatifJSONEncoder` in `whatifd/serialization/encoder.py`. The encoder needs to reference `ReportV01` from `whatifd.report.models_v01` (for `encode_report_v01`'s typed signature). This produces a runtime cycle:

```
whatifd.serialization.encoder
  → whatifd.report.models_v01 (for ReportV01 annotation)
  → whatifd.cache.summary (CacheSummary on ReportV01)
  → whatifd.cache.__init__ (re-exports lock surface)
  → whatifd.cache.lock (uses canonical_json_bytes for lock-file writes)
  → whatifd.serialization (back to start)
```

**v0.1 mitigation pattern:** `TYPE_CHECKING` for type-annotation-only imports; function-level imports inside method bodies for runtime references; module-level prime imports where load-order matters. Three confirmed sites in v0.1:

1. `whatifd/serialization/encoder.py::encode_report_v01` — TYPE_CHECKING import for the `ReportV01` annotation, lazy import inside the function body for the runtime `isinstance` guard.
2. `whatifd/contract/__init__.py::ToolCache._key` — lazy import of `canonical_json_bytes` inside `_key()`. A top-level import on `whatifd.contract` cycles through `whatifd.serialization.lock_io → whatifd.cache._types → whatifd.cache.lock → whatifd.serialization`.
3. `whatifd/replay/tool_cache.py` (Phase 6.2, PR #43) — top-level `import whatifd.cache  # noqa: F401` prime. The module loads `whatifd.contract.ToolCache` which lazy-imports `canonical_json_bytes` at call time; without the prime, running `whatifd.replay` tests in isolation triggers `ImportError: cannot import name 'parse_lock_file_content' from partially initialized module 'whatifd.serialization'`. The prime forces `whatifd.cache` to load completely before any `_key()` call resolves the `whatifd.serialization` import.

The cycle is broken at import time because `TYPE_CHECKING` is False at runtime; lazy imports at call time run after all modules finish loading; the prime forces the dependent subpackage to load eagerly so the runtime lazy imports always find a fully-initialized target.

**Rippled to:**
- Future Phase 5.4 (`assert_no_unredacted_sensitive` graph walk) will face the same cycle and use the same pattern.
- Future Phase 5.5 (schema generation) will read `ReportV01`'s type signature; same TYPE_CHECKING approach.
- A v0.2 reorganization that moved `whatifd.cache.lock` off `canonical_json_bytes` (via inlining or a new dependency direction) would break the cycle structurally and let the imports be straightforward; this is the cleanest end-state but not v0.1 scope.

**Status:** open (acceptable workaround for v0.1).

**Resolution:** v0.2 architectural cleanup PR that re-evaluates the layering. The cycle exists because cache/lock writes lock files via the centralized canonical encoder; one option is to inline canonical-JSON in lock.py (small duplication but clean layering), another is to introduce a `whatifd.serialization.boundaries` module that holds the type-only annotations.

**Trigger for resolution:** v0.2 layering audit, or sooner if the TYPE_CHECKING + lazy-import pattern becomes a maintenance burden (multiple Phase 5 sub-phases needing the same workaround).

### Adapter factory hardcodes Langfuse cohort_classifier (Phase 10.1)

**Source decision:** `src/whatifd/adapters/factory.py::_build_langfuse_source` constructs `LangfuseTraceSource(cohort_classifier=lambda t: "failure" if "failure" in (getattr(t, "tags", None) or []) else "baseline", ...)`. The classifier is hardcoded to a tags-based binary check. The `SourceConfig` Pydantic model has no field to override it.

**Forward consequences:**
- v0.2 adds config-driven classifier selection (e.g., `source.cohort_classifier: "tags" | "metadata.<key>" | "user_id_pattern:<regex>"`). The `SourceConfig` schema gains an optional field; the factory dispatches.
- Operators on v0.1 whose Langfuse projects don't tag traces with `"failure"` / `"baseline"` MUST patch the factory or use the programmatic path until v0.2 lands.

**Status:** open (acceptable for v0.1 — matches the documented Langfuse-readme convention).

**Resolution:** v0.2 schema bump that adds `SourceConfig.cohort_classifier`. Until then, the factory's lambda is the single point of hardcoded policy; document-the-default discipline (the `_build_langfuse_source` docstring + this entry) is the bridge.

**Trigger for resolution:** the first user request for non-tags-based classification, OR v0.2 release planning (whichever fires first).

### Adapter factory has no Langfuse-host reachability check (Phase 10.1)

**Source decision:** `_build_langfuse_source` constructs `Langfuse(host=..., public_key=..., secret_key=...)` without any timeout, retry, or pre-flight reachability probe. The Langfuse SDK has its own internal HTTP-level timeouts; if the configured host is unreachable, the first `api.trace.list(...)` call hangs (or errors) at fork-time, not at config-load time.

**Forward consequences:**
- A typo in `LANGFUSE_HOST` (or a stale `LANGFUSE_BASE_URL`) silently delays the failure to mid-fork instead of surfacing it at startup as `AdapterFactoryError`. The operator gets a less actionable error.
- Phase 10.4 (`_run_fork_pipeline` body) inherits this — the fork pipeline's first contact with Langfuse is the trace-list call, not a connection probe.

**Status:** open (acceptable for v0.1 — matches the Langfuse SDK's own behavior and avoids reaching outside the dispatch responsibility).

**Resolution:** v0.2 may add a `--check-source` pre-flight subcommand (`whatifd source check`) that does an `api.trace.list(page=1, limit=1)` and converts any error into a setup-failure exit. Less invasive than wrapping every adapter construction in a probe.

**Trigger for resolution:** the first Langfuse-host misconfiguration bug report, OR v0.2 CLI scope review.

### Phase 11: scorer projection through `run_pipeline` (Phase 10.4 deferred)

**Source decision:** Phase 10.4's `_run_fork_pipeline` constructs `MethodologyDisclosure.judge` with `rendered_prompt_hash` and `rubric_hash` set to the placeholder `"v01-cli-placeholder-no-scorecase"`. These hashes need a representative `ScoreCase` to compute via `scorer.cache_key_components(case)`, but the dispatcher does not have one at fixture-build time — scoring happens downstream inside the `delta_fn` closure.

**Forward consequences:**
- v0.1 reports carry placeholder strings instead of real prompt/rubric provenance hashes. Cardinal #10 satisfied via the explicit non-hash placeholder (NOT zero-bytes that would look like real hashes), but the rubric/prompt identity isn't actually pinned in the methodology section.
- Phase 11 widens `run_pipeline` to accept the scorer directly and project the first-trace cache-key components into the methodology disclosure; the placeholder string disappears.

**Status:** open (acceptable for v0.1 — placeholder is human-readable; cardinal #10 truthfulness preserved).

**Resolution:** Phase 11 `run_pipeline(... , scorer)` widening + per-trace cache-key-components projection into methodology.

**Trigger for resolution:** the first user request for prompt/rubric-version invalidation in cached reports, OR Phase 11 release planning.

### Phase 11: shared asyncio loop for async-runner trace stream (Phase 10.3 deferred)

**Source decision:** Phase 10.3's `cli_pipeline.build_delta_fn` wraps each async-runner trace in `asyncio.run(...)` — one event loop created and torn down per trace. Defeats `httpx.AsyncClient` connection reuse for runners that build a client per call (the natural async pattern, since clients are loop-bound).

**Forward consequences:**
- Async-runner users with connection-reuse needs hit per-trace TCP/TLS handshake overhead.
- Sync runners get reuse via `httpx.Client` normally — async users can switch to the sync API as a v0.1 workaround.

**Status:** open (acceptable for v0.1 — workload is I/O-bound by judge latency, not connection setup; sync API is the documented escape).

**Resolution:** Phase 11 adds an optional `event_loop` parameter (or context-manager) to `build_delta_fn` so the same loop services every trace in the stream. Existing closure signature stays compatible.

**Trigger for resolution:** the first benchmark showing connection-setup is non-negligible, OR a user report of high handshake overhead, OR Phase 11 release planning.

### Phase 11: `inspect_ai` config-loaded `score_fn` (Phase 10.1 deferred)

**Source decision:** Phase 10.1's `build_scorer(ScorerConfig(adapter="inspect_ai"))` raises `AdapterFactoryError` because v0.1 cannot load a user-supplied `score_fn` from config (it's user code, not config data). Operators wanting Inspect AI judging must use the programmatic `run_pipeline` API documented in `docs/getting-started.md`.

**Forward consequences:**
- v0.1 CLI fork against real Inspect AI judges is not supported. Stub-stub or programmatic-only paths work.
- Phase 11 adds a config field like `scorer.score_fn: "python:<module.path>:<attr>"` and routes through the runner-loader pattern from Phase 10.2.

**Status:** open (acceptable for v0.1 — the factory error is actionable, pointing operators at the programmatic path).

**Resolution:** Phase 11 schema extension + factory dispatch; reuses the runner-loader's `python:<module>:<attr>` resolution.

**Trigger for resolution:** the first user request for CLI Inspect AI runs, OR Phase 11 release planning.

### `RunManifest.environment.dependencies` ordering nondeterminism (deferred from Phase J)

**Source decision:** Phase J (PR #95) widened `x-deterministic` annotations into `RunManifest` sub-fields but left the entire `EnvironmentFingerprint` subtree (`environment.python`, `environment.platform`, `environment.whatif_version`, `environment.dependencies`) tagged non-deterministic. The first three are inherently host-specific; `dependencies` is the load-bearing one — it's a `Mapping[str, str]` of installed package versions whose ordering depends on pip's resolution graph at install time. Different build hosts can produce equivalent dependency *contents* in different *orderings*, so the field is non-deterministic by serialization shape even when semantically equal.

**Why this is carried forward, not closed:** today no consumer reads `environment.dependencies` for cross-run comparison. The moment one does (Phase L+'s `whatifd diff` extends to environment drift, OR a Phase M-class audit-bundle integrity check runs `assert manifest_a == manifest_b` on archived runs across machines), the ordering nondeterminism surfaces as spurious diffs.

**Resolution path when triggered:**
1. Canonicalize the field at projection time: sort `dependencies` items by package name in `whatifd.report.projection` before encoding. This is a serialization-only fix — internal dataclass keeps the dict shape, the wire form gets stable ordering.
2. Promote the field to `x-deterministic: true` via the Phase J `_DETERMINISTIC_FIELDS` mechanism (extending it to `EnvironmentFingerprint`).
3. Add a cross-platform byte-equality test on the `environment.dependencies` projection specifically (the existing Phase J cross-platform job runs `scenario_clean_ship` only and excludes runtime sub-fields beyond the nine documented-deterministic ones).

**Trigger for resolution:** first consumer that reads `environment.dependencies` for cross-run or cross-host comparison. Until then, the field's non-determinism is a known and acceptable shape, not a bug.

**Source telemetry:** flagged as a carried-forward risk in `docs/sessions/telemetry-2026-05-10.md`.

### `PII_ATTRIBUTE_KEYS` registry — adapter-boundary cardinal-#5 enforcement (issue #87)

**Source decision:** Issue #87 closes a gap in cardinal-#5 enforcement: `RawTrace.metadata` was typed `dict[str, Any]` with the convention that "input.value and output.value are `Sensitive[str]`; everything else passes through unwrapped because it's expected to be tooling state." OpenInference and Langfuse both routinely surface PII-bearing attributes (`user.id`, `session.id`, `user.email`, `user_id`, `userId`, etc.) at non-`input`/`output` keys. The convention was a comment, not enforcement. The doctrine bot flagged this on PR #86 across multiple iterations.

The fix (this PR): a frozenset `PII_ATTRIBUTE_KEYS` at `whatifd.adapters.pii` + a `wrap_pii_attributes(metadata)` helper that wraps registered keys as `Sensitive[str]` at the adapter boundary. A Pydantic `model_validator(mode="after")` on `RawTrace.metadata` rejects unwrapped values at registered keys, raising at construction-time. The conformance harness asserts the property structurally across every adapter.

**Rippled to / refactor protection:**

- **Adapters**: both `whatifd-langfuse.LangfuseTraceSource._project` and `whatifd-phoenix.PhoenixTraceSource._project` now pipe their raw metadata dict through `wrap_pii_attributes`. Adapter-specific tests pin the wrap.
- **`enforcement.md`** has a paired row documenting the three-layer chain.
- **Future adapters**: the conformance harness automatically extends to any future adapter that wires `TraceSourceConformance`. No per-adapter code change required to inherit the enforcement.

**Registry contract:**

The static frozenset covers v0.2-era adapter needs (OpenInference + Langfuse + generic). Custom adapter-specific keys are NOT supported in v0.2 — adapter authors observing PII at a non-registered key in production should file an issue, not extend the set locally. A future `register_pii_attribute(key)` API is the natural v0.3 extension surface; until then, the static set is the contract.

**Status:** open (resolves on next merge that wires the registry — this PR).

**Resolution:** closes when this PR merges. Followup cascade entry needed if a third adapter (LangSmith / OTel GenAI) lands and surfaces attribute keys not in the current set.

## Resolved cascades

> **Ordering convention:** entries are reverse-chronological — newest at the top, oldest at the bottom. New resolved cascades are PREPENDED to this section, not appended. Reasoning: a contributor scanning for "what shipped recently" or "what's the latest doctrine on X" gets the answer in the first few entries instead of paging to the end. The original v0.1 entries (PRs #26, #31, etc.) sit at the bottom because they were resolved earliest; the most recent v0.2 phases sit at the top.

### Phase J — Determinism widening: per-field `x-deterministic` on `RunManifest` + cross-platform CI (resolved 2026-05-10)

**Source decision:** v0.1 ships with `runtime` (the entire `RunManifest`) tagged `x-deterministic: false` as a blanket exclusion, but the dataclass's docstring documents that 9+ sub-fields ARE deterministic by intent (`experiment_id`, `whatif_version`, `config_hash`, `selection_seed`, `source`, `target`, `trust_floor`, `decision_policy`, `experiment_shape`). The blanket-exclusion enforced cardinal #4 by convention only — a future refactor that swapped `selection_seed: int` for a `time.time()`-based fallback would silently break determinism without failing the determinism test. Phase J closes the gap.

**Rippled to / refactor protection:**
- `RunManifest._DETERMINISTIC_FIELDS: frozenset[str]` is the source of truth. Adding/removing a sub-field updates the dataclass; the schema generator reads the attribute and emits per-property `x-deterministic` on the `$def` for `RunManifest`.
- `scripts/generate_schema.py::_dataclass_to_schema` now descends into dataclasses with `_DETERMINISTIC_FIELDS` and tags each property accordingly. Classes without the opt-in attribute behave as before (no per-field annotations).
- `whatifd.serialization.determinism.extract_deterministic_subset` descends into the `runtime` subtree when its `$ref` points to a `$def` carrying per-field `x-deterministic` annotations. `runtime` is no longer excluded as a whole; the deterministic subset now includes a partial `runtime` mapping with only the documented-deterministic sub-fields.
- `tests/integration/test_determinism.py::test_runtime_subfield_annotations_match_dataclass_optin` pins schema↔dataclass agreement: a schema regen that doesn't update the dataclass (or vice versa) fails this test.
- `tests/integration/test_determinism.py::test_runtime_field_partial_subset_per_field_determinism` (replaces the prior `_excluded_from_subset` test) pins the partial-subset shape: deterministic sub-fields present, non-deterministic ones excluded.
- New CI matrix `determinism-cross-platform-emit` runs on `[ubuntu-latest, macos-latest]`, emits `determinism-subset.json` from the canonical `scenario_clean_ship` fixture, uploads as a per-OS artifact. The `determinism-cross-platform-compare` job downloads both artifacts and asserts byte-equality via `diff -q`. Real cross-platform float-formatting / JSON-key-ordering / line-ending drift surfaces as a workflow failure with an `::error` annotation.
- Walkthrough fixtures already encode stable `RunManifest` values; no fixture regeneration required.
- Schema bumped fields stay under `REPORT_SCHEMA_VERSION = "0.2"` (annotations are additive metadata, not breaking schema changes).

**What this PR explicitly does NOT change:**
- `environment.*` sub-fields stay non-deterministic (pip-resolution-dependent dependencies; per-host python/platform). Future audit could canonicalize.
- `sensitive_unwraps` stays non-deterministic (cross-thread call ordering). Sorting by `(timestamp, classification, reason_hash)` is a v0.3+ project.
- `agent_identity` stays non-deterministic (Mapping ordering not guaranteed in v0.2).

**Resolved by:** Phase J PR on branch `phase-j-determinism-widening`.

### Phase I — `whatifd-fork` GitHub Action wrapper (resolved 2026-05-10)

**Source decision:** The public site (whatif.codes) promises a "GitHub Action wrapper" as a v0.2 feature. The CLI is already CI-ready (config-file driven, structured exit codes 0/1/2, deterministic `./reports/` artifacts); the Action's job is to capture the artifacts and surface the verdict through GitHub's PR/status surface.

**Rippled to / refactor protection:**
- Composite action at `.github/actions/whatifd-fork/action.yml` — pure shell + standard `gh` CLI. No Docker, no NumPy, no compute (cardinal #9 — orchestration not compute).
- Inputs: `config`, `profile`, `comment-on-pr`, `github-token`, `fail-on-dont-ship`. Outputs: `verdict` / `exit-code` / `report-json` / `report-md`.
- Exit-code → verdict mapping: `0 → "ship"`, `1 → "dont_ship"`, `* → "inconclusive"` (the `*` arm covers exit 2 + any future exit codes; cardinal #1 — never crash on an unrecognized signal).
- PR-comment step guards on `github.event_name == 'pull_request'` AND `comment-on-pr: true` AND `report_md != ''`. The third guard prevents commenting on setup-failure paths where the CLI exits before writing artifacts.
- PR-comment step uses `gh pr comment --edit-last` for rolling-update behavior. Failure-class discrimination: capture stderr; grep-match "no comment / not found" patterns to identify legitimate first-run; on any other non-zero exit, surface `::error` annotation + exit non-zero. Locale-fragile (issue #94 tracks the marker-based replacement).
- Path discovery uses a Python one-liner (`glob` + `os.path.getmtime`) for cross-platform portability — GNU `find -printf` and BSD `stat` diverge; Python is on every GitHub runner. Issue #93 tracks the cleaner CLI-emits-paths follow-up.
- Cross-runner: Linux + macOS supported via the Python discovery; Windows works via Git Bash because every step declares `shell: bash`. PowerShell-only runners are unsupported.
- `fail-on-dont-ship: true` is the default — the workflow fails on Don't Ship and Inconclusive. `fail-on-dont-ship: false` exposes the verdict as an output for downstream steps to inspect (e.g., a "warn but don't block" mode).
- Cardinal #7 (two-affirmation) preserved: when the action is invoked with `profile: forensic`, the underlying CLI still requires the config's `forensic_acknowledgment` block. The action does NOT bypass cardinal #7.
- 31 structural tests in `tests/integration/test_phase_i_github_action.py` parse `action.yml` and pin: top-level shape, YAML schema (lists vs maps, mapping-of-mapping for inputs/outputs), every input default the README documents, every output, the load-bearing `if:` guards on the PR-comment and fail steps (with `${{ }}` interpolation wrapping enforced), the exit-code mapping branches, the `--edit-last` failure-class discrimination, the `$RUNNER_TEMP` matrix-safety pattern, the no-duplicate-`::error` discipline, the cross-platform Python-based path discovery, and the path-discovery error surfacing (real failures produce `::error` annotations + non-zero exit, not silent empty paths).
- Example workflow at `.github/workflows/example-whatifd-fork.yml.example`. The `.example` suffix prevents the whatifd repo's own Actions runner from collecting it (the example references adapter credentials this repo doesn't have).
- Tag-pin convention documented in `CONTRIBUTING.md` (`### Third-party action pinning convention`); the README's `## Security: pinning third-party actions` section tells operators to SHA-pin in security-hardened production forks.
- Marketplace publication (separate repo) deferred to v0.3+; the action is currently consumable via `uses: ./.github/actions/whatifd-fork` (in-repo) or by vendoring into the consumer's repo.

**Known limitations (filed as follow-ups, do not block v0.2.0):**
- **#94 [HIGHEST-PRIORITY Phase I follow-up]**: replace `--edit-last` + grep with marker-based dedup (`<!-- whatifd-fork:run-id=... -->` HTML comment, `gh api` to find/update). Locale-independent. The English-only grep heuristic is a latent correctness hole on localized runners; rare in practice today (English LANG dominates GitHub-hosted runners) but should land in v0.3 ahead of broader Marketplace adoption.
- #93: CLI should emit chosen report paths via `GITHUB_OUTPUT` directly so the action's Python path-discovery scaffolding becomes unnecessary. **Couple to the v0.3 `whatifd diff` workflow** — both Actions then share one path-discovery surface instead of each writing its own shell scaffolding. Clean simplification.

**Resolved by:** Phase I PR on branch `phase-i-github-action`.

### Phase E.2 — pipeline switch + MethodologyDisclosure flip (resolved 2026-05-10)

**Source decision:** Phase E.1 (PR #89) shipped the `paired_percentile_bootstrap` algorithm in `whatifd.statistical`. The pipeline still called `statistics.quantiles` and the methodology disclosure still emitted `bootstrap.method = "unavailable"`. Phase E.2 closes that loop: the pipeline now calls the real bootstrap, and the disclosure declares `paired_percentile_bootstrap` truthfully. The doctrine bot raised this as a cardinal-#10 concern across PRs #82, #86, #88, and #89; the disclosure flip is what earns v0.2 the right to claim non-`unavailable` methodology.

**Rippled to / refactor protection:**
- `whatifd.pipeline._cohort_result_from_bucket` now calls `paired_percentile_bootstrap(bucket.deltas, seed=_BOOTSTRAP_SEED)` instead of `statistics.quantiles`. Wire-boundary crossing uses `to_decimal_string` (Phase E.1's helper).
- `_BOOTSTRAP_SEED = 4_872_109` is a module-level constant. Mirrored in `cli.py`'s `MethodologyDisclosure.bootstrap.seed` so the disclosure echoes the real seed the pipeline used. Future work may parameterize this through `RunManifest.selection_seed` or a dedicated stats-layer seed; v0.2 ships the constant for reproducibility.
- `BootstrapMethodDisclosure` in `cli.py`: `method="paired_percentile_bootstrap"`, `resamples=2000`, `seed=4_872_109`, `unavailable_reason=None`, `assumptions=("i.i.d. resampling across paired traces (no cluster boundaries respected)",)`. The "unavailable" enum value remains legal for genuinely-unavailable cases (sample too small, scoring stage didn't run); cf. walkthrough fixtures #4 and #5 which still use it correctly.
- `import statistics` removed from `pipeline.py` — no other call site needs it after the bootstrap switch.
- `docs/getting-started.md` programmatic example flipped to declare the real method; the v0.1 "Known limitations" entry about empirical CI bounds is marked resolved.

**What this PR explicitly did NOT touch:**
- Walkthrough fixtures #4 (insufficient sample) and #5 (cache corruption) still emit `method="unavailable"` — that's the correct disclosure for those genuine-unavailability scenarios. The bot's earlier "~125 references touched" estimate over-counted: most "unavailable" mentions in the test surface are testing the type's literal-value support, not asserting that the production happy path emits it.
- Cluster-paired bootstrap (`cluster_paired_percentile_bootstrap` enum value) — v0.3 surface; the schema enum already distinguishes.
- Holm correction, observed-MDE warnings, pairwise judging — v0.3 / Phase E.3+.

**Resolved by:** Phase E.2 PR on branch `phase-e2-disclosure-flip`. Closes issue #90.



### Phase E.1 — paired-percentile bootstrap algorithm + property tests (resolved 2026-05-10)

**Source decision:** v0.1 / v0.2 ships an empirical-percentile shortcut in `whatifd.pipeline._cohort_result_from_bucket` (`statistics.quantiles(..., n=20)` 5th/95th percentile of the raw deltas). The methodology disclosure declares this honestly via `bootstrap.method = "unavailable"` + `unavailable_reason`. Phase E.1 implements the doctrinally-correct paired-percentile bootstrap algorithm in a new `whatifd.statistical` module so it can land as an algorithm-only change, reviewable independently of the disclosure flip + walkthrough regeneration churn (Phase E.2).

**Rippled to / refactor protection:**
- `paired_percentile_bootstrap(deltas, *, resamples, ci_level, seed) -> BootstrapResult`. Seed is REQUIRED — no default — so a future caller cannot ship a non-reproducible CI. Uses a local `random.Random` instance to avoid perturbing the global module's state.
- Algorithm is pure-Python (cardinal #9). NumPy vectorization is deferred and gated on profile data; the schema enum stays unchanged either way.
- Paired (i.i.d. across paired traces, not stratified). Cluster-paired bootstrap is v0.3; the schema enum already distinguishes the two so this module's output is forward-compatible.
- 19 tests pin: deterministic-with-seed, no-global-random-perturbation, empty-input rejection, ci_level monotonicity, Hypothesis property tests on arbitrary delta sequences.

**What this PR explicitly does NOT change:**
- `whatifd.pipeline._cohort_result_from_bucket` still calls `statistics.quantiles`. The pipeline-side switch is Phase E.2 (issue #90).
- `MethodologyDisclosure.bootstrap.method` still emits `"unavailable"` from `cli.py`. Phase E.2 flips this to `"paired_percentile_bootstrap"`.
- The six committed walkthrough fixtures (`docs/walkthroughs/01..06`) still encode `"unavailable"` in their methodology blocks. Regeneration is Phase E.2's main scope.

**Why split:** the algorithm is one substantive change; flipping the disclosure default + regenerating six golden walkthrough fixtures is another substantive change. Bundling them produces a PR with ~125+ test references touched, which becomes hard to review for the actual algorithmic correctness.

**On the CI-width monotonicity claim:** an earlier draft of this entry called the property "structurally guaranteed by the index formula." That overstates the case. The percentile-index formula `round((alpha/2)*(N-1))` IS deterministic, so for a fixed seeded resample distribution, higher `ci_level` produces indices that move outward in the sorted distribution — but at small `resamples` (e.g., 50) the rounded indices CAN collide between adjacent ci_levels, producing equal widths rather than strictly larger ones. The Hypothesis test asserts `<=`, which is the correct invariant; the cascade claim is "non-decreasing in ci_level on the same seed," not "strictly increasing."

**Resolved by:** PR on branch `phase-e-paired-bootstrap`. Phase E.2 (the disclosure flip + walkthrough regen) is the explicit follow-up tracked at issue #90.



### Phase C completion — WhatifConfig.experiment_shape closes the CLI loop (resolved 2026-05-10)

**Source decision:** Phase C (PR #82) wired the verdict-layer branch on `experiment_shape` in `compute_verdict`, but the field was reachable only by programmatic `RunManifest` construction. CLI users running `whatifd fork --config whatifd.config.yaml` could not select `regression_check` without dropping into Python. Issue #84 tracked this gap; PR #88 closes it.

**Rippled to / refactor protection:**
- `WhatifConfig.experiment_shape: ExperimentShape = "failure_rescue"` lives at the top level of the config (sibling to `source`, `target`, `selection`, etc.), not nested under a sub-block. Reasoning: the shape is a run-level concern, not adapter-level; placing it under `selection` or `experiment` would imply a future expansion point that doesn't exist yet.
- Default is `"failure_rescue"`. Existing v0.1 configs validate unchanged (back-compat preserved).
- Unknown values fail at config-load with a Pydantic ValidationError naming the field — fail-early discipline matching the rest of v0.2's config validators (cardinal #1).
- `_run_fork_pipeline` threads `cfg.experiment_shape` into the `RunManifest` it constructs at dispatch time. `run_pipeline` already reads `runtime.experiment_shape` (Phase C); the projection layer copies it to `ReportV01.experiment_shape` (Phase A).
- Two tests pin the integration end-to-end:
  - Unit: `TestExperimentShapeConfig` (default, both literals, unknown rejected).
  - Integration: `test_whatif_fork_e2e_experiment_shape_threaded_to_report` reads the emitted JSON report and asserts `report["experiment_shape"]` matches the YAML value. Catches a future regression where the field is accepted by config-load but silently dropped at the dispatch layer.

**Resolved by:** PR #88 on branch `cli-experiment-shape`. Closes issue #84.



### Phase D — Phoenix / OpenInference TraceSource adapter; tracer-neutrality proof (resolved 2026-05-10)

**Source decision:** v0.1 shipped a single trace-source adapter (`whatifd-langfuse`). The v0.2 roadmap declared Phoenix as the second adapter — not because Phoenix is the strongest competitor to Langfuse, but because shipping a second adapter proves the `TraceSource` Protocol isn't shape-coupled to Langfuse. The risk was that v0.1's Protocol absorbed Langfuse-specific assumptions silently; landing Phoenix surfaces any such coupling as a real refactor cost.

**Rippled to / refactor protection:**
- New package `packages/whatifd-phoenix/` (v0.2.0) follows the `whatifd-langfuse` template structurally: pyproject.toml shape, `src/whatifd_phoenix/source.py` projection, `tests/test_conformance.py` harness subclass.
- The adapter is **span-iterator-shaped, not Phoenix-Client-shaped.** Constructor takes a `spans_provider: Callable[[], Iterable[dict]]` rather than a typed Phoenix client. This sidesteps the moving-target arize-phoenix-client API and makes the package usable against any OpenInference-emitting tracer (Phoenix, custom OTLP collectors, etc.). The trade-off: callers write a ~5-line `spans_provider` callable. The README documents the canonical Phoenix client wiring.
- OpenInference attribute conventions are pinned at the top of `source.py`: `_ATTR_INPUT = "input.value"`, `_ATTR_OUTPUT = "output.value"`, `_ATTR_TRACE_ID = "context.trace_id"`, `_ATTR_PARENT_ID = "parent_id"`, `_ATTR_SPAN_KIND = "openinference.span.kind"`. A future OpenInference-spec revision lands in one place.
- `arize-phoenix-client` is an optional dep via the `[live]` extra, not a hard dep. Operators who wire their own client don't pay the install cost; the conformance test runs against synthetic span dicts.
- Conformance harness reused unchanged. The 5 inherited `TraceSourceConformance` test methods plus 9 adapter-specific tests (TestSpanGrouping, TestAdapterMetadata, TestClusterKeySupport) prove the Protocol shape works for non-Langfuse adapters without harness modification.
- `cluster_key_support` returns empty `available_keys` — same doctrinal stance as Langfuse. Cardinal #10 forbids fabricating cluster keys for confirmatory verdicts; v0.3+ adds explicit per-attribute opt-in.
- Recorded-cassette live smoke test is **deferred to v0.3** — Phoenix HTTP-cassette infrastructure parity with `whatifd-langfuse` is its own surface and shouldn't gate the Protocol-shape proof.
- Workspace registration: `pyproject.toml [tool.uv.workspace] members` adds `packages/whatifd-phoenix`. `uv sync` installs editably alongside the other adapters.

**Resolved by:** Phase D PR on branch `phase-d-phoenix-adapter`.



### Phase C — regression_check experiment shape: shape-aware guard chain + required_cohorts (resolved 2026-05-10)

**Source decision:** v0.1 supported only the `failure_rescue` experiment shape — a known-bad failure cohort + a representative baseline cohort, with the verdict policy checking both "did the change rescue failures" and "did it preserve baseline." Phase A introduced `experiment_shape: Literal["failure_rescue", "regression_check"]` structurally; Phase C makes the verdict layer actually branch on it. Regression-check has no failure cohort — only baseline-vs-baseline-with-change — so the failure-cohort guards (`practical_delta`, `improvement_observation`) and the failure-required `required_cohorts` floor input must be conditional.

**Rippled to / refactor protection:**
- `compute_verdict` gains an `experiment_shape: ExperimentShape = "failure_rescue"` keyword parameter. Default preserves v0.1 back-compat; explicit non-default callers get the new branch.
- `_guards_for_shape(shape)` resolves to `_DEFAULT_GUARDS` (failure-rescue) or `_REGRESSION_CHECK_GUARDS` (the lean pair: `primary_endpoint_guard` + `ci_availability_guard`). The `primary_endpoint_guard` is configurable via `policy.primary_endpoints` and naturally handles the regression-check policy when only the baseline non-regression endpoint is declared.
- `_required_cohorts_for_shape(shape, policy)` overrides `policy.required_cohorts` to `("baseline",)` for regression-check. Operators don't need to also flip the policy's `required_cohorts` field — the shape implies it.
- `run_pipeline` reads `runtime.experiment_shape` (Phase A's manifest field) and passes it through. The wire-canonical view at `ReportV01.experiment_shape` (also Phase A) is unaffected.
- Tests pin the shape-conditional behavior on both sides: failure_rescue baseline-only → Inconclusive (floor missing failure cohort); regression_check baseline-only → Ship. Default-no-shape callers still get failure_rescue (back-compat).
- A new walkthrough fixture (#7) documenting the regression-check shape end-to-end is intentionally deferred to a follow-up; this PR ships only the policy/guard branch.

**Resolved by:** Phase C PR on branch `phase-c-regression-check`.



### Phase B — Scorer score_fn config-loadable; inspect_ai reachable from YAML (resolved 2026-05-10)

**Source decision:** v0.1 shipped with `scorer.adapter: inspect_ai` reachable only via the programmatic `run_pipeline` API; the CLI surfaced an actionable setup-failure error pointing at the gap. v0.2 closes the cliff by adding `scorer.score_fn: "python:<module>:<attr>"` plus the judge-config fields (`judge_provider`, `judge_model_id`, `rubric_id`, `rubric_text`, optional `judge_model_snapshot` / `scoring_parameters`) to `ScorerConfig`. A new `whatifd.scorer_loader.load_score_fn` mirrors `runner_loader.load_runner` for the `python:` reference resolution.

**Rippled to / refactor protection:**
- `ScorerConfig.model_validator` enforces all five required fields when `adapter='inspect_ai'`. Validation fires at config-load time, before factory dispatch — a v0.1-shaped config (just `adapter: inspect_ai`) now fails Pydantic validation with a named-field error rather than crashing later in `build_scorer`.
- `whatifd.adapters.factory.build_scorer` constructs `InspectAIScorer` directly when adapter='inspect_ai'. The `score_fn is None` branch becomes unreachable belt-and-suspenders (the validator catches it first); kept in code so a future contributor who bypasses the validator surfaces a clear error.
- `whatifd_inspect_ai` import remains lazy inside the factory branch — the `core-modules-do-not-load-real-adapter-packages` contract is unbroken.
- Existing test fixtures that used `adapter: inspect_ai` as a v0.1 sentinel-failure config (test_config.py, test_cli.py) now use `adapter: stub` for the same purpose. The behavior they pin (e.g. "two-affirmation reaches dispatcher → setup-failure exit 2") is unchanged because stub source's empty trace list also produces a setup-failure outcome.
- `test_build_scorer_inspect_ai_raises_actionable` was retired; replaced by `test_build_scorer_inspect_ai_missing_score_fn_blocked_by_validator` (tests the validator-time enforcement) and `test_build_scorer_inspect_ai_with_real_score_fn_returns_inspect_scorer` (happy-path integration).
- Docs updates (drop "v0.1 caveat" admonitions across inspect-ai.md, langfuse.md, workflow.md, first-experiment.md, live-langfuse.md, config.md) are deferred to a follow-up PR in the `whatifd-docs` repo so the docs reflect shipped behavior.

**Resolved by:** Phase B PR on branch `phase-b-config-score-fn`.



### Phase A v0.2 schema groundwork — experiment_shape + frozen v0.1 + real report-migrate (resolved 2026-05-10)

**Source decision:** v0.2 roadmap Phase A introduces `ExperimentShape = Literal["failure_rescue","regression_check"]` to ReportV01 + RunManifest. The verdict-policy branch on shape lands in Phase C; Phase A is structural-only. Three downstream concerns rippled together: (a) v0.1.schema.json must become immutable now that v0.1.0 has shipped to PyPI consumers, (b) v0.2.schema.json must be generated alongside, (c) the report-migrate CLI's v0.1 no-op stub becomes real v0.1→v0.2 logic.

**Rippled to / refactor protection:**
- `src/whatifd/report/schema/v0.1.schema.json` is byte-frozen — `tests/unit/whatifd/report/test_schema_v0_1_frozen.py` pins its sha256. Any structural edit to v0.1 is now CI-blocking; corrections must land in a new `v0.X.schema.json`.
- `scripts/generate_schema.py` derives the output filename from `REPORT_SCHEMA_VERSION` so future bumps don't overwrite frozen versions.
- `whatifd.report.migrate` carries the `_MIGRATIONS` chain dispatcher: future `v0.X → v0.Y` migrations register here. Each step has a chain-integrity guard (must advance the version) so a buggy migrator surfaces as `MigrationError("chain corruption")` rather than a misleading "no migration path."
- The migrator operates on `dict[str, Any]` (not typed `ReportV01`) because v0.1 dicts lack v0.2-required fields; typed instantiation would fail before injection. This boundary placement preserves cardinal #6 (public schema hand-written; the migrator works at the wire shape, not the typed shape).
- `whatifd.serialization.load_report_json` was added as the read-side counterpart to `canonical_json_bytes` so the migrator's I/O path stays inside the cardinal #5 module-discipline boundary (json activity in `whatifd/serialization/*` only).
- `experiment_shape` lives at top-level on `ReportV01` (deterministic subset per cardinal #4); `RunManifest` carries the same value for audit but `runtime` is non-deterministic, so the wire-canonical view is the top-level field.

**Resolved by:** PR #78 (Phase A), commit on branch `phase-a-schema-v0.2`.



### Banned-import lint scope: cache keying canonical JSON (resolved 2026-05-05)

**Source decision:** Phase 3.1 (PR #31) lands `whatifd/cache/keying/v1.py` which needs to canonicalize `CacheKeyComponents` for SHA-256 hashing. `references/enforcement.md` row 2 documents that the banned-import lint will block `json.dumps` outside `whatifd/serialization/` to enforce cardinal #5 (no accidental `Sensitive[T]` serialization on artifact paths). Two reconciliations were possible: helper centralized in `whatifd/serialization/` (Option A) or per-file lint allowlist (Option B).

**Resolved by:** Option A landed within PR #31 itself. `whatifd/serialization/canonical.py::canonical_json_bytes(obj) -> bytes` carries the canonical encoding (`sort_keys=True, separators=(",", ":"), ensure_ascii=True`); cache keying imports it. The Phase 5 banned-import lint, when implemented, sees zero `json.dumps` calls outside `whatifd/serialization/` — no allowlist needed. The module docstring on `canonical.py` documents the "hash input only — never artifact" boundary so future contributors don't conflate it with the artifact-path encoder.

The v1 digest is preserved across the refactor: the canonical encoding contract is byte-for-byte identical, so the known-digest test in `test_v1.py::test_deterministic_against_known_digest` continues to pass without modification.



### Single Ship-construction site — `whatifd/decision/verdict.py` (resolved 2026-05-05)

**Source decision:** PR #26 (Phase 2.6a) lands `compute_verdict` as the only function that constructs `Ship` instances. Cardinal #2's witness-token contract (`Ship.proof: FloorPassedProof`) is structurally enforced via the closure-capture in `whatifd/decision/floor.py` — only `evaluate_floor` produces proofs. `compute_verdict` is the only call site that calls `evaluate_floor` AND threads the resulting proof into `Ship(proof=...)`.

**Rippled to / refactor protection:**
- A future contributor MUST NOT add a second Ship-construction site. Doing so would either (a) bypass the floor (impossible — `Ship.__init__` requires a `FloorPassedProof`, and only `evaluate_floor` makes them) or (b) replicate the verdict-computation surface, which is duplication.
- The verdict layer's contract surface is `compute_verdict(cohort_results, floor, policy, *, guards=None) -> Verdict`. Any new verdict-affecting concern (multi-endpoint primary, ci_meaningful policy guard, aggregation roll-up) lands by extending this function or the guard chain it composes — not by introducing parallel Ship constructors.
- Tests pin both halves:
  - `tests/unit/whatifd/decision/test_verdict.py::TestCardinalTwoTrustChain::test_ship_carries_proof_from_evaluate_floor` — the proof on Ship comes from `evaluate_floor`.
  - `tests/unit/whatifd/decision/test_floor.py::TestExternalConstructionBlocked` — `FloorPassedProof` cannot be constructed externally.

**Resolved by:** PR #26 (Phase 2.6a), commit `606882b`.

### Fresh-list-per-guard contract — convention, not enforcement (resolved 2026-05-05)

**Source decision:** PR #23 went through three reviewer iterations on whether `run_guards` should structurally enforce that each guard returns a fresh list (not a class-level mutable shared across guards). Iterations: add `id()`-based check → upgrade to `is`-comparison with strong references → drop the check entirely. Final state: convention documented in `whatifd/decision/guards/__init__.py`'s discipline note + `whatifd/decision/guards/protocol.py` `run_guards` docstring; no runtime check.

**Rationale:** The fresh-list contract is a coding-pattern claim, not a structural claim about verdict integrity (which would belong in `references/enforcement.md`). Per the enforcement-strength hierarchy, convention-with-documentation is the appropriate mechanism for non-structural claims. The trust-floor witness pattern (`FloorPassedProof`) is for structural claims; the runtime check would have been belt-and-suspenders that didn't pay rent.

**Recovery path:** if a real shared-list bug ever surfaces, the response is a targeted regression test for that specific failure mode, NOT re-introducing blanket runtime enforcement. The doctrine: defense-in-depth must earn its rent in observed bugs, not hypothetical ones.

**Resolved by:** PR #23, commit `064154c` (final state).



### `__version__` source-of-truth: `importlib.metadata`, not source literal (resolved 2026-05-09)

**Source decision:** PR #76 (post-PR-#74 release-prep). The TestPyPI dry-run for `v0.1.0rc1` exposed a drift bug: `pyproject.toml` advertised `0.1.0rc1` but `whatifd.__version__` still reported the stale literal `0.0.1` because the rename + release-prep PRs never bumped the source string. PyPI version slots cannot be republished, so a real `v0.1.0` cut without this fix would have shipped a wrong-forever `__version__`.

**Resolution:** all three packages (`whatifd`, `whatifd-langfuse`, `whatifd-inspect-ai`) read `__version__` from `importlib.metadata.version(<dist-name>)` at import time. `PackageNotFoundError` (source-only / pre-`pip install` checkout) falls back to the sentinel `"0.0.0+unknown"`. Distribution metadata (the `version` field in each `pyproject.toml`) is the single source of truth.

**Rippled to:**
- `src/whatifd/__init__.py`, `packages/whatifd-langfuse/src/whatifd_langfuse/__init__.py`, `packages/whatifd-inspect-ai/src/whatifd_inspect_ai/__init__.py` — all three switched to the `importlib.metadata` pattern.
- `tests/unit/whatifd/test_version_parity.py` — pins parity for all three packages and asserts the sentinel never leaks into an installed test environment. Regression guard against any future contributor reverting to a hardcoded literal.
- **Downstream `__version__` consumers** — anything that compares `whatifd.__version__` for compatibility now reads installed metadata, not a frozen literal. The semantics match what consumers expect from `pkg.__version__`.
- **Release runbook** — `RELEASING.md` already documents bumping `pyproject.toml` `version`; with this fix, that single edit propagates correctly. No second source-string bump step needed.

**Recovery path:** if a future contributor re-introduces a hardcoded literal, the parity test fails at CI on the PR, before the drift can ship.

**Resolved by:** PR #76 (the source-of-truth switch and the parity test landed on the same branch).

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
