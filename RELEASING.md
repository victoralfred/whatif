# Releasing whatifd

Runbook for cutting a release. The release workflow is fully automated via PyPI Trusted Publishing — pushing a `v*.*.*` tag triggers `.github/workflows/release.yml`, which builds all four distributions, publishes each to its own PyPI project, and creates a GitHub Release with auto-generated notes.

## One-time setup (per maintainer / per project)

### 1. Register Trusted Publishers on PyPI

For each of the four packages (`whatifd`, `whatifd-langfuse`, `whatifd-inspect-ai`, `whatifd-phoenix`), add a Trusted Publisher on PyPI. For an unpublished package, use the "Pending Publisher" form at https://pypi.org/manage/account/publishing/. For an already-published package, go to that project's `Settings → Publishing`.

| Field | Value |
|---|---|
| Owner | `victoralfred` |
| Repository | `whatifd` |
| Workflow filename | `release.yml` |
| Environment | `pypi-whatifd` / `pypi-whatifd-langfuse` / `pypi-whatifd-inspect-ai` / `pypi-whatifd-phoenix` (match the per-job `environment.name` in `release.yml`) |

The environment name MUST match exactly. PyPI's OIDC verifier checks `repository`, `workflow`, AND `environment` claims; mismatch on any of the three rejects the publish.

### 2. (Optional) Configure GitHub environments for additional gating

If you want manual approval before each PyPI publish, create matching environments under `Repo Settings → Environments` and add required reviewers. Without this, the workflow runs end-to-end on tag push.

### 3. Schema URL hosting (load-bearing, NOT optional)

The `ReportV01.schema_uri` field stamped into every produced report points to `https://whatif.codes/schema/report/vX.Y.json`, where X.Y is the schema version active in the producer (currently v0.2; v0.1 is frozen for backward-compat consumers). Before announcing a release, deploy each shipped schema file (`src/whatifd/report/schema/v0.1.schema.json`, `v0.2.schema.json`, and any future versions) to its corresponding URL. Any static-host works (Cloudflare Pages, GitHub Pages on a `gh-pages` branch, S3, etc.). A 404 silently breaks any consumer that fetches the schema for validation — the per-release checklist pins URL resolution as a required verification step for every shipped schema version, not just the newest.

## Per-release checklist

For any release (substitute the target version `vX.Y.Z` throughout):

### 1. Pre-flight (on a release-prep branch)

- [ ] All four `pyproject.toml` versions match the target tag (root + three adapter packages); `tests/unit/whatifd/test_version_parity.py` pins this
- [ ] `Development Status` classifier is appropriate (`3 - Alpha` through v0.4.x; bump to `4 - Beta` at v0.5+)
- [ ] `CHANGELOG.md` `[Unreleased]` block promoted to `[X.Y.Z] - YYYY-MM-DD`; a fresh `[Unreleased]` header added
- [ ] CHANGELOG link footer updated (`[Unreleased]` → `[X.Y.Z]` plus a fresh `[Unreleased]` line)
- [ ] `uv lock` is up-to-date (`uv lock` with no diff)
- [ ] Full test suite passes: `uv run pytest tests/ packages/ -q`
- [ ] mypy + ruff clean: `uv run mypy src && uv run ruff check . && uv run ruff format --check .`
- [ ] Schema is up-to-date: `uv run python scripts/generate_schema.py` produces no diff
- [ ] PR landed on `main`
- [ ] **TestPyPI dry-run completed against a `vX.Y.Zrc1` pre-release tag** (see "Failure modes → Cleanest prevention" below). Skipping this is permitted only for hot-fix patches where the workflow itself hasn't changed since the last successful release; a release that touches `release.yml`, action versions, or environment names MUST dry-run first.

### 2. Tag and push

```bash
git checkout main
git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

The push triggers `.github/workflows/release.yml`. Monitor at `https://github.com/victoralfred/whatifd/actions`.

### 3. Verify

After the workflow completes:

- [ ] All four packages visible at `https://pypi.org/project/whatifd/<version>/` (and `/whatifd-langfuse/`, `/whatifd-inspect-ai/`, `/whatifd-phoenix/`)
- [ ] GitHub Release created at `https://github.com/victoralfred/whatifd/releases/tag/vX.Y.Z` with auto-generated notes
- [ ] `pip install whatifd whatifd-langfuse whatifd-inspect-ai whatifd-phoenix` in a clean venv resolves cleanly
- [ ] `whatifd --help` works after install
- [ ] **Every shipped schema URL resolves with HTTP 200**: `https://whatif.codes/schema/report/v0.1.json` AND `https://whatif.codes/schema/report/v0.2.json` (and any future versions). The active producer's `schema_uri` field points to the newest; older versions remain reachable for consumers still validating archived reports. If any URL 404s post-tag-push, deploy the corresponding `src/whatifd/report/schema/vX.Y.schema.json` file to the static host backing `whatif.codes` BEFORE announcing the release. Load-bearing post-release step, not optional.

