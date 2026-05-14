---
session_id: 2026-05-13-skill-template-system
started_at: 2026-05-13T20:00:00Z
updated_at: 2026-05-14T00:00:00Z
---

## Session start

**User request:** Design and implement a skill template system with three parts:
(1) agent instructions in `.claude/skills/capabilities/SKILL.md`, (2) a Python
runtime in `src/whatifd/skills/` that implements `whatifd skill generate <name>`,
and (3) an example skill that demonstrates the round-trip.

**Skill files read:**
- .claude/skills/whatifd-design/SKILL.md
- (references not read — task was initially below the cardinal-rule threshold for
  requiring full reference reads; the design was for a scaffolding tool, not a
  change to the verdict pipeline)

**Cardinal rules cited:**
- Rule #1: Failures-as-data — every error in the skill loader/generator/writer
  surfaces as a typed exception (`SkillManifestError`, `SkillGenerationError`) with
  an actionable message; no raw exceptions escape the package boundary.
- Rule #5: Sensitive data wrapped, never raw — generated stub code includes inline
  comments directing implementors to wrap user content in `Sensitive[T]` at adapter
  boundaries.
- Rule #6: Public schema hand-written — `SkillManifest` is a hand-written Pydantic
  model with `extra="forbid"`, not inferred from runtime data.
- Rule #9: whatifd is orchestration, not compute — the generator is pure I/O (read
  YAML, emit Python text); no CPU-optimization tools used.

**Clarifying questions asked:**
- Should config.py/factory.py patches be applied automatically or printed as
  instructions? → Print only (safe v0.1 default).
- What should the example skill demonstrate? → Stub scorer.

**Phase plan position (per references/phases.md):**
- Phase: Post-v0.2 (tooling/DX layer; no verdict pipeline impact)
- Sub-item: N/A — new capability orthogonal to experiment phases
- Prerequisites status: All green (v0.2 released per recent commits)

---

## PR review rejection and restructuring (2026-05-13 → 2026-05-14)

After the initial implementation, a PR review rejected the addition on two grounds
and requested restructuring:

### Doctrinal rejection
A scaffolding DX tool is not verdict infrastructure. Core whatifd's product is the
defensibility of the `Verdict`. Including a generator in the same distribution
dilutes that contract and adds import surface to every install, violating the
principle that every line in core must contribute to verdict defensibility.

### Architectural rejection (five bugs)
1. **Wrong output directory**: generator wrote into `src/whatifd/skills/<name>/`
   inside whatifd's source tree rather than the target adapter package.
2. **Bad factory hint import path**: generated `from whatifd.skills.<name> import`
   instead of `from whatifd_<name> import`.
3. **Scorer protocol pollution**: scorer stub contained `iter_traces()`, which
   belongs to `TraceSource` not `Scorer`.
4. **Hardcoded TODO in `adapter_metadata()`**: emitted `TODO: replace package_version`
   instead of calling `importlib.metadata.version("whatifd-<name>")`.
5. **Zero tests**: the entire generator was untested.

### Resolution: Option 1 — extract to standalone workspace package

Option 1 (preferred by reviewer) was taken: extract the generator into a separate
`whatifd-skillgen` workspace package with its own PyPI distribution, fix all five
bugs, and delete the rejected code from core.

---

## Session end

**Artifacts produced:**

*Removed from core whatifd:*
- `src/whatifd/skills/` — generator subpackage (10 files), deleted entirely
- `src/whatifd/cli.py` lines 775–861 — `skill_app` Typer sub-app and
  `skill_generate()` command, deleted
- `.claude/skills/capabilities/` — Claude skill that drove the `skill generate`
  workflow, deleted

*New package `packages/whatifd-skillgen/`:*
- `packages/whatifd-skillgen/pyproject.toml`: standalone package, version `0.2.0`
  (workspace lockstep), no `whatifd` runtime dependency, entry point
  `whatifd-skillgen = "whatifd_skillgen.cli:app"`
- `packages/whatifd-skillgen/src/whatifd_skillgen/__init__.py`: `__version__` via
  `importlib.metadata.version("whatifd-skillgen")` with `0.0.0+unknown` fallback
- `packages/whatifd-skillgen/src/whatifd_skillgen/errors.py`: `SkillError`,
  `SkillManifestError`, `SkillGenerationError` — typed hierarchy, no raw exceptions
  escape the boundary
- `packages/whatifd-skillgen/src/whatifd_skillgen/schema.py`: `SkillManifest`,
  `EnvVarSpec`, `ParameterSpec` — all `extra="forbid"`, validators for
  UPPER_SNAKE_CASE env var names, valid identifiers, duplicate parameter detection
- `packages/whatifd-skillgen/src/whatifd_skillgen/loader.py`: splits `---` fences,
  `yaml.safe_load`, wraps all errors as `SkillManifestError`
- `packages/whatifd-skillgen/src/whatifd_skillgen/generator.py`: deterministic code
  generation; fixes all five architectural bugs over the original
- `packages/whatifd-skillgen/src/whatifd_skillgen/scaffold.py`: thin orchestrator —
  load → generate → write → return `ScaffoldResult`
- `packages/whatifd-skillgen/src/whatifd_skillgen/cli.py`: `whatifd-skillgen
  generate <skill_dir> [--overwrite]`; exit 0 on success, exit 2 on error
- `packages/whatifd-skillgen/tests/conftest.py`: fixtures for minimal/full manifests
  per kind (scorer, tracer, runner)
- `packages/whatifd-skillgen/tests/test_schema.py`: pins `extra="forbid"`, all
  field validators, duplicate parameter detection
