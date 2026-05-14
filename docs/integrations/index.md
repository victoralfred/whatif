# Integrations

whatifd composes with your existing tracer, scorer, and agent runtime — it doesn't replace them. This section documents the adapter packages that wire those systems into the whatifd pipeline.

## Tracers (TraceSource adapters)

Tracers feed production traces into whatifd. Each adapter implements `whatifd.adapters.protocols.TraceSource` and ships as its own PyPI distribution.

| Adapter | Package | Status | Notes |
|---|---|---|---|
| **Langfuse** | [`whatifd-langfuse`](../../packages/whatifd-langfuse/README.md) | v0.1 | Streaming pagination; tag-based cohort classifier. Recorded cassette smoke in v0.3. |
| **Arize Phoenix / OpenInference** | [`whatifd-phoenix`](../../packages/whatifd-phoenix/README.md) | v0.2 | Span-iterator shape; any OpenInference-emitting tracer works. |
| LangSmith | — | v0.3+ | Planned. |
| OpenTelemetry GenAI | — | v0.3+ | Planned. |

## Scorers (Scorer adapters)

Scorers convert a `(trace, replayed_output)` pair into a numeric delta that the pipeline aggregates into a cohort-level verdict.

| Adapter | Package | Status | Notes |
|---|---|---|---|
| **Inspect AI** | [`whatifd-inspect-ai`](../../packages/whatifd-inspect-ai/README.md) | v0.1 | Config-loadable from YAML via `scorer.score_fn` (Phase B, v0.2). |

## Third-party tooling

Tools built around whatifd by the adapter-author community. These are not part of whatifd core.

| Tool | Source | What it does |
|---|---|---|
| **whatifd-skillgen** | [skillgen.md](./skillgen.md) | Scaffolds protocol-compliant adapter stubs from a declarative `skill.md` manifest. Install as a dev tool when authoring a new `whatifd-<name>` adapter package. |

## Writing a new adapter

See **[`docs/integrations/skillgen.md`](./skillgen.md)** for the canonical seven-step walkthrough covering:
- Creating the workspace member directory
- Writing the `skill.md` manifest
- Running `whatifd-skillgen generate` to scaffold the stub
- Applying `config.py` and `factory.py` patches
- Registering the workspace member and wiring version parity
- Adding to the release workflow

The freshest reference adapter is `packages/whatifd-phoenix/`. Copy its `pyproject.toml` structure when starting a new integration.
