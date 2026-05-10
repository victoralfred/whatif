---
session_id: 2026-05-10-phase-j-design-record
started_at: 2026-05-10T00:00:00Z
type: design-record
status: IMPLEMENTED (PR #95)
---

# Phase J — Determinism widening: design record

## Why this document exists

The `v0.2-roadmap.md` declares Phase J in two sentences:

> **Determinism widening:** Audit remaining nondeterministic-but-shouldn't-be fields; promote into `x-deterministic`. Cross-platform byte-equality test on the widened subset.

The substantive design — *what to promote, how to extend the schema generator, what the cross-platform test looks like* — is undecided. This doc proposes the design before any code lands so the choices are reviewable.

The whatifd repo's discipline: cascade-catalog entries describe what shipped, after-the-fact. This is the inverse — a pre-PR design record so the user can push back on scope, alternatives, and acceptance criteria before implementation.

## What "deterministic" means for whatifd

**Cardinal #4 (per `SKILL.md`):** determinism is opt-in *per field*, default off. The schema's `x-deterministic: true` annotation marks fields whose values are byte-stable across re-runs of the same fixture.

**Today's surface:**

- Top-level `ReportV01` fields are individually annotated. `runtime` is the only one tagged `x-deterministic: false`; everything else is `true`.
- The CI determinism test (`tests/integration/test_determinism.py`) extracts the deterministic subset by reading the schema's `x-deterministic` annotations and asserts byte-equality on the projected subset across two pipeline runs of the same fixture.
- **The annotation surface stops at the top level.** The schema generator (`scripts/generate_schema.py:212-213`) annotates `ReportV01.properties[name]` and never descends. `runtime`'s sub-fields are not individually tagged.

**The drift today:**

`RunManifest`'s docstring (in `src/whatifd/types/manifest.py`) explicitly documents which sub-fields ARE deterministic by intent:

> The whole manifest is non-deterministic by default; the schema explicitly tags deterministic sub-fields (`trust_floor`, `decision_policy`, `selection_seed`, `config_hash`, `whatif_version`) with `x-deterministic: true`.

But the schema generator never emits those annotations on the sub-fields, so the docstring's claim is **convention-only**, not structurally enforced. A future refactor that swaps `selection_seed: int` for a `time.time()`-based fallback would silently break determinism without failing the determinism test (because `runtime` is excluded as a whole).

That's the gap Phase J closes.

## Proposed scope

### In scope

1. **Per-field `x-deterministic` annotations inside `runtime`.** Extend the schema generator to descend into nested dataclasses and emit `x-deterministic: true|false` on each field individually, not just at the top level.

2. **Promote the documented-deterministic `RunManifest` sub-fields:**

   | Sub-field | Today | After Phase J | Rationale |
   |---|---|---|---|
   | `experiment_id` | non-det (blanket) | **det** | caller-supplied stable id; same fixture → same id |
   | `whatif_version` | non-det (blanket) | **det** | the version that ran; pinned per release |
   | `config_hash` | non-det (blanket) | **det** | sha256 over the config; deterministic by construction |
   | `selection_seed` | non-det (blanket) | **det** | seeded RNG input; deterministic by construction |
   | `source` | non-det (blanket) | **det** | adapter identifier (`"langfuse"`, `"phoenix"`, `"stub"`) |
   | `target` | non-det (blanket) | **det** | runner reference (`"python:my_agent.replay:run"`) |
   | `trust_floor` | non-det (blanket) | **det** | structural policy; deterministic by construction |
   | `decision_policy` | non-det (blanket) | **det** | structural policy; deterministic by construction |
   | `experiment_shape` | non-det (blanket) | **det** | Phase A field; declared per run |
   | `started_at` | non-det | non-det | wall-clock timestamp |
   | `finished_at` | non-det | non-det | wall-clock timestamp |
   | `duration_ms` | non-det | non-det | wall-clock derived |
   | `environment.python` | non-det | non-det | per-host |
   | `environment.platform` | non-det | non-det | per-host |
   | `environment.whatif_version` | non-det | non-det | redundant with `runtime.whatif_version`; sub-field stays non-det because EnvironmentFingerprint is captured for *audit* (host-specific), not byte-equality |
   | `environment.dependencies` | non-det | non-det | pip-resolution-dependent |
   | `agent_identity` | non-det | non-det | optional Mapping; ordering not guaranteed in v0.2 |
   | `redaction` | non-det | non-det | adapter-specific; profile dependent |
   | `sensitive_unwraps` | non-det | non-det | call-order dependent |

3. **Cross-platform byte-equality test.** Today's `test_determinism.py` runs on Ubuntu only. Phase J adds a CI-matrix test that runs the determinism comparison on Ubuntu + macOS, asserting the deterministic-subset bytes are identical across runner OSes.

4. **Backwards-compatible schema bump.** Adding `x-deterministic` annotations to existing fields is a non-breaking change: consumers reading the v0.2 schema already ignore unknown annotations on `$defs` properties. The `REPORT_SCHEMA_VERSION` stays `"0.2"` (Phase A's bump).

### Out of scope

- **`environment.dependencies` ordering.** Pip-resolution order is build-host-dependent. A future Phase could canonicalize it (sort by package name) but it doesn't unblock anything in v0.2.
- **`sensitive_unwraps` ordering.** Cross-thread call ordering is structurally non-deterministic. Sorting by `(timestamp, classification, reason_hash)` is a v0.3+ project.
- **Promoting `agent_identity`.** v0.2 leaves it `Mapping[str, str] | None`; a future schema-bump may freeze its key ordering.
- **Walkthrough fixture regeneration.** Walkthrough fixtures already encode the documented-deterministic fields with stable values; no changes required.
- **Cross-platform Python version drift.** Floats are formatted via `DecimalString` (already byte-stable); JSON keys are sorted in `canonical_json_bytes`. The cross-platform test should pass without further work, but if it surfaces a real platform-specific bug, the fix lands as part of Phase J.

## Design choices (with alternatives considered)

### Choice 1: How to declare per-field determinism on the dataclass

**Decision:** Add a class-attribute frozenset of deterministic field names: `RunManifest._DETERMINISTIC_FIELDS = frozenset({"experiment_id", "whatif_version", ...})`. The schema generator reads this attribute when descending.

**Alternatives considered:**

- **`Annotated[T, "deterministic"]`.** Cleaner per-field but requires `typing.Annotated` walking in the schema generator and breaks `dataclasses.fields()` introspection ergonomics.
- **A `deterministic=True` kwarg on `dataclasses.field()` via `metadata`.** Works but `dataclasses.field` metadata is opaque dict; loses type-checker visibility.
- **A separate registry module.** Loose coupling; the source-of-truth becomes a separate file, easier to drift from the dataclass.

The class-attribute frozenset is the most boring choice: visible at the dataclass definition, accessible via `getattr(cls, "_DETERMINISTIC_FIELDS", frozenset())`, no library dependencies.

### Choice 2: Where the schema generator emits the annotations

**Decision:** When the generator encounters a dataclass that has `_DETERMINISTIC_FIELDS`, emit `x-deterministic: true|false` on each property of its `$def` based on whether the field name is in the frozenset.

**Alternatives considered:**

- **Annotate only at the top level.** Keeps the schema flat but doesn't structurally enforce the runtime-sub-field claims.
- **Annotate every `$def` property.** Over-tags fields that don't have a determinism opinion (e.g., `CohortResult.name` is "deterministic" but only via the top-level cohort_results array's annotation propagation — annotating it twice is noise).

Per-field-on-opt-in dataclasses is the minimal change.

### Choice 3: How `extract_deterministic_subset` walks the new annotations

**Decision:** When the top-level field is `runtime` (currently `x-deterministic: false`), the extractor recursively projects the sub-fields tagged `x-deterministic: true` from the schema's `$def` for `RunManifest`. Other top-level fields keep current behavior (whole-subtree included or excluded).

**Alternatives considered:**

- **Promote `runtime` to top-level `x-deterministic: true`.** Wrong: most of `runtime` is genuinely non-deterministic. Promoting whole-subtree would re-introduce the test-flake class the v0.1 design avoided.
- **Add a parallel `runtime_deterministic` top-level field.** Doubles the wire surface for no consumer benefit.

The recursive descent only fires when the top-level field is excluded by blanket but has internally-tagged sub-fields. Other top-level fields are unchanged.

### Choice 4: Cross-platform CI test shape

**Decision:** Extend `.github/workflows/ci.yml`'s `test` matrix with `os: [ubuntu-latest, macos-latest]` for a single test file (`tests/integration/test_determinism_cross_platform.py`). The test:

1. Runs the same fixture through `run_pipeline`.
2. Computes `extract_deterministic_subset` on the resulting `ReportV01`.
3. Writes the canonical JSON bytes to a workflow artifact.
4. A separate matrix-finalizer job downloads both artifacts and asserts byte-equality.

**Alternatives considered:**

- **Cross-version Python.** Already covered by the existing matrix; not what cardinal #4's "cross-platform" means.
- **Windows.** Composite-action support for `whatifd-fork` is conditional (Phase I); core whatifd library should work on Windows but isn't a v0.2 promise. Add later.
- **Run inside Docker.** Defeats the purpose — we want to catch real-runner platform drift.

The matrix-finalizer pattern is the standard GitHub Actions idiom for cross-job byte-equality assertions.

## Acceptance criteria (the gate)

1. **Schema generator** descends into dataclasses with `_DETERMINISTIC_FIELDS` and emits per-field `x-deterministic`.
2. **`v0.2.schema.json` regenerated** with the new annotations on `RunManifest`'s `$def`. v0.1 frozen schema unchanged.
3. **`extract_deterministic_subset`** projects `runtime` to the sub-fields tagged deterministic, not the whole subtree.
4. **Existing single-platform `test_determinism.py`** still passes (the new annotations are a strict superset of what was deterministic before).
5. **New cross-platform CI matrix** asserts byte-equality of the deterministic-subset JSON across Ubuntu + macOS runners on the same fixture. Cardinal #4 honored structurally, not by convention.
6. **Cascade-catalog entry** documents the rippled invariants: which fields moved, the schema-generator extension, the matrix-CI shape.
7. **CHANGELOG** entry under `[Unreleased]` describes the user-visible change ("more fields are now byte-stable across re-runs and across platforms").

## Risk inventory

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Cross-platform test surfaces an existing bug (e.g., float formatting drift on macOS) | medium | medium | If real, fix as part of Phase J. The bug exists today regardless; Phase J just makes it visible. |
| `RunManifest` field that's "documented deterministic" turns out to vary in practice (e.g., `source` adapter id changes case across runners) | low | low | The cross-platform test catches it; promote-or-not decided per finding. |
| Walkthrough fixtures fail because their RunManifest values aren't actually byte-stable | low | medium | Walkthroughs use stable fixture values (`whatif_version="0.0.1"`, `started_at="2026-05-06T..."`); should not surface. |
| Consumer tooling depends on `runtime` being whole-subtree non-deterministic | very low | low | `x-deterministic` is a hint annotation; consumers that ignore it (most) are unaffected. |

## What this doc does NOT decide

- **Promoting `environment.*` fields.** Out of scope; would need a separate audit.
- **Cluster-paired bootstrap (cardinal #10 v0.3 surface).** Different cardinal, different phase.
- **Marketplace publication of the action.** Phase I.x.

## Recommended next step

If this scope and these design choices look right, I implement against the acceptance criteria above. If you want to adjust scope (e.g., narrow the promoted-field set, defer the cross-platform matrix to v0.3), edit this doc and I work to the revised version.
