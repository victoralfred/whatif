# whatifd-design Skill Instrumentation Bundle

Four-layer instrumentation for the `whatifd-design` skill. Drop this into your
project root alongside the `.claude/skills/whatifd-design/` skill folder and
your `CLAUDE.md`.

## What's in here

```
.
├── README.md                                  (this file)
├── CLAUDE.md.append.md                        (block to append to your CLAUDE.md)
├── scripts/
│   ├── collect-transcripts.sh                 (Layer 1: copy session logs)
│   ├── run-skill-benchmark.sh                 (Layer 3: run benchmark prompts)
│   ├── grade-skill-benchmark.sh               (Layer 3: grade benchmark results)
│   └── skill-dashboard.sh                     (Layer 4: aggregate dashboard)
├── tests/
│   └── skill-benchmarks/
│       └── prompts.json                       (Layer 3: 10 starter prompts)
└── docs/
    └── sessions/
        ├── README.md                          (Layer 2: telemetry log directory)
        └── raw/
            └── .gitkeep                       (Layer 1: raw transcript dir)
```

## The four layers

| Layer | What it does | Effort | When to deploy |
|-------|--------------|--------|----------------|
| 1 | Saves Claude Code session transcripts | Zero (script) | Day 1 |
| 2 | Agent self-reports skill activation per session | Low (CLAUDE.md edit) | Day 1 |
| 3 | Benchmark prompts catch skill regressions | Medium (run weekly) | Week 2 |
| 4 | Dashboard aggregates layers 1–3 | Low (run periodically) | Week 3+ |

## Quick deploy (week 1)

```bash
# 1. From your whatifd project root:
cd /path/to/your/whatifd-project

# 2. Drop the bundle contents into the project root:
cp -r path/to/this/bundle/* .

# 3. Make scripts executable:
chmod +x scripts/*.sh

# 4. Append the telemetry block to your existing CLAUDE.md:
cat CLAUDE.md.append.md >> CLAUDE.md
# (Or open CLAUDE.md.append.md and merge it manually if you prefer.)

# 5. Test transcript collection (no-op if you haven't run a session yet):
./scripts/collect-transcripts.sh

# 6. Decide what to commit:
#    - scripts/ → commit (your team needs it)
#    - tests/skill-benchmarks/prompts.json → commit (the test set)
#    - docs/sessions/raw/ → optionally .gitignore (raw logs)
#    - docs/sessions/*.md → commit (the agent's self-reported telemetry)
```

## Layer 1: Transcript collection

Run after each significant session:

```bash
./scripts/collect-transcripts.sh
```

This copies `~/.claude/projects/<project-key>/*.jsonl` into
`docs/sessions/raw/` for analysis with `jq`, `grep`, etc.

If your Claude Code version stores logs elsewhere, the script will tell you.
Find them with:

```bash
find ~ -name "*.jsonl" -path "*claude*" 2>/dev/null | head
```

Then adjust `CLAUDE_LOGS` in the script.

## Layer 2: Self-reported telemetry

Adds a session-start and session-end logging protocol to your CLAUDE.md.
The agent writes `docs/sessions/<YYYY-MM-DD>-<topic>.md` with structured
information about which skill files it read, which cardinal rules it
applied, what it produced, and which cascade catalog items moved.

This is the highest-value-per-effort layer. After 5 sessions you can grep:

```bash
# Which references actually get read?
grep -h "references/" docs/sessions/*.md | sort | uniq -c | sort -rn

# Which cardinal rules get cited?
grep -hE "rule #?[0-9]+|cardinal rule [0-9]+" docs/sessions/*.md \
  | sort | uniq -c | sort -rn

# Which references never get read in 30 days?
for f in .claude/skills/whatifd-design/references/*.md; do
    name=$(basename "$f")
    count=$(grep -lc "$name" docs/sessions/*.md 2>/dev/null | wc -l)
    echo "$count $name"
done | sort -n
```

Underused references are either irrelevant (consider trimming) or
unfindable (the SKILL.md routing isn't pointing to them clearly).

## Layer 3: Benchmark prompts

Run periodically (weekly is reasonable):

```bash
./scripts/run-skill-benchmark.sh
# Then for the printed results directory:
./scripts/grade-skill-benchmark.sh tests/skill-benchmarks/results/2026-05-04
# Open the grades.md file and fill in the manual review sections.
```

The starter prompt set in `tests/skill-benchmarks/prompts.json` covers
each cardinal rule plus negative tests (prompts that should NOT trigger
the skill). Replace these with prompts derived from real failure modes
once you have telemetry data from layer 2.

The benchmark scripts assume `claude -p "prompt"` works for non-interactive
prompting. If your Claude Code version uses different flags, adjust
`run-skill-benchmark.sh` accordingly.

## Layer 4: Dashboard

Run periodically to aggregate everything:

```bash
./scripts/skill-dashboard.sh > docs/sessions/dashboard-$(date +%Y-%m-%d).md
git add docs/sessions/dashboard-*.md
git commit -m "Skill dashboard $(date +%Y-%m-%d)"
```

Over time the committed dashboards form a time series of skill effectiveness.
Falling pass rates or unread references are the signal to iterate on the
skill itself.

## What this is NOT

- Not automated quality enforcement. The agent can still ignore the skill;
  this just makes the ignoring visible.
- Not a replacement for reading transcripts. The aggregate metrics catch
  patterns; only reading actual sessions catches subtle drift.
- Not a substitute for the skill-creator's eval framework. If you need
  rigorous A/B comparisons (with vs without skill), use that. This is the
  lightweight version that doesn't need subagents or browsers.

## Iteration loop

The point of all this is to drive iteration on the skill itself, not just
to collect data. The loop:

1. Run real work sessions (the agent self-logs via CLAUDE.md telemetry).
2. Read transcripts and session logs after each significant session.
3. Note where the skill missed (rule not cited, reference not read,
   wrong default chosen, cascade not updated).
4. Run the benchmark periodically to catch regressions.
5. Iterate the skill: tighten descriptions, push references that get
   skipped, soften references that always get read regardless.
6. Re-run the benchmark; pass rate should hold or improve.

You're done when the benchmark holds at >90% pass rate across two
consecutive runs and the dashboard shows balanced reference usage with
no zeros in the cardinal-rule citations table.
