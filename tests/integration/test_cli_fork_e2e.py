"""Phase 10.4 end-to-end CLI smoke: `whatifd fork` runs through.

Constructs a minimal whatifd config (stub source + stub scorer +
test-fixture runner), invokes the typer CLI via `CliRunner`, and
asserts the exit code, stderr/stdout, and that the JSON+Markdown
artifacts were written. This is the proof that the CLI dispatcher
in `src/whatifd/cli.py::_run_fork_pipeline` actually wires the
factory + loader + delta_fn + run_pipeline + render path
end-to-end, not just compiles.
"""

from __future__ import annotations

import sys
import textwrap
import types
from pathlib import Path

import pytest
from typer.testing import CliRunner

from whatifd.cli import EXIT_INCONCLUSIVE_OR_SETUP_FAILURE, app
from whatifd.contract import ReplayConfig, ReplayOutput, ToolCache, TraceInput

_RUNNER_FIXTURE_MODULE = "_whatif_cli_fork_e2e_fixture"


@pytest.fixture(autouse=True)
def _register_runner_fixture() -> None:
    """Register an in-memory module the test config's
    `target.runner = python:<module>:run` resolves to."""
    module = types.ModuleType(_RUNNER_FIXTURE_MODULE)

    def run(
        trace_input: TraceInput,
        config: ReplayConfig,
        tool_cache: ToolCache,
    ) -> ReplayOutput:
        _ = (trace_input, config, tool_cache)
        return ReplayOutput(text="e2e-stub", tool_spans=[], metadata={})

    module.run = run  # type: ignore[attr-defined]
    sys.modules[_RUNNER_FIXTURE_MODULE] = module
    yield
    sys.modules.pop(_RUNNER_FIXTURE_MODULE, None)


def _write_config(tmp_path: Path) -> Path:
    cfg = textwrap.dedent(
        f"""\
        source:
          adapter: stub
        target:
          runner: python:{_RUNNER_FIXTURE_MODULE}:run
        selection:
          failure_cohort:
            limit: 5
          baseline_cohort:
            limit: 5
        change:
          system_prompt: e2e test prompt
        scorer:
          adapter: stub
        decision: {{}}
        reporting:
          profile: default
        timeouts:
          replay_seconds: 5.0
          score_seconds: 5.0
        """
    )
    path = tmp_path / "whatifd.config.yaml"
    path.write_text(cfg, encoding="utf-8")
    return path


