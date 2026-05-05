# Repository-specific Copilot Instructions

Purpose: quick, machine-friendly notes to help future Copilot/Copilot-CLI sessions understand how to build, test, and reason about this repository.

---

1) Build, test, and lint commands

- Project tooling uses the `uv` helper (see CONTRIBUTING). Common commands:
  - Install dev deps: `uv sync --all-extras --dev`
  - Run full test suite: `uv run pytest -v`
  - Run a single test by path: `uv run pytest tests/path/to/test_file.py::test_name -v`
  - Run a single test by keyword: `uv run pytest -k "pattern" -v`
  - Lint (ruff): `uv run ruff check .`
  - Format check (ruff): `uv run ruff format --check .`
  - Typecheck: `uv run mypy src`
  - Optional pre-commit: `pre-commit install` after installing pre-commit
  - Release (maintainers): `uv build` then follow repo's release steps in CONTRIBUTING.md

Exit codes used by the CLI (from README):
  - 0 = passed configured policy
  - 1 = failed configured policy
  - 2 = inconclusive (setup/replay/scoring failure)


2) High-level architecture (big picture)

- Purpose: `whatif` is an experiment runner that forks production traces, replays them under a proposed change, scores results, and emits a PR-ready verdict + evidence report.

- Planned source layout (per `.claude/skills/whatif-design/phases.md`; not all dirs exist yet):
  - `src/whatif/contract/` — public runner-contract types (TraceInput, ReplayConfig, ToolCache, ReplayOutput, ScoreCase, Runner Protocol). **EXISTS.**
  - `src/whatif/types/` — internal frozen-dataclass types (FailureRecord, DecisionFinding, CohortResult, FloorPassedProof, Sensitive[T], MethodologyDisclosure, etc.). Phase 1.
  - `src/whatif/decision/` — floor evaluation, guard chain, finding/failure/fix-suggestion registries, cohort-systemic detection. Phase 2.
  - `src/whatif/cache/` — scorer cache (keying, storage, lock, policy, summary). Phase 3.
  - `src/whatif/adapters/` — adapter loader (lazy). Reference adapters live in separate packages: `whatif-langfuse`, `whatif-inspect-ai`. Phase 4.
  - `src/whatif/report/` — public ReportV01 model + projection layer + JSON Schema. Phase 5.
  - `src/whatif/serialization/` — encoder, graph walk for Sensitive[T], DecimalString, determinism subset. Phase 5.
  - `src/whatif/replay/` — streaming pipeline (sync + async runners), tool cache, replay result types. Phase 6.
  - `src/whatif/render/` — three-format renderer (1-line CI status, 30-line summary, full report). Phase 7.
  - `src/whatif/cli.py`, `src/whatif/config.py` — Typer CLI + Pydantic config. Phase 8.

- Where to look for design constraints: DESIGN.md, CONTRIBUTING.md, README.md, and `.claude/skills/whatif-design/SKILL.md` (policy/doctrine for design decisions).


3) Key conventions and repository-specific rules

- Branching & commits:
  - Trunk-based on `main`. Feature branches: `feat/...`, `fix/...`, `docs/...`, `chore/...`, `refactor/...`, `test/...`, `ci/...`.
  - Conventional Commits enforced; PR title becomes squashed commit subject.

- Pull requests / CI:
  - CI checks required before review: lint, type, tests (py3.11/3.12/3.13), pip-audit, bandit, gitleaks. CodeQL runs separately via GitHub's Default Setup (no custom workflow file).
  - Optional Claude-based PR review via `tools/pr_checker.py` + `.github/workflows/pr-review.yml` (advisory; does not block merges on `inconclusive`).
  - One human review required for merges to `main`. Maintainers squash-merge.

- Tests:
  - Two flavors for adapters/integrations: recorded fixtures (always run in CI) and live tests (integration, skipped unless env vars present). Live tests use pytest.mark.integration and env gating.
  - Put ingest adapter tests in `tests/ingest/test_<adapter>.py`.

- Scorers & reports:
  - Scorers must return a numeric score and a mandatory rationale string (rationale surfaces in Evidence section).
  - Report must include mandatory sections (Verdict, Stats, Replay validity, Baseline integrity, Evidence + judge rationale). Preserve these when changing report format.

- Architecture governance:
  - Architectural changes touching `src/whatif/contract/`, `src/whatif/replay/`, `src/whatif/score/`, `src/whatif/diff/` require a DESIGN.md update or explicit justification in the PR.
  - When you change schema/major decisions, update the cascade-catalog (see `.claude/skills/whatif-design/references/cascade-catalog.md`).

- Sensitive/defensive rules (from whatif-design SKILL):
  - Failure-as-data: expected failures are structured data in reports, not unhandled exceptions.
  - Trust floor cannot be bypassed; disclosure rules and two-affirmation apply (see `.claude/skills/whatif-design/SKILL.md`).


4) Where Copilot should look first

- READ FIRST: README.md, CONTRIBUTING.md, DESIGN.md, and `.claude/skills/whatif-design/SKILL.md` and its references.
- Source entry points: `src/whatif/ingest/`, `src/whatif/replay/`, `src/whatif/score/`, `src/whatif/diff/`.
- Tests and fixtures: `tests/` (use recorded fixtures to avoid network calls during local analysis).


5) Existing AI-assistant configs to respect

- CLAUDE.md at repository root documents session telemetry and whatif-design doctrine — read before making design/architecture proposals.
- `.claude/skills/whatif-design/` contains SKILL.md and references that encode cardinal rules and session logging conventions. When using the whatif-design skill, add session logs to `docs/sessions/` per the template.


6) Small quick tips for automated agents (concise)

- Use `uv run pytest tests/path::test_name -q` to run single tests.
- Favor recorded-fixture tests for offline analysis to avoid flakiness and secrets.
- When editing report shapes or runner contract, include a DESIGN.md change and a changelog entry.

---

If an existing `.github/copilot-instructions.md` is present, prefer merging these notes into it rather than replacing the whole file.

MCP servers

- Pytest MCP helper: `./.mcp/run_pytest.sh` (see `.github/mcp-pytest.md`). Use this to run the full suite or a single test.
- Claude PR checker MCP helper: `./.mcp/run_pr_check_claude.sh <pr-number>` (see `.github/mcp-claude.md`). This invokes `tools/pr_checker.py` and returns exit codes: 0=pass, 1=fail, 2=inconclusive.

(End of copilot instructions)
