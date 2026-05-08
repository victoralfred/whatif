"""Tests for `whatif.cli` — Phase 8.2.

Pin properties:

1. `whatif --help` succeeds (typer app loads).
2. `whatif fork` with valid config exits 2 (Phase 4 adapter
   integration not yet wired); the message names the gap.
3. `whatif fork` with missing config file exits 2 with
   ConfigFileError.
4. `whatif fork` with invalid config exits 2 with
   `format_validation_errors` output (Hint: lines visible).
5. `whatif fork --profile forensic` against non-forensic config
   exits 2 with ForensicAffirmationError.
6. `whatif fork --profile forensic` against forensic config (with
   acknowledgment block) reaches the Phase 4 stub (exit 2 setup-
   failure with that specific message).
7. Subcommand stubs (`cache rebuild|unlock|verify`, `diff`,
   `report-migrate`) all exit 2 with their phase-stub messages.
"""

from __future__ import annotations

import json

import pytest
from click.testing import Result
from typer.testing import CliRunner

from whatif.cli import (
    EXIT_INCONCLUSIVE_OR_SETUP_FAILURE,
    EXIT_SUCCESS,
    app,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _all_output(result: Result) -> str:
    """Combined stdout/stderr — newer click/typer versions mix
    streams in `result.output` by default, dropping the
    `mix_stderr` constructor arg. This helper smooths the
    difference so assertions read whichever of the two is
    populated.

    Note on potential double-counting: `result.stdout` and
    `result.output` may overlap on some click/typer versions
    (newer versions alias them; older versions don't). The
    concatenation can technically duplicate content. We accept
    this for the assertion use case — `assert "foo" in <combined>`
    only cares about presence, not count, so duplicates are
    benign. If a future test asserts on substring counts, that
    test should call `result.stdout` / `result.stderr` directly
    rather than going through this helper.
    """
    return (result.stdout or "") + (getattr(result, "stderr", "") or "") + (result.output or "")


def _minimal_config_dict() -> dict[str, object]:
    return {
        "source": {"adapter": "langfuse"},
        "target": {"runner": "python:my_agent.replay:run"},
        "selection": {
            "failure_cohort": {"limit": 20},
            "baseline_cohort": {"limit": 20},
        },
        "change": {"system_prompt": "be concise"},
        "scorer": {"adapter": "inspect_ai", "cache_mode": "auto"},
        "decision": {},
        "reporting": {},
        "timeouts": {},
    }


def _forensic_config_dict() -> dict[str, object]:
    d = _minimal_config_dict()
    d["reporting"] = {
        "profile": "forensic",
        "forensic_acknowledgment": {
            "accepted_by": "ops",
            "accepted_at": "2026-05-07",
            "reason": "audit",
        },
    }
    return d


# ---------------------------------------------------------------------------
# Help / app load
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_succeeds(self, runner: CliRunner) -> None:
        # `whatif --help` exits 0 — typer convention for help.
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "whatif: trust-first" in _all_output(result)

    def test_no_args_prints_help(self, runner: CliRunner) -> None:
        # no_args_is_help=True on the root app.
        result = runner.invoke(app, [])
        # typer convention: exit 2 (usage error) when no args; help
        # text is shown.
        assert result.exit_code != 0
        assert "Usage:" in _all_output(result)


# ---------------------------------------------------------------------------
# `whatif fork` config-load / setup failures
# ---------------------------------------------------------------------------


class TestForkConfigFailures:
    def test_missing_config_file_exits_2(self, runner: CliRunner, tmp_path) -> None:
        result = runner.invoke(app, ["fork", "--config", str(tmp_path / "nonexistent.yaml")])
        assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
        assert "config error" in _all_output(result)
        assert "not found" in _all_output(result)

    def test_invalid_config_exits_2_with_hints(self, runner: CliRunner, tmp_path) -> None:
        # selection.failure_cohort.limit=0 triggers a registered
        # hint; CLI surfaces format_validation_errors output.
        d = _minimal_config_dict()
        d["selection"]["failure_cohort"]["limit"] = 0
        p = tmp_path / "invalid.json"
        p.write_text(json.dumps(d), encoding="utf-8")

        result = runner.invoke(app, ["fork", "--config", str(p)])
        assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
        assert "selection.failure_cohort.limit" in _all_output(result)
        assert "Hint:" in _all_output(result)

    def test_unknown_section_exits_2(self, runner: CliRunner, tmp_path) -> None:
        d = _minimal_config_dict()
        d["mystery"] = {}
        p = tmp_path / "extra.json"
        p.write_text(json.dumps(d), encoding="utf-8")

        result = runner.invoke(app, ["fork", "--config", str(p)])
        assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
        assert "mystery" in _all_output(result)


# ---------------------------------------------------------------------------
# Two-affirmation cross-surface (cardinal #7)
# ---------------------------------------------------------------------------


class TestForkTwoAffirmation:
    def test_cli_forensic_without_config_exits_2(self, runner: CliRunner, tmp_path) -> None:
        # Default-profile config + --profile forensic → CLI flag
        # alone is insufficient (cardinal #7).
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps(_minimal_config_dict()), encoding="utf-8")

        result = runner.invoke(app, ["fork", "--config", str(p), "--profile", "forensic"])
        assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
        assert "CLI flag alone is insufficient" in _all_output(result)

    def test_config_forensic_without_cli_exits_2(self, runner: CliRunner, tmp_path) -> None:
        # Forensic config + no --profile flag → config alone
        # insufficient. Pin the cross-surface check fires.
        p = tmp_path / "forensic.json"
        p.write_text(json.dumps(_forensic_config_dict()), encoding="utf-8")

        result = runner.invoke(app, ["fork", "--config", str(p)])
        assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
        assert "CLI invocation did not include" in _all_output(result)

    def test_both_forensic_reaches_dispatcher_setup_failure(
        self, runner: CliRunner, tmp_path
    ) -> None:
        # Both surfaces forensic-aligned → two-affirmation passes;
        # CLI proceeds into _run_fork_pipeline. The minimal config
        # uses inspect_ai scorer, which requires a programmatic
        # score_fn config can't load (Phase 10.1 documented behavior),
        # so the dispatcher exits 2 with a setup-failure message.
        # The witness-token threading is proven by reaching the
        # dispatcher body at all — the stderr is the real adapter
        # factory error, not a witness-token bypass.
        p = tmp_path / "forensic.json"
        p.write_text(json.dumps(_forensic_config_dict()), encoding="utf-8")

        result = runner.invoke(app, ["fork", "--config", str(p), "--profile", "forensic"])
        assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
        assert "setup failure" in _all_output(result)


