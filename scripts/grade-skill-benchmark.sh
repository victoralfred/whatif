#!/usr/bin/env bash
# scripts/grade-skill-benchmark.sh
#
# Layer 3 of whatifd-design skill instrumentation.
# Auto-checks each benchmark result and produces a grading template
# for manual review.
#
# Usage:
#   ./scripts/grade-skill-benchmark.sh tests/skill-benchmarks/results/2026-05-04_143022

set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
PROMPTS_FILE="$PROJECT_ROOT/tests/skill-benchmarks/prompts.json"

RESULTS_DIR="${1:?Usage: $0 <results-dir>}"

if [ ! -d "$RESULTS_DIR" ]; then
    echo "Error: $RESULTS_DIR is not a directory."
    exit 1
fi

if [ ! -f "$PROMPTS_FILE" ]; then
    echo "Error: $PROMPTS_FILE not found."
    exit 1
fi

GRADE_FILE="$RESULTS_DIR/grades.md"

# --- Header ---
{
    echo "# Benchmark grades: $(basename "$RESULTS_DIR")"
    echo ""
    echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo ""
    echo "Auto-checks are scriptable signals. Manual review is required for"
    echo "qualitative grading. Fill in the manual sections below, then commit"
    echo "this file."
    echo ""
    echo "---"
    echo ""
} > "$GRADE_FILE"

# --- Per-prompt grading ---
count=$(jq '.evaluations | length' "$PROMPTS_FILE")
auto_pass=0
auto_fail=0

