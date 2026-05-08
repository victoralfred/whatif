# Contributing to whatif

Thanks for thinking about contributing. This document covers the development workflow, branching strategy, commit and PR conventions, security reporting, and how to add the most common kinds of changes.

If you've not yet read [DESIGN.md](./DESIGN.md), do that first - many *"why is it like this?"* questions are answered there, and PRs that conflict with documented non-goals are usually closed unless they argue convincingly for changing the non-goal itself.

---

## TL;DR

- Discuss non-trivial changes in an issue or Discussion **before** writing code.
- Branch off `main`. Use `feat/...`, `fix/...`, `docs/...`, `chore/...`.
- Commit subjects follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
- Open a PR. CI must be green. One review required for merges to `main`.
- Maintainer squash-merges. The PR title becomes the squashed commit subject - make it Conventional Commits compliant.
- Add a `## [Unreleased]` entry to `CHANGELOG.md` for any user-visible change.

---

## Development setup

```bash
git clone https://github.com/victoralfred/whatif
cd whatif
uv sync --all-extras --dev

# verify the toolchain works
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

### Optional: pre-commit hooks

To catch formatting / lint issues before they hit CI:

```bash
uv run pip install pre-commit
pre-commit install
# Now ruff + mypy run on each `git commit`.
```

---

## Branching strategy

Trunk-based development on `main`. Feature branches are short-lived (target < 1 week) and named:

| Prefix      | When to use                                  |
|-------------|----------------------------------------------|
| `feat/`     | New user-visible capability.                 |
| `fix/`      | Bug fix.                                     |
| `docs/`     | Documentation only.                          |
| `chore/`    | Tooling, deps, internal refactor.            |
| `refactor/` | Internal restructure with no behavior change.|
| `test/`     | Test-only changes.                           |
| `ci/`       | CI / GitHub Actions changes.                 |

**Direct push to `main` is blocked by branch protection.** Open a PR for everything.

---

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/) for all commits. Prefix one of: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `perf`. Optional scope.

Examples:

```
feat(ingest): add Phoenix adapter
fix(replay): handle missing tool_cache entries gracefully
docs(README): add CI badge
chore(deps): bump pydantic to 2.7
refactor(score): extract bootstrap CI helper
ci: add CodeQL workflow
```

Subject ≤ 72 chars, imperative mood. Body wrapped at 72.

Use `BREAKING CHANGE:` footer for any change that breaks the public API or the runner contract:

```
feat(contract): rename ToolCache.lookup → ToolCache.get

BREAKING CHANGE: existing user runners that called `tool_cache.lookup(...)`
must update to `tool_cache.get(...)`.
```

---

## Pull requests

1. Open against `main`.
2. The PR template auto-loads. Fill every section - vague PRs get blocked.
3. CI runs: `lint`, `type`, `test (3.11)`, `test (3.12)`, `test (3.13)`, `pip-audit`, `bandit`, `gitleaks`. CodeQL runs separately via GitHub's Default Setup.
4. **All checks must pass before review.** Don't ask for review on a red PR.
5. Address review comments by pushing additional commits. **Don't force-push during review** - it makes incremental review hard. The maintainer will squash on merge.
6. After approval, the maintainer squash-merges. The PR title becomes the squashed commit message subject.

### What gets reviewed especially carefully

- **Architectural changes** (anything in `src/whatifd/contract/`, `src/whatifd/replay/`, `src/whatifd/score/`, `src/whatifd/diff/`) require a corresponding `DESIGN.md` update or a clear note about why the design is unchanged.
- **Report format changes** must preserve all 5 mandatory sections (Verdict / Stats / Replay validity / Baseline integrity / Evidence + judge rationale). Removing a section requires a major-version bump.
- **Public API changes** (anything users import from `whatif.*`) must be either additive or behind a major-version bump. Pre-1.0, breaking changes are allowed but documented in `CHANGELOG.md` under `### Changed (BREAKING)`.
- **CLI flag or exit-code changes** must update the README quickstart and any docs mentioning them.
- **Dependency additions** require justification - every dep is a maintenance and security cost.

---

## Adding a tracer adapter (`src/whatifd/ingest/`)

