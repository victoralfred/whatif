# whatifd-fork action

Composite GitHub Action wrapping `whatifd fork --config <path>`. Phase I of
the v0.2 roadmap.

The CLI is already CI-ready (config-file driven, structured exit codes,
deterministic artifacts under `./reports/`); this Action saves the
boilerplate of capturing the artifacts, posting the verdict to the PR, and
mapping the exit code to a status annotation.

## Usage

```yaml
# .github/workflows/whatifd-pr-check.yml
name: whatifd PR verdict

on:
  pull_request:
    branches: [main]

permissions:
  contents: read
  pull-requests: write   # required for the PR comment

jobs:
  whatifd:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up uv
        uses: astral-sh/setup-uv@v7
        with:
          python-version: "3.12"

      - name: Install whatifd
        run: uv pip install whatifd whatifd-langfuse whatifd-inspect-ai

      - name: Run whatifd fork
        uses: ./.github/actions/whatifd-fork
        with:
          config: whatifd.config.yaml
          # Optional inputs (defaults shown):
          # profile: ""
          # comment-on-pr: "true"
          # fail-on-dont-ship: "true"
          # github-token: ${{ github.token }}
        env:
          # Adapter credentials per cfg.source / cfg.scorer.
          LANGFUSE_HOST: ${{ secrets.LANGFUSE_HOST }}
          LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
          LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

## Inputs

| Input | Default | Description |
|---|---|---|
| `config` | `whatifd.config.yaml` | Path to the whatifd config file. |
| `profile` | `""` | Reporting profile override (must match `cfg.reporting.profile`; `forensic` requires the acknowledgment block per cardinal #7). |
| `comment-on-pr` | `"true"` | Post the rendered Markdown verdict as a PR comment on `pull_request` events. |
| `github-token` | `${{ github.token }}` | Token used by `gh pr comment`. Override with a PAT to author from a bot account. |
| `fail-on-dont-ship` | `"true"` | Fail the workflow when the verdict is Don't Ship (1) or Inconclusive / setup failure (2). Set to `"false"` to expose the verdict as an output and let downstream steps decide. |

## Outputs

| Output | Description |
|---|---|
| `verdict` | `ship` / `dont_ship` / `inconclusive`. Mirrors the CLI exit code. |
| `exit-code` | Raw exit code: `0` / `1` / `2`. |
| `report-json` | Path to the emitted `ReportV01` JSON file. |
| `report-md` | Path to the emitted Markdown verdict file. |

## Permissions

When `comment-on-pr: true` (the default) the action posts to the PR via
`gh pr comment`. The workflow that uses this action must grant
`pull-requests: write` on the `permissions:` block, otherwise the comment
step fails with a 403.

## Cardinal alignment

- **#1 (failure-as-data):** the action surfaces every outcome as a
  GitHub annotation (`::notice` / `::warning` / `::error`) carrying the
  verdict string. No stack traces leak through the workflow log unless the
  CLI itself crashes (which would be a real bug, not a verdict).
- **#2 (trust floor):** floor-failure Inconclusives produce exit 2,
  which the action maps to `verdict=inconclusive`. The same workflow
  behavior fires whether the floor failed or the policy fired — both are
  "not Ship and not a clean reject" from the CI gate's perspective.
- **#7 (two-affirmation):** when `profile: forensic` is set on the
  action, the CLI's two-affirmation check still fires against the
  config's `forensic_acknowledgment` block. The action does NOT bypass
  cardinal #7.

## Security: pinning third-party actions

The example workflow above uses `astral-sh/setup-uv@v7` (version-tag
pinning) to match the whatifd repo's own CI convention. For
**security-hardened production workflows**, GitHub
[recommends pinning to a commit SHA](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions#using-third-party-actions)
so a compromised tag cannot silently swap the action's source.
Operators adopting this Action in production should replace each
`uses: ...@v7` with `uses: ...@<sha>  # v7.x.y` before checking in.
A repo-wide SHA-pin migration is tracked separately and applies to
the whatifd repo's own workflows alongside the example.

## What this Action does NOT do

- Manage adapter credentials. Set `LANGFUSE_*` / `ANTHROPIC_API_KEY` in
  the workflow's `env:` from your repo secrets.
- Install whatifd. Use a separate `pip install` step (see usage example);
  the action assumes `whatifd` is on `$PATH`.
- Render or annotate diff against a previous report. Use `whatifd diff`
  in a downstream step if you want a regression-vs-baseline view.

## Status

| Surface | v0.2 |
|---|---|
| Composite action wrapping `whatifd fork` | ✅ |
| PR comment with rendered verdict | ✅ |
| Status annotation (notice / warning / error) | ✅ |
| Exit-code mapping → `verdict` output | ✅ |
| Marketplace publication (separate repo) | ❌ — v0.3+ |
| `whatifd diff` regression workflow | ❌ — v0.3+ |
