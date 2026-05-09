---
name: whatifd-features
description: Deferred-work catalog for `whatifd`. Use when triaging whether an idea belongs in the active plan now or as future work, when proposing a refactor, or when looking for post-v0.1 candidates.
---

# whatifd-features: forward-work candidates

## Hard constraint: this skill is a workshop, not a driver

**Do NOT use this skill to drive in-flight implementation.** The active plan lives in `whatifd-design/references/phases.md` and is the source of truth for what gets built and in what order. This skill is a **read-from / append-to** surface only — entries here promote *into* the active plan when their trigger fires; nothing flows the other way without that trigger.

If you're tempted to start implementing an entry here directly, that's the signal to STOP and either (a) confirm the trigger has fired and promote the entry, or (b) re-read the active plan and find the actual next step.

## Purpose

`whatifd-design` encodes the doctrine and the active phased plan. That plan is the source of truth for what gets built and in what order. This skill is a **separate** catalog of ideas that came up during implementation but were correctly judged out-of-scope for the current sub-phase.

## How to use

Before adding work to the active plan, check this skill: is the idea already logged here as deferred? If yes, see what trigger the entry names; if the trigger has fired, promote the entry to a real cascade-catalog item (or a phase plan amendment) and consume it from the active plan.

If the idea is new, add a reference file under `references/` rather than expanding the active phase plan. The plan is reviewed and merged; this skill is a workshop.

## What goes here

- **Discovered refactors.** Improvements that would make sense but aren't blocking current work.
- **YAGNI rejections.** Suggestions that came up in review and were declined for cause; logging them prevents re-litigation.
- **Trigger-based deferrals.** Items that should land when a specific event happens (real adapter friction, a schema bump, a downstream consumer).

## What does NOT go here

- **Active in-flight work.** That belongs in the merged phase plan.
- **Doctrine.** That belongs in `whatifd-design/references/doctrine.md`.
- **Cascade-tracked open items.** Those live in `whatifd-design/references/cascade-catalog.md` because they have a structural contract with the design.

## Boundary with the cascade catalog

Cascade catalog: design decisions whose ripples MUST resolve before schema freeze or v0.1 release.
This skill: discovered improvements whose ripples MAY land at v0.2+ (or never) without blocking v0.1.

If an entry here grows a hard dependency on v0.1, promote it to the cascade catalog with a Status / Resolution field and link this skill's entry to it.

## Reference files

- `references/deferred-refactors.md` — concrete items with trigger conditions for promotion.
