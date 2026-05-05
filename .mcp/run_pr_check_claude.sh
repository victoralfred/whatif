#!/usr/bin/env bash
# MCP helper: run the Claude-based PR checker against a single PR.
#
# Usage:
#   ./run_pr_check_claude.sh <pr-number>
#
# Environment:
#   ANTHROPIC_API_KEY  (required) Anthropic API key. CLAUDE_API_KEY honored as
#                                 legacy fallback for backwards compatibility.
#   ANTHROPIC_MODEL    (optional) Model ID. Default: claude-haiku-4-5.
#                                 CLAUDE_MODEL honored as legacy fallback.
#   GH_TOKEN           (required) Github token; gh CLI must be configured.
#   PR_REVIEW_OUTPUT   (optional) Write structured verdict JSON to this path.
#
# Exit codes (passed through from tools/pr_checker.py):
#   0 = Ship              (no blocking issues)
#   1 = Don't Ship        (cardinal-rule violation, missing tests, etc.)
#   2 = Inconclusive      (setup/credentials/network/parse failure, or genuinely
#                          ambiguous PR that needs human judgment)
set -euo pipefail

PR_NUMBER="${1:-}"
if [[ -z "$PR_NUMBER" ]]; then
    echo "Usage: $0 <pr-number>" >&2
    exit 2
fi

# Honor legacy env names; export the canonical ones for the Python checker.
if [[ -z "${ANTHROPIC_API_KEY:-}" ]] && [[ -n "${CLAUDE_API_KEY:-}" ]]; then
    export ANTHROPIC_API_KEY="$CLAUDE_API_KEY"
fi
if [[ -z "${ANTHROPIC_MODEL:-}" ]] && [[ -n "${CLAUDE_MODEL:-}" ]]; then
    export ANTHROPIC_MODEL="$CLAUDE_MODEL"
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# Workspace for transient artifacts; cleaned on exit.
TMPDIR_WORK="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_WORK"' EXIT

PR_JSON="$TMPDIR_WORK/pr.json"
PR_DIFF="$TMPDIR_WORK/pr.diff"

# pr_checker.py needs both metadata AND the actual diff.
gh pr view "$PR_NUMBER" \
    --json number,title,body,author,baseRefName,headRefName,files \
    > "$PR_JSON"

gh pr diff "$PR_NUMBER" > "$PR_DIFF"

CHECKER_ARGS=(
    --pr-json "$PR_JSON"
    --diff-file "$PR_DIFF"
)
if [[ -n "${PR_REVIEW_OUTPUT:-}" ]]; then
    CHECKER_ARGS+=(--output-json "$PR_REVIEW_OUTPUT")
fi

# uv run if available so the anthropic extra resolves; falls back to python3.
if command -v uv &> /dev/null; then
    uv run python tools/pr_checker.py "${CHECKER_ARGS[@]}"
else
    python3 tools/pr_checker.py "${CHECKER_ARGS[@]}"
fi
