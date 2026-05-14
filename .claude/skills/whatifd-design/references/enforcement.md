# Enforcement

Every structural claim must have a paired enforcement mechanism. Convention with a strong adjective is not enforcement. This file is the audit trail.

If you find yourself writing the word "structural" elsewhere, check that the claim appears here with a mechanism. If it doesn't, either add it with a mechanism, or weaken the claim.

## The enforcement table

| Structural claim | Enforced by |
|---|---|
| Floor cannot be overridden | `FloorPassedProof` witness token; `Ship` cannot be constructed without it; `evaluate_floor()` is the only producer; `_FLOOR_INTERNAL_TOKEN` is module-private. Property test: no `DecisionPolicy` configuration produces `Ship` when `evaluate_floor()` returns `FloorFailure`. |
| Sensitive fields cannot be written without redaction | Three layers: (a) `Sensitive[T]` type wrapper enforced via mypy strict; (b) pre-serialization graph walk `assert_no_unredacted_sensitive(obj)` before any artifact write; (c) `WhatifJSONEncoder.default()` raises `UnredactedSensitiveError` as last line. Audit is grep-able via `.unwrap(` call sites. Banned-import lint blocks `json.dumps` outside `whatifd/serialization/`. |
| PII-bearing metadata attributes at the adapter boundary (issue #87) | `whatifd.adapters.PII_ATTRIBUTE_KEYS` registry names attribute keys (OpenInference + Langfuse conventions) whose values MUST be `Sensitive[str]` or `None`. Layer (a): `RawTrace.metadata` Pydantic `model_validator(mode="after")` rejects unwrapped values at registered keys, raising at construction-time before the trace flows through the pipeline. Layer (b): conformance harness's `test_emitted_traces_wrap_pii_attributes` walks every emitted RawTrace from every adapter and asserts the same property. Layer (c): the existing graph-walk catches any `Sensitive[T]` that would otherwise reach serialization. Adapter ergonomics: `whatifd.adapters.wrap_pii_attributes(raw_dict)` produces the typed shape mechanically — adapters call it once per projection. |
| Single-writer cache access | OS-level `fcntl.flock(LOCK_EX | LOCK_NB)` is primary defense (reliable on Linux, releases on process death including SIGKILL). Stale-lock fallback: lock file records `{pid, process_start_time, hostname, started_at}`; takeover requires both `os.kill(pid, 0)` raising `ProcessLookupError` AND `psutil.Process(pid).create_time()` mismatch with recorded start time. NFS unsupported (documented). Conflict produces typed `CacheLockedError` with exit code 2. |
| Same inputs → byte-identical JSON | (a) Schema-tag-based determinism: each field in `ReportV01` annotated `x-deterministic: true | false`; new fields default to false. (b) Numeric fields in determinism budget use `DecimalString` (`format(value, '.3f')`), not float. (c) Sorted JSON keys via custom encoder. (d) Seeded sampling in selection. (e) Injected clock for tests. (f) CI test diffs only `x-deterministic: true` subset across two runs of same input. (g) Python interpreter version pinned in determinism CI test. |
| Cache disclosure cannot be disabled | `cache_summary: CacheSummary` is a required field on `ReportV01`. Schema validation fails if missing. `CacheSummary` is itself a typed object with required fields (mode, hits, misses, writes, stale_hits, corrupted_entries, schema_version, key_version, storage_profile, policy). Required-field schema validation enforces content, not just presence. |
| Failures-as-data (no silent crashes) | All adapter and core code paths produce `FailureRecord` for expected failures, never raise unhandled exceptions to the CLI. Property test: synthetic adversarial inputs (malformed traces, scorer errors, network failures) all produce reports with non-empty `failures` array, no uncaught exceptions. CLI never exits 1 with an unhandled traceback for foreseeable failure modes. **Bug paths (not data paths)** raise `whatifd.exceptions.InvariantViolationError` — a typed exception subclassing `Exception` directly (not `ValueError`/`RuntimeError`) so call-site intent is legible: structural type contract violated upstream, not a runtime data condition. Cardinal #1's "no silent crashes" promise covers expected failures; programmer-contract violations are bugs and propagate as typed errors with chained `__cause__`. See `src/whatifd/exceptions.py` for the class docstring + boundary criteria. |
| Inconclusive must be actionable | Every `FloorRule` and every `DecisionFindingCode` with `severity in {blocks_ship, blocks_all}` has a registered entry in `FIX_SUGGESTION_REGISTRY`. CI test enumerates the registry and asserts coverage. The renderer queries the registry when rendering Inconclusive or Don't Ship and inserts the fix text into the report. |
| Public schema is hand-written | Public types live in `whatifd/report/models_v01.py`; internal types in `whatifd/internal/`. Projection functions in `whatifd/report/projection.py` translate. CI test: `test_no_internal_types_in_public_module` asserts no imports from `whatifd/internal/` into `whatifd/report/models_v01.py`. CI test: `test_schema_matches_models` regenerates JSON Schema from `ReportV01` and diffs against committed `schemas/report/v0.1.schema.json`. |
| Two-affirmation for forensic profile | Both required: `reporting.profile: forensic` AND `reporting.forensic_acknowledgment` block in config, AND `--profile forensic` CLI flag. Validation function rejects with typed errors if either is missing. Both affirmations are disclosed in `manifest.runtime`. CI test asserts that single-affirmation attempts fail. |
| Verdict-state space is closed | `Verdict = Ship | DontShip | Inconclusive` is a sealed union. Pattern matching with `match` statement in renderers; mypy strict catches missing cases. Adding a new verdict state in v1.0 requires schema major version bump. |
| Methodology disclosure cannot be omitted | `ReportV01.methodology: MethodologyDisclosure` is a required field. Schema validation enforces presence; required-field validation enforces content of all five sub-disclosures (`BootstrapMethodDisclosure`, `MultiplicityDisclosure`, `JudgeMethodDisclosure`, `EffectSizeDisclosure`, plus the parent). Renderer test asserts the methodology block appears in every full-form rendered report. |
| Causal-claim scope cannot be exceeded | `MethodologyDisclosure.causal_claim_scope: Literal["associated_under_cached_tool_replay"]` is sealed at the type level for v0.1; mypy strict catches assignments of other values. Renderer-template test asserts no rendered output contains "caused" without "associated under cached-tool replay" in the same paragraph. |
| Per-trace inference is descriptive only | `MethodologyDisclosure.per_trace_inference: Literal["descriptive_only"]` is sealed. Renderer's per-trace evidence section emits the disclaimer "No per-trace statistical significance is claimed. Evidence examples are descriptive." Renderer test asserts the disclaimer appears whenever per-trace evidence is rendered. |
| Paired-delta is the unit of analysis (cannot be unpaired) | `TraceDelta` internal type stores `original_score`, `replayed_score`, and the computed `delta` together. Analysis functions in `whatifd/internal/stats.py` accept `Sequence[TraceDelta]` exclusively — function signatures forbid `Sequence[float]` original + `Sequence[float]` replayed as a pair, which would invite accidental unpaired analysis. mypy strict catches misuse at type-check; banned-import lint asserts no `whatifd/internal/stats.py` callers pass score arrays directly. Cardinal rule #10. |
| `ci_computable=False` on a required cohort cannot Ship | Per V0_1_DECISION_RECORD §2's CI split: `ci_computable: bool` is a typed required field on `CohortResult` (no default; mypy strict refuses construction without it — type-level prevention is the first defense). `ci_availability_guard` reads it and emits `ci_unavailable_for_required_cohort` at `blocks_all` severity for any required cohort with `ci_computable=False`. `compute_verdict` routes `blocks_all` to `Inconclusive` regardless of policy. There is no `--accept-no-ci` escape hatch (§6); `policy.max_ci_width` is the lever for accepting wider but computable CIs and operates on the policy side via the deferred `ci_meaningful` guard (Phase 3, cascade-tracked). Tests: `tests/unit/whatifd/decision/guards/test_ci_availability.py` covers the emission + boundary behavior. |
| Floor vs policy concerns are partitioned on `CohortResult` | Per V0_1_DECISION_RECORD §2: `ci_computable` (structural, `blocks_all`) and `ci_meaningful` (policy-quality, `blocks_ship`, deferred Phase 3) are separate fields. `CohortResult.__post_init__` raises `InvariantViolationError` if `ci_meaningful=False` is constructed without `ci_computable=True` — meaningfulness is the quality assessment of a CI that exists; an incoherent combination cannot be constructed. Tests: `TestCiMeaningfulSplit` in `tests/unit/whatifd/types/test_cohort.py` pins all four valid/invalid shapes; `TestCiMeaningfulBoundary` in `test_ci_availability.py` pins that `ci_availability_guard` reads only `ci_computable`. |

## How to add a new structural claim

The pattern:

1. **State the claim.** "X cannot happen."
2. **Identify what would falsify it.** What would a malicious or careless contributor have to do to break it?
3. **Pick a mechanism that catches the falsification.** Type-level prevention > property test > runtime assertion > convention. Choose the strongest available.
4. **Write the test that proves the mechanism works.** A claim without a test is a claim without an enforcement.
5. **Add the row to this table.** Schema-freeze test asserts every "structural" claim in the codebase appears in this table.

The hierarchy of strength:

- **Type-level prevention** — `mypy strict` catches at type-check time. Witness tokens, sealed unions, opaque types. Cannot be bypassed without rewriting the type system.
- **Pre-serialization / pre-write hooks** — runtime checks before data leaves the boundary. Graph walks, encoder hooks. Can be bypassed by going around the boundary, which is detectable.
- **Property tests** — sample-based coverage of configuration space. Catch regressions in known-shape configurations. Cannot catch novel bypass patterns the test author didn't imagine.
- **CI lint rules** — banned imports, banned patterns. Catch contributor mistakes at PR time.
- **Convention with documentation** — weakest. Drifts under contributor pressure. Use only when stronger mechanisms aren't available.

## Common patterns and where they apply

### Witness tokens (capability-based prevention)

When a value type should only be constructible via a specific function, give the type a private constructor that requires a token. The token is module-private. The function returns a new token on success.

Used for: `FloorPassedProof` (`Ship` requires this).

Cascade catalog item: closure-capture variant for v1.0 strengthens this — `evaluate_floor` returned from a module-init factory with the token closed over. Closer to true capability security.

### Type wrappers with redacted defaults

When a value should never be serialized in raw form, wrap it in a type whose `__repr__`, `__str__`, `__format__`, `__reduce__`, and `default()` all produce redacted output. Provide an explicit unwrap with audit logging.

Used for: `Sensitive[T]` (user content from adapters).

### Pre-write graph walks

When a property should hold over an entire object graph (no `Sensitive` anywhere, no `dict[str, Any]` anywhere), walk the graph before serialization and refuse on first sight.

Used for: redaction enforcement.

### Sealed unions with mypy

When a value space is closed (Verdict is exactly three states), use a union type. mypy strict catches missing pattern-match cases at type-check time. Adding a new variant becomes a deliberate, reviewable change.

Used for: `Verdict`, `FloorEvaluation = FloorPassedProof | FloorFailure`.

### Schema-tag determinism

When a property applies to a subset of fields, tag the fields in the schema and have the test enumerate them at runtime. New fields default to non-tagged (out of the budget); opting in requires explicit annotation.

Used for: determinism budget. Generalizable to any cross-cutting property (PII-bearing, retention-relevant, externally-visible).

### Two-affirmation structurally-dangerous capabilities

When a capability is dangerous if accidentally enabled, require affirmation across two surfaces (config + CLI, or two separate config blocks). One alone is insufficient.

Used for: forensic profile. Generalize to v1.0 acceptance flags.

## What "structural" does NOT mean

- "We strongly recommend." — that's documentation, not enforcement.
- "The property test catches it." — only catches what the test imagined; not type-level.
- "Code review will notice." — social enforcement, drifts under pressure.
- "It's in the contributing guide." — see above.

If the only mechanism is one of the above, the claim is **convention**, not structural. State it as such. Convention is fine for things that can drift safely. Structural is for things that cannot.

## The enforcement audit

Before schema freeze, run the enforcement audit:

1. Grep the codebase for "structural" / "cannot be" / "must" in docs and comments.
2. For each occurrence, confirm it appears in the enforcement table above with a mechanism.
3. For each table row, confirm the mechanism actually exists in code (not just in plan).
4. For each mechanism, confirm there's a test that exercises it.

Gaps from the audit feed the cascade catalog.