- `packages/whatifd-skillgen/tests/test_loader.py`: pins all error shapes — missing
  file → `SkillManifestError`, malformed YAML → `SkillManifestError`, invalid
  manifest → `SkillManifestError` (none of the raw exceptions escape)
- `packages/whatifd-skillgen/tests/test_generator.py`: pins determinism, scorer
  protocol correctness (no `iter_traces`), `adapter_metadata` fix (no TODO),
  factory import path, dist name format
- `packages/whatifd-skillgen/.claude/skills/capabilities/SKILL.md`: Claude skill
  for this package's four-step authoring process
- `packages/whatifd-skillgen/.claude/skills/capabilities/templates/skill-template.md`:
  copy-paste starting template
- `packages/whatifd-skillgen/README.md`: quickstart, CLI reference, what generator
  produces per kind, skill.md schema, common errors

*Workspace registration:*
- `pyproject.toml`: added `whatifd-skillgen` to `[tool.uv.workspace] members`,
  `[tool.uv.sources]`, and `[dependency-groups] workspace`
- `tests/unit/whatifd/test_version_parity.py`: updated `_DISTRIBUTIONS` tuple to
  all five packages (also fixed pre-existing gap: `whatifd-phoenix` was missing);
  added `test_whatifd_skillgen_version_matches_distribution_metadata()`; updated
  `test_no_package_reports_sentinel_when_installed()` and
  `test_all_workspace_packages_share_the_same_version()`
- `RELEASING.md`: all "four packages" references updated to five — package list,
  environment names table, pre-flight checklist, verify step, failure-mode recovery
  sections, TestPyPI dry-run steps
- `.github/workflows/release.yml`:
  - Tag↔version guard `packages` list includes `packages/whatifd-skillgen/pyproject.toml`
  - Success message updated: "five workspace pyproject.toml versions"
  - Build step: `uv build --package whatifd-skillgen --out-dir dist-whatifd-skillgen`
  - Upload-artifact step for `dist-whatifd-skillgen`
  - New `publish-whatifd-skillgen` job (environment `pypi-whatifd-skillgen`,
    `needs: publish-whatifd`)
  - `github-release.needs` includes all five publish jobs

*Documentation:*
- `docs/sessions/2026-05-13-skill-template-system.md`: this log (updated)
- `docs/integrations/index.md`: new adapter index covering tracers, scorers,
  third-party tooling
- `docs/integrations/skillgen.md`: canonical seven-step walkthrough for writing a
  new adapter using whatifd-skillgen
- `README.md`: links to `docs/integrations/`
- `docs/getting-started.md`: links to `docs/integrations/`

**Cascade catalog items:**
- None — skill scaffolding has no verdict-pipeline impact. Removal from core
  (`src/whatifd/skills/`, CLI subcommand) has no downstream effect on the verdict
  contract or report schema.

**Gaps surfaced:**
- PyPI Pending Publisher for `whatifd-skillgen` must be registered manually before
  the next release tag. Environment name: `pypi-whatifd-skillgen`. Cannot be
  automated from the workflow itself.
- Auto-patching of `config.py` and `factory.py` is still not implemented (deferred).
  The generator prints actionable instructions; the author applies them manually.
- The generator uses template strings, not Jinja2. Extracting templates to
  user-customizable files remains a future enhancement.

**Doctrine moments:**
- **Extraction over rejection**: when the review flagged the tool as non-verdict
  infrastructure, the question was "does this make the verdict more defensible?"
  A scaffolding tool that ships with core doesn't — but neither does silently
  removing scaffolding support. Extraction to a standalone package preserves the
  DX value without polluting core's surface area. Defensibility test resolved the
  trade-off.
- **Misleading vs. inconvenient (generator output dir)**: the original generator
  wrote into `src/whatifd/skills/` because that was easiest to implement. Writing
  to the wrong location would silently produce a file that compiles but imports from
  the wrong path — a misleading result. Requiring the user to pass `<skill_dir>`
  and writing there is slightly more inconvenient but not misleading.
- **Protocol purity (scorer stub)**: including `iter_traces()` in a scorer stub
  would mislead an adapter author into implementing a method that the scorer
  protocol does not require and the scorer dispatch will never call. The
  misleading-vs-inconvenient test was unambiguous: remove it.
- **Determinism as regression gate**: the generator's output is deterministic by
  construction (no timestamps, no random seeds, no LLM calls). A test that calls
  `generate_skill` twice and asserts identical output makes determinism a hard
  invariant, not a convention. Applied cardinal rule #4 (determinism opt-in per
  field) in reverse: the whole output is deterministic and pinned by test.
- **Generated stub raises `NotImplementedError`**: a silent default (e.g. returning
  `0.5` always) would mislead production users into thinking the adapter works.
  `NotImplementedError` is immediately discoverable at first test run. Inconvenient
  chosen over misleading.

**Notes for the next session:**
- Register the PyPI Pending Publisher for `whatifd-skillgen` before tagging the
  next release: https://pypi.org/manage/account/publishing/ — environment name
  `pypi-whatifd-skillgen`, owner `victoralfred`, repo `whatifd`, workflow
  `release.yml`.
- Consider `--auto-patch` flag (future) that applies `config.py` / `factory.py`
  patches with a backup. The v0.1 print-only approach is safe; auto-patch is
  the natural next step after the tool stabilizes.
- An LLM-assisted implementation step (calling Claude to implement the `TODO`
  sections from the skill.md body) is the natural next enhancement after the
  template system stabilizes.
