# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Pre-1.0, the minor version may introduce breaking changes - every breaking
change is called out under `### Changed (BREAKING)`.

---

## [Unreleased]

### Added — Phase 3.3 (cache lock)

- `src/whatif/cache/lock.py` — `acquire_cache_lock(cache_root, *, stale_after_seconds=86400, allow_age_takeover=False)` context manager. Two layers of defense per `references/enforcement.md` row "Single-writer cache access": (1) OS-level `fcntl.flock(LOCK_EX | LOCK_NB)` on `<cache>/.lock` (kernel releases on process death — SIGKILL, OOM, kernel panic — including across SIGKILL), (2) stale-lock fallback that records `{pid, process_start_time, hostname, started_at}` and takes over when the recorded process is dead OR its `psutil.Process(pid).create_time()` mismatches `process_start_time` (PID-reuse defense).
- `CacheLockedError` typed exception — DATA condition (a held lock is legitimate runtime state, not a programmer bug); callers convert to `FailureRecord` per cardinal #1. Error message names PID, hostname, started_at from the held lock so operators can decide between `whatif cache unlock` (CLI sub-command, Phase 8) and `whatif cache rebuild --force`.
- `LockFileContent` and `CacheLock` typed dataclasses — typed boundaries per cardinal #6.
- Age-based takeover (`allow_age_takeover=True`) is opt-in only. Default behavior takes over only on dead-process or PID-reuse evidence; age alone is a weak signal because long-running batches can legitimately hold locks for days.
- NFS unsupported; documented in module docstring + clear error message naming NFS as the likely cause if `flock` returns `ENOLCK`/`EOPNOTSUPP`. Multi-tenant cache directories deferred to v0.3 (cascade entry).
- New runtime dependency: `psutil>=6.0` (and `types-psutil` for mypy strict). Used for `Process.create_time()` PID-reuse defense.
- `tests/unit/whatif/cache/test_lock.py` — 13 tests across five classes:
  - `TestSingleWriter`: real-process contention via subprocess (NOT mocks; per Phase 3 gate); release on normal exit; release on exception (no orphan locks).
  - `TestStaleTakeover`: takeover when recorded PID is dead (the scenario-5 recovery loop); takeover when PID was recycled (live process but `create_time` mismatch); no takeover when PID alive and matches; takeover on corrupted/empty lock file.
  - `TestAgeTakeover`: default off (long-running batch not preempted); opt-in path reaches the age check (OS-level flock still primary defense, file-level age is advisory).
  - `TestLockProvenance`: lock content records this process correctly; `CacheLockedError` message includes PID/hostname/started_at.
  - `TestLockFileContentDataclass`: frozen-dataclass immutability.

### Added — Phase 3.2 (cache storage)

