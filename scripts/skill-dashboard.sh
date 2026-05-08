#!/usr/bin/env bash
# scripts/skill-dashboard.sh
#
# Layer 4 of whatifd-design skill instrumentation.
# Aggregates session telemetry (Layer 2) and benchmark results (Layer 3)
# into a single Markdown dashboard.
#
# Usage:
#   ./scripts/skill-dashboard.sh
#   ./scripts/skill-dashboard.sh --since 2026-04-01
#
# Suggested workflow (weekly):
#   ./scripts/skill-dashboard.sh > docs/sessions/dashboard-$(date +%Y-%m-%d).md
#   git add docs/sessions/dashboard-*.md
#   git commit -m "Skill dashboard $(date +%Y-%m-%d)"

set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$PROJECT_ROOT"

SKILL_DIR=".claude/skills/whatifd-design"
SESSIONS_DIR="docs/sessions"
BENCHMARKS_DIR="tests/skill-benchmarks/results"

# --- Argument parsing ---
SINCE_DAYS=30
SINCE_DATE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --since)
            SINCE_DATE="$2"
            shift 2
            ;;
        --days)
            SINCE_DAYS="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

# --- Header ---
cat <<EOF
# whatifd-design Skill Dashboard

**Generated:** $(date -u +%Y-%m-%dT%H:%M:%SZ)
**Project:** $(basename "$PROJECT_ROOT")

---

EOF

# --- Section: Sessions ---
echo "## Sessions"
echo ""

if [ ! -d "$SESSIONS_DIR" ]; then
    echo "_No session telemetry directory found at \`$SESSIONS_DIR\`._"
    echo ""
    echo "_Layer 2 (telemetry) is not deployed yet. Add the telemetry block"
    echo "from \`CLAUDE.md.append.md\` to your CLAUDE.md and start logging._"