# ---------------------------------------------------------------------------
# Default (non-forensic) flow reaches the Phase 4 stub
# ---------------------------------------------------------------------------


class TestForkDefaultFlow:
    def test_default_profile_reaches_dispatcher_setup_failure(
        self, runner: CliRunner, tmp_path
    ) -> None:
        # Non-forensic config + no --profile → two-affirmation
        # returns proof with forensic_active=False; CLI proceeds
        # into _run_fork_pipeline. The minimal config uses
        # inspect_ai scorer (config can't load score_fn) so the
        # dispatcher's adapter factory raises AdapterFactoryError →
        # setup-failure stderr → exit 2 (cardinal #1: structured
        # data, not stack trace). Pin that the path completes
        # cleanly, not that any specific stub message appears.
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps(_minimal_config_dict()), encoding="utf-8")
        result = runner.invoke(app, ["fork", "--config", str(p)])
        assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
        assert "setup failure" in _all_output(result)


# ---------------------------------------------------------------------------
# Subcommand stubs
# ---------------------------------------------------------------------------


class TestWitnessThreading:
    def test_run_fork_pipeline_signature_requires_proof(self) -> None:
        # Cardinal #2 / #7 mirror: the dispatcher's signature is
        # the structural contract surface. A future Phase 4
        # contributor can extend the body but cannot drop the
        # `proof: TwoAffirmationProof` parameter without breaking
        # this test (and every typed caller). Pin the resolved
        # annotations via `get_type_hints` (the module uses
        # `from __future__ import annotations` so raw signature
        # values are strings; `get_type_hints` evaluates them).
        import inspect
        import typing

        from whatif.cli import _run_fork_pipeline
        from whatif.config import TwoAffirmationProof, WhatifConfig

        sig = inspect.signature(_run_fork_pipeline)
        params = list(sig.parameters.values())
        assert len(params) == 2
        assert params[0].name == "cfg"
        assert params[1].name == "proof"
        # Both parameters required (no defaults).
        assert params[0].default is inspect.Parameter.empty
        assert params[1].default is inspect.Parameter.empty
        # Resolved annotations match the declared types.
        hints = typing.get_type_hints(_run_fork_pipeline)
        assert hints["cfg"] is WhatifConfig
        assert hints["proof"] is TwoAffirmationProof
        assert hints["return"] is int


