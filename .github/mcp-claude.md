# MCP server: Claude PR checker

Purpose: run an automated PR review against the whatif project's cardinal
rules using the Anthropic SDK. The MCP server invokes
`./.mcp/run_pr_check_claude.sh <pr-number>` and interprets its exit code.

## Environment variables

Required:
- `ANTHROPIC_API_KEY` — Anthropic API key. (`CLAUDE_API_KEY` is honored as a
  legacy fallback by the wrapper script.)
- `GH_TOKEN` — GitHub token with PR read access; `gh` CLI must be configured.

Optional:
- `ANTHROPIC_MODEL` — model ID. Default: `claude-haiku-4-5` (fast, cheap; sufficient
  for first-pass review). Override to `claude-sonnet-4-6` or `claude-opus-4-7` for
  deeper review on high-stakes PRs. (`CLAUDE_MODEL` honored as legacy fallback.)
- `PR_REVIEW_OUTPUT` — path to write structured verdict JSON for downstream tooling.

## Exit codes (matching whatif's verdict semantics)

- `0` — Ship: no blocking issues; PR aligns with cardinal rules.
- `1` — Don't Ship: at least one cardinal-rule violation, missing tests for a
  behavioral change, or sensitive data leaked into the diff.
- `2` — Inconclusive: setup/credentials/network/parse failure, or genuinely
  ambiguous PR that needs human judgment.

The exit-code semantics deliberately match `whatif fork`'s own exit codes —
the PR checker is a doctrine-aligned tool reviewing a doctrine-aligned project.

## Suggested MCP behavior

- Run on `pull_request` events: `opened`, `synchronize`, `reopened`.
- On exit `0`: post the verdict summary as a non-blocking PR comment.
- On exit `1`: post the verdict as a PR comment AND fail the check, surfacing the
  blocking-issues list.
- On exit `2`: post the verdict as a PR comment with a "needs human review" note;
  do NOT auto-block the merge — inconclusive ≠ failure.

## Implementation notes

- The actual review logic lives in `tools/pr_checker.py`. It uses the
  `anthropic` Python SDK (already in `pyproject.toml` as the `anthropic`
  optional extra).
- The wrapper script `./.mcp/run_pr_check_claude.sh` fetches both PR metadata
  (`gh pr view --json title,body,...`) AND the diff (`gh pr diff`), and
  passes both to `tools/pr_checker.py`.
- The system prompt in `tools/pr_checker.py` explicitly enumerates the ten
  cardinal rules from `.claude/skills/whatif-design/SKILL.md`. When a cardinal
  rule changes, update the prompt in lockstep.
- The reviewer is advisory; it does not replace human review. It's a first-pass
  filter that catches obvious doctrine violations before maintainers look.
