"""Phase 10.4 end-to-end CLI smoke: `whatif fork` runs through.

Constructs a minimal whatif config (stub source + stub scorer +
test-fixture runner), invokes the typer CLI via `CliRunner`, and
asserts the exit code, stderr/stdout, and that the JSON+Markdown
artifacts were written. This is the proof that the CLI dispatcher
in `src/whatif/cli.py::_run_fork_pipeline` actually wires the
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

from whatif.cli import EXIT_INCONCLUSIVE_OR_SETUP_FAILURE, app
from whatif.contract import ReplayConfig, ReplayOutput, ToolCache, TraceInput

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
    path = tmp_path / "whatif.config.yaml"
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
    cfg_path = tmp_path / "whatif.config.yaml"
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
    cfg_path = tmp_path / "whatif.config.yaml"
    cfg_path.write_text(cfg, encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["fork", "--config", str(cfg_path)])
    assert result.exit_code == EXIT_INCONCLUSIVE_OR_SETUP_FAILURE
