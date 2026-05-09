# Security policy

## Supported versions

This project is pre-alpha. Security fixes will be issued for the most recent minor release once v0.1 ships.

| Version | Supported                       |
|---------|---------------------------------|
| 0.0.x   | :x: (pre-alpha, no guarantees)  |
| 0.1.x   | :white_check_mark: (planned)    |

## Reporting a vulnerability

**Please do not open public GitHub issues for security reports.**

Use [GitHub's private vulnerability reporting](https://github.com/victoralfred/whatifd/security/advisories/new) to file the report privately. You will receive an acknowledgement within **7 days**.

If GitHub Advisories is not an option for you, email:

> **security@whatif.codes**

When reporting, please include:

- Affected version (release tag or commit SHA).
- Minimal steps to reproduce.
- Impact assessment-what an attacker could achieve in practice.
- Suggested remediation, if you have one.

## Coordinated disclosure

We follow standard coordinated disclosure:

1. **Acknowledged within 7 days** of report.
2. **Investigated and patched** in a private branch.
3. **Patch released** with a security advisory; reporter credited if they wish.
4. **Public disclosure** 90 days after the patch ships, or earlier with the reporter's written agreement.

Please do not publicly disclose the issue or open public PRs that reference it until the coordinated window closes.

## Scope

**In scope:**

- The `whatifd` library and CLI itself.
- The runner-contract Pydantic models in `src/whatifd/contract/`.
- Official adapters shipped under `src/whatifd/ingest/`.
- The default scorer wrappers in `src/whatifd/score/`.
- The default report templates and exit-code policy.

**Out of scope** (these are the user's responsibility):

- The user-supplied  - target` runner code.
- Tools cached or invoked during replay (cache policies prevent side effects, but tool implementations themselves are user code).
- Underlying LLM provider security (covered by each provider's own policy).
- The user's tracer or SLO platform integrations.
- Issues that require an attacker with local write access to the user's repository or CI configuration - these are outside our threat model.

## Hall of fame

Reporters who follow this policy will be credited (with their permission) in `CHANGELOG.md` and the corresponding GitHub Security Advisory.
