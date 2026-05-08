## Session telemetry (whatifd-design skill)

This project uses the `whatifd-design` skill installed at
`.claude/skills/whatifd-design/`. To support iteration on the skill, log every
significant work session using the protocol below.

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

The agent self-reports its own behavior so the user can see whether the skill
is working without reading every transcript. Patterns across many sessions
reveal which references get used, which cardinal rules get cited, and where
the skill falls short. This drives iteration on the skill itself.

The discipline is unenforced — the agent could skip telemetry — but skipping
shows up as missing files in `docs/sessions/`, which is itself diagnostic
information.

### When to skip telemetry

Skip telemetry only for trivial sessions: pure clarification questions,
status checks, conversational exchanges that produce no artifacts. If a
session produces a file, modifies a file, or makes an architectural
decision, log it.
