# Deferred refactors and feature candidates

Each entry: **what**, **why deferred**, **trigger to promote**.

When a trigger fires, move the entry to `whatifd-design/references/cascade-catalog.md` (if it's blocking) or open a phase-plan amendment PR (if it's a sub-phase of new work). Do NOT silently start working on a deferred item without promoting it first — that path is how the active plan drifts.

---

## 1. Promote conformance harness to `whatifd.testing.adapter_conformance`

**What:** Move `tests/adapters/conformance.py` into `src/whatifd/testing/adapter_conformance.py` and re-export from `whatifd.testing.__init__`. Update in-tree tests to import from the public location.

**Why deferred:** The plan's Phase 4B is "real adapters," not "harness publication." The current location works for in-tree consumers (the stub at 4A.3, the in-file fakes at 4A.2 self-test). Promoting it without a concrete external consumer is YAGNI — and Phase 4B's separate-package adapters CAN consume the harness via `sys.path` tweak in their `conftest.py` or a small re-export shim if that proves clumsy.

**Trigger to promote:** When writing `packages/whatifd-langfuse/tests/test_conformance.py` (Phase 4B.1) OR `packages/whatifd-inspect-ai/tests/` (Phase 4B.2), if the harness import demonstrably blocks the work — i.e., conftest tweaks fail under uv workspace install OR the test layout requires an external import path that pytest can't resolve. Then this refactor lands as a small precursor PR with the rationale grounded in real friction. Until that demonstrably appears, don't touch it.