- `src/whatif/cache/storage/v1.py` — file layout + entry I/O for the scorer cache. Layout: `.whatif/cache/entries/<digest[0:2]>/<digest>.json` (sharded by first 2 hex chars; `v1:` prefix excluded from filename per Windows compat). Public surface: `init_cache(root) -> CacheMeta` (idempotent; refuses mismatched on-disk schema version), `write_entry(root, key, entry) -> Path` (refuses entries with mismatched `cache_schema_version`), `read_entry(root, key) -> CacheEntry | None` (None on miss; raises `CacheSchemaMismatchError` on disk-version mismatch), `read_meta(root) -> CacheMeta`.
- `CacheEntry` typed dataclass per `references/contracts.md` §"Entry format": `cache_key_version`, `cache_schema_version`, `created_at`, `key_components` (provenance — full asdict of `CacheKeyComponents`), `result: CacheResult`. `CacheResult` carries `score_delta`/`confidence` as `DecimalString` strings (cardinal #4 cross-platform stability), `verdict`, `flags`, optional `rationale`.
- `CacheSchemaMismatchError` — typed failure; callers convert to `FailureRecord` per cardinal #1. Used at three boundaries: init-time meta-version check, write-time entry-version check, read-time on-disk-version check, and key-prefix mismatch (`v2:` key against v1 storage).
- Profile gating on `rationale` is the CALLER'S responsibility — storage writes whatever entry it gets. The cardinal #5 boundary is preserved by upstream invariants (`CacheKeyComponents` hex-validation; `canonical_json_bytes` Sensitive guard).
- Entries written via `canonical_json_bytes` so two caches given the same input produce byte-identical files (cache verify can diff bytes).
- `tests/unit/whatif/cache/storage/test_v1.py` — 14 tests across init idempotence, round-trip integrity (with and without rationale), cache miss → None, sharding pin (`<digest[0:2]>/<digest>.json`; no `:` in filename), schema mismatch on write/read/init, v2-key rejection, byte-identical on-disk encoding via monkeypatched timestamp, meta round-trip.

`CACHE_SCHEMA_VERSION = "v1"`. PRs touching `whatif/cache/storage/` MUST bump version. The cache-version-bump CI test (Phase 3 gate) asserts this.

### Added — Phase 3.1 (cache key construction)

- `src/whatif/cache/keying/v1.py` — `CacheKeyComponents` dataclass + `build_cache_key(components) -> str`. Deterministic SHA-256 over canonical JSON of the full required component set per `references/contracts.md`: whatif schema version, scorer adapter version, scorer type/package, judge provider/model/snapshot, rendered-prompt hash, rubric hash, scoring-parameters hash, score-case serialization version, per-case content hash. Output format: `v1:<64-char hex digest>`. The version prefix is part of the key contract — storage layout uses it to split entries across versions.
- `src/whatif/serialization/canonical.py` — `canonical_json_bytes(obj) -> bytes`. Canonical-JSON encoder for HASH inputs (sort_keys=True, separators=(",", ":"), ensure_ascii=True). Centralized in `whatif/serialization/` so the Phase 5 banned-import lint sees zero `json.dumps` calls outside the serialization package without needing per-file allowlists. Module docstring documents the load-bearing distinction: this helper is for hash inputs only, not artifact bytes; the artifact-path encoder (Phase 5) carries cardinal #5 redaction enforcement separately.
- `src/whatif/cache/__init__.py` + `src/whatif/cache/keying/__init__.py` — package skeleton; `keying` re-exports `v1` so call sites import from the stable surface (`whatif.cache.keying`) rather than the versioned module directly.
- `tests/unit/whatif/cache/keying/test_v1.py` — 19 tests pinning format/version prefix/hex digest, determinism against a known-input known-output digest literal (verified across the full CI matrix 3.11/3.12/3.13/3.14), per-field sensitivity parametrized over all 12 fields, `None`-vs-empty-string distinctness on `judge_model_snapshot`, field-order independence.
- `tests/unit/whatif/serialization/test_canonical.py` — 9 tests pinning the canonical encoding contract: ASCII bytes, sorted keys (including nested dicts), whitespace-free, non-ASCII escaped, list order preserved, `None`/empty-string and int/float distinctness, deterministic across repeated calls.

`CACHE_KEY_VERSION = "v1"`. Future PRs that change keying semantics MUST introduce `v2` rather than mutate `v1`. The cascade entry "Banned-import lint scope: cache keying canonical JSON" landed resolved.

### Internal / Docs — Phase 0 closure (0.2 + 0.4)

- `docs/concepts.md`: filled the missing sections (verdict states, floor-vs-policy, evidence/audit bundle); glossary now includes `ci_computable`, `ci_meaningful`, primary endpoint; §4 spells out the sticky-manifest guarantee operates at write AND read time.
- `enforcement.md`: two new explicit rows surfacing implemented-but-untracked structural claims — "`ci_computable=False` on a required cohort cannot Ship" and "Floor vs policy concerns are partitioned on `CohortResult`." Both were mechanism-backed in code already; the audit just made them explicit in the canonical table for the schema-freeze gate.
- Phase 0 gate now closed (0.1 walkthroughs ✅, 0.2 conceptual model ✅, 0.3 audience-distribution ✅, 0.4 enforcement audit ✅). Phase 3 (cache subsystem) is the next substantive phase.

### Changed (BREAKING) — Skill-alignment pass (post Phase 2.6b)

A skill-vs-implementation audit surfaced three doctrine drifts. All three resolved here. See `whatif-private/V0_1_DECISION_RECORD.md` 2026-05-05 addendum.

- `CohortResult.ci_available: bool` renamed to `ci_computable: bool` and a new `ci_meaningful: bool = True` field added per V0_1_DECISION_RECORD §2's CI-status split. `ci_computable` is the structural fact (bootstrap successful?) read by `ci_availability_guard`; `ci_meaningful` is the policy-quality assessment (CI width below `policy.max_ci_width`?) read by a deferred guard. `__post_init__` enforces that `ci_meaningful=False` requires `ci_computable=True`. Cascade entry "ci_meaningful policy-guard wiring" tracks the deferred Phase 3 wiring.
- `DecisionPolicy.accept_no_ci: bool` removed per V0_1_DECISION_RECORD §6 ("`--accept-no-ci` removed in favor of CI-as-policy reclassification"). The field had been shipped as a placeholder with Phase 2.6c TODO — that was a doctrine breach. CI unavailability remains `blocks_all` (forces Inconclusive); the policy lever for accepting wider CIs is `policy.max_ci_width`. `test_accept_no_ci_can_be_enabled` deleted.
- V0_1_DECISION_RECORD §2's `Ship` type amended to include `findings: list[DecisionFinding]` (matching the implementation; observational/info findings are non-blocking by construction since `compute_verdict` would have downgraded the verdict otherwise).

Skill references updated: `type-model.md` (CohortResult split + accept_no_ci removed), `phases.md` (2.6 sub-phase decomposition), `cascade-catalog.md` (Phase 2.5 deferred-guards bullets re-scoped; new "ci_meaningful policy-guard wiring" entry).

### Added — Phase 2.6b (configurable primary_endpoint_guard)

- `src/whatif/decision/guards/primary_endpoint.py` — `primary_endpoint_guard`. Reads `policy.primary_endpoints` and dispatches by `EndpointDirection`: `improvement_above_threshold` evaluates against `policy.min_failure_improvement_ratio`; `non_regression_below_threshold` evaluates against `policy.max_baseline_regression_ratio`. Emits the existing finding codes (`failure_improvement_below_threshold`, `baseline_regression_above_threshold`) — no new registry entries needed. Boundary semantics preserved from Phase 2.5b: strict `<` for improvement, strict `>` for regression. Findings emit in `policy.primary_endpoints` order, not cohort discovery order. Multi-metric (one primary metric per cohort today; v0.2 adds Holm correction) is `MethodologyDisclosure.multiplicity`'s concern, not this guard's.
- `tests/unit/whatif/decision/guards/test_primary_endpoint.py` — 17 tests across default-policy improvement boundary cases, default-policy non-regression boundary cases, both-cohorts-active scenarios, ordering pin (findings in policy order, not cohort order), and the configurable-policy surface (single-endpoint, custom thresholds, unknown cohort silently skipped).

### Changed — Phase 2.6b consolidation

- `src/whatif/decision/guards/__init__.py` — exports `primary_endpoint_guard`; removes the now-deleted `failure_improvement_guard` and `baseline_regression_guard` exports.
- `src/whatif/decision/verdict.py::_DEFAULT_GUARDS` — replaces the Phase 2.5b hardcoded pair with `primary_endpoint_guard`. The default guard chain shrinks from 5 to 4 guards; behavior on the default policy is identical.
- `tests/unit/whatif/decision/guards/test_layer_composition.py` — updated `_LAYER` to `(primary_endpoint, practical_delta)`; the test assertions still pin the same finding-code ordering for the catastrophe scenario (because `primary_endpoint_guard` emits in `policy.primary_endpoints` order, which defaults to failure-then-baseline).

### Removed — Phase 2.6b

- `src/whatif/decision/guards/failure_improvement.py` — consolidated into `primary_endpoint_guard`.
- `src/whatif/decision/guards/baseline_regression.py` — consolidated into `primary_endpoint_guard`.
- `tests/unit/whatif/decision/guards/test_failure_improvement.py` and `test_baseline_regression.py` — coverage migrated into `test_primary_endpoint.py`.

### Added — Phase 7 cascade entry (PR #26 review F2)

- Cascade-catalog "Inconclusive renderer must distinguish floor_failures from blocking_findings" — files the rendering rule for the floor-failure-Inconclusive case so a renderer that prints `blocking_findings` without also surfacing `floor_failures` can't ship without addressing it. Cross-references cardinal #3 (disclosure necessary but not sufficient) and walkthrough scenario 4 as the empirical pin.

### Added — Phase 2.6a (verdict computation)

- `src/whatif/decision/verdict.py` — `compute_verdict(cohort_results, floor, policy, *, guards=None) -> Verdict`. Single entry point composing the existing decision pipeline: `evaluate_floor` (cardinal #2 structural gate) + `run_guards` (cardinal #10 layer chain) + severity-sorted verdict construction. Branches: any `blocks_all` finding → `Inconclusive` (operational catastrophe), any `blocks_ship` finding → `DontShip`, else → `Ship` with the `FloorPassedProof`. The `Ship` branch is the only consumer of the witness token; structurally cannot construct without it. Floor failures produce `Inconclusive` regardless of guard findings (floor precedence is absolute). v0.1 default guard chain (as of Phase 2.6a) had 5 guards in cardinal-#10 layer order: failure_improvement, baseline_regression, practical_delta, improvement_observation, ci_availability. Phase 2.6b below consolidates the first two into `primary_endpoint`, shrinking the chain to 4.
- `tests/unit/whatif/decision/test_verdict.py` — 13 tests covering Ship branch (clean run; cohort_results carried), DontShip branch (each blocking finding type — baseline regression, failure improvement below threshold, practical delta below epsilon), Inconclusive via floor failures (min_scored below floor; floor failure overrides clean findings), Inconclusive via blocks_all (CI unavailable; blocks_all overrides blocks_ship), cardinal-#2 trust-chain pins (Ship carries the FloorPassedProof from evaluate_floor; DontShip has no proof field), and the type-input contract (non-TrustFloor raises TypeError per cardinal #1).
- Phase 2.6a deliberately does NOT consult `policy.accept_no_ci` — the escape-hatch arithmetic is Phase 2.6c work. Tests pin the unconditional emission so Phase 2.6c can flip them cleanly.

### Added — Phase 2.5c (CI availability guard)

- `src/whatif/decision/finding_codes.py` — new `ci_unavailable_for_required_cohort` finding code (severity `blocks_all`, derived_from_failures="always"). Pairs with `FAILURE_CODE_REGISTRY['ci_uncomputable_for_required_cohort']` (the operational fact); the finding is the policy conclusion that forces Inconclusive when CI is missing on a required cohort.
- `src/whatif/decision/fix_suggestions.py` — new fix-suggestion entry guiding users through the `--accept-no-ci` escape hatch (the v0.1 single-flag opt-out for known-small-sample experiments) and the diagnostic path for `sample_too_small` / `zero_variance` / `computation_failed` reasons.
- `src/whatif/decision/guards/ci_availability.py` — `ci_availability_guard`. For every cohort named in `policy.required_cohorts`, checks `cohort.ci_available`; emits one finding per affected cohort (ordered to match `policy.required_cohorts`). Missing cohorts (the floor's `required_cohort_present` rule) and non-required cohorts are skipped. `accept_no_ci` is NOT consulted here — emission is unconditional; Phase 2.6 verdict computation does the acceptance arithmetic so the manifest records both finding AND opt-out.
- `tests/unit/whatif/decision/guards/test_ci_availability.py` — 11 tests covering boundary cases (CI on all required, CI missing on one, CI missing on all, CI missing on non-required, missing-cohort silence, empty cohort list), per-cohort emission ordering, custom `required_cohorts` (3-cohort policy), and the `unspecified` reason fallback when projection-layer bug leaves `ci_unavailable_reason=None`.
- `tests/unit/whatif/decision/guards/test_blocking_finding_fix_suggestions_inline.py` — added the cardinal-#8 spot-check assertion for the new finding code.
- Cascade catalog "Phase 2.5 deferred guards" entry: bullet 2 marked resolved. Pending in bullet 4: real `derived_from_failures` wiring (placeholder used today) lands when Phase 2.6 plumbs failure records end-to-end.

### Added — Phase 2.5b (rate-count `CohortResult` extension + cardinal #10 primary endpoints)

- `src/whatif/types/cohort.py` — `CohortResult` extended with three int fields: `improved_count`, `unchanged_count`, `regressed_count` (defaulting to 0 for backward compatibility). The triple partitions scored traces per cardinal #10's paired-delta unit of analysis: `improved` when the paired delta exceeds `policy.practical_delta_epsilon`, `regressed` when it falls below `-epsilon`, `unchanged` otherwise. The two new rate-based guards read these counts; existing construction sites (test fixtures, floor evaluator) keep working without changes.
- `src/whatif/decision/guards/failure_improvement.py` — `failure_improvement_guard`. **The load-bearing primary endpoint for cardinal #10's failure-rescue scope.** Emits `failure_improvement_below_threshold` (blocks_ship) when `improved_count / total_scored < policy.min_failure_improvement_ratio`. Strict `<` so equality at the threshold meets the policy's "at least N%" promise.
- `src/whatif/decision/guards/baseline_regression.py` — `baseline_regression_guard`. The symmetric non-regression endpoint on the baseline cohort. Emits `baseline_regression_above_threshold` (blocks_ship) when `regressed_count / total_scored > policy.max_baseline_regression_ratio`. Strict `>` so equality meets the policy's "at most N%" promise.
- `src/whatif/decision/guards/practical_delta.py` — docstring framing-cleanup per the cascade entry that PR #23 deferred to this PR. The TODO marker is removed; the docstring now cross-references `failure_improvement_guard` as the primary endpoint and frames `practical_delta_guard` as the supplementary magnitude layer.
- `tests/unit/whatif/decision/guards/_helpers.py` — extended `failure_cohort` with optional rate-count kwargs; added `baseline_cohort` builder.
- `tests/unit/whatif/decision/guards/test_baseline_regression.py` — 11 tests covering boundary at exactly-threshold, custom thresholds (strict + lenient), missing cohort, zero-scored guard, and message format.
- `tests/unit/whatif/decision/guards/test_failure_improvement.py` — 12 tests including a `TestPrimaryEndpointPairing` class that pins independence: each rate-based guard reads only its own cohort's counts.

### Added — Phase 2.5 (guard chain — protocol + first two guards)

- `src/whatif/decision/guards/protocol.py` — `Guard` Protocol (callable taking `Sequence[CohortResult]` + `DecisionPolicy`, returning `list[DecisionFinding]`) plus `run_guards` chain composer that concatenates findings in registration order. Guards are pure functions; they never raise (cardinal #1: expected failures are data; unexpected failures propagate).
- `src/whatif/decision/guards/practical_delta.py` — `practical_delta_guard`. Cardinal rule #10 enforcement: emits `practical_delta_below_threshold` (blocks_ship) when the failure cohort's median delta is at or below `policy.practical_delta_epsilon`. Equality counts as below-threshold (small statistical wins inside the noise floor are not shippable).
- `src/whatif/decision/guards/improvement_observation.py` — `improvement_observation_guard`. Emits `improvement_observed` (info) when the failure cohort's median delta is strictly above the epsilon. Mutually exclusive with `practical_delta_guard` by design (`<=` vs `>`); together they partition the real line.
- `tests/unit/whatif/decision/guards/` — 26 tests across protocol/chain composition (registration order, fresh-list semantics, empty chain, zero-finding guards), practical_delta boundary cases (exactly at epsilon, negative delta, custom epsilon, malformed delta string), improvement_observation boundary cases, and the mutual-exclusion invariant.
- Subsequent guards (`baseline_regression`, `failure_improvement`, `ci_availability`, `cache_staleness`, `primary_endpoint`) land in follow-up PRs as their dependencies arrive (CohortResult rate-count extension, `ci_unavailable_for_required_cohort` finding code, Phase 3 cache metadata, Phase 2.6 endpoint-resolution logic).

### Changed — contributor tooling

- Vendored the `whatif-design` skill from the parent workspace into `.claude/skills/whatif-design/` plus a project-rooted `CLAUDE.md` so contributors get the doctrine on a clean clone. Layout: `SKILL.md` (router) + `references/{doctrine,practices,contracts,type-model,phases,enforcement,statistical-defaults,walkthroughs,cascade-catalog}.md`. The parent-workspace deliberation drafts and decision record are intentionally not vendored (they reference private reasoning artifacts). `.gitignore` extended for Claude Code session-runtime artifacts (`scheduled_tasks.lock`, `cache/`, `state/`) without excluding the skill itself. Cascade-catalog entry "Dashboard SKILL_DIR resolution" marked resolved-2026-05-05.

### Added — Phase 2.4 (fix-suggestion registry, cardinal #8 gate)

- `src/whatif/decision/fix_suggestions.py` — `FixSuggestion` (finding_code, summary, ordered tuple of Markdown step strings, internal description) plus `FIX_SUGGESTION_REGISTRY` (frozen `MappingProxyType` over six suggestions, one per blocking finding code: `baseline_regression_above_threshold`, `failure_improvement_below_threshold`, `practical_delta_below_threshold`, `cache_corruption_detected`, `cache_lock_unavailable`, `cohort_systemic_failure`). Step text on cache-related suggestions matches the recovery playbook in walkthrough scenario 5.
- `tests/unit/whatif/decision/test_fix_suggestions.py` — 14 tests across registry shape (snake_case keys, finding_code/key consistency, ≥1 step per entry, non-empty steps as strings, tuple ordering, frozen `FixSuggestion`, `MappingProxyType` immutability) and the cardinal #8 cross-registry gate: positive coverage (every blocking finding has a fix suggestion), inverse coverage (every fix suggestion targets a real finding code), negative coverage (no info finding code appears here — addresses PR #17 review suggestion), and the composite "exact match" assertion.

### Changed — Phase 2.4

- `tests/unit/whatif/decision/test_finding_codes.py` — removed the `xfail(strict=True)` placeholder for `TestCrossRegistryCoverage`; the canonical coverage gate now lives next to `FIX_SUGGESTION_REGISTRY` in `test_fix_suggestions.py`. A short comment marks the relocation.

### Added — Phase 2.3 (finding code registry)

- `src/whatif/decision/finding_codes.py` — `FindingCodeSpec` (severity, message_template, required_details tuple, derived_from_failures_expectation, description) plus `FINDING_CODE_REGISTRY` (frozen `MappingProxyType` over the v0.1 starter set: 1 info code, 3 blocks_ship codes, 3 blocks_all codes — 7 total). The `make_decision_finding` factory pulls severity from the registry (deliberately non-overrideable per cardinal #2 — severity drives verdict) and validates the derived_from_failures expectation (`"never"` rejects non-empty, `"always"` rejects empty, `"sometimes"` unconstrained).
- `tests/unit/whatif/decision/test_finding_codes.py` — 25 tests across registry shape (snake_case codes, valid Severity literal, non-empty descriptions and message templates, frozen `FindingCodeSpec`, `MappingProxyType` immutability), placeholder/required_details symmetry on the message template, severity-specific shape rules (every `blocks_all` code expects failure derivation; every `info` code does not), positive sweep, contract-violation rejection, and severity non-overrideable enforcement. Includes a `strict=True` xfail placeholder for the Phase 2.4 cross-registry coverage test (`every blocking finding has a fix suggestion`); the xfail flips to a regular passing test when Phase 2.4 ships `FIX_SUGGESTION_REGISTRY`.
- `tests/unit/whatif/decision/test_failure_codes.py` — added `TestStageScopeReachability`: `default_scope=="trace"` ⇒ stage in {ingest, selection, replay, score, diff}; `default_scope=="cohort"` ⇒ stage in {decision, report}; run-scope unconstrained. Catches future drift on registry edits. Addresses the structural-invariant suggestion from PR #16's review.

### Added — Phase 2.2 (failure code registry)

- `src/whatif/decision/failure_codes.py` — `FailureCodeSpec` dataclass (stage, default_scope, required_details tuple, retryable_default, description) plus `FAILURE_CODE_REGISTRY` (frozen `MappingProxyType` over the v0.1 starter set: `trace_schema_mismatch`, `trace_invalid`, `tool_cache_miss`, `runner_timeout`, `runner_exception`, `scorer_unavailable`, `scorer_invalid_output`, `ci_uncomputable_for_required_cohort`, `cache_lock_unavailable`, `cache_corruption_detected`). The `make_failure_record` factory pulls defaults from the registry and validates programmer-contract invariants — unknown code, missing required details, scope/identifier mismatch — with `ValueError` (cardinal #1: expected failures are data, contract violations are bugs in whatif itself).
- `tests/unit/whatif/decision/test_failure_codes.py` — 27 tests across registry shape (lowercase snake_case codes, valid stage/scope literals, non-empty descriptions, `MappingProxyType` immutability), positive sweep over every registered code, default propagation, scope override for Phase 2.7 aggregation, and contract-violation rejection (unknown code, missing required details, all six scope/identifier mismatches).

### Added — Phase 2.1 (floor evaluator)

- `src/whatif/decision/floor.py` — replaced the Phase 1.4 stub `evaluate_floor()` with the real signature `evaluate_floor(cohort_results, floor, required_cohorts, *, now=None)`. The proof's `evaluated_at` is now an ISO 8601 timestamp from the injected clock (defaults to UTC wall clock); `floor_version` is propagated from the `TrustFloor` argument. Introduced `compute_cohort_floor_failures(cohort, floor)` as the per-cohort rule helper — checks `min_selected`, `min_replayed`, `min_scored` (each emitting `blocks_all` on failure) and `min_replay_validity_ratio` (emitting `blocks_ship` on failure, skipped when `selected == 0`). The aggregator emits a `required_cohort_present` failure (severity `blocks_all`) when a required cohort is absent from the input. An empty `required_cohorts` is itself a structural failure (`required_cohorts_nonempty`, severity `blocks_all`) per cardinal #2 — a misconfigured policy with nothing to require would otherwise produce a vacuous proof and bypass the floor.
- `tests/unit/whatif/decision/test_floor.py` — 17 new tests covering per-cohort rule trips at boundaries, ratio computation, zero-selected guard, custom thresholds, cross-cohort aggregation, missing-cohort detection, non-required cohort isolation, ISO timestamp emission and round-trip, and floor-version propagation. The seven Phase 1.4 witness/immutability/equality tests were updated to call `evaluate_floor` with passing-cohort fixtures and a fixed clock.

### Added — Phase 1 (type model)

- `src/whatif/types/primitives.py` — `DecimalString` (NewType over `str`) and `JsonPrimitive` (`str | int | float | bool | None`). The two smallest building blocks for the internal type model. Cardinal rule #4 (determinism opt-in per field) and #6 (public schema hand-written).
- `src/whatif/types/sensitive.py` — `Sensitive[T]` redaction wrapper (cardinal rule #5). `__repr__` / `__str__` / `__format__` / `__reduce__` all return the redacted form so f-strings, log lines, and pickle never leak the wrapped value. `.unwrap(reason=...)` returns the value AND records a `SensitiveUnwrap` audit entry to a thread-safe in-process collector. Includes `SensitiveSerializationError`, `UnredactedSensitiveError` exception types and an `_infer_caller()` helper that auto-fills the unwrap call site.
- `src/whatif/types/__init__.py` — re-exports the public surface and documents the Phase 1 sub-ordering (1.1 primitives → 1.2 sensitive → 1.3 operational → 1.4 verdict → 1.5 policy → 1.6 manifest → 1.7 statistical).
- `tests/unit/whatif/types/` — nested test layout. 22 tests across `test_primitives.py` (5: construction, str-runtime, fixed-precision preservation, JsonPrimitive scalar acceptance, import-budget < 50 ms) and `test_sensitive.py` (17: redacted serialization × 4, pickle blocking, slots discipline × 2, unwrap behavior × 5, audit-log concurrency × 2, infer-caller, exception type distinction × 2).

### Added — Phase 0 (paper artifacts)

- `docs/walkthroughs/` — six rendered Markdown reports (clean Ship, Don't Ship regression, Don't Ship failure-rescue gap, Inconclusive insufficient sample, Inconclusive cache corruption, rerun-after-fix diff) plus a README index. These are the canonical Phase 7 renderer test fixtures. Each includes a `## Methodology` block per cardinal rule #10. The empirical reviewer for the design.
- `docs/concepts.md` — two-page conceptual model document plus glossary. Distilled from the doctrine and the walkthroughs. Sections: defensible verdicts, non-claims, verdict states, trust floor vs decision policy, failure-as-data, evidence and audit bundle, privacy and redaction, examples of misleading outputs whatif must never produce.
- `docs/internal/PHASE_0_4_ENFORCEMENT_AUDIT.md` — Phase 0.4 audit report. Inventories every "structural" claim across the skill, cross-references against `enforcement.md` (now 14 rows), confirms each open cascade has a resolution phase. Closes Phase 0 gate.
- `docs/sessions/` — Layer 2 telemetry session logs (`2026-05-04`, `2026-05-05`).

### Added — telemetry bundle (skill instrumentation)

- `tools/pr_checker.py` — Claude-based PR doctrine reviewer. Reads PR metadata + diff via `gh`, checks the change against the project's ten cardinal rules using the Anthropic SDK (`claude-haiku-4-5` default), emits a structured verdict. Exit codes match whatif's own verdict semantics (0=Ship, 1=Don't Ship, 2=Inconclusive). Every failure path is a typed `ReviewVerdict`, never an exception (cardinal rule #1).
- `.github/workflows/pr-review.yml` — GitHub Actions workflow that runs `tools/pr_checker.py` on every PR. Inconclusive surfaces as a warning + PR comment but does NOT block merges (advisory only).
- `.mcp/run_pr_check_claude.sh`, `.mcp/run_pytest.sh` — MCP-server wrapper scripts.
- `.github/mcp-claude.md`, `.github/mcp-pytest.md` — MCP server configuration documentation.
- `.github/copilot-instructions.md` — repo-specific Copilot guidance with the canonical `src/whatif/` layout and Phase-N-status annotations per directory.
- `scripts/collect-transcripts.sh`, `scripts/run-skill-benchmark.sh`, `scripts/grade-skill-benchmark.sh`, `scripts/skill-dashboard.sh` — four-layer skill-instrumentation bundle.
- `tests/skill-benchmarks/prompts.json` — 11 benchmark prompts (8 should-trigger covering cardinal rules 2/5/9/10 + doctrine + scope + enforcement; 3 negative tests).
- `CLAUDE.md.append.md` — session-telemetry protocol block for adopters.
- `AGENT_TELEMENTRY.md` — telemetry bundle documentation.

### Changed

- Adopted cardinal rule #10 ("Statistical claims must match the design") into the `whatif-design` skill at `.claude/skills/whatif-design/`. New rule + supporting `statistical-defaults.md` reference + `MethodologyDisclosure` types added to the type model. The `methodology` field on `ReportV01` is now required; schema validation enforces presence.
- Phase 0.3 audience-distribution decision: ship v0.1 as `failure_rescue` only; ROADMAP `regression_check` for v0.2; revisit after first 5 production users. Schema keeps `cohort: str` (not `Literal`) so v0.2 expansion is non-breaking. Recorded as an addendum in `references/V0_1_DECISION_RECORD.md`.

### Fixed

- `pip-audit` step in `.github/workflows/security.yml` — `pip-audit` 2.10.0 rejects `--disable-pip` without `-r`, breaking the weekly run. Install the project with all extras and audit the resulting environment, filtering whatif itself (pre-release; not on PyPI). Match both `whatif==` and `whatif @ file:///` freeze-output formats per pip 25+.
- `.github/workflows/ci.yml` — restored `actions/checkout` step in lint and test jobs (dropped by a dependabot merge), unified `setup-uv` to `@v7`, fixed stray blank lines.

### Removed

- `.github/workflows/codeql.yml` — replaced by GitHub's Default Setup (no custom workflow file). The custom workflow conflicted with Default Setup's SARIF processing.

### Notes

- Phase 0 gate: GREEN. Phase 1 in progress (1.1 primitives, 1.2 Sensitive[T] complete; 1.3–1.7 pending).
- 22 tests in `tests/unit/whatif/types/` plus the 10 existing contract tests = 32 tests passing on the v0.1 branch.

---

### Added — earlier scaffold (pre-Phase-0)

- Initial public scaffold:
  - `DESIGN.md` - canonical design through the M10–M12 roadmap; problem framing, prior art, runner contract, report shape, eval target, risks, Path Z.
  - `LICENSE` - Apache 2.0.
  - `README.md - hero copy + workflow / overview / pipeline images + status table + runner contract teaser.
  - `pyproject.toml` - uv-managed; src layout; Python ≥ 3.11; ruff/mypy/pytest configured.
  - `src/whatif/__init__.py` - version 0.0.1.
  - `src/whatif/contract/__init__.py - runner contract Pydantic models: `TraceInput`, `ReplayConfig`, `ToolCache`, `ReplayOutput`, `TraceOutput`, `ScoreCase`, `Runner` Protocol.
  - `tests/test_contract.py - 10 smoke tests for the contract API.
  - 3 architectural / workflow images in the repo root.
- Production-grade GitHub plumbing:
  - `.github/workflows/ci.yml - lint (ruff), type-check (mypy), test on Python 3.11 / 3.12 / 3.13.
  - `.github/workflows/security.yml - `pip-audit`, `bandit`, `gitleaks`; runs on push, PR, and weekly schedule.
  - `.github/workflows/codeql.yml - CodeQL static analysis with `security-extended` + `security-and-quality` queries.
  - `.github/workflows/release.yml - sdist + wheel build, PyPI publish via Trusted Publishers, GitHub Release with auto-generated notes; triggered by `v*.*.*` tags.
  - `.github/dependabot.yml - weekly grouped pip + GitHub Actions updates.
  - `.github/CODEOWNERS - review routing.
  - `.github/PULL_REQUEST_TEMPLATE.md - PR checklist with whatif-specific gates.
  - `.github/ISSUE_TEMPLATE/ - bug + feature templates with structured fields, plus a `config.yml` that disables blank issues and routes to Discussions / private security advisories.
- Project governance:
  - `CONTRIBUTING.md - branch strategy, commit conventions, PR / merge / release workflow, manual GitHub config checklist.
  - `CODE_OF_CONDUCT.md` -Contributor Covenant 2.1 (adopted by reference).
  - `SECURITY.md - disclosure policy, scope, coordinated disclosure timeline.
  - `.pre-commit-config.yaml` - ruff + ruff-format + mypy + standard hygiene hooks.

### Notes

- No runtime yet. v0.1 - Langfuse ingest, replay engine, Inspect AI scorer, evidence - first Markdown + JSON reports, CI-ready exit codes-begins in M10.

---

[Unreleased]: https://github.com/victoralfred/whatif/commits/main
