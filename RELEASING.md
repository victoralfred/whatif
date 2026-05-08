# Releasing whatifd

Runbook for cutting a release. The release workflow is fully automated via PyPI Trusted Publishing — pushing a `v*.*.*` tag triggers `.github/workflows/release.yml`, which builds all three distributions, publishes each to its own PyPI project, and creates a GitHub Release with auto-generated notes.

## One-time setup (per maintainer / per project)

### 1. Register Trusted Publishers on PyPI

For each of the three packages (`whatifd`, `whatifd-langfuse`, `whatifd-inspect-ai`), add a Trusted Publisher on PyPI. For an unpublished package, use the "Pending Publisher" form at https://pypi.org/manage/account/publishing/. For an already-published package, go to that project's `Settings → Publishing`.

| Field | Value |
|---|---|
| Owner | `victoralfred` |
| Repository | `whatifd` |
| Workflow filename | `release.yml` |
| Environment | `pypi-whatifd` / `pypi-whatifd-langfuse` / `pypi-whatifd-inspect-ai` (match the per-job `environment.name` in `release.yml`) |

The environment name MUST match exactly. PyPI's OIDC verifier checks `repository`, `workflow`, AND `environment` claims; mismatch on any of the three rejects the publish.

### 2. (Optional) Configure GitHub environments for additional gating

If you want manual approval before each PyPI publish, create matching environments under `Repo Settings → Environments` and add required reviewers. Without this, the workflow runs end-to-end on tag push.

### 3. Schema URL hosting

The `ReportV01.schema_uri` field is `https://whatif.codes/schema/report/v0.1.json`. Before announcing the release, deploy `src/whatifd/report/schema/v0.1.schema.json` to that URL. Any static-host works (Cloudflare Pages, GitHub Pages on a `gh-pages` branch, S3, etc.). Until deployed, consumers can validate against the in-repo schema; the URI just won't dereference.

## Per-release checklist

For the v0.1.0 release (or any subsequent release; substitute the version):

### 1. Pre-flight (on a release-prep branch)

- [ ] All three `pyproject.toml` versions match the target tag (root + both adapter packages)
- [ ] `Development Status` classifier is appropriate (`3 - Alpha` for v0.1.x; bump to `4 - Beta` at v0.5+)
- [ ] `CHANGELOG.md` `[Unreleased]` block promoted to `[0.1.0] - YYYY-MM-DD`; a fresh `[Unreleased]` header added
- [ ] CHANGELOG link footer updated (`[Unreleased]` → `[0.1.0]` plus a fresh `[Unreleased]` line)
- [ ] `uv lock` is up-to-date (`uv lock` with no diff)
- [ ] Full test suite passes: `uv run pytest tests/ packages/ -q`
- [ ] mypy + ruff clean: `uv run mypy src && uv run ruff check . && uv run ruff format --check .`
- [ ] Schema is up-to-date: `uv run python scripts/generate_schema.py` produces no diff
- [ ] PR landed on `main`

### 2. Tag and push

```bash
git checkout main
git pull
git tag v0.1.0
git push origin v0.1.0
```

The push triggers `.github/workflows/release.yml`. Monitor at `https://github.com/victoralfred/whatifd/actions`.

### 3. Verify

After the workflow completes:

- [ ] All three packages visible at `https://pypi.org/project/whatifd/0.1.0/` (and `/whatifd-langfuse/`, `/whatifd-inspect-ai/`)
- [ ] GitHub Release created at `https://github.com/victoralfred/whatifd/releases/tag/v0.1.0` with auto-generated notes
- [ ] `pip install whatifd whatifd-langfuse whatifd-inspect-ai` in a clean venv resolves cleanly
- [ ] `whatif --help` works after install
- [ ] Schema URL `https://whatif.codes/schema/report/v0.1.json` resolves (post hosting deploy)

### 4. Announce

- Update `README.md` Status table if the version-roadmap claim shifts
- Open a tracking issue for the next milestone (v0.2)

## Failure modes

### Trusted Publisher rejection

> `OIDC token claim 'environment' did not match expected value`

The job's `environment.name` doesn't match what's configured on PyPI for that project. Fix one or the other so they align exactly.

### Build failure on a single package

The build job builds all three in sequence; a failure in one fails the whole tag's release. Fix and either delete + re-tag (if no PyPI uploads happened) or bump to the next patch version (if any package already uploaded — PyPI does NOT permit overwriting a published version).

### Mid-release partial upload

If `whatifd` publishes but one of the adapters fails, the resulting state is inconsistent (e.g., users can install `whatifd` but the adapters reference a now-orphaned version). The recovery is:

1. Bump the two unpublished packages to the next patch (e.g., `0.1.1`).
2. Update their `dependencies` to require `whatifd>=0.1.0`.
3. Tag `v0.1.1` and re-run the workflow with only the adapter publish jobs (or accept that `whatifd 0.1.1` will be a no-op republish and let it run).

The cleanest prevention is to test the workflow on a pre-release tag (e.g., `v0.1.0a1`) against PyPI Test Index first. Add `repository-url: https://test.pypi.org/legacy/` to each `pypa/gh-action-pypi-publish` step in a fork of the workflow if you want to dry-run.

## Hot-fix releases

For `0.1.x` patches:

1. Branch off `main`, fix
2. Bump version in all three `pyproject.toml` files
3. Add `[0.1.x] - YYYY-MM-DD` block to CHANGELOG
4. Open + merge PR
5. Tag `v0.1.x` and push

The schema URI is stable across `v0.1.x` patches; do NOT regenerate the schema unless the bug is in the schema itself (and even then, bump to v0.2 for any breaking change).

## v0.2+ migrations

When the wire format changes (`schema_version: "v0.2"`), additional steps:

1. New schema file at `src/whatifd/report/schema/v0.2.schema.json`; old `v0.1.schema.json` kept (consumers still validate older reports against the v0.1 schema)
2. `whatif report-migrate` body wired to project v0.1 reports forward
3. Schema URL deployed at `https://whatif.codes/schema/report/v0.2.json` BEFORE the tag push (otherwise `schema_uri` resolves to a 404 in the immediate post-release window)
4. CHANGELOG `[0.2.0]` block calls out every breaking change explicitly under `### Changed (BREAKING)`
