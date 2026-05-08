#!/usr/bin/env bash
# scripts/run-skill-benchmark.sh
#
# Layer 3 of whatifd-design skill instrumentation.
# Runs each prompt in tests/skill-benchmarks/prompts.json through Claude Code
# in non-interactive mode and saves the responses for grading.
#
# Requires:
#   - jq
#   - claude (Claude Code CLI) with -p (print/non-interactive) mode
#
# Usage:
#   ./scripts/run-skill-benchmark.sh
#   ./scripts/run-skill-benchmark.sh --filter cardinal-rule
#   ./scripts/run-skill-benchmark.sh --id trust-floor-bypass

set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PROMPTS_FILE="$PROJECT_ROOT/tests/skill-benchmarks/prompts.json"
RUN_DATE="$(date +%Y-%m-%d)"
RUN_TIME="$(date +%H%M%S)"
RESULTS_DIR="$PROJECT_ROOT/tests/skill-benchmarks/results/${RUN_DATE}_${RUN_TIME}"

# --- Argument parsing ---
FILTER=""
SINGLE_ID=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --filter)
            FILTER="$2"
            shift 2
            ;;
        --id)
            SINGLE_ID="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [--filter <category>] [--id <prompt-id>]"
            echo ""
            echo "Options:"
            echo "  --filter <category>  Run only prompts matching category (e.g., 'cardinal-rule')"
            echo "  --id <prompt-id>     Run only the prompt with this ID"
            echo "  --help               Show this help"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# --- Preflight ---
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed."
    echo "Install: https://stedolan.github.io/jq/download/"
    exit 1
fi

if ! command -v claude &> /dev/null; then
    echo "Error: 'claude' CLI not found in PATH."
    echo "Install Claude Code first, or adjust this script if your CLI"
    echo "uses a different command name."
    exit 1
fi

if [ ! -f "$PROMPTS_FILE" ]; then
    echo "Error: $PROMPTS_FILE not found."
    exit 1
fi

mkdir -p "$RESULTS_DIR"

# --- Build filter expression ---
if [ -n "$SINGLE_ID" ]; then
    FILTER_EXPR=".evaluations[] | select(.id == \"$SINGLE_ID\")"
elif [ -n "$FILTER" ]; then
    FILTER_EXPR=".evaluations[] | select(.category == \"$FILTER\")"
else
    FILTER_EXPR=".evaluations[]"
fi

# --- Get list of prompt IDs to run ---
ids=$(jq -r "$FILTER_EXPR | .id" "$PROMPTS_FILE")

if [ -z "$ids" ]; then
    echo "No prompts matched filter."
    exit 1
fi

count=$(echo "$ids" | wc -l | tr -d ' ')
echo "=== Skill benchmark run ==="
echo "Date:    $RUN_DATE $RUN_TIME"
echo "Prompts: $count"
echo "Output:  $RESULTS_DIR"
echo ""

# --- Run each prompt ---
i=0
for id in $ids; do
    i=$((i + 1))
    prompt=$(jq -r "$FILTER_EXPR | select(.id == \"$id\") | .prompt" "$PROMPTS_FILE")
    category=$(jq -r "$FILTER_EXPR | select(.id == \"$id\") | .category" "$PROMPTS_FILE")

    echo "[$i/$count] $id ($category)"
    echo "  Prompt: $(echo "$prompt" | head -c 80)..."

    output_file="$RESULTS_DIR/${id}.txt"

    # Run Claude Code in print mode. Redirect stderr to capture errors too.
    # Adjust the claude invocation if your version uses different flags.
    if claude -p "$prompt" > "$output_file" 2>&1; then
        echo "  Saved: $output_file"
    else
        echo "  ERROR: claude returned non-zero exit; output saved anyway"
    fi
    echo ""
done

# --- Save run metadata ---
cat > "$RESULTS_DIR/run-metadata.json" <<EOF
{
  "run_date": "$RUN_DATE",
  "run_time": "$RUN_TIME",
  "prompt_count": $count,
  "filter": "${FILTER:-none}",
  "single_id": "${SINGLE_ID:-none}",
  "prompts_file_sha": "$(shasum -a 256 "$PROMPTS_FILE" | cut -c1-16)"
}
EOF

echo "=== Run complete ==="
echo "Results: $RESULTS_DIR"
echo ""
echo "Next: grade the results"
echo "  ./scripts/grade-skill-benchmark.sh $RESULTS_DIR"