**Status update (Phase 4B.1 — PR #65 landed 2026-05-08):** the conftest `sys.path.insert` workaround in `packages/whatifd-langfuse/tests/conftest.py` is in production. It works for an in-repo workspace member but is fragile for **out-of-tree** consumers (a third-party adapter package that lives in its own git repo and depends on `whatif` from PyPI). The conftest tweak relies on `Path(__file__).resolve().parents[3]` resolving to the whatif repo root — that path doesn't exist for an out-of-tree consumer.

**Concrete backlog item — promote at Phase 4B.2 if the seam needs a second consumer:**
1. Move `tests/adapters/conformance.py` to `src/whatifd/testing/adapter_conformance.py`.
2. Create `src/whatifd/testing/__init__.py` re-exporting `TraceSourceConformance`, `ScorerConformance`, `StructuralFailureScorerConformance`, `make_score_case`.
3. Update `tests/adapters/test_stub_conformance.py`, `tests/adapters/test_conformance_self_test.py`, and `packages/whatifd-langfuse/tests/test_conformance.py` to `from whatifd.testing import ...`.
4. Delete `packages/whatifd-langfuse/tests/conftest.py` (the `sys.path` tweak becomes unnecessary).
5. Add `tests/unit/whatifd/testing/test_public_surface.py` pinning the public re-exports (catches accidental removal).
6. Update the cascade-catalog entry "Monorepo workspace + `whatifd-langfuse` distribution (Phase 4B.1)" → "Conformance harness reuse" line: replace the conftest description with the public-import description.

**Promotion criterion:** Phase 4B.2 (`packages/whatifd-inspect-ai/`) needs the harness too. If we duplicate the conftest pattern there, we have two fragile sites; promoting to public is the right move at that point. If 4B.2 lands cleanly with a copy of the same conftest, the promotion stays deferred for v0.2.

**Risk if done eagerly:** introducing a refactor mid-plan when the cascade-catalog already has 4B-tracking entries; bloating the v0.1 publishable surface (`whatifd.testing` becomes a stability commitment) without a concrete user.

---

## 2. PEP 440 validator on `AdapterMetadata.package_version`

**What:** Validate `package_version` against PEP 440 in `__post_init__` so misconfigured adapters fail at construction rather than at report-render time.

**Why deferred:** Suggested in PR #57 review (Phase 4A.1) and declined. The value is set once at adapter init and isn't read by any logic that depends on its shape — it's just metadata stamped into `RunManifest`. A misconfigured adapter would emit a slightly weird version string in the report; not a correctness bug.

**Trigger to promote:** First real adapter (Phase 4B.1 or 4B.2) where the version string IS read by a comparison (e.g., a future `whatif report-migrate` that gates on adapter version semver). Until a real consumer needs structured comparison, the str field is enough.

---

## 3. Typed `ToolSpan` model replacing `dict[str, Any]`

**What:** Replace `tool_spans: list[dict[str, Any]]` on `TraceInput`, `RawTrace`, `ReplayOutput` with a typed `ToolSpan` Pydantic model. Adapter projection updates accordingly.

**Why deferred:** Cardinal #6 governs the **public report schema** (`ReportV01`), not adapter↔core internal boundaries. The current shapes mirror each other (`whatifd.contract.TraceInput.metadata`, `ReplayOutput.tool_spans`, `RawTrace.tool_spans`) — tightening the adapter side without lifting the contract would diverge them.

**Trigger to promote:** v0.2 schema bump where the contract grows a typed `ToolSpan`. Then all four shapes update in lockstep. Currently cascade-tracked under "whatifd.adapters package introduced (Phase 4A.1)" → "Adapter→core typed-boundary review" line.

---

## 4. Real stratified bootstrap CI replacing 9A.1's empirical-percentile shortcut

**What:** Replace `statistics.quantiles(deltas, n=20)` in `whatif/pipeline.py::_cohort_result_from_bucket` with a proper paired-bootstrap implementation respecting `BootstrapMethodDisclosure.method="paired_percentile_bootstrap"` or `"cluster_paired_percentile_bootstrap"` per `policy.bootstrap_*` settings.

**Why deferred:** Phase 9A.1 explicitly documented this as a shortcut; the function signature is the stable contract. Real bootstrap is broader stats-layer work, not a pipeline-glue change.

**Trigger to promote:** The first phase that needs methodology disclosures to be honest in published reports — almost certainly Phase 9B (real-adapter smoke) or Phase 10 (release packaging). The `unavailable_reason` string in `_default_methodology()` (`"Phase 9A.1 empirical-percentile shortcut..."`) is the search anchor.

**Honesty obligation while deferred (cardinal #10):** the empirical-percentile shortcut is acceptable ONLY because every report emitted during the shortcut period carries the matching `BootstrapMethodDisclosure(method="unavailable", unavailable_reason="Phase 9A.1 empirical-percentile shortcut; proper stratified bootstrap pending stats-layer integration.")` in its methodology block. If a future PR populates `ci_lower` / `ci_upper` while flipping `method` to `"paired_percentile_bootstrap"` WITHOUT actually implementing the bootstrap, that's a cardinal-#10 violation — the disclosure would lie about how the CI was computed. Phase 9A.3's `test_deterministic_field_set_matches_schema` covers field presence; the honesty pin is that `method` and `resamples` must reflect what actually ran. Add a regression test asserting the disclosure is consistent with the runtime path WHEN this entry is promoted.

---

## 5. Cluster-key scenarios in Phase 9A integration

**What:** Add an integration scenario where `StubTraceSource.cluster_key_support_value` declares non-empty `available_keys` AND emitted `RawTrace.cluster_key` is populated. Asserts `MethodologyDisclosure.bootstrap.cluster_key` reflects the source's signal end-to-end.

**Why deferred:** None of the six walkthrough scenarios (1–6) describe a clustered-source case, so 9A.1/9A.2 didn't include one. The stub adapter ALREADY supports it via `cluster_key_support_value` parameterization — the integration coverage is the missing piece.

**Trigger to promote:** When real bootstrap lands (item 4 above), the cluster-key path becomes load-bearing on the disclosure. Add one scenario then.

---

## 6. CI determinism diff gate workflow

**What:** A `.github/workflows/` workflow that consumes `whatifd.serialization.determinism.extract_deterministic_subset` to diff deterministic subsets across runs (e.g., on PRs that touch the pipeline).

**Why deferred:** Cascade-tracked under "Deterministic-subset extractor (Phase 9A.3)" with explicit owner = Phase 10 release-prep CI hardening PR. The extractor is the production surface; the workflow is the consumer.

**Trigger to promote:** Phase 10 (release packaging). Or earlier if Phase 9B's smoke suite needs cross-process determinism evidence.

---

## 7. `delta_fn` → real paired `Scorer` wiring

**What:** Replace the `delta_fn: Callable[[RawTrace], float]` parameter on `whatifd.pipeline.run_pipeline` with a path that constructs `ScoreCase` from each `RawTrace` and routes through a `Scorer` instance to compute paired deltas.

**Why deferred:** Phase 9A.1 documented this as a shortcut. Real paired scoring needs a `Runner` in scope (to produce `ReplayOutput`) AND a `Scorer` (to score against `original_output`). The pipeline doesn't yet receive both.

**Trigger to promote:** Phase 9B (real-adapter smoke) — that's the first surface that has both a Runner and a real Scorer in scope. The `_PIPELINE_SCORER_FAILURE_CODE` comment and the `TODO(Phase 4B)` on the hardcoded `"provider": "stub"` in `pipeline.py` are the search anchors.

---

## 8. Two-affirmation pattern usage beyond forensic profile

**What:** Cardinal #7 says the two-affirmation pattern (config block + CLI flag) generalizes to "any future structurally-dangerous flag." Currently only the forensic profile uses it. Codify the generalization with a reusable helper.

**Why deferred:** No second use case yet. Generalizing without a second concrete use is over-engineering — the helper would lock in a shape that may not fit the next case.

**Trigger to promote:** When a Phase 4B / 9B / 10 design decision proposes a second structurally-dangerous flag (e.g., a v1.0 persistent-acceptance mechanism). The two-affirmation infrastructure (`TwoAffirmationProof`, closure-captured `_PROOF_TOKEN`, `assert_two_affirmation`) becomes the helper at that point.

---

## 9. Verdict-change matrix tests for `whatif diff`

**What:** Verify `whatif diff` correctly renders all 9 verdict transitions: Ship→Ship, Ship→DontShip, Ship→Inconclusive, DontShip→Ship, DontShip→DontShip, DontShip→Inconclusive, Inconclusive→Ship, Inconclusive→DontShip, Inconclusive→Inconclusive.

**Why deferred:** Cascade-tracked under "CLI whatif diff for v0.1" → "Deferred to v0.2." Current `tests/unit/whatifd/test_diff.py` pins the load-bearing transitions; the full matrix becomes useful when the renderer grows verdict-specific guidance.

**Auditable cross-reference** (verified at PR #64 author time; re-verify when promoting):

- `TestComputeDiff::test_verdict_and_failures` — exercises the dont_ship → ship transition through `compute_diff` (one of the 9 cells; load-bearing because the verdict line is the cardinal-#10 claim).
- `TestRenderDiffMarkdown::test_verdict_transition_arrow` — pins the `→` rendering for a verdict change in the Markdown output.
- `TestRenderDiffMarkdown::test_no_changes_sentinel` — pins the unchanged-verdict-and-nothing-else sentinel (covers the diagonal cells of the matrix where prev == new and no other field moved).
- `TestRenderDiffMarkdown::test_schema_only_change_is_not_no_change` and `test_unchanged_count_shift_is_not_no_change` — pin that specific non-verdict deltas don't accidentally trigger the no-changes path.

These together cover ~3 of the 9 matrix cells with regression-grade pins. The remaining 6 cells (Ship→Inconclusive, Inconclusive→Ship, DontShip→Inconclusive, etc.) are covered only by the `compute_diff` call-shape tests, not by render-output assertions. Promotion of this entry adds the missing 6 cells.

**Trigger to promote:** When the diff renderer adds verdict-transition-aware messaging (e.g., "DontShip → Inconclusive: a previously-blocked verdict now lacks evidence"). The matrix becomes the regression surface for that text.

---

## 10. Machine-checkable `whatif-json-dumps` allowlist

**What:** Extend the AST-walking banned-import lint at `tests/unit/whatifd/serialization/test_banned_imports.py` to ALSO walk `packages/*/tests/` and `tests/integration/` with an explicit allowlist of call sites carrying the `# whatif-json-dumps: test-scaffold-allowed` marker comment. The lint then enforces the test-scaffold carve-out machine-checkably instead of relying on the comment-as-convention.

**Why deferred:** The current lint targets `src/whatifd/` only, which IS the cardinal-#5 enforcement boundary. Test-scaffold `json.dumps` calls (notably `_scrub_response_body` in `packages/whatifd-langfuse/tests/test_recorded_smoke.py`) live in `packages/*/tests/` and `tests/`, which are out of scope by design. Building a marker-comment-respecting allowlist now is forward-looking machinery for a lint scope expansion that hasn't happened yet.

**Trigger to promote:** Whenever someone proposes broadening the banned-import lint to cover `packages/`, `tests/`, or both. At that point this entry's marker convention (`# whatif-json-dumps: test-scaffold-allowed`) becomes load-bearing and needs the AST recognition. Land the lint extension and the allowlist parser in the same PR. Until that proposal lands, the marker comment is a search anchor, not enforcement.

**Existing markers to preserve:** at least one `# whatif-json-dumps: test-scaffold-allowed` in `packages/whatifd-langfuse/tests/test_recorded_smoke.py::_scrub_response_body`. Future test-scaffold usage of `json.dumps` should add the same marker.

## How to add a new entry

Use this template:

```markdown
## N. <Title>

**What:** <one-sentence description of the change>

**Why deferred:** <reason — usually YAGNI, scope, or "trigger condition not met yet">

**Trigger to promote:** <concrete event that should move this from this skill to the active plan or cascade catalog>
```

Number entries in addition order; do NOT renumber on removal (link stability matters more than density).
