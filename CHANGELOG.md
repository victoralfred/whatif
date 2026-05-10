# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Pre-1.0, the minor version may introduce breaking changes - every breaking
change is called out under `### Changed (BREAKING)`.

---

## [Unreleased]

### Added — Phase C completion: WhatifConfig.experiment_shape (#84)

- **`WhatifConfig.experiment_shape`** (`Literal["failure_rescue", "regression_check"]`, default `"failure_rescue"`). Closes the Phase C loop: the verdict-layer branch on `experiment_shape` shipped in PR #82, but `whatifd fork` CLI users could only get `failure_rescue` because the config schema didn't expose the field. Operators can now set `experiment_shape: regression_check` in `whatifd.config.yaml` and the CLI threads it into `RunManifest`.
- Unknown values (e.g., `experiment_shape: exploratory_ab`) fail at config-load with a Pydantic ValidationError naming the field — fail-early discipline matching the rest of v0.2's config validators.

### Added — Phase D (Arize Phoenix / OpenInference TraceSource adapter)

- **New package: `whatifd-phoenix`** (v0.2.0). Implements `whatifd.adapters.TraceSource` against an OpenInference span-iterator surface. Tracer-neutrality proof: the `TraceSource` Protocol is genuinely shape-agnostic, not Langfuse-shaped by accident.
- **Span-iterator construction** rather than Phoenix-Client-pinned. Callers pass a `spans_provider: Callable[[], Iterable[dict]]` that yields OpenInference-shaped span dicts. Wires from `arize-phoenix-client`, custom OTLP collectors, or any other OpenInference-emitting tracer with a ~5-line adapter callable.
- **OpenInference attribute conventions:** the adapter reads `context.trace_id`, `parent_id`, `openinference.span.kind`, `input.value`, `output.value`. `input.value` and `output.value` are wrapped as `Sensitive[str]`; other attributes pass through to `RawTrace.metadata` unwrapped (cardinal #5).
- **Conformance harness coverage:** 14 tests (5 inherited from `TraceSourceConformance` + 9 adapter-specific) pin Protocol shape, span grouping, root-span identification, classifier-receives-full-span-list semantics, and `cluster_key_support` honest-empty.
- **Workspace-aware:** `packages/whatifd-phoenix` registered as a workspace member; `uv sync` installs editably alongside `whatifd-langfuse` and `whatifd-inspect-ai`.
- **Recorded-cassette smoke test** (live Phoenix HTTP) is deferred to v0.3 — Phoenix HTTP-cassette infrastructure parity with `whatifd-langfuse` is its own surface.

### Added — Phase C (regression_check experiment shape)

- **Shape-aware verdict computation.** `compute_verdict` gains `experiment_shape: ExperimentShape = "failure_rescue"`. Default is the v0.1 behavior; `experiment_shape="regression_check"` switches to the lean guard chain (`primary_endpoint` + `ci_availability` only) and overrides `required_cohorts` to `("baseline",)` so a baseline-only run doesn't produce a spurious "missing failure cohort" floor failure.
- **Pipeline wiring.** `run_pipeline` reads `runtime.experiment_shape` (Phase A's manifest field) and passes it to `compute_verdict`. Operators select the shape via the manifest they construct; YAML callers will inherit this via the config layer when the regression-check config shape lands.
- **Shape→guard registry** (`_REGRESSION_CHECK_GUARDS`) skips the failure-cohort guards (`practical_delta`, `improvement_observation`). The `primary_endpoint_guard` is configurable via `policy.primary_endpoints` and naturally handles the regression-check policy when only the baseline endpoint is declared.

### Added — Phase B (config-loaded score_fn; inspect_ai reachable from YAML)

- **`scorer.score_fn` config field** — `python:<module.path>:<attr>` reference to an Inspect AI score function. Closes the v0.1 setup-failure cliff where `scorer.adapter: inspect_ai` was reachable only via the programmatic `run_pipeline` API.
- **`scorer.judge_provider` / `judge_model_id` / `judge_model_snapshot` / `rubric_id` / `rubric_text` / `scoring_parameters`** — the remaining `InspectAIScorer` constructor fields, all expressible from YAML.
- **`ScorerConfig.model_validator`** enforces all five required fields when `adapter='inspect_ai'`. Validation fires at config-load time, before factory dispatch — a v0.1-shaped config (`adapter: inspect_ai` alone) now fails Pydantic validation with a named-field error.
- **`whatifd.scorer_loader`** — new module mirroring `runner_loader`: resolves `python:<module>:<attr>` to a callable, with typed `ScorerLoadError` for every failure path.
- **`build_scorer` constructs `InspectAIScorer` from config** — adapter='inspect_ai' branch wires `score_fn` + judge fields straight through to the `InspectAIScorer` constructor. The lazy-import contract is preserved.

### Added — Phase A (v0.2 schema groundwork)

- **`ExperimentShape` literal + top-level `experiment_shape` field on `ReportV01`** — `Literal["failure_rescue", "regression_check"]`. v0.1 was failure-rescue only; the field is now structural so the v0.2 verdict-policy branch (Phase C) has somewhere to dispatch. Default on `RunManifest` is `"failure_rescue"` for caller ergonomics; required (no default) on the wire shape.
- **Schema bumped to v0.2** — `REPORT_SCHEMA_VERSION = "0.2"`, `REPORT_SCHEMA_URI = "https://whatif.codes/schema/report/v0.2.json"`. v0.1 schema file is FROZEN at `src/whatifd/report/schema/v0.1.schema.json` (sha256 pinned in `tests/unit/whatifd/report/test_schema_v0_1_frozen.py`); v0.2 ships at `src/whatifd/report/schema/v0.2.schema.json`. Schema-gen script now derives filename from `REPORT_SCHEMA_VERSION`.
- **`whatifd report-migrate` real v0.1 → v0.2 logic** — replaces the v0.1 no-op stub. Loads JSON, walks the migration chain via `whatifd.report.migrate.migrate_report`, writes `<name>.v0.2.json` (or overwrites with `--in-place`). Idempotent: a v0.2 input is a reported no-op exit 0. Cardinal #1: malformed input produces a typed `MigrationError` → stderr message → exit 2.
- **`whatifd.report.migrate` module** — extension point for future v0.X → v0.Y migrations via the `_MIGRATIONS` chain dispatcher.

### Fixed

- **`__version__` drift between `pyproject.toml` and source literal** — `src/whatifd/__init__.py` previously hardcoded `__version__ = "0.0.1"` and was never bumped when `pyproject.toml` moved to `0.1.0`. The TestPyPI dry-run install verification surfaced the drift (`whatifd 0.0.1` reported by an installed `0.1.0rc1` distribution). All three packages (`whatifd`, `whatifd-langfuse`, `whatifd-inspect-ai`) now read `__version__` from `importlib.metadata.version(<dist>)` at import time, so the distribution metadata is the single source of truth. Source-only checkouts fall back to `0.0.0+unknown`. A new `tests/unit/whatifd/test_version_parity.py` pins the parity to prevent regression.

### Documentation

- **`README.md` and `docs/getting-started.md` install snippet** — the first package in the install command was missing the trailing `d`. The PyPI distribution and CLI command are both `whatifd`; the missing-`d` form would have silently installed a different PyPI project. Caught by user review pre-publish; would have shipped a broken install command otherwise.
- **CI sentinel against this typo class** — `.github/workflows/ci.yml` gains a `pip-install missing-d sentinel` step that fails the build on any `.md` file where the install snippet drops the trailing `d` from the distribution name. Three rename rounds missed this regex shape; the sentinel makes regression structurally impossible.

## [0.1.0] - 2026-05-09

### Added — Phase 10.6 (release prep)

- Root `pyproject.toml` version bumped from `0.0.1` to `0.1.0` to align with the adapter packages.
- `Development Status` classifier bumped from `2 - Pre-Alpha` to `3 - Alpha` across all three packages.
- **`RELEASING.md`** — runbook for cutting releases. One-time PyPI Trusted Publisher setup (per-package, per-environment claim), per-release checklist, failure-mode recovery, hot-fix flow, v0.2+ schema-migration notes.
- **`.github/workflows/release.yml` extended** — now builds and publishes all three distributions (`whatifd`, `whatifd-langfuse`, `whatifd-inspect-ai`) on a single `v*.*.*` tag push. Each PyPI publish runs in its own GitHub environment (`pypi-whatifd`, `pypi-whatifd-langfuse`, `pypi-whatifd-inspect-ai`) so PyPI's OIDC verifier can scope the Trusted Publisher per project. Adapters publish only after the root `whatifd` succeeds, so a partial-failure state where adapters reference an unpublished `whatifd` is impossible.
- **GitHub repo URL references re-applied** — the URL renames from PR #73's third commit didn't make it through the squash merge to `main`; this branch re-applies them across `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `pyproject.toml`, both adapter `pyproject.toml`/`README.md`, `docs/getting-started.md`, `.github/ISSUE_TEMPLATE/config.yml`, and `CHANGELOG.md`.

### Added — Phase 10.5 (release polish)

- **`docs/schema/v0.1.md`** — `ReportV01` consumer compatibility guide. Documents the v0.1.x stability contract, top-level shape, `verdict_state` ↔ exit-code mapping, determinism subset (cardinal #4), methodology disclosure (cardinal #10), failure + finding code registries, and a programmatic-read example.
- **`README.md` final pass** — reframed lead with the v0.1 doctrine sentence (*"whatifd's product is the verdict's defensibility"*). Removed aspirational CLI flags that aren't in scope; replaced with two real Quickstart paths (programmatic + CLI-with-stub-adapters). Linked the new `docs/schema/v0.1.md`. Updated the version-roadmap table to reflect the actual v0.1 release-candidate state.
- **`phases.md` gap inventory updated** — flipped resolved gaps (`_run_fork_pipeline` body, `delta_fn` shortcut, cardinal-#5 graph walk, examples + getting-started, `config_hash` placeholder) into a "Resolved" section. Remaining-blocker list trimmed to the four truly-external items (README final pass [done], schema docs [done], schema URL hosting [user-driven], PyPI publish [user-driven]).
- **`src/whatifd/cli.py` stale labels stripped** — module header no longer calls `whatifd report-migrate` / `cache rebuild|unlock|verify` / `diff` "stubs"; they're full implementations.

### Added — Phase 10.4 (`whatifd fork` CLI dispatcher body wired end-to-end)

- **`src/whatifd/cli.py::_run_fork_pipeline`** body filled in. The dispatcher now actually runs: (1) `build_trace_source(cfg.source)` from Phase 10.1, (2) `build_scorer(cfg.scorer)` from Phase 10.1, (3) `load_runner(cfg.target.runner)` from Phase 10.2, (4) `build_delta_fn(...)` from Phase 10.3, (5) construct `RunManifest` + `MethodologyDisclosure` + `CacheSummary`, (6) `run_pipeline(...)` → `ReportV01`, (7) `assert_no_unredacted_sensitive(report)` graph-walk BEFORE serialization (closes the cardinal-#5 graph-walk gap from `phases.md`), (8) `encode_report_v01` → JSON + `render_full_report` → Markdown to `./reports/whatifd-fork-<date>.{md,json}`, (9) exit code from `verdict_state` (`ship` → 0, `dont_ship` → 1, `inconclusive` → 2; floor-failure Inconclusive always wins per cardinal #2).
- **Cardinal-#1 boundary**. Every adapter / loader / pipeline exception is caught and converted to setup-failure stderr + exit 2. No stack traces leak. Three failure surfaces pinned: `AdapterFactoryError`, `RunnerLoadError`, generic pipeline `Exception` — each produces a typed message.
- **Cardinal-#5 graph-walk wired** at `cli.py` artifact-write site per cascade-catalog entry "Artifact-write call-site sequencing for graph walk". Encoder's `default()` reject-unwrapped-Sensitive is the last-line fallback; the graph walk is the primary defense and runs first.
- **End-to-end CLI smoke** in `tests/integration/test_cli_fork_e2e.py` — three scenarios: (a) successful dispatcher run with stub source/scorer + fixture runner producing artifacts at `./reports/`, (b) unknown-adapter setup failure with no artifacts written, (c) malformed runner-target reference setup failure.
- **`tests/unit/whatifd/test_cli.py`** updated: the two existing "reaches Phase 4 stub" tests now assert "reaches dispatcher setup failure" — the witness-token threading is still proven (the dispatcher body runs only after the cardinal-#7 witness check), the message just changed because the dispatcher actually works now instead of being a documented stub.
- **Closes the v0.1 release blocker** flagged in `phases.md`'s "Implementation gaps" section. `whatifd fork` runs end-to-end against stub adapters with no credentials needed; against real Langfuse + Inspect AI when env credentials and a programmatic score_fn are wired (the latter remains a Phase 11 cascade entry — `inspect_ai` config-loaded score_fn).

### Added — Phase 10.3 (CLI fork wiring; per-trace `delta_fn` closure)

- **`src/whatifd/cli_pipeline.py`** — `build_delta_fn(loaded_runner, scorer, change, replay_timeout_seconds)` returns a `Callable[[RawTrace], float]` suitable for `whatifd.pipeline.run_pipeline`. The closure runs the user's runner through the appropriate replay kernel (sync `replay_one_trace` for `loaded_runner.kind == "sync"`, async `replay_one_trace_async` wrapped in `asyncio.run` for `kind == "async"`), projects the resulting `ReplayOutput` into a `ScoreCase`, calls `Scorer.score`, and returns `JudgeResult.score`.
- **Cardinal #5 unwrap with explicit reason.** The closure unwraps `RawTrace.user_message` and `RawTrace.original_response` (both `Sensitive[str]`) at the runner-feed and ScoreCase-build sites with audit-log reasons naming the call site.
- **Cardinal #1 failure mapping.** A `ReplayFailure` from the kernel raises `_ReplayStageError`; a `JudgeResult.score == None` raises `_ScorerStructuralError`. Both surface to the pipeline's `except Exception` capture, which constructs a `scorer_unavailable` `FailureRecord` with the underlying error message preserved. v0.1's `delta_fn`-shape pipeline collapses replay+score into one closure surface; Phase 11+ may widen `run_pipeline` to consume `ReplayResult` directly so replay failures get their own typed `FailureRecord` projection.
- **Sync/async runner cast at the boundary.** `LoadedRunner.callable_` is typed `Callable[..., object]`; the closure narrows via `cast(Runner, ...)` / `cast(AsyncRunner, ...)` after Phase 10.2's loader has already validated the shape via `inspect.iscoroutinefunction` + Protocol `isinstance` belt-and-suspenders.
- **Documented limitation: `asyncio.run`-per-trace.** One event loop per async-runner trace. Acceptable for v0.1 — the pipeline is I/O-bound and `run_pipeline`'s sequential iteration is already the concurrency bound. A future refinement could share a loop across the trace stream.
- **7 new tests.** Sync runner, async runner via `asyncio.run`, runner exception → replay failure → pipeline exception, scorer None → structural-error path, ChangeConfig.system_prompt threading, StubScorer 0.5 sanity, closure docstring carries `LoadedRunner.reference`.

### Added — Phase 10.2 (CLI fork wiring; runner-target loader)

- **`src/whatifd/runner_loader.py`** — `load_runner(reference)` parses `python:<module.path>:<attr>` and returns `LoadedRunner(callable_, kind, reference)` where `kind ∈ {"sync", "async"}` selects the replay kernel. Module-private to the CLI wiring layer; `RunnerLoadError` carries actionable messages for every failure class (bad scheme, malformed shape, module not importable, attribute missing, non-callable, protocol-shape mismatch).
- **Sync vs async classification uses `inspect.iscoroutinefunction`, not Protocol `isinstance` alone.** Real Python limitation surfaced during implementation: `runtime_checkable` Protocols verify attribute presence only — both sync and async functions satisfy `Runner` and `AsyncRunner` structurally. Misclassifying an `async def` runner as sync would let the sync kernel treat the returned coroutine as a `ReplayOutput` (it isn't), producing a confusing downstream type error. The loader's check inspects the actual coroutine-function nature; `isinstance(candidate, AsyncRunner)` and `isinstance(candidate, Runner)` then run as belt-and-suspenders so a future Protocol-shape extension catches the regression at load time. Pinned by `test_async_classified_before_sync`.
- **Error surface is structured (cardinal #1).** Every failure path raises `RunnerLoadError` — never leaks `ImportError`, `AttributeError`, `TypeError` to the operator. The CLI's `_run_fork_pipeline` (Phase 10.4) catches and converts to setup-failure exit code.
- **12 new tests** covering each parse/resolve/validation branch. 1071 tests pass total.

### Added — Phase 10.1 (CLI fork wiring foundation; adapter factory)

- **`src/whatifd/adapters/factory.py`** — `build_trace_source(cfg.source)` and `build_scorer(cfg.scorer)` dispatch the validated config's adapter name to a concrete instance. `AdapterFactoryError` carries actionable messages naming the missing env var or config field; the CLI dispatcher converts these to stderr + setup-failure exit code per cardinal #1.
- **Lazy-load contract pinned at the wiring boundary.** `import whatifd.adapters.factory` does not pull `whatifd_langfuse` or `whatifd_inspect_ai` into `sys.modules`; the real-adapter import is inside `_build_langfuse_source` and only fires when the caller asks for that adapter. `test_factory_does_not_import_real_adapter_packages` is the focused gate; the broader `test_core_modules_do_not_load_real_adapter_packages` is the cross-cutting one.
- **`stub` adapter is the credentialless escape hatch.** `cfg.source.adapter="stub"` and `cfg.scorer.adapter="stub"` work without any env setup — the right default for an end-to-end CLI wiring smoke. **Behavior pinned:** `build_trace_source(SourceConfig(adapter="stub"))` returns `StubTraceSource(specs=[])` (empty by design — the factory dispatches, it doesn't provision fixtures). `build_scorer(ScorerConfig(adapter="stub"))` returns `StubScorer()` whose default `score_fn` returns the constant **`0.5`** (not zero, not "no judgment"). A real run that accidentally uses `scorer.adapter="stub"` will appear to improve uniformly across every trace — operators MUST treat the stub scorer as wiring-validation only, not as a substitute for a real judge. The `langfuse` source reads `LANGFUSE_HOST` (or `LANGFUSE_BASE_URL`) + `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` from the environment; missing creds, a malformed host, or any SDK construction failure all surface as `AdapterFactoryError` (cardinal #1: structured data, not leaked stack traces).
- **`inspect_ai` scorer raises actionable.** v0.1 doesn't load `score_fn` from config (it's user code, not config data); the factory surfaces this with a message pointing at the programmatic `run_pipeline` path documented in `docs/getting-started.md`. Pinned by `test_build_scorer_inspect_ai_raises_actionable` because a future contributor could silently default `score_fn` to a zero-stub here, producing a misleading Ship verdict under an `inspect_ai` config.
- **Scope:** dispatch only. Runner-target loader, per-trace `delta_fn` closure, and `_run_fork_pipeline` body land in subsequent Phase 10 sub-branches per the gap inventory in `phases.md`.

### Added — Phase 9B (real-adapter smoke; product proof)

- **`tests/integration/test_real_adapters.py`** — three end-to-end scenarios (Ship, Don't Ship, Inconclusive) driving `run_pipeline` with both real adapter packages in the path: `whatifd_langfuse.LangfuseTraceSource` (real adapter projection; synthetic `_FakeAPI` matching the Langfuse SDK `Trace` shape, mirroring the conformance fake) and `whatifd_inspect_ai.InspectAIScorer` (real adapter; deterministic mock `score_fn` per the package's documented mocked-only mode).
- **Bridge: `_delta_fn_from(scorer)`** — projects `RawTrace` → `ScoreCase` → `InspectAIScorer.score()` → `JudgeResult.score`. A `score=None` (cardinal-#1 structural failure) raises into the pipeline's existing `scorer_unavailable` `FailureRecord` capture. The Inconclusive scenario exercises this path: 5 of 8 baseline traces emit a non-numeric `Score.value` (the same shape a real Inspect AI judge outage produces), forcing `score=None`, which the bridge raises and the pipeline records — leaving 3 scored baseline traces, below `floor.min_scored_per_required_cohort=5`, so cardinal #2 forces Inconclusive.
- **Adapter-metadata cross-cut** — `test_real_adapter_metadata_surfaces` pins both adapters reporting non-empty `package_version` and the correct `adapter_id` ("langfuse" / "inspect_ai"). Per-package conformance already pins this; the cross-cut catches a regression that swaps either for the `"unknown"` placeholder.
- **Lazy-load assertion at integration boundary** — parameterized over `whatifd_langfuse` and `whatifd_inspect_ai`. Subprocess imports `whatifd`, `whatifd.cli`, `whatifd.pipeline` and asserts neither real-adapter package landed in `sys.modules`. Duplicates the contract pinned in `tests/unit/whatifd/adapters/test_protocols.py`; this copy runs alongside the smoke scenarios so a Phase 9B regression that wires an adapter into the core import graph fails here too.
- **Why not the typer CLI:** Phase 8.2's `_run_fork_pipeline` is still a documented stub returning the setup-failure exit code with a clear "Phase 4 adapter integration not yet wired" message. CLI integration is Phase 10 release work; Phase 9B's gate item ("three smoke scenarios pass against real adapters") is satisfied at the contract surface (`run_pipeline`), which is the load-bearing boundary the CLI will eventually thread the same fixtures through.

### Added — Phase 4B.2 (`whatifd-inspect-ai` real adapter package; closes Phase 4B)

- **`packages/whatifd-inspect-ai/`** — second sibling distribution under the uv workspace, implementing `whatifd.adapters.Scorer` against the Inspect AI scorer abstraction. Per the Phase 4B.2 reviewer checklist landed with PR #65, all 5 gate items satisfied: separate package, workspace registration, TODO(4B.2) marker + false-green prose removed from `tests/unit/whatifd/adapters/test_protocols.py`, conformance harness reused via the same conftest sys.path pattern as `whatifd-langfuse`, recorded smoke deliberately skipped (Inspect AI is a local eval framework, not a hosted API — no cassette target).
- **Library version pinning per industry practice** (lower bound + minor-cap, since Inspect AI is pre-1.0): `inspect-ai>=0.3.216,<0.4`.
- **`InspectAIScorer`** — `score_fn: Callable[[ScoreCase], Score | None | Awaitable[Score | None]]` injected at construction; the caller wires their Inspect AI scorer (and any `TaskState`/`Target` construction) into this callable. Async return values are awaited via `asyncio.run`. `judge_provider` / `judge_model_id` / `judge_model_snapshot` / `rubric_id` / `rubric_text` / `scoring_parameters` flow through to `cache_key_components`. Cardinal-#1 surfaces: `score_fn` raising or returning `None` produces `JudgeResult(score=None)` with a structured `Sensitive[str]` rationale, NOT a propagated exception. A non-numeric `Score.value` (e.g., a categorical label) projects to `score=None` instead of crashing on `float()`.
- **Cardinal alignment:** `Sensitive[str]` wrapping at the projection boundary (cardinal #5 — the conformance harness pins it; package-specific `test_judge_rationale_is_sensitive` re-pins on the explicit-None and exception paths). Adapter-agnostic to the metric (cardinal #10 — methodology disclosure flows through cache-key components, not the scorer).
- **Mocked-only conformance** in `tests/test_conformance.py` — runs the parent harness's `ScorerConformance` and `StructuralFailureScorerConformance` against fake `score_fn` callables, plus 7 Inspect-AI-specific behaviors (async awaiting, exception → None projection, non-numeric coercion, deterministic cache keys, distinct-rubric distinct-hash, adapter-metadata sourcing, Sensitive-on-failure-paths).
- **Pytest `--import-mode=importlib`** added to root `pyproject.toml` `addopts`. Both packages have a `tests/test_conformance.py`; the default `prepend` mode raises `ImportPathMismatchError` on the basename collision. importlib mode is the modern pytest recommendation for monorepo / multi-package layouts.
- **Phase 4B complete.** Both real adapters ship; the conformance harness is green against both. Phase 9B (real-adapter smoke through the CLI) and Phase 10 (release) remain for v0.1.

### Added — Phase 4B.1 (`whatifd-langfuse` real adapter package)

- **`packages/whatifd-langfuse/`** — separate sibling package implementing `whatifd.adapters.TraceSource` against the Langfuse v4 SDK (`langfuse.api.LangfuseAPI`). Industry-standard monorepo layout: own `pyproject.toml`, own `src/whatifd_langfuse/` tree, own `README`, dependency on `whatifd` via `[tool.uv.sources] whatifd = { workspace = true }`.
- **Library version pinning per industry practice** (lower bound + major-cap): `langfuse>=4.5.1,<5.0`. The next Langfuse major requires a coordinated migration; the cap reserves it.
- **Cardinal alignment:** `Sensitive[str]` wrapping at the projection boundary (cardinal #5); generator-only `iter_traces` with paginated `api.trace.list(...)` (Phase 4 contract); deterministic `json.dumps(..., sort_keys=True)` for non-string `input`/`output` projection (cardinal #4); empty `cluster_key_support()` because Langfuse `user_id`/`session_id` aren't predeclared cluster signals (cardinal #10 — v0.2+ may add explicit opt-in).
- **Two test surfaces:**
  - **Mocked-client conformance** (`tests/test_conformance.py`) — runs the parent repo's `TraceSourceConformance` harness against an in-file fake `LangfuseAPI`. No network. CI runs it on every change. Plus 4 Langfuse-specific behaviors: deterministic dict-projection, multi-page pagination, `max_traces` cap, adapter-metadata sourcing.
  - **Recorded real-network smoke** (`tests/test_recorded_smoke.py`) — uses `pytest-recording` (vcrpy). Replays from a committed cassette in CI; records from real Langfuse credentials when run locally with `--record-mode=once`. Filters secrets (`Authorization`, `x-langfuse-public-key`, `x-langfuse-sdk-*`, `user-agent`) before the cassette hits disk. Skips with an actionable message when neither cassette nor credentials are present. Accepts both `LANGFUSE_HOST` and `LANGFUSE_BASE_URL` env names.
- **Workspace-aware lazy-load test** — extends `test_protocols.py::TestLazyLoad` with `test_core_modules_do_not_load_real_adapter_packages` asserting that `whatifd_langfuse` (and the future `whatifd_inspect_ai`) are NOT pulled by core modules. Phase 4B contract: real adapter packages ship as separate distributions; lazy-load is enforced at test time across the workspace.
- **Cassette recording deferred** — the YAML cassette under `tests/cassettes/` is a contributor-supplied artifact. Recording requires real credentials AND a deliberate review of the cassette content (request/response bodies may contain user content from the recorder's Langfuse project). The README documents the record command; the smoke test skips cleanly until the cassette is committed.

### Added — Phase 9A.4 (failure injection across `FAILURE_CODE_REGISTRY`); Phase 9A complete

- `tests/integration/test_failure_injection.py` — registry-coverage failure injection. For every code in `FAILURE_CODE_REGISTRY`: `make_failure_record` constructs cleanly with realistic required details; the resulting `FailureRecord` carries the spec's stage/scope/retryable defaults; the record round-trips through `project_to_report_v01` into `ReportV01.failures` with all fields intact. An exhaustiveness pin (`test_every_registered_code_is_covered`) fails if a future code is added to the registry without a corresponding entry in the test's coverage map.
- `src/whatifd/pipeline.py` — the existing `delta_fn`-exception path now routes through `make_failure_record("scorer_unavailable", ...)` instead of constructing a `FailureRecord` with the literal code `"delta_fn_raised"`. The registry is now the single source of truth: code, stage, and scope are validated; required details (`provider`, `reason`) are enforced at construction; `exc_type` remains as an extension key (cardinal #6 extra-keys allowance). Existing flaky-scorer integration test updated for the new code.
- **Scope and what 9A.4 does NOT do:** this is a **construction + projection** coverage test, not a behavioral simulation. Adapter-specific failure-mode coverage (the actual paths that produce `trace_schema_mismatch`, `runner_timeout`, `scorer_unavailable`, etc. in production) lives in adapter-package tests at Phase 4B and in `tests/unit/whatifd/cache/test_recovery.py` for cache-corruption paths. 9A.4 owns the **registry contract**: every documented code constructs cleanly and round-trips through the report shape.
- **Phase 9A complete.** All four sub-phases landed: 9A.1 pipeline + Ship; 9A.2 Don't Ship + Inconclusive; 9A.3 determinism byte-equality; 9A.4 failure-code coverage. Phase 4B (real adapters) and Phase 9B (real-adapter smoke) remain for v0.1 release.
- 1002 unit + integration tests; mypy --strict clean.

### Added — Phase 9A.3 (determinism byte-equality)

- `src/whatifd/serialization/determinism.py` — schema-driven deterministic-subset extractor. `extract_deterministic_subset(report_dict)` projects a serialized `ReportV01` down to the top-level fields tagged `x-deterministic: true` in `v0.1.schema.json`. Schema-driven (not hardcoded) so a future schema change automatically updates the extractor. v0.1 deterministic fields: schema_version, schema_uri, verdict_state, cohort_results, failures, decision_findings, cache_summary, trust_floor, decision_policy, methodology. Excluded: `runtime` (timestamps, env fingerprint, sensitive-unwrap audit log).
- `tests/integration/test_determinism.py` — Cardinal #4 byte-equality test. Re-runs each Phase 9A scenario (Clean Ship, Don't Ship × 2, Inconclusive insufficient sample) twice from fresh fixtures, extracts the deterministic subset, encodes both with the canonical kwargs (sort_keys + tight separators), and asserts byte-equality. Three additional pins: `runtime` excluded from subset; the extractor's deterministic-field set MUST match the schema's annotations (catches drift); a regression in any tagged field surfaces as a test failure rather than silently propagating.
- 987 unit + integration tests pass; mypy --strict clean.

### Added — Phase 9A.2 (Don't Ship + Inconclusive walkthrough scenarios)

- `tests/integration/test_pipeline_dont_ship.py` — walkthroughs 02 (baseline regression: 6/20 = 30% > policy threshold 10% → `baseline_regression_above_threshold` blocks_ship) and 03 (failure-rescue gap: 2/20 improved = 10% < policy threshold 50% → `failure_improvement_below_threshold` blocks_ship). Each pins verdict resolution to DontShip with floor passing — DontShip is a policy verdict above the floor, not a structural verdict.
- `tests/integration/test_pipeline_inconclusive.py` — walkthrough 04 (insufficient sample: baseline 8 selected with 5 carrying `skip_reason` → only 3 scored → below floor's `min_scored_per_required_cohort=5` → `Inconclusive`). Pins that skipped traces flow through and contribute to `selected` count without contributing to `scored`, preserving the walkthrough's "8 selected, 3 scored" shape end-to-end.
- `tests/integration/_fixtures.py` — three new scenario builders + small helpers (`_spec`, `_idx`, `_build_fixture`) consolidate the per-cohort `StubTraceSpec` construction. The Phase 9A.1 Ship scenario builder remains intact.
- **Walkthroughs 5 and 6 deliberately deferred** with cascade-catalog entry. Walkthrough 5 (cache corruption) is a recovery-path scenario whose signal flows through the `whatifd cache verify` CLI + `cache_summary.policy_violations`, not through the per-trace stream — Phase 9A.4 (CLI failure-injection harness) is the right home. Walkthrough 6 (rerun-after-fix / diff) is fully exercised at the diff seam by `tests/unit/whatifd/test_diff.py`; reproducing through `run_pipeline` would mostly re-test what's already covered.
- 18 integration tests pass total (6 Ship + 4×2 DontShip + 4 Inconclusive). 981 unit + integration tests; mypy --strict clean.

### Added — Phase 9A.1 (programmatic integration entry + Clean Ship scenario)

- `src/whatifd/pipeline.py::run_pipeline` — adapter-agnostic programmatic entry point that stitches `TraceSource → cohort aggregation → compute_verdict → project_to_report_v01` into a `ReportV01`. v0.1 Phase 9A callers pass the synthetic stub from `whatifd.adapters.stub`; Phase 9B will pass real Langfuse / Inspect AI through the same signature.
- **Two deliberate Phase 9A.1 shortcuts** documented at the call sites: per-trace deltas come from a caller-supplied `delta_fn: Callable[[RawTrace], float]` (real paired scoring through the stub's `Scorer` is Phase 9A.2+ work that needs a Runner in scope), and CI bounds use empirical 5th/95th percentiles of the deltas (proper stratified bootstrap is the broader stats-layer work). Both shortcuts are sufficient for cardinal-#2 floor + verdict resolution; the function signature is the stable contract.
- `tests/integration/__init__.py` + `tests/integration/_fixtures.py` + `tests/integration/test_pipeline_ship.py` — Phase 9A.1 integration suite. The Clean Ship scenario (walkthrough 1) reproduces end-to-end against the stub: 20 failure traces with 14 improved (delta=0.20) + 6 unchanged, 20 baseline traces with delta=0.01 (under epsilon=0.05). Four pinned properties: verdict resolves to Ship, cohort counts match the fixture's delta function, floor passes on both required cohorts, CI bounds populated as `DecimalString`. Fixtures co-located so Phase 9A.2's remaining five scenarios can extend the same module.
- 967 unit + integration tests pass. Phase 9A.2 (remaining walkthrough scenarios), 9A.3 (determinism byte-equality), and 9A.4 (failure injection) sit on this foundation.

### Added — Phase 4A.3 (synthetic stub adapter; Phase 4A complete)

- `src/whatifd/adapters/stub.py` — `StubTraceSource` and `StubScorer` implementing the Phase 4A.1 protocols. Fixture-driven: tests construct a stub with `StubTraceSpec` rows (plain strings — the stub wraps them in `Sensitive[str]` at construction per cardinal #5) and an optional `score_fn: Callable[[ScoreCase], float | None]`. `cluster_key_support` is parameterizable so integration tests exercise both the "source provides clusters" and "source does not" branches of the methodology disclosure (cardinal #10). `cache_key_components` produces deterministic 16-hex digests derived from input identifiers (satisfies the `CacheKeyComponents.__post_init__` invariants without ever touching raw judge prompts — cardinal #5).
- The stub is shipped under `whatifd.adapters` (not `tests/`) so tests outside this repo (skill-benchmarks, future contributor reproductions) can import it. The lazy-load contract from Phase 4A.1 already includes `whatifd.adapters.stub` in its scan — `import whatifd` does not pull the stub.
- `tests/adapters/test_stub_conformance.py` — the inverse of the 4A.2 self-test: subclasses every conformance base class with stub fixtures and pins three additional stub-specific behaviors (fixture ordering preserved, cache keys deterministic for identical cases, distinct keys for distinct cases). The Phase 9A integration suite will rely on these.
- Closes the cascade-catalog Phase 4A.2 conformance-harness checklist's "harness runs against the synthetic stub at 4A.3" item. **Phase 4A is complete.** Phase 4B (real Langfuse + Inspect AI adapters in separate packages) and Phase 9A (stub end-to-end) are now unblocked.

### Added — Phase 4A.2 (adapter conformance harness)

- `tests/adapters/conformance.py` — parameterized base classes (`TraceSourceConformance`, `ScorerConformance`, `StructuralFailureScorerConformance`) that any concrete adapter subclasses to inherit a battery of conformance tests. Single source of truth for "what makes an adapter valid"; runs against the synthetic stub at Phase 4A.3 and against `whatifd-langfuse` / `whatifd-inspect-ai` at Phase 4B. Base classes carry `__test__ = False` so pytest does not collect them with the unimplemented fixture; concrete subclasses set `__test__ = True`.
- Conformance properties pinned: `isinstance` protocol check, `adapter_metadata()` shape (non-empty id + version), `cluster_key_support()` shape (returns `ClusterKeySupport`), `iter_traces()` is a generator/iterator (Phase 4 forbids list returns — bounded-memory contract), every emitted `RawTrace` wraps `user_message` and `original_response` as `Sensitive[str]` (cardinal #5 re-asserted at the harness boundary so a regression bypassing Pydantic construction fails loudly), `Scorer.score()` returns `JudgeResult` with `Sensitive[str]` rationale and `score: float | None`, `cache_key_components()` returns a valid `CacheKeyComponents` (its `__post_init__` enforces hex-digest invariants — raw text fails construction). Optional `StructuralFailureScorerConformance` exercises the cardinal-#1 `score=None` path explicitly for adapters whose backend can be configured to emit structural failures.
- `tests/adapters/test_conformance_self_test.py` — proves the harness machinery is correct using **minimum-viable in-file fakes** (NOT the Phase 4A.3 stub). Three concrete subclasses (`TestHarnessTraceSource`, `TestHarnessScorer`, `TestHarnessFailingScorer`) plug the fakes in and run every inherited conformance test. A fourth class pins that the harness REJECTS bad adapters (a list-returning `iter_traces` triggers `AssertionError` from the harness method) so the assertions stay load-bearing instead of vacuous.
- The `make_score_case()` helper at module level is the canonical realistic input for `Scorer.score` / `cache_key_components`; adapter-specific subclasses can extend with additional cases without re-deriving the shape.
- Phase 4A.2 closes the cascade-catalog conformance-harness checklist for the harness side; the remaining checklist items (running the harness against the stub) close at Phase 4A.3.

### Added — Phase 4A.1 (adapter protocols + result types)

- `src/whatifd/adapters/__init__.py` + `protocols.py` — first slice of Phase 4A. Defines the adapter-side surface separate from the user-runner contract:
  - `TraceSource` Protocol (runtime_checkable): `iter_traces()` (generator-only — Phase 4 forbids returning a list), `adapter_metadata()`, `cluster_key_support()` (mandatory per cardinal #10 — drives `MethodologyDisclosure.bootstrap.cluster_key`).
  - `Scorer` Protocol (runtime_checkable): `score(case)`, `cache_key_components(case)` returning the existing `whatifd.cache.keying.v1.CacheKeyComponents` (hashes pre-computed at the boundary so the cache subsystem never sees raw judge prompts — cardinal #5), `adapter_metadata()`.
  - `RawTrace` (Pydantic, `extra="forbid"`): adapter-side trace shape with `user_message: Sensitive[str]` and `original_response: Sensitive[str]` typed fields. `cluster_key: str | None` per cardinal #10. `skip_reason: str | None` so structurally-unusable traces flow through as `FailureRecord` rather than silently dropping (cardinal #1).
  - `JudgeResult` (Pydantic, `extra="forbid"`): scorer output with `rationale: Sensitive[str]`. `score: float | None` — None signals structural scoring failure (cardinal #1; surfaces as `FailureRecord` rather than substituting a neutral value). `judge_model_snapshot: str | None` with explicit-None contract so the cache-key field shape is constant.
  - `AdapterMetadata` (frozen + slotted dataclass, cardinal #6): `adapter_id` / `package_version` / `sdk_version`. Surfaced into `RunManifest`.
- Tests in `tests/unit/whatifd/adapters/test_protocols.py` cover: protocol-shape isinstance assertions (good vs missing-method classes), `RawTrace`/`JudgeResult` strict construction + extra-field rejection + Sensitive-required (raw `str` rejected with `ValidationError`), `AdapterMetadata` frozen + slots, and the **lazy-load contract** — a subprocess-based test asserts `import whatifd` does NOT trigger any `whatifd.adapters.*` import.
- No implementation. The synthetic stub adapter is Phase 4A.3; the conformance harness that parameterizes over the protocol is Phase 4A.2.

### Changed — Phase plan: split Phase 4 into 4A/4B and Phase 9 into 9A/9B (doctrine)

- `.claude/skills/whatifd-design/references/phases.md` — phase dependencies are now explicitly **gate-based, not strictly calendar-based**. The previous "no phase can begin until predecessors' gates are green" wording made the actual implementation order (Phases 5/6/7/8 against the runner-contract stub before completing real adapters) read as a violation. The split formalizes what already happened and de-risks future contributors reading the plan.
- **Phase 4A** = adapter protocol + conformance harness + synthetic stub adapter. **This is the dependency for Phases 5–8 and Phase 9A.** Stubs prove the architecture.
- **Phase 4B** = real Langfuse + Inspect AI adapters in separate packages. **Dependency for Phase 9B and v0.1 release.** Real adapters prove the product.
- **Phase 9A** = stub end-to-end. All six walkthrough scenarios reproduce against the stub; every `FAILURE_CODE_REGISTRY` entry injects cleanly; determinism byte-equality holds. Architectural proof.
- **Phase 9B** = real-adapter smoke. Three scenarios (one Ship, one Don't Ship, one Inconclusive) through real adapters. Smaller by design — 9A handles the invariant coverage. Product proof.
- **Release rule:** v0.1.0 requires both 4B and 9B green. 9A alone is not the release bar.

### Added — Phase 8.4 (`whatifd diff` — compare two reports)

- `src/whatifd/diff.py` — `load_report` / `compute_diff` / `render_diff_markdown` plus typed `DiffReport`, `CohortDelta`, `FindingDelta` (frozen + slotted, cardinal #6). `load_report` raises `DiffError` on file-level errors (missing, unreadable, malformed JSON, non-mapping root); shape errors propagate (genuine programmer bugs, not boundary errors). The diff operates on the raw dict rather than reconstructing `ReportV01` so cross-version comparisons during migration don't fail spuriously — exactly the rerun-after-fix workflow scenario 6 surfaces.
- v0.1 scope: verdict-state transitions, cohort row deltas (selected / scored / improved / regressed / median_delta), `decision_findings` added/removed (keyed on `(code, severity)` so a severity transition surfaces as both rows), and failure-count deltas. Per-trace evidence diff deferred to v0.2 alongside the per-trace evidence schema. Cardinal #10: the renderer surfaces deltas as descriptive numbers — no inferential claims beyond the verdict-state transition itself.
- CLI wiring: `whatifd diff <prev.json> <new.json>` replaces the Phase 8.4 stub. Renders to stdout; exits 0 on a successful diff (descriptive, not a verdict), 2 on `DiffError` from either input.
- **Renderer behavior operators should know:** (a) **asymmetric cohorts** — a cohort name present in only one report (added or dropped between runs) renders with zeroed counters on the absent side (e.g., a new failure cohort appears as `0→10`, a dropped cohort as `10→0`). Deliberate; the row IS the diff signal. (b) **Failures line suppression** — when `failures_prev == failures_new` the line is omitted, matching the Schema-line behavior; the verdict line stays always-present because it's the load-bearing claim per cardinal #10.
- Tests in `tests/unit/whatifd/test_diff.py` cover the four `load_report` failure modes plus round-trip; verdict / failure-count / cohort / findings-added/removed paths through `compute_diff`; trailing-newline contract, "(No changes detected.)" sentinel, verdict-arrow rendering, cohort-table cell formatting (`prev→new (±delta)` for changed, bare value for unchanged), and findings-section rendering. Two new CLI smoke tests pin the missing-file → exit 2 and successful-diff → stdout-Markdown surfaces.

### Added — Phase 8.3 (cache recovery: rebuild / unlock / verify)

- `src/whatifd/cache/recovery.py` — three operator-facing recovery primitives separated from the runtime-path `whatifd.cache.storage`:
  - `rebuild(cache_root, *, force) -> RebuildResult` wipes `<cache_root>/entries/` (preserving `meta.json` and the lock file). `force=False` is a no-op safety belt against typos.
  - `unlock(cache_root, *, allow_alive) -> UnlockResult` removes `<cache_root>/.lock` after a `psutil`-backed PID-alive check. Default refuses to clobber a live lock; `allow_alive=True` overrides. Corrupted lock files are treated as stale (safe to remove).
  - `verify(cache_root) -> VerifyResult` walks every JSON under entries/ and reports total / valid / corrupted. v0.1 checks structural integrity (parse + required CacheEntry fields); cryptographic content-hash verification deferred to v0.2 when entries carry stored hashes.
- CLI subcommands (`whatifd cache rebuild|unlock|verify`) now wire to the recovery primitives. Each accepts `--cache-root` (default `.whatifd/cache`); `rebuild` requires `--force`; `unlock` accepts `--allow-alive` for the live-PID override. Exit codes: 0 on success / no-op-clean, 2 on `--force` missing, 2 on lock-holder-alive without `--allow-alive`, 2 on any verify-found corruption.
- Per the cascade-catalog entry "CLI cache subcommands for v0.1": unlock is recovery, NOT a structurally-dangerous capability requiring two-affirmation. `--allow-alive` is sufficient for the override.
- 17 tests: `tests/unit/whatifd/cache/test_recovery.py` covers each primitive's branches (force-required, missing-dir, deletes-and-preserves, idempotent-no-lock, stale-removed, corrupted-lock-treated-as-stale, live-lock-refused-without-allow-alive, live-lock-removed-with-allow-alive, vacuous-clean, all-valid, corrupted-flagged, missing-required-field-flagged) plus two CLI smoke tests. Replaces the now-stale Phase 8.3 stub tests in `test_cli.py` with real-behavior assertions.

### Added — Phase 8.2 (CLI shell: typer entry, exit codes, two-affirmation wiring)

- `src/whatifd/cli.py::app` — typer-based command surface. `whatifd fork [--config PATH] [--profile {default|review|minimal|forensic}]` is the main entrypoint; `cache rebuild|unlock|verify`, `diff`, and `report-migrate` ship as Phase 8.3 / 8.4 / 8.5 stubs (each exits 2 with a clear "not yet implemented" message naming the phase).
- **Exit code precedence:** 0 = Ship, 1 = Don't Ship, 2 = Inconclusive / setup failure / floor violation. Floor violations always produce exit 2 regardless of policy (cardinal #2). Setup failures (missing config, validation errors, missing forensic affirmation) also exit 2 because they prevent producing a verdict at all.
- **Cardinal #7 wiring:** `whatifd fork` calls `assert_two_affirmation(cfg, cli_profile=<--profile>)` IMMEDIATELY after `load_config` returns and BEFORE any forensic-path code runs. The returned `TwoAffirmationProof` is held locally as the downstream-pipeline contract surface (Phase 4 adapter / Phase 9 integration consumes it). `TODO(cardinal #7)` comment at the call site so a future refactor sees the marker. Cascade-catalog entry "CLI must enforce two-affirmation before forensic-path code" tracks the cross-phase commitment.
- **Config-load failure surface:** `ConfigFileError` (file not found / parse error) prints `whatifd: config error: <message>`; `ValidationError` prints `format_validation_errors(exc)` output with `Hint:` lines for registered codes; `ForensicAffirmationError` prints `whatifd: <message>`. All three exit 2.
- **Phase 4 stub:** the downstream pipeline (replay → score → decision → render) requires Phase 4 adapter integration. v0.1 8.2 ships the CLI SHELL — argument parsing, config load, two-affirmation, exit-code dispatch. The fork pipeline currently exits 2 with a clear setup-failure message naming the missing wiring; this is intentional, NOT a runtime crash. Phase 4 / Phase 9 wires the real path.
- 14 tests pin: help command loads + exits 0; fork with missing/invalid/unknown-section configs all exit 2 with the appropriate diagnostic surface; two-affirmation cross-surface (CLI-only-forensic / config-only-forensic / both-forensic) all behave correctly; default-profile flow reaches the Phase 4 stub; all five subcommand stubs exit appropriately for their semantics.
- **`report-migrate` exits 0 (EXIT_SUCCESS) deliberately**, not 2. v0.1 has no schema bumps to migrate from; the no-op IS a success, not a setup failure. Conflating "intentional no-op" with "setup failure" in the exit-code contract would mislead operators wiring this into automated pipelines. The other four stubs (`fork` Phase-4 stub, `cache rebuild|unlock|verify`, `diff`) exit 2 because their absence IS a setup blocker until the corresponding phase lands.

### Added — Phase 8.1 (config schema + hint generation + two-affirmation)

- `src/whatifd/config.py::WhatifConfig` — Pydantic v2 strict (`extra="forbid"`) at every nesting level. Sections: `source`, `target`, `selection` (per-cohort `failure_cohort` / `baseline_cohort` limits), `change`, `scorer`, `decision`, `reporting`, `timeouts`. A typo at any level raises `ValidationError` rather than silently absorbing.
- **Cardinal #7 two-affirmation:** `ReportingConfig.profile == "forensic"` requires a populated `reporting.forensic_acknowledgment` block (config-side validator) AND `--profile forensic` on the CLI (cross-surface check via `assert_two_affirmation(cfg, *, cli_profile)`). Single-surface attempts raise `ForensicAffirmationError` with a message naming exactly which surface is missing. The acknowledgment block has `extra="forbid"` so a typo (e.g., `accepted_b` missing y) fails immediately rather than producing half-populated forensic enablement.
- **Hint generation:** `format_validation_errors(ValidationError) -> str` translates Pydantic errors into a multi-line operator-facing message with field paths + per-error suggestions from a `_HINTS` table covering the top-N misconfigurations (negative limit, ratio out of [0, 1], zero timeout, missing acknowledgment block, etc.). Falls back to the bare Pydantic message for unregistered codes.
- 31 tests pin: minimal-config construction + defaults; strict-mode rejection at every nesting level (top-level, nested field, acknowledgment-block typo); range constraints (negative limit, ratio out of [0, 1], zero timeout); forensic config-side enforcement (profile-without-block fails; profile-with-block validates); two-affirmation cross-surface returning `TwoAffirmationProof` with `forensic_active=True` on both-surfaces, raising on each-alone, returning `forensic_active=False` on neither, plus a fabrication defense (constructing the proof without the closure-captured token raises); hint generator (registered code emits Hint line, model_validator path gets a Hint, unregistered code emits raw Pydantic message, multi-error output lists each, empty-loc fallback renders as `(root)`); int→float coercion (verifies dropping `strict=True` was the right call); `load_config` end-to-end (YAML, JSON, missing file, YAML parse error, JSON parse error, unsupported extension, non-mapping root, validation propagates, permission-denied → ConfigFileError, forensic file→proof seam pinning the integration).
- **TwoAffirmationProof witness:** `assert_two_affirmation` returns a `TwoAffirmationProof` mirroring cardinal #2's `FloorPassedProof`. Construction outside this module is blocked by a closure-captured `_PROOF_TOKEN` sentinel; Phase 8.2 forensic-path code must accept the proof, structurally forcing callers through the affirmation function. `proof.forensic_active` is the single source of truth for "are we writing unredacted artifacts" — downstream code branches on this, not on raw config/CLI values.

### Added — Phase 7.1c (walkthrough structural-fidelity tests)

- `tests/unit/whatifd/render/_walkthrough_fixtures.py` — six `ReportV01` builders matching the "Underlying state" sections of `docs/walkthroughs/01..06-*.md`. `SCENARIOS` map keys by scenario number → (name, expected verdict_state, builder). Ship verdicts route through `evaluate_floor()` so the `FloorPassedProof` is real (cardinal #2 enforcement).
- `tests/unit/whatifd/render/test_walkthroughs.py` — 39 parameterized tests across the six scenarios:
  - **Verdict-state fidelity:** each scenario's `verdict_state` matches the walkthrough's documented verdict.
  - **All formats render:** `render_ci_status` / `render_summary` / `render_full_report` produce strings without raising; CI status ≤80 chars; summary + full report start with `# whatifd verdict:`.
  - **Three-format consistency:** the verdict label appears in all three formats; cohort `(N)` counts match between summary and full report (skip when no cohort_results).
  - **Per-scenario structural pins:** scenario 2 surfaces the baseline-regression message in summary + full; scenario 4 renders the floor-evaluation table with the expected rule + cohort + numbers; scenario 5 renders the `cache_lock_unavailable` registered fix-suggestion summary; scenario 1 (clean Ship) renders "No actionable findings" rather than a registry template.
- **Why structural fidelity instead of byte-equality (the original Phase 7 gate):** several walkthrough features are deferred from v0.1 — per-trace evidence schema (scenarios 2, 3), multi-cause fix-suggestion templating (scenario 3), floor table with PASSING rules surfaced (scenario 4). These have cascade entries; byte-equality lands when those features land. Phase 7.1c ships structural fidelity now and the fixtures are concrete enough to drive byte-equality without rebuilding.

### Added — Phase 7.1b (FIX_SUGGESTION_REGISTRY templates wired into full report)

- `_suggested_next_steps_section` in `whatifd/render/markdown.py` now consumes `whatifd.decision.fix_suggestions.FIX_SUGGESTION_REGISTRY`. Each blocking finding (severity `blocks_all` or `blocks_ship`) renders as `### <FixSuggestion.summary>` followed by a Markdown numbered list of `FixSuggestion.steps`. Findings sorted by severity rank (highest first); ties stable on input order so reports are deterministic.
- **Cardinal #8 closure path:** the section is now structurally non-empty for any non-Ship verdict with blocking findings. The cardinal-#8 coverage test in `tests/unit/whatifd/decision/` already pins that every floor rule + every blocking finding code has a registered fix-suggestion; the renderer defensively falls back to "(no registered template)" only on the unreachable production path (a forged finding code), so test forging proves the renderer doesn't crash on registry gaps mid-development.
- Removed the 7.1a placeholder paragraph ("Fix-suggestion templates land in Phase 7.1b"); pinned by `test_placeholder_text_removed_in_7_1b` so a future revert surfaces.
- Tests added: registered-template summary + steps render correctly; placeholder text gone; multiple blocking findings sorted by severity (`blocks_all` before `blocks_ship` via index comparison in the rendered output); unregistered-code fallback doesn't crash.

### Added — Phase 7.1a (full Markdown report skeleton)

- `src/whatifd/render/markdown.py::render_full_report(report: ReportV01) -> str` — the canonical Markdown artifact `whatifd fork` writes alongside the JSON report. Sections: verdict header, bold reason, Stats (per-cohort breakdown with median Δ + CI), Replay validity (with `<a id="replay-validity">` anchor), Floor evaluation table (rendered IFF a floor failure is present), Suggested next steps (`<a id="fix">` anchor), Methodology, Manifest pointer.
- **Anchors resolve the summary's forward-reference jump links:** `#fix` and `#replay-validity` live here so when Phase 8 CLI splices summary + full-report into one Markdown file, the summary's jump links become live in-document navigation.
- **Floor evaluation table** rendered only when at least one floor failure is present. Clean Ship omits the table for compactness; non-Ship verdicts surface the failed rule(s) per cohort.
- **Methodology block (cardinal #10):** every required disclosure field rendered, including the five reliability concepts (reproducibility / reliability / validity / calibration / bias) — surfaced explicitly even when False, never silently omitted (the disclosure-vs-silence test pins this).
- **CI bounds:** rendered as `CI [lower, upper]` when present; `(CI not computed: <reason>)` when `ci_unavailable_reason` is set; bare `(CI not computed)` fallback when neither.
- 22 tests pin: verdict header per state, anchors present for every verdict, methodology renders all five reliability concepts by name, floor table omitted on clean Ship and rendered on floor failure, suggested-next-steps surfaces blocking findings, stats/CI/replay-validity content.
- **Phase 7.1 split:** this delivery is **7.1a** (skeleton + sections + anchors + methodology). Outstanding: **7.1b** wires `FIX_SUGGESTION_REGISTRY` templates into the Suggested-next-steps section (placeholder text retained until then; pinned by `test_phase_7_1b_placeholder_message`); **7.1c** walkthrough-match tests for all six `docs/walkthroughs/*.md` scenarios (Phase 7 gate).

### Added — Phase 7.2 (compact summary renderer)

- `src/whatifd/render/summary.py::render_summary(report: ReportV01) -> str` — compact-form Markdown summary, ≤30 lines. Suitable for PR comments / Slack posts. Format: verdict header, bold reason line, per-cohort stats (failure / baseline first, then any others), replay-validity + cache one-liner, trailing jump-link bar.
- **Compact-Ship degenerate case:** clean Ship omits the `Suggested next steps ↓` jump link (no actionable findings), lands at ≤12 lines.
- **Forward-reference jump links:** `#fix`, `#replay-validity`, `manifest.json`. Targets the anchors Phase 7.1 will produce in the full report; consumers that splice summary + full-report (Phase 8 CLI) get working in-document navigation.
- **Reason source:** clean Ship → "All floor rules passed. All policy rules passed." Non-Ship → highest-severity finding's message (severity rank shared with `render_ci_status` via `_SEVERITY_RANK` import). Floor-failure fallback for non-Ship + no findings; defensive contract-violation string mirrors the CI-status fallback wording for cross-format consistency.
- **Budget enforcement:** `ValueError` raised if rendered output exceeds 30 lines — surfaces a renderer bug or shape regression rather than silently truncating (cardinal #1).
- `tests/unit/whatifd/render/test_summary.py` (15 tests) — verdict header per state, line budget per verdict, compact-Ship degenerate case (no `#fix` link, ≤12 lines, all-passed reason), non-Ship paths (highest-severity selection, fix-link present), stats block (failure/baseline ordering, generic per-cohort fallback for non-standard names), replay-validity line.
- Reuses `_COHORT_FAILURE` / `_COHORT_BASELINE` / `_SEVERITY_RANK` from `whatifd.render.ci_status` so the two formats stay aligned on which cohort is canonical and which finding "wins".

### Added — Phase 7.3 (CI status renderer)

- `src/whatifd/render/ci_status.py::render_ci_status(report: ReportV01) -> str` — one-line CI status string for a `ReportV01`, ≤80 visible chars. Format: `<glyph> whatifd: <Verdict> — <reason>` where the glyph is `✓` (Ship) / `✗` (Don't Ship) / `⚠` (Inconclusive).
- Reason source rules: Ship → cohort summary (`failures X/Y ↑, baseline Z/Y stable`); Don't Ship / Inconclusive → highest-severity decision finding's message (severity rank: `blocks_all` > `blocks_ship` > `degrades_trust` > `info`); fallback for non-Ship with no findings → top floor-failure rule (`<cohort> cohort below floor (<observed> < <threshold> <rule>)`). Defensive fallback string for non-Ship + no findings + no floor failures (contract violation upstream — surfaces the violation rather than raising).
- 80-char budget enforced by truncating the reason with `…`; verdict prefix always intact so the verdict is legible even on the most aggressive truncation.
- `tests/unit/whatifd/render/test_ci_status.py` (11 tests) — pins glyph + label per verdict, length budget for all three verdicts, ellipsis truncation on long messages, Ship cohort-summary structure, highest-severity finding selection, floor-failure fallback path, KeyError on unknown verdict_state (defensive boundary).
- Cardinal alignment: **#8 actionable Inconclusive** (reason surfaces a registered finding or floor rule); **#2 floor cannot be bypassed** (floor failure cited when present); **#10 disclosure necessary** (CI status is the COMPACT form; methodology disclosure lives in the full report).

### Added — Phase 6.3c (async runner kernel)

- `whatifd.contract.AsyncRunner` Protocol — `__call__(...) -> Awaitable[ReplayOutput]`. Runtime-checkable; sibling to the existing `Runner` (sync) protocol. Sync and async runners are NOT interchangeable; the user picks one and uses the matching kernel/stream entry point.
- `src/whatifd/replay/kernel_async.py::replay_one_trace_async(*, ...) -> ReplayResult` — async per-trace kernel. Same three failure classifications as the sync kernel (cache_miss / runner_timeout / runner_exception), different concurrency primitive: a coroutine awaited under `asyncio.wait_for(timeout=...)`. Re-exported from `whatifd.replay` as `replay_one_trace_async`.
- **No leaked-thread workaround:** unlike the sync path, async cancellation IS portable. `wait_for` schedules a `CancelledError` into the running task on expiry; the runner's `try/finally` and async-context-manager cleanup runs at the next `await`. Pinned by `test_cancellation_runs_runner_cleanup` (asserts the runner's `finally` ran after timeout fires).
- **External-cancellation discipline:** when the caller cancels the kernel's own task from outside the timeout, `CancelledError` propagates as-is — NOT swept into `runner_exception`. Cardinal #1 covers expected failures; `CancelledError` inherits `BaseException` (Python 3.8+) for exactly this signal-propagation purpose. `test_external_cancellation_propagates` pins this.
- `tests/unit/whatifd/replay/test_kernel_async.py` — 7 async tests mirroring the sync kernel suite (success / cache miss via lookup / direct CacheMissError / timeout-with-cleanup / runner exception / external cancellation propagates).

### Added — Phase 6.3b (streaming pipeline `replay_stream`)

- `src/whatifd/replay/pipeline.py::replay_stream(bundles, *, max_workers=4, timeout_seconds=60.0) -> Iterator[ReplayResult]` — bounded-concurrency wrapper over `replay_one_trace`. Sliding-window submit pattern: prime `max_workers` initial bundles, yield each completion, submit one more. Bounded memory (O(max_workers)), lazy input consumption (large iterables don't materialize), streaming yield (results emitted as they complete; completion order, NOT input order — the report aggregator sorts by trace_id at assembly).
- `ReplayInputBundle(trace_id, cohort, trace_input, config, tool_cache, runner)` frozen + slotted dataclass. The adapter (Phase 4) builds a generator that yields these from the underlying trace stream.
- Double-executor pattern: streaming layer holds an outer `ThreadPoolExecutor(max_workers=N)`; kernel holds an inner per-call `ThreadPoolExecutor(max_workers=1)` for timeout enforcement. Peak threads = 2 * max_workers (one outer + one inner per concurrent kernel). The kernel returns synchronously even on timeout via `shutdown(wait=False)` — so the streaming layer's `shutdown(wait=True)` only waits for kernel returns, NOT for leaked runner threads. The cascade-catalog warning about outer-wait-True serializing timeouts is honored: timeouts don't serialize because kernel-return is fast.
- `tests/unit/whatifd/replay/test_pipeline.py` (10 tests) — pins basic correctness (count preservation, no trace_id swap, empty/single bundle), mixed success+failure streams, bounded concurrency probe (lock-protected counter asserts peak ≤ max_workers), `max_workers < 1` rejection, lazy input consumption (input generator records pulled count; first-yield must NOT have drained 100 inputs).

### Added — Phase 6.3a (per-trace replay kernel)

- `src/whatifd/replay/kernel.py::replay_one_trace(*, trace_id, cohort, trace_input, config, tool_cache, runner, timeout_seconds) -> ReplayResult` — synchronous per-trace runner-call wrapper. The boundary that converts the three classes of runner-execution failure into typed `ReplayFailure` records: `CacheMissError` → `tool_cache_miss`; wall-clock timeout → `runner_timeout`; any other exception → `runner_exception`. Clean returns produce `ReplaySuccess` carrying the runner's `ReplayOutput`.
- Catch-order: `CacheMissError` is caught BEFORE the bare `Exception` catch so a cache miss is classified correctly even though it IS a Python exception. Test `TestOrderCorrect` pins this so a future refactor that reorders the catches surfaces immediately.
- Timeout enforcement via `ThreadPoolExecutor(max_workers=1)` + `Future.result(timeout=...)`. On timeout, `executor.shutdown(wait=False)` detaches so the kernel returns immediately; the runner thread leaks until it returns naturally (Python can't kill threads). Module docstring documents the requirement that runners be timeout-aware via inner I/O timeouts; the wall-clock limit is a backstop, not the primary bound. Subprocess-pool hardening deferred to v0.2.
- `BaseException` (KeyboardInterrupt, SystemExit) is intentionally NOT caught — cardinal #1 covers EXPECTED failures, not programmer-bug exit signals. Pinned by `TestNeverRaises::test_kernel_swallows_all_runner_exceptions` which asserts `SystemExit` propagates.
- Long exception messages truncated at 2048 chars with `...(truncated)` suffix to bound report bloat from runaway-message bugs.
- `tests/unit/whatifd/replay/test_kernel.py` — pins all four classifications (success / cache-miss / timeout / exception), the catch-order defense, the no-raise boundary, message truncation, and the timeout's "must return immediately" property (asserts elapsed wall-clock < 1s on a 0.1s timeout against a 2s sleep).
- Phase 6.3 split into 6.3a (kernel, this PR), 6.3b (streaming pipeline + ThreadPoolExecutor parallelism, next), 6.3c (async runner path).

### Added — Phase 6.2 (strict per-trace tool cache)

- `src/whatifd/replay/tool_cache.py::StrictToolCache` — `whatifd.contract.ToolCache` subclass that overrides `lookup(...)` to raise `CacheMissError` on miss instead of returning `None`. Liskov-substitutable: user runners annotated `tool_cache: ToolCache` receive the strict variant transparently. Public `ToolCache` contract remains unchanged (Pydantic v2 `extra="forbid"` boundary preserved); strictness lives in the subclass.
- `CacheMissError` — typed exception module-private to `whatifd.replay`. Carries `trace_id`, `tool_name`, `tool_args` for diagnostic context. Renamed from `args` to avoid `BaseException.args` shadow. The pipeline (Phase 6.3) catches at the runner-call boundary and converts to `ReplayFailure(code="tool_cache_miss")`.
- `make_strict_tool_cache(entries, *, trace_id) -> StrictToolCache` — factory the adapter / pipeline calls per-trace. Captures `trace_id` via Pydantic v2 `PrivateAttr` so the raised `CacheMissError` names it diagnostically. Defensively dict-copies the entries map.
- `CacheMissError.details_for_failure() -> Mapping[str, JsonPrimitive]` — projection helper that returns the shape `ReplayFailure(details=...)` expects. Only `tool_name` is included; `tool_args` is NOT propagated (cardinal #5 boundary — args may carry sensitive user content like emails or credentials). The diagnostic message names the tool and arg COUNT but not VALUES, so logs stay safe.
- Top-level `import whatifd.cache` in the module primes the serialization↔cache import order so the replay tests run cleanly in isolation. The cascade entry "Serialization ↔ report ↔ cache import cycle" tracks the root-cause refactor; this prime is a load-order safety net until that lands.
- `tests/unit/whatifd/replay/test_tool_cache.py` — pins factory + Liskov substitutability, hit returns value, miss raises with full context, args-dict-copied defense, message-leak-safety (no PII in exception text), details-shape (only `tool_name`, no args), and registry alignment (the projected details map satisfies `FAILURE_CODE_REGISTRY["tool_cache_miss"].required_details`).

### Added — Phase 6.1 (replay-stage result types)

- `src/whatifd/replay/result.py` — `ReplaySuccess(trace_id, cohort, output: ReplayOutput)`, `ReplayFailure(trace_id, cohort, code, message, details)`, sealed union `ReplayResult = ReplaySuccess | ReplayFailure`. Frozen + slotted; `ReplayOutput` referenced via TYPE_CHECKING to keep `whatifd.replay` import-time-cheap.
- `ReplayFailure.__post_init__` validates `code` against `FAILURE_CODE_REGISTRY` with `stage="replay"` (cardinal #1: closed-set codes; typos at the call site fail loudly, not at report-assembly time when the trace context is gone). Required-details enforcement is deferred to projection via `make_failure_record` per the registry-knows-best discipline.
- `tests/unit/whatifd/replay/test_result.py` — pins construction, registry validation (all three replay codes accepted; unknown code rejected; non-replay-stage codes rejected with clear stage-mismatch message), frozen behavior, default empty-details, and the sealed-union shape (a future variant addition surfaces for explicit review).
- Module docstring documents the in-pipeline shape vs `FailureRecord` distinction: `ReplayFailure` is light routing state for the pipeline; projection to the report-level `FailureRecord` happens at aggregation (Phase 2.7 / Phase 9) where stable ids are assigned and required-details validation runs through the registry.

### Added — Phase 5.5 (JSON Schema generation + byte-stable `v0.1.schema.json`)

- `scripts/generate_schema.py` — derives JSON Schema from `ReportV01` by walking `dataclasses.fields` + `typing.get_type_hints` recursively. Type-to-schema mapping handles `str`/`int`/`float`/`bool`/`None`, `Literal[...]` → `enum`, `Union`/`A | B` → `oneOf`, `list[T]`/`tuple[T, ...]` → array, `Mapping[str, T]`/`dict[str, T]` → object with `additionalProperties`, frozen dataclasses → `$ref` into `$defs`. NewType (`DecimalString`) unwraps to its supertype. Variadic-tuples-only enforced (fixed-length raises). Non-str mapping keys raise (cardinal #6 boundary). CLI: default writes the canonical file; `--stdout` prints (used by drift test).
- `src/whatifd/report/schema/v0.1.schema.json` — committed wire-shape schema (~23KB). 18 nested `$defs`, all top-level `ReportV01` fields required, every dataclass closed via `additionalProperties: false`. Top-level `runtime` annotated `x-deterministic: false`; every other top-level property `x-deterministic: true` per cardinal #4. `$id` matches `REPORT_SCHEMA_URI`; `schema_version` matches `REPORT_SCHEMA_VERSION`.
- `tests/unit/whatifd/report/test_schema.py` — drift test re-runs the generator and asserts byte equality with the committed file (a `models_v01.py` edit without `python scripts/generate_schema.py` fails CI). Plus structural pins: every `ReportV01` field appears in `required`, `additionalProperties: false` at root, every nested `$def` is a closed object, `runtime` is the only non-deterministic top-level property, encoded fixture has every required key + valid `verdict_state` enum value.
- Cardinal #6 alignment: the doctrine ("public schema hand-written") is satisfied by hand-writing `ReportV01` (the Python dataclass); the JSON Schema FILE is a derived artifact that mirrors it. Generation eliminates a class of drift bugs (schema says one thing, dataclass says another) and makes schema review = code review of `models_v01.py`.

### Added — Phase 5.4 (`assert_no_unredacted_sensitive` graph walk)

- `src/whatifd/serialization/graph_walk.py::assert_no_unredacted_sensitive(obj, *, path="<root>") -> None` — layer (b) of the cardinal #5 three-layer defense per `enforcement.md` row 2 (type-level → graph walk → encoder fallback). Recursive walk over frozen dataclasses (via `dataclasses.fields`), `Mapping` keys AND values (a `Sensitive` in a key is just as bad as in a value), `list`/`tuple` elements, `set`/`frozenset` elements; primitives short-circuit. Raises `UnredactedSensitiveError` on any reachable `Sensitive[T]` with a path breadcrumb (e.g. `<root>.runtime.sensitive_unwraps[3].location`) and the offending classification. `seen: set[int]` cycle guard keeps the walk total even on a future cycle (the wire shape is acyclic by design, but the walk is robust).
- Re-exported from `whatifd.serialization` package so the artifact-write path imports `assert_no_unredacted_sensitive` alongside `encode_report_v01`.
- `tests/unit/whatifd/serialization/test_graph_walk.py` — pins clean-graph silent pass on a real `ReportV01`, detection across every container shape (dataclass field, list, tuple, dict value, dict KEY, `MappingProxyType`, set, frozenset, deeply nested combinations), path breadcrumb in error messages, classification in error message, custom `path` override, and cycle protection (self-referential list and dict terminate; cycle-with-Sensitive still raises so the cycle guard never masks a leak).

### Added — Phase 5.3 (WhatifJSONEncoder + banned-import lint)

- `src/whatifd/serialization/encoder.py::WhatifJSONEncoder` — `json.JSONEncoder` subclass with `default()` dispatch on the project's typed shapes: `Sensitive[T]` raises `UnredactedSensitiveError` (cardinal #5 last line of defense — graph walk in 5.4 is primary; this is fail-loud fallback), frozen dataclasses dispatch via shallow `{name: getattr}` (avoids `dataclasses.asdict`'s deep-copy choking on `MappingProxyType`), `Mapping`/`MappingProxyType` cast to dict, `frozenset`/`set` to sorted lists (determinism), unknown types fall through to stdlib `TypeError` (cardinal #1).
- `encode_report_v01(report: ReportV01) -> bytes` — typed entry point stamping canonical kwargs (`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=True`). Same input → byte-identical output across platforms.
- `tests/unit/whatifd/serialization/test_banned_imports.py` — AST-walk lint for `enforcement.md` row 2. Walks every `.py` under `src/whatifd/`, parses each, finds every `json.dumps(...)` call (handles all import forms: `json.dumps`, `from json import dumps`, `from json import dumps as alias`), asserts zero violations outside `whatifd.serialization.*`. Sanity-checks the boundary itself uses `json.dumps` so the test isn't vacuously passing. Module-name resolution defended against `__init__.py` and prefix-trap edge cases.
- Refactored `whatifd/contract/__init__.py::ToolCache._key` from inline `json.dumps(args, sort_keys=True)` to use `canonical_json_bytes` — same hash-input pattern as Phase 3.1 keying. Removed the now-unused `import json` from contract module.

### Added — Phase 5.2 (projection: internal Verdict → ReportV01)

- `src/whatifd/report/projection.py::project_to_report_v01(verdict, *, failures, cache_summary, methodology, runtime) -> ReportV01`. Flattens internal types into the v0.1 wire format. Cardinal #2 enforcement at the type level: the function takes the sealed `Verdict` union (`Ship | DontShip | Inconclusive`) — the only path to obtain a `Ship` is through `compute_verdict`/`evaluate_floor` which produce and consume `FloorPassedProof`. A `verdict_state: str` parameter would re-open the bypass; the `Verdict` input is the structural chokepoint.
- `_flatten_verdict(verdict) -> tuple[VerdictState, list[CohortResult], list[DecisionFinding]]` — pure helper using `match` + `assert_never` for type-system-enforced exhaustiveness on the sealed union. Returns the verdict's `findings` list (NOT the derived `blocking_findings` subset; consumers compute that view from severity tags).
- `trust_floor` and `decision_policy` are read from `runtime` (the `RunManifest`) so the report's top-level fields can't drift from what the manifest records.
- `tests/unit/whatifd/report/_fixtures.py` — shared no-arg fixture builders (`trust_floor()`, `decision_policy()`, `cohort()`, `cache_summary()`, `methodology()`, `runtime()`) used by both `test_models_v01.py` and `test_projection.py`. Centralized to avoid drift across the two test files when sub-shapes add required fields.
- `tests/unit/whatifd/report/test_projection.py` — 17 tests across six classes: verdict-state mapping (Ship/DontShip/Inconclusive, real `_ship()` routed through `evaluate_floor`); `_flatten_verdict` direct coverage (state mapping + findings-not-blocking-subset contract); manifest single-source-of-truth (`trust_floor`/`decision_policy` propagate from `runtime`); pass-through (`cache_summary`/`methodology`/`runtime` are same instance; `failures` tuple input → list output); schema constants stamped; cardinal #2 chokepoint pin via `typing.get_type_hints` + `inspect.signature` (refactor that loosened to `verdict_state: str` would fail the test).
- Module constants `REPORT_SCHEMA_VERSION` / `REPORT_SCHEMA_URI` now typed as their respective Literal types (`_SchemaVersion` / `_SchemaUri`), eliminating the type mismatch when projection passes them to the Literal-typed fields on `ReportV01`.

### Added — Phase 5.1 (ReportV01 wire-format types)

- `src/whatifd/report/__init__.py` + `src/whatifd/report/models_v01.py` — hand-written `ReportV01` dataclass per cardinal #6 (public schema is hand-written; internal types refactor freely). Sub-shapes reuse internal types directly: `CohortResult`, `FailureRecord`, `DecisionFinding`, `CacheSummary`, `TrustFloor`, `DecisionPolicy`, `MethodologyDisclosure`, `RunManifest`. The cardinal #6 boundary governs the WHATIF-emitted schema, not the universe of types it composes.
- `REPORT_SCHEMA_VERSION = "0.1"` and `REPORT_SCHEMA_URI = "https://whatif.codes/schema/report/v0.1.json"` constants — stamped into every report instance.
- `VerdictState = Literal["ship", "dont_ship", "inconclusive"]` — wire-format flattening of the internal `Verdict` sealed union. JSON schema can express literal strings but not Python sealed unions; projection (later sub-phase) does the flattening.
- All 11 fields required (`schema_version`, `schema_uri`, `verdict_state`, `cohort_results`, `failures`, `decision_findings`, `cache_summary`, `trust_floor`, `decision_policy`, `methodology`, `runtime`); no `Optional[...]` hiding unset state behind `None`. `failures=[]`/`decision_findings=[]` is valid (clean run).
- `runtime` is the only non-deterministic field per `references/type-model.md`. Schema generation (later sub-phase) annotates it `x-deterministic: false`; everything else defaults to true.
- `tests/unit/whatifd/report/test_models_v01.py` — 17 tests across six classes: schema constants pinned, all three verdict states accepted, frozen-dataclass immutability, no-`dict[str, Any]` boundary check via `typing.get_type_hints`, determinism-budget field-set pin (whole-set assertion against future drift), sub-shape integration smoke (internal types accepted directly), public-import surface defense.

### Added — Phase 3.5 (CacheSummary — closes Phase 3)

- `src/whatifd/cache/summary.py::CacheSummary` — typed dataclass that becomes the `cache_summary` field on `ReportV01`. Required fields per `references/contracts.md` §"Cache disclosure content spec": `schema_version`, `key_version`, `mode`, `storage_profile`, `storage_path`, `hits`, `misses`, `writes`, `stale_hits`, `corrupted_entries`, `policy`, `policy_violations`. Optional: `oldest_hit_age_days: int | None`, `models_distribution: Mapping[str, int]` (defaults `MappingProxyType({})`).
- `CachePolicySnapshot` — captures the runtime cache-policy fields from `DecisionPolicy` (`mode`, `warn_after_days`, `block_after_days`, `storage_profile`) so the manifest carries policy-at-run-time without cross-referencing.
- `PolicyViolationRecord` — typed structured-record shape parallel to `FloorFailure` (`rule`, `observed: int | float | str`, `threshold: int | float`). Cardinal #6: structured records, not free-form strings; the deferred `cache_staleness_guard` emits these.
- `whatifd.cache.__init__` re-exports `CacheSummary`, `CachePolicySnapshot`, `PolicyViolationRecord`.
- `tests/unit/whatifd/cache/test_summary.py` — 16 tests across five classes: construction (minimal/optional defaults/full), frozen-dataclass immutability (summary, snapshot, violation), tuple-not-list / `Mapping`-not-dict pins, `PolicyViolationRecord` shape (int/float/string observed, value equality), `CachePolicySnapshot` field set + equality, cardinal #6 boundary pins via `typing.get_type_hints` (origin checks on `tuple` and `collections.abc.Mapping`).

Phase 3 complete (3.1 keying / 3.2 storage / 3.3 lock / 3.4 mode resolution / 3.5 summary). Schema validation enforcing `cache_summary` presence on `ReportV01` lands with Phase 5.

### Added — Phase 3.4 (cache mode resolution)

- `src/whatifd/cache/policy.py::resolve_cache_mode(config_mode, env) -> CachePolicyResolution`. Resolves `DecisionPolicy.scorer_cache_mode` into a concrete `ScorerCacheMode`, honoring CI environment signals per `references/contracts.md` §"CI environment detection". Concrete inputs (`on`/`off`/`read_only`/`refresh`) pass through unchanged. `auto` + CI signal (`CI`/`GITHUB_ACTIONS`/`GITLAB_CI`/`BUILDKITE`/`JENKINS_URL`, lowercased-truthy-aware: accepts `true`/`1`, rejects `false`/`0`) → `on` with a `cache_mode_inferred` finding. `auto` + no CI → `auto` unchanged.
- `CachePolicyResolution` typed dataclass (`mode`, `findings: tuple`) — frozen, slot, no `dict[str, Any]` boundary. Callers (Phase 2.6+ projection) splice `findings` into `decision_findings` and use `mode` for cache I/O.
- New `cache_mode_inferred` info-severity finding code in `FINDING_CODE_REGISTRY`. Required details: `input_mode`, `resolved_mode`, `env_signal`. Cardinal #1: mode inference is structured data, not a log line — the manifest discloses what the user got even when they didn't pick it.
- `whatifd.cache.__init__` re-exports `resolve_cache_mode` and `CachePolicyResolution`.
- `tests/unit/whatifd/cache/test_policy.py` — 24 tests across five classes: concrete-input pass-through (parametrized × 4 modes + ignore-CI), `auto` + CI signal (parametrized × 5 env vars + finding details + first-match ordering + `1` truthy variant), `auto` interactive (`{}` / `false` / `0` / empty / unrelated env), `_detected_ci_signal` direct coverage (case-insensitive truthy boundary), structure pins (frozen, tuple-not-list, dataclass type).

### Added — Phase 3.3 (cache lock)

- `src/whatifd/cache/lock.py` — `acquire_cache_lock(cache_root, *, stale_after_seconds=86400, allow_age_takeover=False)` context manager. Two layers of defense per `references/enforcement.md` row "Single-writer cache access": (1) OS-level `fcntl.flock(LOCK_EX | LOCK_NB)` on `<cache>/.lock` (kernel releases on process death — SIGKILL, OOM, kernel panic — including across SIGKILL), (2) stale-lock fallback that records `{pid, process_start_time, hostname, started_at}` and takes over when the recorded process is dead OR its `psutil.Process(pid).create_time()` mismatches `process_start_time` (PID-reuse defense).
- `CacheLockedError` typed exception — DATA condition (a held lock is legitimate runtime state, not a programmer bug); callers convert to `FailureRecord` per cardinal #1. Error message names PID, hostname, started_at from the held lock so operators can decide between `whatifd cache unlock` (CLI sub-command, Phase 8) and `whatifd cache rebuild --force`.
- `LockFileContent` and `CacheLock` typed dataclasses — typed boundaries per cardinal #6.
- Age-based takeover (`allow_age_takeover=True`) is opt-in only. Default behavior takes over only on dead-process or PID-reuse evidence; age alone is a weak signal because long-running batches can legitimately hold locks for days.
- NFS unsupported; documented in module docstring + clear error message naming NFS as the likely cause if `flock` returns `ENOLCK`/`EOPNOTSUPP`. Multi-tenant cache directories deferred to v0.3 (cascade entry).
- New runtime dependency: `psutil>=6.0` (and `types-psutil` for mypy strict). Used for `Process.create_time()` PID-reuse defense.
- `tests/unit/whatifd/cache/test_lock.py` — 13 tests across five classes:
  - `TestSingleWriter`: real-process contention via subprocess (NOT mocks; per Phase 3 gate); release on normal exit; release on exception (no orphan locks).
  - `TestStaleTakeover`: takeover when recorded PID is dead (the scenario-5 recovery loop); takeover when PID was recycled (live process but `create_time` mismatch); no takeover when PID alive and matches; takeover on corrupted/empty lock file.
  - `TestAgeTakeover`: default off (long-running batch not preempted); opt-in path reaches the age check (OS-level flock still primary defense, file-level age is advisory).
  - `TestLockProvenance`: lock content records this process correctly; `CacheLockedError` message includes PID/hostname/started_at.
  - `TestLockFileContentDataclass`: frozen-dataclass immutability.

### Added — Phase 3.2 (cache storage)

- `src/whatifd/cache/storage/v1.py` — file layout + entry I/O for the scorer cache. Layout: `.whatifd/cache/entries/<digest[0:2]>/<digest>.json` (sharded by first 2 hex chars; `v1:` prefix excluded from filename per Windows compat). Public surface: `init_cache(root) -> CacheMeta` (idempotent; refuses mismatched on-disk schema version), `write_entry(root, key, entry) -> Path` (refuses entries with mismatched `cache_schema_version`), `read_entry(root, key) -> CacheEntry | None` (None on miss; raises `CacheSchemaMismatchError` on disk-version mismatch), `read_meta(root) -> CacheMeta`.
- `CacheEntry` typed dataclass per `references/contracts.md` §"Entry format": `cache_key_version`, `cache_schema_version`, `created_at`, `key_components` (provenance — full asdict of `CacheKeyComponents`), `result: CacheResult`. `CacheResult` carries `score_delta`/`confidence` as `DecimalString` strings (cardinal #4 cross-platform stability), `verdict`, `flags`, optional `rationale`.
- `CacheSchemaMismatchError` — typed failure; callers convert to `FailureRecord` per cardinal #1. Used at three boundaries: init-time meta-version check, write-time entry-version check, read-time on-disk-version check, and key-prefix mismatch (`v2:` key against v1 storage).
- Profile gating on `rationale` is the CALLER'S responsibility — storage writes whatever entry it gets. The cardinal #5 boundary is preserved by upstream invariants (`CacheKeyComponents` hex-validation; `canonical_json_bytes` Sensitive guard).
- Entries written via `canonical_json_bytes` so two caches given the same input produce byte-identical files (cache verify can diff bytes).
- `tests/unit/whatifd/cache/storage/test_v1.py` — 14 tests across init idempotence, round-trip integrity (with and without rationale), cache miss → None, sharding pin (`<digest[0:2]>/<digest>.json`; no `:` in filename), schema mismatch on write/read/init, v2-key rejection, byte-identical on-disk encoding via monkeypatched timestamp, meta round-trip.

`CACHE_SCHEMA_VERSION = "v1"`. PRs touching `whatifd/cache/storage/` MUST bump version. The cache-version-bump CI test (Phase 3 gate) asserts this.

### Added — Phase 3.1 (cache key construction)

- `src/whatifd/cache/keying/v1.py` — `CacheKeyComponents` dataclass + `build_cache_key(components) -> str`. Deterministic SHA-256 over canonical JSON of the full required component set per `references/contracts.md`: whatifd schema version, scorer adapter version, scorer type/package, judge provider/model/snapshot, rendered-prompt hash, rubric hash, scoring-parameters hash, score-case serialization version, per-case content hash. Output format: `v1:<64-char hex digest>`. The version prefix is part of the key contract — storage layout uses it to split entries across versions.
- `src/whatifd/serialization/canonical.py` — `canonical_json_bytes(obj) -> bytes`. Canonical-JSON encoder for HASH inputs (sort_keys=True, separators=(",", ":"), ensure_ascii=True). Centralized in `whatifd/serialization/` so the Phase 5 banned-import lint sees zero `json.dumps` calls outside the serialization package without needing per-file allowlists. Module docstring documents the load-bearing distinction: this helper is for hash inputs only, not artifact bytes; the artifact-path encoder (Phase 5) carries cardinal #5 redaction enforcement separately.
- `src/whatifd/cache/__init__.py` + `src/whatifd/cache/keying/__init__.py` — package skeleton; `keying` re-exports `v1` so call sites import from the stable surface (`whatifd.cache.keying`) rather than the versioned module directly.
- `tests/unit/whatifd/cache/keying/test_v1.py` — 19 tests pinning format/version prefix/hex digest, determinism against a known-input known-output digest literal (verified across the full CI matrix 3.11/3.12/3.13/3.14), per-field sensitivity parametrized over all 12 fields, `None`-vs-empty-string distinctness on `judge_model_snapshot`, field-order independence.
- `tests/unit/whatifd/serialization/test_canonical.py` — 9 tests pinning the canonical encoding contract: ASCII bytes, sorted keys (including nested dicts), whitespace-free, non-ASCII escaped, list order preserved, `None`/empty-string and int/float distinctness, deterministic across repeated calls.

`CACHE_KEY_VERSION = "v1"`. Future PRs that change keying semantics MUST introduce `v2` rather than mutate `v1`. The cascade entry "Banned-import lint scope: cache keying canonical JSON" landed resolved.

### Internal / Docs — Phase 0 closure (0.2 + 0.4)

- `docs/concepts.md`: filled the missing sections (verdict states, floor-vs-policy, evidence/audit bundle); glossary now includes `ci_computable`, `ci_meaningful`, primary endpoint; §4 spells out the sticky-manifest guarantee operates at write AND read time.
- `enforcement.md`: two new explicit rows surfacing implemented-but-untracked structural claims — "`ci_computable=False` on a required cohort cannot Ship" and "Floor vs policy concerns are partitioned on `CohortResult`." Both were mechanism-backed in code already; the audit just made them explicit in the canonical table for the schema-freeze gate.
- Phase 0 gate now closed (0.1 walkthroughs ✅, 0.2 conceptual model ✅, 0.3 audience-distribution ✅, 0.4 enforcement audit ✅). Phase 3 (cache subsystem) is the next substantive phase.

### Changed (BREAKING) — Skill-alignment pass (post Phase 2.6b)

A skill-vs-implementation audit surfaced three doctrine drifts. All three resolved here. See `whatifd-private/V0_1_DECISION_RECORD.md` 2026-05-05 addendum.

- `CohortResult.ci_available: bool` renamed to `ci_computable: bool` and a new `ci_meaningful: bool = True` field added per V0_1_DECISION_RECORD §2's CI-status split. `ci_computable` is the structural fact (bootstrap successful?) read by `ci_availability_guard`; `ci_meaningful` is the policy-quality assessment (CI width below `policy.max_ci_width`?) read by a deferred guard. `__post_init__` enforces that `ci_meaningful=False` requires `ci_computable=True`. Cascade entry "ci_meaningful policy-guard wiring" tracks the deferred Phase 3 wiring.
- `DecisionPolicy.accept_no_ci: bool` removed per V0_1_DECISION_RECORD §6 ("`--accept-no-ci` removed in favor of CI-as-policy reclassification"). The field had been shipped as a placeholder with Phase 2.6c TODO — that was a doctrine breach. CI unavailability remains `blocks_all` (forces Inconclusive); the policy lever for accepting wider CIs is `policy.max_ci_width`. `test_accept_no_ci_can_be_enabled` deleted.
- V0_1_DECISION_RECORD §2's `Ship` type amended to include `findings: list[DecisionFinding]` (matching the implementation; observational/info findings are non-blocking by construction since `compute_verdict` would have downgraded the verdict otherwise).

Skill references updated: `type-model.md` (CohortResult split + accept_no_ci removed), `phases.md` (2.6 sub-phase decomposition), `cascade-catalog.md` (Phase 2.5 deferred-guards bullets re-scoped; new "ci_meaningful policy-guard wiring" entry).

### Added — Phase 2.6b (configurable primary_endpoint_guard)

- `src/whatifd/decision/guards/primary_endpoint.py` — `primary_endpoint_guard`. Reads `policy.primary_endpoints` and dispatches by `EndpointDirection`: `improvement_above_threshold` evaluates against `policy.min_failure_improvement_ratio`; `non_regression_below_threshold` evaluates against `policy.max_baseline_regression_ratio`. Emits the existing finding codes (`failure_improvement_below_threshold`, `baseline_regression_above_threshold`) — no new registry entries needed. Boundary semantics preserved from Phase 2.5b: strict `<` for improvement, strict `>` for regression. Findings emit in `policy.primary_endpoints` order, not cohort discovery order. Multi-metric (one primary metric per cohort today; v0.2 adds Holm correction) is `MethodologyDisclosure.multiplicity`'s concern, not this guard's.
- `tests/unit/whatifd/decision/guards/test_primary_endpoint.py` — 17 tests across default-policy improvement boundary cases, default-policy non-regression boundary cases, both-cohorts-active scenarios, ordering pin (findings in policy order, not cohort order), and the configurable-policy surface (single-endpoint, custom thresholds, unknown cohort silently skipped).

### Changed — Phase 2.6b consolidation

- `src/whatifd/decision/guards/__init__.py` — exports `primary_endpoint_guard`; removes the now-deleted `failure_improvement_guard` and `baseline_regression_guard` exports.
- `src/whatifd/decision/verdict.py::_DEFAULT_GUARDS` — replaces the Phase 2.5b hardcoded pair with `primary_endpoint_guard`. The default guard chain shrinks from 5 to 4 guards; behavior on the default policy is identical.
- `tests/unit/whatifd/decision/guards/test_layer_composition.py` — updated `_LAYER` to `(primary_endpoint, practical_delta)`; the test assertions still pin the same finding-code ordering for the catastrophe scenario (because `primary_endpoint_guard` emits in `policy.primary_endpoints` order, which defaults to failure-then-baseline).

### Removed — Phase 2.6b

- `src/whatifd/decision/guards/failure_improvement.py` — consolidated into `primary_endpoint_guard`.
- `src/whatifd/decision/guards/baseline_regression.py` — consolidated into `primary_endpoint_guard`.
- `tests/unit/whatifd/decision/guards/test_failure_improvement.py` and `test_baseline_regression.py` — coverage migrated into `test_primary_endpoint.py`.

### Added — Phase 7 cascade entry (PR #26 review F2)

- Cascade-catalog "Inconclusive renderer must distinguish floor_failures from blocking_findings" — files the rendering rule for the floor-failure-Inconclusive case so a renderer that prints `blocking_findings` without also surfacing `floor_failures` can't ship without addressing it. Cross-references cardinal #3 (disclosure necessary but not sufficient) and walkthrough scenario 4 as the empirical pin.

### Added — Phase 2.6a (verdict computation)

- `src/whatifd/decision/verdict.py` — `compute_verdict(cohort_results, floor, policy, *, guards=None) -> Verdict`. Single entry point composing the existing decision pipeline: `evaluate_floor` (cardinal #2 structural gate) + `run_guards` (cardinal #10 layer chain) + severity-sorted verdict construction. Branches: any `blocks_all` finding → `Inconclusive` (operational catastrophe), any `blocks_ship` finding → `DontShip`, else → `Ship` with the `FloorPassedProof`. The `Ship` branch is the only consumer of the witness token; structurally cannot construct without it. Floor failures produce `Inconclusive` regardless of guard findings (floor precedence is absolute). v0.1 default guard chain (as of Phase 2.6a) had 5 guards in cardinal-#10 layer order: failure_improvement, baseline_regression, practical_delta, improvement_observation, ci_availability. Phase 2.6b below consolidates the first two into `primary_endpoint`, shrinking the chain to 4.
- `tests/unit/whatifd/decision/test_verdict.py` — 13 tests covering Ship branch (clean run; cohort_results carried), DontShip branch (each blocking finding type — baseline regression, failure improvement below threshold, practical delta below epsilon), Inconclusive via floor failures (min_scored below floor; floor failure overrides clean findings), Inconclusive via blocks_all (CI unavailable; blocks_all overrides blocks_ship), cardinal-#2 trust-chain pins (Ship carries the FloorPassedProof from evaluate_floor; DontShip has no proof field), and the type-input contract (non-TrustFloor raises TypeError per cardinal #1).
- Phase 2.6a deliberately does NOT consult `policy.accept_no_ci` — the escape-hatch arithmetic is Phase 2.6c work. Tests pin the unconditional emission so Phase 2.6c can flip them cleanly.

### Added — Phase 2.5c (CI availability guard)

- `src/whatifd/decision/finding_codes.py` — new `ci_unavailable_for_required_cohort` finding code (severity `blocks_all`, derived_from_failures="always"). Pairs with `FAILURE_CODE_REGISTRY['ci_uncomputable_for_required_cohort']` (the operational fact); the finding is the policy conclusion that forces Inconclusive when CI is missing on a required cohort.
- `src/whatifd/decision/fix_suggestions.py` — new fix-suggestion entry guiding users through the `--accept-no-ci` escape hatch (the v0.1 single-flag opt-out for known-small-sample experiments) and the diagnostic path for `sample_too_small` / `zero_variance` / `computation_failed` reasons.
- `src/whatifd/decision/guards/ci_availability.py` — `ci_availability_guard`. For every cohort named in `policy.required_cohorts`, checks `cohort.ci_available`; emits one finding per affected cohort (ordered to match `policy.required_cohorts`). Missing cohorts (the floor's `required_cohort_present` rule) and non-required cohorts are skipped. `accept_no_ci` is NOT consulted here — emission is unconditional; Phase 2.6 verdict computation does the acceptance arithmetic so the manifest records both finding AND opt-out.
- `tests/unit/whatifd/decision/guards/test_ci_availability.py` — 11 tests covering boundary cases (CI on all required, CI missing on one, CI missing on all, CI missing on non-required, missing-cohort silence, empty cohort list), per-cohort emission ordering, custom `required_cohorts` (3-cohort policy), and the `unspecified` reason fallback when projection-layer bug leaves `ci_unavailable_reason=None`.
- `tests/unit/whatifd/decision/guards/test_blocking_finding_fix_suggestions_inline.py` — added the cardinal-#8 spot-check assertion for the new finding code.
- Cascade catalog "Phase 2.5 deferred guards" entry: bullet 2 marked resolved. Pending in bullet 4: real `derived_from_failures` wiring (placeholder used today) lands when Phase 2.6 plumbs failure records end-to-end.

### Added — Phase 2.5b (rate-count `CohortResult` extension + cardinal #10 primary endpoints)

- `src/whatifd/types/cohort.py` — `CohortResult` extended with three int fields: `improved_count`, `unchanged_count`, `regressed_count` (defaulting to 0 for backward compatibility). The triple partitions scored traces per cardinal #10's paired-delta unit of analysis: `improved` when the paired delta exceeds `policy.practical_delta_epsilon`, `regressed` when it falls below `-epsilon`, `unchanged` otherwise. The two new rate-based guards read these counts; existing construction sites (test fixtures, floor evaluator) keep working without changes.
- `src/whatifd/decision/guards/failure_improvement.py` — `failure_improvement_guard`. **The load-bearing primary endpoint for cardinal #10's failure-rescue scope.** Emits `failure_improvement_below_threshold` (blocks_ship) when `improved_count / total_scored < policy.min_failure_improvement_ratio`. Strict `<` so equality at the threshold meets the policy's "at least N%" promise.
- `src/whatifd/decision/guards/baseline_regression.py` — `baseline_regression_guard`. The symmetric non-regression endpoint on the baseline cohort. Emits `baseline_regression_above_threshold` (blocks_ship) when `regressed_count / total_scored > policy.max_baseline_regression_ratio`. Strict `>` so equality meets the policy's "at most N%" promise.
- `src/whatifd/decision/guards/practical_delta.py` — docstring framing-cleanup per the cascade entry that PR #23 deferred to this PR. The TODO marker is removed; the docstring now cross-references `failure_improvement_guard` as the primary endpoint and frames `practical_delta_guard` as the supplementary magnitude layer.
- `tests/unit/whatifd/decision/guards/_helpers.py` — extended `failure_cohort` with optional rate-count kwargs; added `baseline_cohort` builder.
- `tests/unit/whatifd/decision/guards/test_baseline_regression.py` — 11 tests covering boundary at exactly-threshold, custom thresholds (strict + lenient), missing cohort, zero-scored guard, and message format.
- `tests/unit/whatifd/decision/guards/test_failure_improvement.py` — 12 tests including a `TestPrimaryEndpointPairing` class that pins independence: each rate-based guard reads only its own cohort's counts.

### Added — Phase 2.5 (guard chain — protocol + first two guards)

- `src/whatifd/decision/guards/protocol.py` — `Guard` Protocol (callable taking `Sequence[CohortResult]` + `DecisionPolicy`, returning `list[DecisionFinding]`) plus `run_guards` chain composer that concatenates findings in registration order. Guards are pure functions; they never raise (cardinal #1: expected failures are data; unexpected failures propagate).
- `src/whatifd/decision/guards/practical_delta.py` — `practical_delta_guard`. Cardinal rule #10 enforcement: emits `practical_delta_below_threshold` (blocks_ship) when the failure cohort's median delta is at or below `policy.practical_delta_epsilon`. Equality counts as below-threshold (small statistical wins inside the noise floor are not shippable).
- `src/whatifd/decision/guards/improvement_observation.py` — `improvement_observation_guard`. Emits `improvement_observed` (info) when the failure cohort's median delta is strictly above the epsilon. Mutually exclusive with `practical_delta_guard` by design (`<=` vs `>`); together they partition the real line.
- `tests/unit/whatifd/decision/guards/` — 26 tests across protocol/chain composition (registration order, fresh-list semantics, empty chain, zero-finding guards), practical_delta boundary cases (exactly at epsilon, negative delta, custom epsilon, malformed delta string), improvement_observation boundary cases, and the mutual-exclusion invariant.
- Subsequent guards (`baseline_regression`, `failure_improvement`, `ci_availability`, `cache_staleness`, `primary_endpoint`) land in follow-up PRs as their dependencies arrive (CohortResult rate-count extension, `ci_unavailable_for_required_cohort` finding code, Phase 3 cache metadata, Phase 2.6 endpoint-resolution logic).

### Changed — contributor tooling

- Vendored the `whatifd-design` skill from the parent workspace into `.claude/skills/whatifd-design/` plus a project-rooted `CLAUDE.md` so contributors get the doctrine on a clean clone. Layout: `SKILL.md` (router) + `references/{doctrine,practices,contracts,type-model,phases,enforcement,statistical-defaults,walkthroughs,cascade-catalog}.md`. The parent-workspace deliberation drafts and decision record are intentionally not vendored (they reference private reasoning artifacts). `.gitignore` extended for Claude Code session-runtime artifacts (`scheduled_tasks.lock`, `cache/`, `state/`) without excluding the skill itself. Cascade-catalog entry "Dashboard SKILL_DIR resolution" marked resolved-2026-05-05.

### Added — Phase 2.4 (fix-suggestion registry, cardinal #8 gate)

- `src/whatifd/decision/fix_suggestions.py` — `FixSuggestion` (finding_code, summary, ordered tuple of Markdown step strings, internal description) plus `FIX_SUGGESTION_REGISTRY` (frozen `MappingProxyType` over six suggestions, one per blocking finding code: `baseline_regression_above_threshold`, `failure_improvement_below_threshold`, `practical_delta_below_threshold`, `cache_corruption_detected`, `cache_lock_unavailable`, `cohort_systemic_failure`). Step text on cache-related suggestions matches the recovery playbook in walkthrough scenario 5.
- `tests/unit/whatifd/decision/test_fix_suggestions.py` — 14 tests across registry shape (snake_case keys, finding_code/key consistency, ≥1 step per entry, non-empty steps as strings, tuple ordering, frozen `FixSuggestion`, `MappingProxyType` immutability) and the cardinal #8 cross-registry gate: positive coverage (every blocking finding has a fix suggestion), inverse coverage (every fix suggestion targets a real finding code), negative coverage (no info finding code appears here — addresses PR #17 review suggestion), and the composite "exact match" assertion.

### Changed — Phase 2.4

- `tests/unit/whatifd/decision/test_finding_codes.py` — removed the `xfail(strict=True)` placeholder for `TestCrossRegistryCoverage`; the canonical coverage gate now lives next to `FIX_SUGGESTION_REGISTRY` in `test_fix_suggestions.py`. A short comment marks the relocation.

### Added — Phase 2.3 (finding code registry)

- `src/whatifd/decision/finding_codes.py` — `FindingCodeSpec` (severity, message_template, required_details tuple, derived_from_failures_expectation, description) plus `FINDING_CODE_REGISTRY` (frozen `MappingProxyType` over the v0.1 starter set: 1 info code, 3 blocks_ship codes, 3 blocks_all codes — 7 total). The `make_decision_finding` factory pulls severity from the registry (deliberately non-overrideable per cardinal #2 — severity drives verdict) and validates the derived_from_failures expectation (`"never"` rejects non-empty, `"always"` rejects empty, `"sometimes"` unconstrained).
- `tests/unit/whatifd/decision/test_finding_codes.py` — 25 tests across registry shape (snake_case codes, valid Severity literal, non-empty descriptions and message templates, frozen `FindingCodeSpec`, `MappingProxyType` immutability), placeholder/required_details symmetry on the message template, severity-specific shape rules (every `blocks_all` code expects failure derivation; every `info` code does not), positive sweep, contract-violation rejection, and severity non-overrideable enforcement. Includes a `strict=True` xfail placeholder for the Phase 2.4 cross-registry coverage test (`every blocking finding has a fix suggestion`); the xfail flips to a regular passing test when Phase 2.4 ships `FIX_SUGGESTION_REGISTRY`.
- `tests/unit/whatifd/decision/test_failure_codes.py` — added `TestStageScopeReachability`: `default_scope=="trace"` ⇒ stage in {ingest, selection, replay, score, diff}; `default_scope=="cohort"` ⇒ stage in {decision, report}; run-scope unconstrained. Catches future drift on registry edits. Addresses the structural-invariant suggestion from PR #16's review.

### Added — Phase 2.2 (failure code registry)

- `src/whatifd/decision/failure_codes.py` — `FailureCodeSpec` dataclass (stage, default_scope, required_details tuple, retryable_default, description) plus `FAILURE_CODE_REGISTRY` (frozen `MappingProxyType` over the v0.1 starter set: `trace_schema_mismatch`, `trace_invalid`, `tool_cache_miss`, `runner_timeout`, `runner_exception`, `scorer_unavailable`, `scorer_invalid_output`, `ci_uncomputable_for_required_cohort`, `cache_lock_unavailable`, `cache_corruption_detected`). The `make_failure_record` factory pulls defaults from the registry and validates programmer-contract invariants — unknown code, missing required details, scope/identifier mismatch — with `ValueError` (cardinal #1: expected failures are data, contract violations are bugs in whatifd itself).
- `tests/unit/whatifd/decision/test_failure_codes.py` — 27 tests across registry shape (lowercase snake_case codes, valid stage/scope literals, non-empty descriptions, `MappingProxyType` immutability), positive sweep over every registered code, default propagation, scope override for Phase 2.7 aggregation, and contract-violation rejection (unknown code, missing required details, all six scope/identifier mismatches).

### Added — Phase 2.1 (floor evaluator)

- `src/whatifd/decision/floor.py` — replaced the Phase 1.4 stub `evaluate_floor()` with the real signature `evaluate_floor(cohort_results, floor, required_cohorts, *, now=None)`. The proof's `evaluated_at` is now an ISO 8601 timestamp from the injected clock (defaults to UTC wall clock); `floor_version` is propagated from the `TrustFloor` argument. Introduced `compute_cohort_floor_failures(cohort, floor)` as the per-cohort rule helper — checks `min_selected`, `min_replayed`, `min_scored` (each emitting `blocks_all` on failure) and `min_replay_validity_ratio` (emitting `blocks_ship` on failure, skipped when `selected == 0`). The aggregator emits a `required_cohort_present` failure (severity `blocks_all`) when a required cohort is absent from the input. An empty `required_cohorts` is itself a structural failure (`required_cohorts_nonempty`, severity `blocks_all`) per cardinal #2 — a misconfigured policy with nothing to require would otherwise produce a vacuous proof and bypass the floor.
- `tests/unit/whatifd/decision/test_floor.py` — 17 new tests covering per-cohort rule trips at boundaries, ratio computation, zero-selected guard, custom thresholds, cross-cohort aggregation, missing-cohort detection, non-required cohort isolation, ISO timestamp emission and round-trip, and floor-version propagation. The seven Phase 1.4 witness/immutability/equality tests were updated to call `evaluate_floor` with passing-cohort fixtures and a fixed clock.

### Added — Phase 1 (type model)

- `src/whatifd/types/primitives.py` — `DecimalString` (NewType over `str`) and `JsonPrimitive` (`str | int | float | bool | None`). The two smallest building blocks for the internal type model. Cardinal rule #4 (determinism opt-in per field) and #6 (public schema hand-written).
- `src/whatifd/types/sensitive.py` — `Sensitive[T]` redaction wrapper (cardinal rule #5). `__repr__` / `__str__` / `__format__` / `__reduce__` all return the redacted form so f-strings, log lines, and pickle never leak the wrapped value. `.unwrap(reason=...)` returns the value AND records a `SensitiveUnwrap` audit entry to a thread-safe in-process collector. Includes `SensitiveSerializationError`, `UnredactedSensitiveError` exception types and an `_infer_caller()` helper that auto-fills the unwrap call site.
- `src/whatifd/types/__init__.py` — re-exports the public surface and documents the Phase 1 sub-ordering (1.1 primitives → 1.2 sensitive → 1.3 operational → 1.4 verdict → 1.5 policy → 1.6 manifest → 1.7 statistical).
- `tests/unit/whatifd/types/` — nested test layout. 22 tests across `test_primitives.py` (5: construction, str-runtime, fixed-precision preservation, JsonPrimitive scalar acceptance, import-budget < 50 ms) and `test_sensitive.py` (17: redacted serialization × 4, pickle blocking, slots discipline × 2, unwrap behavior × 5, audit-log concurrency × 2, infer-caller, exception type distinction × 2).

### Added — Phase 0 (paper artifacts)

- `docs/walkthroughs/` — six rendered Markdown reports (clean Ship, Don't Ship regression, Don't Ship failure-rescue gap, Inconclusive insufficient sample, Inconclusive cache corruption, rerun-after-fix diff) plus a README index. These are the canonical Phase 7 renderer test fixtures. Each includes a `## Methodology` block per cardinal rule #10. The empirical reviewer for the design.
- `docs/concepts.md` — two-page conceptual model document plus glossary. Distilled from the doctrine and the walkthroughs. Sections: defensible verdicts, non-claims, verdict states, trust floor vs decision policy, failure-as-data, evidence and audit bundle, privacy and redaction, examples of misleading outputs whatifd must never produce.
- `docs/internal/PHASE_0_4_ENFORCEMENT_AUDIT.md` — Phase 0.4 audit report. Inventories every "structural" claim across the skill, cross-references against `enforcement.md` (now 14 rows), confirms each open cascade has a resolution phase. Closes Phase 0 gate.
- `docs/sessions/` — Layer 2 telemetry session logs (`2026-05-04`, `2026-05-05`).

### Added — telemetry bundle (skill instrumentation)

- `tools/pr_checker.py` — Claude-based PR doctrine reviewer. Reads PR metadata + diff via `gh`, checks the change against the project's ten cardinal rules using the Anthropic SDK (`claude-haiku-4-5` default), emits a structured verdict. Exit codes match whatifd's own verdict semantics (0=Ship, 1=Don't Ship, 2=Inconclusive). Every failure path is a typed `ReviewVerdict`, never an exception (cardinal rule #1).
- `.github/workflows/pr-review.yml` — GitHub Actions workflow that runs `tools/pr_checker.py` on every PR. Inconclusive surfaces as a warning + PR comment but does NOT block merges (advisory only).
- `.mcp/run_pr_check_claude.sh`, `.mcp/run_pytest.sh` — MCP-server wrapper scripts.
- `.github/mcp-claude.md`, `.github/mcp-pytest.md` — MCP server configuration documentation.
- `.github/copilot-instructions.md` — repo-specific Copilot guidance with the canonical `src/whatifd/` layout and Phase-N-status annotations per directory.
- `scripts/collect-transcripts.sh`, `scripts/run-skill-benchmark.sh`, `scripts/grade-skill-benchmark.sh`, `scripts/skill-dashboard.sh` — four-layer skill-instrumentation bundle.
- `tests/skill-benchmarks/prompts.json` — 11 benchmark prompts (8 should-trigger covering cardinal rules 2/5/9/10 + doctrine + scope + enforcement; 3 negative tests).
- `CLAUDE.md.append.md` — session-telemetry protocol block for adopters.
- `AGENT_TELEMENTRY.md` — telemetry bundle documentation.

### Changed

- Adopted cardinal rule #10 ("Statistical claims must match the design") into the `whatifd-design` skill at `.claude/skills/whatifd-design/`. New rule + supporting `statistical-defaults.md` reference + `MethodologyDisclosure` types added to the type model. The `methodology` field on `ReportV01` is now required; schema validation enforces presence.
- Phase 0.3 audience-distribution decision: ship v0.1 as `failure_rescue` only; ROADMAP `regression_check` for v0.2; revisit after first 5 production users. Schema keeps `cohort: str` (not `Literal`) so v0.2 expansion is non-breaking. Recorded as an addendum in `references/V0_1_DECISION_RECORD.md`.

### Fixed

- `pip-audit` step in `.github/workflows/security.yml` — `pip-audit` 2.10.0 rejects `--disable-pip` without `-r`, breaking the weekly run. Install the project with all extras and audit the resulting environment, filtering whatifd itself (pre-release; not on PyPI). Match both `whatifd==` and `whatifd @ file:///` freeze-output formats per pip 25+.
- `.github/workflows/ci.yml` — restored `actions/checkout` step in lint and test jobs (dropped by a dependabot merge), unified `setup-uv` to `@v7`, fixed stray blank lines.

### Removed

- `.github/workflows/codeql.yml` — replaced by GitHub's Default Setup (no custom workflow file). The custom workflow conflicted with Default Setup's SARIF processing.

### Notes

- Phase 0 gate: GREEN. Phase 1 in progress (1.1 primitives, 1.2 Sensitive[T] complete; 1.3–1.7 pending).
- 22 tests in `tests/unit/whatifd/types/` plus the 10 existing contract tests = 32 tests passing on the v0.1 branch.

---

### Added — earlier scaffold (pre-Phase-0)

- Initial public scaffold:
  - `DESIGN.md` - canonical design through the M10–M12 roadmap; problem framing, prior art, runner contract, report shape, eval target, risks, Path Z.
  - `LICENSE` - Apache 2.0.
  - `README.md - hero copy + workflow / overview / pipeline images + status table + runner contract teaser.
  - `pyproject.toml` - uv-managed; src layout; Python ≥ 3.11; ruff/mypy/pytest configured.
  - `src/whatifd/__init__.py` - version 0.0.1.
  - `src/whatifd/contract/__init__.py - runner contract Pydantic models: `TraceInput`, `ReplayConfig`, `ToolCache`, `ReplayOutput`, `TraceOutput`, `ScoreCase`, `Runner` Protocol.
  - `tests/test_contract.py - 10 smoke tests for the contract API.
  - 3 architectural / workflow images in the repo root.
- Production-grade GitHub plumbing:
  - `.github/workflows/ci.yml - lint (ruff), type-check (mypy), test on Python 3.11 / 3.12 / 3.13.
  - `.github/workflows/security.yml - `pip-audit`, `bandit`, `gitleaks`; runs on push, PR, and weekly schedule.
  - `.github/workflows/codeql.yml - CodeQL static analysis with `security-extended` + `security-and-quality` queries.
  - `.github/workflows/release.yml - sdist + wheel build, PyPI publish via Trusted Publishers, GitHub Release with auto-generated notes; triggered by `v*.*.*` tags.
  - `.github/dependabot.yml - weekly grouped pip + GitHub Actions updates.
  - `.github/CODEOWNERS - review routing.
  - `.github/PULL_REQUEST_TEMPLATE.md - PR checklist with whatifd-specific gates.
  - `.github/ISSUE_TEMPLATE/ - bug + feature templates with structured fields, plus a `config.yml` that disables blank issues and routes to Discussions / private security advisories.
- Project governance:
  - `CONTRIBUTING.md - branch strategy, commit conventions, PR / merge / release workflow, manual GitHub config checklist.
  - `CODE_OF_CONDUCT.md` -Contributor Covenant 2.1 (adopted by reference).
  - `SECURITY.md - disclosure policy, scope, coordinated disclosure timeline.
  - `.pre-commit-config.yaml` - ruff + ruff-format + mypy + standard hygiene hooks.

### Notes

- No runtime yet. v0.1 - Langfuse ingest, replay engine, Inspect AI scorer, evidence - first Markdown + JSON reports, CI-ready exit codes-begins in M10.

---

[Unreleased]: https://github.com/victoralfred/whatifd/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/victoralfred/whatifd/releases/tag/v0.1.0