The adapter contract is small:

```python
class TracerAdapter(Protocol):
    """Read-only adapter for a tracer backend."""

    def fetch_traces(self, *, filter: str, limit: int) -> list[Trace]: ...
```

Tests should live at `tests/ingest/test_<adapter>.py` with two flavors:

- **Recorded fixtures** (always run in CI) - pre-captured trace JSON, no network.
- **Live tests** (skipped without env vars) - talk to the real backend, gated by `pytest.mark.integration` and an env-var presence check.

---

## Adding a scorer (`src/whatifd/score/`)

Wrap an existing eval framework rather than reimplementing scoring from scratch. A scorer receives a `ScoreCase` and returns a numeric score plus a rationale string. **The rationale is mandatory** because it surfaces in the report's Evidence section, and the report's unit of trust is *verdict + evidence + rationale*, not just numbers.

---

## Releasing (maintainers only)

1. Bump `__version__` in `src/whatifd/__init__.py` and `version` in `pyproject.toml - keep them in sync.
2. Move `[Unreleased]` items in `CHANGELOG.md` under a new `[X.Y.Z] - YYYY-MM-DD` heading.
3. Open a PR titled `chore(release): vX.Y.Z`.
4. After merge to `main`, tag and push:
   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```
5. The `release` workflow:
   - Builds sdist + wheel via `uv build`.
   - Publishes to PyPI via [Trusted Publishers](https://docs.pypi.org/trusted-publishers/) (no API tokens needed).
   - Creates a GitHub Release with auto-generated notes.

Versioning follows [SemVer](https://semver.org/). Pre-1.0, the minor version is allowed to introduce breaking changes - but each one is called out in `CHANGELOG.md`.

---

## Reporting security issues

**Don't open public issues for security vulnerabilities.** See [SECURITY.md](./SECURITY.md) for the disclosure policy.

---

## Code of conduct

This project follows the [Contributor Covenant 2.1](./CODE_OF_CONDUCT.md). Be excellent to each other.

---

## Manual GitHub configuration (maintainers, one-time)

These have to be set in GitHub's UI; they aren't part of the repo files.

### Branch protection - `main`

`Settings → Branches → Add branch protection rule → Branch name pattern: main`:

- ☑ Require a pull request before merging
  - ☑ Require approvals (1)
  - ☑ Dismiss stale pull request approvals when new commits are pushed
  - ☑ Require review from Code Owners
- ☑ Require status checks to pass before merging
  - ☑ Require branches to be up to date before merging
  - Required status checks: `lint`, `type`, `test (py3.11)`, `test (py3.12)`, `test (py3.13)`, `pip-audit`, `bandit`, `analyze (python)`
- ☑ Require conversation resolution before merging
- ☑ Require linear history
- ☐ Allow force pushes (leave unchecked)
- ☐ Allow deletions (leave unchecked)

### Pull request defaults

`Settings → General → Pull Requests`:

- ☑ Allow squash merging - **default merge strategy**
- ☑ Default to PR title for squashed commits
- ☐ Allow merge commits (uncheck)
- ☐ Allow rebase merging (uncheck - keep history simple)
- ☑ Always suggest updating pull request branches
- ☑ Automatically delete head branches

### Code security

`Settings → Code security and analysis`:

- ☑ Dependabot alerts
- ☑ Dependabot security updates
- ☑ Dependabot version updates (already configured via `.github/dependabot.yml`)
- ☑ Secret scanning
- ☑ Push protection (blocks pushes containing secrets)
- ☑ Private vulnerability reporting (enables the SECURITY.md GitHub Advisories link)
- ☑ Code scanning — CodeQL via GitHub's Default Setup (Settings → Code security → CodeQL → Default)

### PyPI Trusted Publisher (one-time, before first release)

After a manual first publish (or via PyPI's pending publisher flow):

- On `pypi.org` → `whatif` project → `Manage` → `Publishing` → `Add a new publisher`:
  - **Owner**: `victoralfred`
  - **Repository name**: `whatif`
  - **Workflow filename**: `release.yml`
  - **Environment**: `pypi`

For the *first* release, use [pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/) to bootstrap without uploading manually.
