#!/usr/bin/env bash
# scripts/collect-transcripts.sh
#
# Layer 1 of whatifd-design skill instrumentation.
# Copies Claude Code session logs from ~/.claude/projects/<project-key>/
# into docs/sessions/raw/ for analysis.
#
# Run after each significant session, or wire into a post-commit hook.

set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PROJECT_KEY="$(echo "$PROJECT_ROOT" | tr '/' '-')"
CLAUDE_LOGS="${CLAUDE_CODE_LOG_DIR:-$HOME/.claude/projects/$PROJECT_KEY}"
DEST="$PROJECT_ROOT/docs/sessions/raw"

mkdir -p "$DEST"

if [ ! -d "$CLAUDE_LOGS" ]; then
    echo "No Claude Code logs found at $CLAUDE_LOGS"
    echo ""
    echo "Possible reasons:"
    echo "  - You haven't run a Claude Code session in this project yet."
    echo "  - Your Claude Code version stores logs elsewhere."
    echo ""
    echo "Try locating session logs with:"
    echo "  find ~ -name '*.jsonl' -path '*claude*' 2>/dev/null | head"
    echo ""
    echo "Then either:"
    echo "  - Symlink the discovered directory to $CLAUDE_LOGS, or"
    echo "  - Set CLAUDE_CODE_LOG_DIR=<path> and re-run this script."
    exit 1
fi

copied=0
skipped=0

shopt -s nullglob
for log in "$CLAUDE_LOGS"/*.jsonl; do
    fname="$(basename "$log")"
    dest_file="$DEST/$fname"
    if [ ! -f "$dest_file" ] || [ "$log" -nt "$dest_file" ]; then
        cp "$log" "$dest_file"
        copied=$((copied + 1))
    else
        skipped=$((skipped + 1))
    fi
done
shopt -u nullglob

total=$(find "$DEST" -maxdepth 1 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')

echo "=== Transcript collection ==="
echo "Source:  $CLAUDE_LOGS"
echo "Dest:    $DEST"
echo "Copied:  $copied new, $skipped already up-to-date"
echo "Total:   $total transcripts"

if [ "$total" -eq 0 ]; then
    echo ""
    echo "No transcripts found. Either no sessions have been run yet, or"
    echo "the source directory was empty."
fi
