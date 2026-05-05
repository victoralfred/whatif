# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Pre-1.0, the minor version may introduce breaking changes - every breaking
change is called out under `### Changed (BREAKING)`.

---

## [Unreleased]

### Added

- Initial public scaffold:
  - `DESIGN.md` - canonical design through the M10–M12 roadmap; problem framing, prior art, runner contract, report shape, eval target, risks, Path Z.
  - `LICENSE` - Apache 2.0.
  - `README.md - hero copy + workflow / overview / pipeline images + status table + runner contract teaser.
  - `pyproject.toml` - uv-managed; src layout; Python ≥ 3.11; ruff/mypy/pytest configured.
  - `src/whatif/__init__.py` - version 0.0.1.
  - `src/whatif/contract/__init__.py - runner contract Pydantic models: `TraceInput`, `ReplayConfig`, `ToolCache`, `ReplayOutput`, `TraceOutput`, `ScoreCase`, `Runner` Protocol.
  - `tests/test_contract.py - 10 smoke tests for the contract API.
  - 3 architectural / workflow images in the repo root.
- Production-grade GitHub plumbing:
  - `.github/workflows/ci.yml - lint (ruff), type-check (mypy), test on Python 3.11 / 3.12 / 3.13.
  - `.github/workflows/security.yml - `pip-audit`, `bandit`, `gitleaks`; runs on push, PR, and weekly schedule.
  - `.github/workflows/codeql.yml - CodeQL static analysis with `security-extended` + `security-and-quality` queries.
  - `.github/workflows/release.yml - sdist + wheel build, PyPI publish via Trusted Publishers, GitHub Release with auto-generated notes; triggered by `v*.*.*` tags.
  - `.github/dependabot.yml - weekly grouped pip + GitHub Actions updates.
  - `.github/CODEOWNERS - review routing.
  - `.github/PULL_REQUEST_TEMPLATE.md - PR checklist with whatif-specific gates.
  - `.github/ISSUE_TEMPLATE/ - bug + feature templates with structured fields, plus a `config.yml` that disables blank issues and routes to Discussions / private security advisories.
- Project governance:
  - `CONTRIBUTING.md - branch strategy, commit conventions, PR / merge / release workflow, manual GitHub config checklist.
  - `CODE_OF_CONDUCT.md` -Contributor Covenant 2.1 (adopted by reference).
  - `SECURITY.md - disclosure policy, scope, coordinated disclosure timeline.
  - `.pre-commit-config.yaml` - ruff + ruff-format + mypy + standard hygiene hooks.

### Notes

- No runtime yet. v0.1 - Langfuse ingest, replay engine, Inspect AI scorer, evidence - first Markdown + JSON reports, CI-ready exit codes-begins in M10.

---

[Unreleased]: https://github.com/victoralfred/whatif/commits/main