def test_whatif_fork_e2e_setup_failure_no_traces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: stub source + stub scorer + fixture runner,
    config validates, two-affirmation passes (default profile),
    pipeline runs, but the stub source yields zero traces (factory
    default per the documented behavior in PR #68's CHANGELOG).

    Floor failure on both required cohorts → Inconclusive (exit 2).
    Pin this so a future change to the stub-source default
    (e.g., adding fixtures) shifts the verdict and surfaces
    deliberately, not silently.
    """
    monkeypatch.chdir(tmp_path)
    cfg_path = _write_config(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["fork", "--config", str(cfg_path)])
    assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE, (
        result.exit_code,
        result.stdout,
        result.stderr if hasattr(result, "stderr") else "",
    )
    # Artifacts written to ./reports/.
    reports_dir = tmp_path / "reports"
    assert reports_dir.is_dir()
    artifacts = sorted(reports_dir.iterdir())
    md_files = [p for p in artifacts if p.suffix == ".md"]
    json_files = [p for p in artifacts if p.suffix == ".json"]
    assert md_files, artifacts
    assert json_files, artifacts


def test_whatif_fork_e2e_filesystem_write_failure_no_stack_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F-1.3: filesystem write failures (read-only dir, ENOSPC,
    PermissionError) must surface as a structured operator message +
    setup-failure exit code, never a raw Python stack trace.

    Pre-fix, `report_md_path.parent.mkdir` / `write_bytes` /
    `write_text` ran outside any try/except, so a `PermissionError`
    propagated past the dispatcher's cardinal-#1 boundary.

    Simulated by monkeypatching `Path.mkdir` to raise PermissionError.
    """
    monkeypatch.chdir(tmp_path)
    cfg_path = _write_config(tmp_path)

    real_mkdir = Path.mkdir

    def _raise_permission_error(self, *args: object, **kwargs: object) -> None:  # type: ignore[no-untyped-def]
        if self.name == "reports":
            raise PermissionError(13, "Permission denied", str(self))
        return real_mkdir(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "mkdir", _raise_permission_error)

    runner = CliRunner()
    result = runner.invoke(app, ["fork", "--config", str(cfg_path)])
    assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
    combined = (result.stdout or "") + (result.output or "")
    assert "Traceback" not in combined, combined
    assert "failed to write report artifacts" in combined
    assert "PermissionError" in combined


def test_whatif_fork_e2e_experiment_shape_threaded_to_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #84 end-to-end: `experiment_shape: regression_check` in
    YAML reaches the wire-format report's top-level
    `experiment_shape` field via RunManifest → run_pipeline →
    project_to_report_v01. WhatifConfig acceptance alone
    (TestExperimentShapeConfig) is necessary but not sufficient — a
    config field that's accepted but not threaded is a silent-zero
    bug. This test pins the full CLI → JSON-on-disk path.
    """
    import json

    monkeypatch.chdir(tmp_path)
    cfg = textwrap.dedent(
        f"""\
        source:
          adapter: stub
        target:
          runner: python:{_RUNNER_FIXTURE_MODULE}:run
        selection:
          baseline_cohort:
            limit: 5
        change:
          system_prompt: e2e regression-check test
        scorer:
          adapter: stub
        decision: {{}}
        reporting:
          profile: default
        timeouts:
          replay_seconds: 5.0
          score_seconds: 5.0
        experiment_shape: regression_check
        """
    )
    cfg_path = tmp_path / "whatifd.config.yaml"
    cfg_path.write_text(cfg, encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, ["fork", "--config", str(cfg_path)])
    # Stub source yields zero traces → Inconclusive (exit 2). The
    # interesting bit is the JSON-on-disk, not the verdict.
    assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE

    # Read the emitted JSON report and assert the experiment_shape
    # field made it through CLI → cfg → manifest → pipeline →
    # projection → wire shape.
    json_files = sorted((tmp_path / "reports").glob("*.json"))
    assert json_files, "no JSON report emitted"
    report = json.loads(json_files[-1].read_text(encoding="utf-8"))
    assert report["experiment_shape"] == "regression_check"


def test_whatif_fork_e2e_default_experiment_shape_is_failure_rescue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Back-compat: a config WITHOUT experiment_shape (v0.1 shape)
    emits `experiment_shape: failure_rescue` in the wire report."""
    import json

    monkeypatch.chdir(tmp_path)
    cfg_path = _write_config(tmp_path)  # _write_config uses no experiment_shape key
    runner = CliRunner()
    result = runner.invoke(app, ["fork", "--config", str(cfg_path)])
    assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE

    json_files = sorted((tmp_path / "reports").glob("*.json"))
    assert json_files
    report = json.loads(json_files[-1].read_text(encoding="utf-8"))
    assert report["experiment_shape"] == "failure_rescue"


def test_whatif_fork_e2e_unknown_adapter_setup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bogus `source.adapter` produces exit 2 + setup-failure
    stderr from the adapter factory, NOT a stack trace.
    Cardinal #1 at the CLI boundary."""
    monkeypatch.chdir(tmp_path)
    cfg = textwrap.dedent(
        f"""\
        source:
          adapter: not_a_real_adapter
        target:
          runner: python:{_RUNNER_FIXTURE_MODULE}:run
        selection:
          failure_cohort:
            limit: 5
          baseline_cohort:
            limit: 5
        change:
          system_prompt: x
        scorer:
          adapter: stub
        decision: {{}}
        reporting:
          profile: default
        timeouts:
          replay_seconds: 5.0
          score_seconds: 5.0
        """
    )
    cfg_path = tmp_path / "whatifd.config.yaml"
    cfg_path.write_text(cfg, encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["fork", "--config", str(cfg_path)])
    assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
    # No artifacts written — pipeline never ran.
    assert not (tmp_path / "reports").exists()


def test_whatif_fork_e2e_bad_runner_target_setup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A malformed `target.runner` reference produces exit 2 +
    runner-loader stderr from the loader, NOT a stack trace."""
    monkeypatch.chdir(tmp_path)
    cfg = textwrap.dedent(
        """\
        source:
          adapter: stub
        target:
          runner: not_a_python_ref
        selection:
          failure_cohort:
            limit: 5
          baseline_cohort:
            limit: 5
        change:
          system_prompt: x
        scorer:
          adapter: stub
        decision: {}
        reporting:
          profile: default
        timeouts:
          replay_seconds: 5.0
          score_seconds: 5.0
        """
    )
    cfg_path = tmp_path / "whatifd.config.yaml"
    cfg_path.write_text(cfg, encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["fork", "--config", str(cfg_path)])
    assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