for i in $(seq 0 $((count - 1))); do
    id=$(jq -r ".evaluations[$i].id" "$PROMPTS_FILE")
    category=$(jq -r ".evaluations[$i].category" "$PROMPTS_FILE")
    prompt=$(jq -r ".evaluations[$i].prompt" "$PROMPTS_FILE")
    expected=$(jq -r ".evaluations[$i].expected_behavior" "$PROMPTS_FILE")
    should_read=$(jq -r ".evaluations[$i].should_read | join(\", \")" "$PROMPTS_FILE")
    should_cite_rule=$(jq -r ".evaluations[$i].should_cite_rule" "$PROMPTS_FILE")
    should_refuse=$(jq -r ".evaluations[$i].should_refuse" "$PROMPTS_FILE")
    output_file="$RESULTS_DIR/${id}.txt"

    {
        echo "## $id"
        echo ""
        echo "**Category:** \`$category\`"
        echo ""
        echo "**Prompt:**"
        echo ""
        echo "> $prompt"
        echo ""
        echo "**Expected behavior:** $expected"
        echo ""
        echo "**Should read:** ${should_read:-(none)}"
        echo "**Should cite rule #:** $should_cite_rule"
        echo "**Should refuse:** $should_refuse"
        echo ""
        echo "### Auto-checks"
        echo ""
    } >> "$GRADE_FILE"

    if [ ! -f "$output_file" ]; then
        echo "- ❌ No output file found at \`$output_file\`" >> "$GRADE_FILE"
        auto_fail=$((auto_fail + 1))
        echo "" >> "$GRADE_FILE"
        echo "### Manual review" >> "$GRADE_FILE"
        echo "" >> "$GRADE_FILE"
        echo "- [ ] PASS / [ ] PARTIAL / [ ] FAIL" >> "$GRADE_FILE"
        echo "- **Notes:**" >> "$GRADE_FILE"
        echo "" >> "$GRADE_FILE"
        echo "---" >> "$GRADE_FILE"
        echo "" >> "$GRADE_FILE"
        continue
    fi

    # Check 1: Did the agent reference the right files?
    file_check_passed=true
    has_should_read=$(jq -r ".evaluations[$i].should_read | length" "$PROMPTS_FILE")
    if [ "$has_should_read" -gt 0 ]; then
        for ref in $(jq -r ".evaluations[$i].should_read[]" "$PROMPTS_FILE"); do
            if grep -qF "$ref" "$output_file"; then
                echo "- ✅ Referenced \`$ref\`" >> "$GRADE_FILE"
            else
                echo "- ❌ Did NOT reference \`$ref\` (expected)" >> "$GRADE_FILE"
                file_check_passed=false
            fi
        done
    else
        # Negative test: should NOT reference any whatifd-design files
        if grep -qE "references/(doctrine|type-model|enforcement|contracts|cascade-catalog|practices|phases|walkthroughs)\.md" "$output_file"; then
            echo "- ❌ Referenced whatifd-design files (negative test: should not have)" >> "$GRADE_FILE"
            file_check_passed=false
        else
            echo "- ✅ Did not reference whatifd-design files (negative test passes)" >> "$GRADE_FILE"
        fi
    fi

    # Check 2: Did the agent cite the expected cardinal rule?
    rule_check_passed=true
    if [ "$should_cite_rule" != "null" ]; then
        if grep -qiE "rule #?$should_cite_rule\b|cardinal rule $should_cite_rule\b|#$should_cite_rule\b.*orchestration|#$should_cite_rule\b.*compute|#$should_cite_rule\b.*floor|#$should_cite_rule\b.*sensitive" "$output_file"; then
            echo "- ✅ Cited cardinal rule #$should_cite_rule" >> "$GRADE_FILE"
        else
            echo "- ❌ Did NOT cite cardinal rule #$should_cite_rule (expected)" >> "$GRADE_FILE"
            rule_check_passed=false
        fi
    fi

    # Check 3: Refusal pattern
    refusal_check_passed=true
    if [ "$should_refuse" = "true" ]; then
        # Heuristic: refusal involves words like "cannot", "should not", "won't",
        # "refuse", "decline", "reject", or "violates"
        if grep -qiE "\b(cannot|won't|will not|should not|refuse|decline|reject|violates|conflicts with|breaks|prevents)\b" "$output_file"; then
            echo "- ✅ Output contains refusal language" >> "$GRADE_FILE"
        else
            echo "- ⚠️  No refusal language detected (expected refusal)" >> "$GRADE_FILE"
            refusal_check_passed=false
        fi
    fi

    # Tally
    if $file_check_passed && $rule_check_passed && $refusal_check_passed; then
        auto_pass=$((auto_pass + 1))
        auto_status="auto-PASS"
    else
        auto_fail=$((auto_fail + 1))
        auto_status="auto-FAIL or PARTIAL"
    fi

    {
        echo ""
        echo "**Auto-check status:** $auto_status"
        echo ""
        echo "### Manual review"
        echo ""
        echo "Read the actual output at \`${id}.txt\` and grade qualitatively."
        echo "Auto-checks are necessary but not sufficient — the agent might"
        echo "name the right file but apply the wrong reasoning, or refuse for"
        echo "the wrong reason."
        echo ""
        echo "- [ ] PASS — output matches expected behavior"
        echo "- [ ] PARTIAL — partial match (e.g., right rule but wrong reasoning)"
        echo "- [ ] FAIL — output does not match expected behavior"
        echo ""
        echo "**Notes:**"
        echo ""
        echo "---"
        echo ""
    } >> "$GRADE_FILE"
done

# --- Summary ---
{
    echo "## Summary"
    echo ""
    echo "- Total prompts: $count"
    echo "- Auto-checks PASS: $auto_pass"
    echo "- Auto-checks FAIL or PARTIAL: $auto_fail"
    echo ""
    echo "Note: auto-checks are heuristic. The manual review above is the source"
    echo "of truth. After completing manual review, count [x] PASS / [x] PARTIAL /"
    echo "[x] FAIL marks to get the real pass rate."
    echo ""
    echo "Reasonable pass-rate target for a healthy skill: ≥90% PASS, with"
    echo "PARTIAL only on edge cases."
} >> "$GRADE_FILE"

echo "=== Grading complete ==="
echo "Auto-checks: $auto_pass passed, $auto_fail failed/partial (of $count)"
echo "Grade file:  $GRADE_FILE"
echo ""
echo "Next: open the grade file and fill in the manual review sections."
