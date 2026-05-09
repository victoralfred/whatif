# whatifd: Project Guide for Claude

## Mandatory reading

Before any architecture, design, or implementation work on this project,
read `.claude/skills/whatifd-design/SKILL.md` and the relevant reference
files in `.claude/skills/whatifd-design/references/`.

The skill encodes the convergent design from extensive deliberation. Do
not re-litigate decisions captured in the cascade catalog without first
reading the relevant cascade entry.

## Cardinal rules (non-negotiable)

These survive every dispute. If you propose anything that violates one
of these, the proposal is rejected regardless of rationale.

1. Failure-as-data: every expected failure is structured data in the
   report, never an unhandled exception.
2. Trust floor cannot be bypassed: floor failures produce Inconclusive
   regardless of policy.
3. Disclosure is necessary but not sufficient: severe trust failures
   must affect the verdict, not just appear in a footnote.
4. Determinism is opt-in per field, default off.
5. Sensitive data is wrapped, never raw.
6. Public schema hand-written; internal types refactor freely.
7. Two-affirmation for dangerous capabilities.
8. Inconclusive must be actionable.
9. whatifd is orchestration, not compute. Reject CPU-optimization tools
   (Ray, ProcessPool for replay, NumPy throughout, MKL, SIMD, BF16/INT8,
   Numba, ONNX, shared-memory IPC).
10. Statistical claims must match the design. Paired trace deltas are
    the unit of analysis; predeclared cohort-level endpoints drive the
    verdict; per-trace evidence is descriptive, not inferential.
    Methodology is disclosed in every report. Scorer caching addresses
    reproducibility — NOT reliability, validity, calibration, or absence
    of bias. No causal claims beyond "associated under cached-tool
    replay."

## Working with the design

The cascade catalog (`.claude/skills/whatifd-design/references/cascade-catalog.md`)
tracks open architectural decisions. When you make a change with
downstream consequences, update the catalog in the same PR. When you
discover a new gap during implementation, file it in the catalog before
proposing a fix.

The catalog is the project's design memory. Treat it as production
documentation, not as a draft.

## When in doubt

Ask: "Would this make the verdict more defensible?" If you cannot
answer yes with a concrete reason, do not write the code. Surface the
question to the project owner before proceeding.

## Scope discipline

- v0.1 is failure-rescue only. Other experiment shapes are deferred.
- Schema freeze is blocked until the cascade catalog is clean.
- Walkthroughs come before code.
- Performance work requires profile data; CPU is not the bottleneck.

## What to do if you disagree with the design

Surface it explicitly to the project owner. Do not silently work around
it. The design has survived multiple rounds of adversarial review;
the load-bearing concepts are intentional.

---

## Session telemetry (whatifd-design skill)

This project uses the `whatifd-design` skill installed at
`.claude/skills/whatifd-design/`. To support iteration on the skill, log
every significant work session using the protocol below.

### At session start

Before doing any task work, write a session log to
`docs/sessions/<YYYY-MM-DD>-<short-topic-slug>.md` using this template:

```markdown
---
session_id: <YYYY-MM-DD>-<topic-slug>
started_at: <iso-8601 timestamp>
---

## Session start

**User request:** <one-line summary of what the user asked for>

**Skill files read:**
- .claude/skills/whatifd-design/SKILL.md
- .claude/skills/whatifd-design/references/<each-file>.md
  (list every reference file you actually read this session,
   in the order you read them)

**Cardinal rules cited:**
- Rule #N: <one line on why this rule applies to today's task>
  (list each cardinal rule from SKILL.md you applied; if none apply,
   say "none — task is below cardinal-rule threshold")

**Clarifying questions asked:**
- <question 1>
- <question 2>
  (list every clarifying question; if none asked, say "none — task was unambiguous")

**Phase plan position (per references/phases.md):**
- Phase: <number and name>
- Sub-item: <which step within the phase>
- Prerequisites status: <list any earlier-phase gates not yet green>
```

### At session end

Append this section to the same file:

```markdown
## Session end

**Artifacts produced:**
- <path/to/file>: <brief description of what was added/changed>
  (every file you created or modified)

**Cascade catalog items:**
- Opened: <code or one-line title> — <reason>
- Resolved: <code> — <how>
- Updated: <code> — <what changed>
  (entries in references/cascade-catalog.md you touched; if none, say "none")

**Gaps surfaced:**
- <gap discovered that isn't yet in the cascade catalog>
  (things that turned out not to be specified that should be filed
   as cascade items in a follow-up session; if none, say "none")

**Doctrine moments:**
- <decision point where you applied the misleading-vs-inconvenient test,
   the trust-floor rule, the orchestration-not-compute rule, or any other
   cardinal rule, and what you decided>
  (include the specific decision; this is the most valuable diagnostic
   data because it captures real applications of the doctrine)

**Notes for the next session:**
- <anything left undone, or context worth anchoring next time>
```

### Why this matters

The agent self-reports its own behavior so the user can see whether the
skill is working without reading every transcript. Patterns across many
sessions reveal which references get used, which cardinal rules get
cited, and where the skill falls short. This drives iteration on the
skill itself.

The discipline is unenforced — the agent could skip telemetry — but
skipping shows up as missing files in `docs/sessions/`, which is itself
diagnostic information.

### When to skip telemetry

Skip telemetry only for trivial sessions: pure clarification questions,
status checks, conversational exchanges that produce no artifacts. If a
session produces a file, modifies a file, or makes an architectural
decision, log it.
