<!--
  Thanks for the PR. Please fill every section below - the template exists
  because reviewing a PR with missing context costs more time than writing it.
-->

## What this PR does

<!-- 1–2 sentences. Link the issue. -->

Closes #

## Why

<!--
  Brief context. What user pain does this address, or what design goal does
  this advance? If this is purely refactor / tooling, say so.
-->

## How

<!--
  Implementation overview. Architectural impact (if any). Anything reviewers
  should look at carefully (e.g., a non-obvious tradeoff)?
-->

## Type of change

- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change (requires changelog note + version bump)
- [ ] Refactor (no behavior change)
- [ ] Documentation
- [ ] CI / build / tooling
- [ ] Dependency update

## Checklist

- [ ] CI is green (`lint`, `type`, `test`, `pip-audit`, `bandit`, `codeql`).
- [ ] New code has tests; existing tests pass locally.
- [ ] `DESIGN.md` updated **iff** architecture changed.
- [ ] `CHANGELOG.md` updated under `[Unreleased]`.
- [ ] If this changes the runner contract (`src/whatif/contract/`), the change is **additive** or behind a major version bump - no silent breakage of user runners.
- [ ] If this changes the report format, all 5 mandatory sections still present (Verdict / Stats / Replay validity / Baseline integrity / Evidence + judge rationale).
- [ ] If this changes a CLI flag or exit code, README quickstart still accurate.

## Sample output (for UX-affecting changes)

<!--
  For changes that affect user-visible CLI output, report format, or error
  messages, paste the before/after sample output here. A picture is worth
  three review rounds.
-->

## Notes for reviewers

<!-- Anything else reviewers should know. Timezones, follow-ups, etc. -->