class TestSubcommands:
    """Subcommand smoke tests at the CLI surface.

    Renamed from `TestSubcommandStubs`: the cache subcommands
    became real implementations in Phase 8.3 (PR #54). `diff`
    and `report-migrate` are still stub paths but exit with
    their own documented semantics — a future contributor wiring
    Phase 8.4 / 8.5 should treat these as the surface contract,
    not as placeholders to delete.
    """

    def test_cache_rebuild_without_force_refuses(self, runner: CliRunner, tmp_path) -> None:
        # Phase 8.3 landed: cache rebuild is real. Without --force
        # it's a no-op safety belt. Detailed integration coverage
        # is in tests/unit/whatif/cache/test_recovery.py.
        result = runner.invoke(app, ["cache", "rebuild", "--cache-root", str(tmp_path)])
        assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
        assert "refusing to delete without --force" in _all_output(result)

    def test_cache_unlock_idempotent_when_no_lock(self, runner: CliRunner, tmp_path) -> None:
        # No lock file in tmp_path → idempotent success.
        result = runner.invoke(app, ["cache", "unlock", "--cache-root", str(tmp_path)])
        assert result.exit_code == EXIT_SUCCESS
        assert "already unlocked" in _all_output(result)

    def test_cache_verify_vacuously_clean(self, runner: CliRunner, tmp_path) -> None:
        # No entries dir → vacuously clean (exit 0).
        result = runner.invoke(app, ["cache", "verify", "--cache-root", str(tmp_path)])
        assert result.exit_code == EXIT_SUCCESS
        assert "vacuously clean" in _all_output(result)

    def test_diff_missing_file_exits_2(self, runner: CliRunner, tmp_path) -> None:
        # File-level errors surface as DiffError → exit 2.
        new = tmp_path / "new.json"
        new.write_text(
            json.dumps(
                {
                    "verdict_state": "ship",
                    "schema_version": "v0.1",
                    "cohort_results": [],
                    "decision_findings": [],
                    "failures": [],
                }
            ),
            encoding="utf-8",
        )
        result = runner.invoke(app, ["diff", str(tmp_path / "missing.json"), str(new)])
        assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
        assert "not found" in _all_output(result)

    def test_diff_renders_markdown(self, runner: CliRunner, tmp_path) -> None:
        prev = tmp_path / "prev.json"
        new = tmp_path / "new.json"
        base = {
            "schema_version": "v0.1",
            "cohort_results": [],
            "decision_findings": [],
            "failures": [],
        }
        prev.write_text(json.dumps({**base, "verdict_state": "dont_ship"}), encoding="utf-8")
        new.write_text(json.dumps({**base, "verdict_state": "ship"}), encoding="utf-8")
        result = runner.invoke(app, ["diff", str(prev), str(new)])
        assert result.exit_code == EXIT_SUCCESS
        out = _all_output(result)
        assert "# whatif diff" in out
        assert "Don't Ship" in out and "Ship" in out

    def test_report_migrate_no_op_exits_zero(self, runner: CliRunner, tmp_path) -> None:
        # v0.1 has no schema bumps to migrate; the no-op IS a
        # success, not a setup failure. Exit 0 (Ship-equivalent)
        # so automated pipelines can wire this without false
        # alarms.
        report = tmp_path / "report.json"
        report.write_text("{}", encoding="utf-8")
        result = runner.invoke(app, ["report-migrate", str(report)])
        assert result.exit_code == EXIT_SUCCESS
        assert "No-op success" in _all_output(result)