else
    if [ -n "$SINCE_DATE" ]; then
        # POSIX find doesn't have -newermt portably. Use a simpler date filter.
        sessions=$(find "$SESSIONS_DIR" -maxdepth 1 -name "*.md" -type f | grep -v "^$SESSIONS_DIR/dashboard-" | grep -v "^$SESSIONS_DIR/README" | xargs -I {} sh -c 'echo "{}"' | sort)
    else
        sessions=$(find "$SESSIONS_DIR" -maxdepth 1 -name "*.md" -type f -mtime "-$SINCE_DAYS" 2>/dev/null | grep -v "/dashboard-" | grep -v "/README" || true)
    fi

    if [ -z "$sessions" ]; then
        session_count=0
    else
        session_count=$(echo "$sessions" | grep -c '\.md$')
    fi
    echo "Sessions in window: **$session_count**"
    echo ""

    if [ "$session_count" -gt 0 ]; then
        echo "### Reference file usage"
        echo ""
        echo "Which files in the skill actually get read?"
        echo ""
        echo "| Reference | Sessions referenced |"
        echo "|-----------|--------------------:|"
        if [ -d "$SKILL_DIR/references" ]; then
            for f in "$SKILL_DIR"/references/*.md; do
                [ -f "$f" ] || continue
                name=$(basename "$f")
                count=0
                for s in $sessions; do
                    [ -f "$s" ] || continue
                    if grep -q "$name" "$s" 2>/dev/null; then
                        count=$((count + 1))
                    fi
                done
                echo "| \`$name\` | $count |"
            done
        else
            echo "| _(skill not found at $SKILL_DIR)_ | - |"
        fi
        echo ""
        echo "_Files with 0 reads are either irrelevant (consider trimming or merging) or unfindable (the SKILL.md routing isn't pointing to them clearly)._"
        echo ""

        echo "### Cardinal rule citations"
        echo ""
        echo "Which cardinal rules from SKILL.md actually get applied?"
        echo ""
        echo "| Rule # | Sessions citing |"
        echo "|-------:|----------------:|"
        # Derive max rule number from SKILL.md so adding rule #N+1 doesn't
        # require touching this script. Numbered list items at column 1.
        max_rule=$(grep -cE '^[0-9]+\. \*\*' "$SKILL_DIR/SKILL.md" 2>/dev/null || true)
        max_rule=${max_rule:-9}
        n=1
        while [ "$n" -le "$max_rule" ]; do
            count=0
            for s in $sessions; do
                [ -f "$s" ] || continue
                if grep -qiE "rule #?$n\b|cardinal rule $n\b" "$s" 2>/dev/null; then
                    count=$((count + 1))
                fi
            done
            echo "| #$n | $count |"
            n=$((n + 1))
        done
        echo ""
        echo "_Rules with 0 citations across many sessions either don't apply to your work patterns (fine), or aren't being recognized (consider strengthening the description)._"
        echo ""
    fi
fi

# --- Section: Benchmarks ---
echo "## Benchmarks"
echo ""

if [ ! -d "$BENCHMARKS_DIR" ]; then
    echo "_No benchmark results directory found at \`$BENCHMARKS_DIR\`._"
    echo ""
    echo "_Layer 3 (benchmarks) is not deployed yet. Run \`./scripts/run-skill-benchmark.sh\` to start._"
else
    latest_run=$(find "$BENCHMARKS_DIR" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | sort -r | head -1)

    if [ -z "$latest_run" ]; then
        echo "_No benchmark runs found yet._"
    else
        echo "**Latest run:** \`$(basename "$latest_run")\`"
        echo ""

        if [ -f "$latest_run/grades.md" ]; then
            # Count manual-review marks. grep -c outputs the count and exits 1
            # on no-match, so route through `|| true` and trust the count line.
            pass=$(grep -c "^- \[x\] PASS\b" "$latest_run/grades.md" 2>/dev/null || true)
            partial=$(grep -c "^- \[x\] PARTIAL" "$latest_run/grades.md" 2>/dev/null || true)
            fail=$(grep -c "^- \[x\] FAIL" "$latest_run/grades.md" 2>/dev/null || true)
            pass=${pass:-0}
            partial=${partial:-0}
            fail=${fail:-0}
            graded=$((pass + partial + fail))

            ungraded=$(grep -cE "^- \[ \] (PASS|PARTIAL|FAIL)" "$latest_run/grades.md" 2>/dev/null || true)
            ungraded=${ungraded:-0}

            echo "**Manual grades:**"
            echo ""
            echo "- ✅ PASS: $pass"
            echo "- ⚠️  PARTIAL: $partial"
            echo "- ❌ FAIL: $fail"
            echo "- ⏳ Ungraded: $ungraded"
            echo ""

            if [ "$graded" -gt 0 ]; then
                pct=$((pass * 100 / graded))
                echo "**Pass rate:** ${pct}% ($pass / $graded graded prompts)"
                echo ""
                if [ "$pct" -ge 90 ]; then
                    echo "_Healthy skill (target: ≥90%)._"
                elif [ "$pct" -ge 70 ]; then
                    echo "_Needs iteration. Identify the failing prompts and trace which references/rules were missed._"
                else
                    echo "_Skill is not effective. Significant rework needed._"
                fi
            fi
        else
            echo "_grades.md not found. Run \`./scripts/grade-skill-benchmark.sh $latest_run\`._"
        fi
        echo ""

        # List previous runs
        all_runs=$(find "$BENCHMARKS_DIR" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | sort -r)
        run_count=$(echo "$all_runs" | wc -l | tr -d ' ')
        if [ "$run_count" -gt 1 ]; then
            echo "**All benchmark runs:** $run_count"
            echo ""
            echo "$all_runs" | head -10 | while read -r run; do
                echo "- \`$(basename "$run")\`"
            done
            if [ "$run_count" -gt 10 ]; then
                echo "- _… and $((run_count - 10)) more_"
            fi
            echo ""
        fi
    fi
fi

# --- Section: Cascade catalog status ---
echo "## Cascade catalog"
echo ""

CATALOG="$SKILL_DIR/references/cascade-catalog.md"
if [ ! -f "$CATALOG" ]; then
    echo "_Cascade catalog not found at \`$CATALOG\`._"
else
    open_count=$(grep -cE "^\*\*Status:\*\*\s*open" "$CATALOG" 2>/dev/null || true)
    in_progress_count=$(grep -cE "^\*\*Status:\*\*\s*in_progress" "$CATALOG" 2>/dev/null || true)
    resolved_count=$(grep -cE "^\*\*Status:\*\*\s*resolved" "$CATALOG" 2>/dev/null || true)
    deferred_count=$(grep -cE "^\*\*Rationale for deferral" "$CATALOG" 2>/dev/null || true)
    open_count=${open_count:-0}
    in_progress_count=${in_progress_count:-0}
    resolved_count=${resolved_count:-0}
    deferred_count=${deferred_count:-0}

    echo "| Status | Count |"
    echo "|--------|------:|"
    echo "| Open | $open_count |"
    echo "| In progress | $in_progress_count |"
    echo "| Resolved | $resolved_count |"
    echo "| Deferred (v1.0+) | $deferred_count |"
    echo ""

    if [ "$open_count" -gt 0 ]; then
        echo "_Schema freeze is blocked while open cascades exist. v0.1 is not ship-ready until these resolve to 'resolved' or 'deferred' with explicit rationale._"
    else
        echo "_All cascades resolved or deferred. Schema freeze unblocked._"
    fi
    echo ""
fi

# --- Section: Recommendations ---
echo "## Recommendations"
echo ""

# Heuristic recommendations based on the data above
recommendations=()

if [ -d "$SESSIONS_DIR" ]; then
    session_count=$(find "$SESSIONS_DIR" -maxdepth 1 -name "*.md" -type f -mtime "-$SINCE_DAYS" 2>/dev/null | grep -v "/dashboard-" | grep -v "/README" | wc -l | tr -d ' ')
    if [ "$session_count" -lt 3 ]; then
        recommendations+=("Run more real work sessions before drawing conclusions. Fewer than 3 sessions in the window is too sparse to identify patterns.")
    fi
fi

if [ ! -d "$BENCHMARKS_DIR" ] || [ -z "$(find "$BENCHMARKS_DIR" -maxdepth 1 -mindepth 1 -type d 2>/dev/null)" ]; then
    recommendations+=("Run the benchmark at least once to establish a baseline pass rate: \`./scripts/run-skill-benchmark.sh\`")
fi

if [ "${#recommendations[@]}" -eq 0 ]; then
    echo "_No specific recommendations. Continue collecting data and iterating._"
else
    for rec in "${recommendations[@]}"; do
        echo "- $rec"
    done
fi
echo ""

# --- Footer ---
cat <<EOF
---

_To save this dashboard for the time series:_

\`\`\`bash
./scripts/skill-dashboard.sh > docs/sessions/dashboard-\$(date +%Y-%m-%d).md
git add docs/sessions/dashboard-*.md
git commit -m "Skill dashboard \$(date +%Y-%m-%d)"
\`\`\`
EOF