### 4. Announce

- Update `README.md` Status table if the version-roadmap claim shifts
- Open a tracking issue for the next milestone (v0.2)

## Failure modes

### Trusted Publisher rejection

> `OIDC token claim 'environment' did not match expected value`

The job's `environment.name` doesn't match what's configured on PyPI for that project. Fix one or the other so they align exactly.

### Build failure on a single package

The build job builds all four in sequence; a failure in one fails the whole tag's release. Fix and either delete + re-tag (if no PyPI uploads happened) or bump to the next patch version (if any package already uploaded — PyPI does NOT permit overwriting a published version).

### Mid-release partial upload

If `whatifd` publishes but one of the adapters fails, the resulting state is inconsistent (e.g., users can install `whatifd` but the adapters reference a now-orphaned version). The recovery is:

1. **Bump ALL four packages to the next patch** (e.g., `0.2.1` everywhere — root + three adapters). Workspace version parity is a release invariant that operator-facing docs (README version table, CHANGELOG, schema URI mapping) depend on; `tests/unit/whatifd/test_version_parity.py` pins it. Skipping any bump orphans that package against the others, breaking the "one workspace, one version" mental model.
2. Update the adapters' `dependencies` to require `whatifd==<new-version>` (or `>=` if you don't need strict parity).
3. Tag `vX.Y.Z` and re-run the workflow. PyPI rejects republishing a version, so the bump is necessary even if no source changed. Adapters publish after the root succeeds.

**Cleanest prevention: TestPyPI dry-run on a pre-release tag.** Before pushing the real `vX.Y.Z` tag, push `vX.Y.ZrcN` (or any PEP 440 pre-release suffix — `a1`, `b1`, `rc1` all work) against TestPyPI first. This proves the entire publish path end-to-end without committing to a permanent PyPI version.

> **Note on workflow shape.** The TestPyPI route is intentionally **manual and ephemeral** — there's no committed `release-rc.yml` or auto-detected pre-release branch in `.github/workflows/`. Each dry-run is a temporary local edit on a throwaway branch (`release-testpypi-rc`-style), not a permanent surface that future maintainers need to keep in sync. This keeps the canonical release path single-source (`release.yml` → PyPI) while preserving the option for ad-hoc dry-runs.

Steps:
1. Configure a parallel set of TestPyPI Trusted Publishers at https://test.pypi.org/manage/account/publishing/ — same owner / repo / workflow / environment-name claims; `test.pypi.org` is a separate registry from `pypi.org` so the publishers don't collide.
2. In a temporary workflow branch, point each `pypa/gh-action-pypi-publish` step at TestPyPI by adding `repository-url: https://test.pypi.org/legacy/`.
3. Tag and push `vX.Y.ZrcN` (e.g., `v0.2.0rc1`). Verify all four packages appear at `https://test.pypi.org/project/whatifd/X.Y.ZrcN/` etc.
4. `pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ whatifd==X.Y.ZrcN whatifd-langfuse==X.Y.ZrcN whatifd-inspect-ai==X.Y.ZrcN whatifd-phoenix==X.Y.ZrcN` in a clean venv.
5. If everything resolves and `whatifd --help` works, revert the workflow back to PyPI proper, push the real `vX.Y.Z` tag.

The pre-release tag remains on TestPyPI and on a GitHub Release; you can delete the GitHub Release if you want to keep the public release notes focused on the real tag.

## Supply-chain hardening

The release workflow grants `id-token: write` to four publish jobs so PyPI can verify the OIDC claim. The action that *consumes* that token, `pypa/gh-action-pypi-publish`, is currently pinned to `release/v1` (PyPA's recommended floating ref). For maximum hardening on a sensitive release, pin to a full commit SHA before tagging:

1. Find the latest commit SHA for the release on https://github.com/pypa/gh-action-pypi-publish/releases.
2. Replace each `pypa/gh-action-pypi-publish@release/v1` line in `.github/workflows/release.yml` with `pypa/gh-action-pypi-publish@<full-40-char-sha> # v1.X.Y`.
3. Land the SHA-pin as part of the release-prep PR (or a hot-fix PR immediately before tagging).

The github-published `actions/checkout`, `actions/upload-artifact`, `actions/download-artifact`, and `astral-sh/setup-uv` are pinned to major-version tags. SHA-pinning these too is defensible but lower-priority — they don't handle the OIDC token. If a future release wants belt-and-suspenders, the same pattern applies to all four.

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
2. `whatifd report-migrate` body wired to project v0.1 reports forward
3. Schema URL deployed at `https://whatif.codes/schema/report/v0.2.json` BEFORE the tag push (otherwise `schema_uri` resolves to a 404 in the immediate post-release window)
4. CHANGELOG `[0.2.0]` block calls out every breaking change explicitly under `### Changed (BREAKING)`
