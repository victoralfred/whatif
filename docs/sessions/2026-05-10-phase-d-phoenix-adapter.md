---
session_id: 2026-05-10-phase-d-phoenix-adapter
started_at: 2026-05-10T00:00:00Z
---

## Session start

**User request:** Phase D of the v0.2 roadmap — Arize Phoenix tracer adapter. Tracer-neutrality proof: ship a second `TraceSource` adapter to prove the v0.1 Protocol isn't Langfuse-shaped by accident.

**Phase plan position:** Phase D of v0.2-roadmap.md. Phases A, B, C merged. This PR branches off `5a17ae4` (Phase C merge).

## Session end

**Artifacts produced:**
- `packages/whatifd-phoenix/pyproject.toml` (new) — package skeleton mirroring `whatifd-langfuse`. v0.2.0 version. `arize-phoenix-client` as `[live]` extra, not hard dep.
- `packages/whatifd-phoenix/src/whatifd_phoenix/__init__.py` (new) — public surface, `__version__` from distribution metadata.
- `packages/whatifd-phoenix/src/whatifd_phoenix/source.py` (new) — `PhoenixTraceSource` against a `spans_provider: Callable[[], Iterable[dict]]` shape. Groups spans by `context.trace_id`, projects root span's `input.value` / `output.value` as `Sensitive[str]`.
- `packages/whatifd-phoenix/tests/conftest.py` + `tests/test_conformance.py` (new) — 14 tests: 5 inherited from `TraceSourceConformance` + 9 adapter-specific (span grouping, root identification, classifier semantics, max_traces, adapter_metadata, cluster_key_support).
- `packages/whatifd-phoenix/README.md` (new) — usage, OpenInference attribute table, status table, doctrine alignment.
- `pyproject.toml` (root): `tool.uv.workspace.members` extended to include `packages/whatifd-phoenix`.
- `CHANGELOG.md`: Phase D section under [Unreleased].
- `.claude/skills/whatifd-design/references/cascade-catalog.md`: Phase D resolved entry.
- `docs/sessions/2026-05-10-phase-d-phoenix-adapter.md`: this file.

**Cascade catalog items:**
- Resolved: "Phase D — Phoenix / OpenInference TraceSource adapter; tracer-neutrality proof" (2026-05-10).

**Gaps surfaced:**
- Recorded-cassette smoke test against live Phoenix is deferred to v0.3. The Langfuse adapter has `tests/test_recorded_smoke.py` with vcr cassettes; Phoenix needs the same infrastructure but Phoenix's HTTP API surface differs and would need its own cassette collection.
- The `spans_provider` shape is more flexible than Langfuse's `LangfuseAPI` constructor but pushes more wiring onto the user. README documents the canonical pattern; field experience will tell whether it's the right level of abstraction.

**Doctrine moments:**
- Considered taking `arize-phoenix-client.Client` directly as a constructor argument (matching the Langfuse adapter's `LangfuseAPI`-typed shape). Declined: Phoenix's Client API has churned across versions (`arize-phoenix` → `arize-phoenix-client`; methods on `Client` change between major versions). Pinning a specific Client surface would force a sync-with-Phoenix-release cycle. The span-iterator shape is the stable API — OpenInference attributes are an open standard, decoupled from Phoenix's Python wrapper.
- Considered making Phoenix a hard dep. Declined: keeping it `[live]`-extra means the package's basic install is lightweight, the conformance test runs without arize-phoenix-client, and operators who wire their own client (or use a different OpenInference source like a custom OTLP collector) don't pay the install cost.
- `cluster_key_support` returns empty even though OpenInference spans naturally carry `user.id` and `session.id`. Same cardinal-#10 stance as Langfuse: fabricating cluster keys for confirmatory verdicts requires predeclaration. v0.3+ adds explicit opt-in.

**Notes for the next session:**
- Phase E — statistical layer upgrade (real cluster bootstrap, Holm correction) — is the next big surface and unblocks `MethodologyDisclosure.bootstrap.method != "unavailable"`.
- Phoenix recorded-cassette smoke test (Phase D follow-up) — when Phoenix's cassette infrastructure parity is set up.
- Test count: 1154 passing on this branch (was 1140 on `main`; +14 Phoenix tests).
