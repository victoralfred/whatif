"""Phase I integration tests — `whatifd-fork` composite GitHub Action.

The action is a thin shell-script wrapper; the tested surface is:

1. The `action.yml` is structurally valid YAML and declares the
   inputs/outputs/runs sections the README documents.
2. The exit-code → verdict mapping covers the CLI's three outcomes.
3. The PR-comment guard fires only on `pull_request` events.
4. The `fail-on-dont-ship` guard fires only when exit_code != '0'.

We don't run the action end-to-end here — that requires a real GitHub
runner. The structural pins catch the most common refactor regressions
(missing input/output, broken guard expression) without that infra.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACTION_YML = _REPO_ROOT / ".github" / "actions" / "whatifd-fork" / "action.yml"

# `Mapping[str, Any]` (not `dict[str, Any]`) signals read-only
# intent across the test fixture boundary — matches the project
# convention used in adapter constructors (e.g.,
# `LangfuseTraceSource.list_kwargs: Mapping[str, Any]`). Tests
# never mutate the parsed action.yml; the type signature reflects
# that. `yaml.safe_load` itself returns `Any`, so the inner Any
# can't be narrowed without writing a TypedDict mirroring every
# action-yml key — that's maintenance overhead without a
# doctrinal payoff.
ActionYmlData = Mapping[str, Any]


@pytest.fixture(scope="module")
def action() -> ActionYmlData:
    return yaml.safe_load(_ACTION_YML.read_text(encoding="utf-8"))


class TestActionStructure:
    def test_action_yml_exists(self) -> None:
        assert _ACTION_YML.is_file(), f"action.yml missing at {_ACTION_YML}"

    def test_top_level_keys(self, action: ActionYmlData) -> None:
        for key in ("name", "description", "inputs", "outputs", "runs"):
            assert key in action, f"action.yml missing top-level key: {key}"

    def test_runs_using_composite(self, action: ActionYmlData) -> None:
        assert action["runs"]["using"] == "composite", (
            "Action must be a composite action — the v0.2 plan calls for a "
            "thin wrapper, not a Docker action."
        )

    def test_runs_has_steps(self, action: ActionYmlData) -> None:
        steps = action["runs"]["steps"]
        assert isinstance(steps, list) and len(steps) >= 2, (
            "Composite action needs at least 2 steps (run whatifd fork + "
            "PR comment / fail-handler)."
        )

    def test_runs_steps_is_list_not_map(self, action: ActionYmlData) -> None:
        # YAML structural pin: `runs.steps` must be a sequence (list),
        # not a mapping (dict). A typo that drops the `- ` prefix
        # silently parses as a key-value pair under `steps:` and
        # GitHub Actions rejects the action at workflow-runtime.
        # Catch that here at test-time instead.
        assert isinstance(action["runs"]["steps"], list), (
            "runs.steps must be a YAML sequence (list of step mappings). "
            "Got a dict — likely a missing `- ` prefix on a step key."
        )

    def test_inputs_and_outputs_are_maps_of_maps(self, action: ActionYmlData) -> None:
        # YAML structural pin: each input / output is a mapping with
        # `description`, optional `default`, etc. A typo that turns
        # one into a plain string would silently break the workflow
        # caller's input-passing.
        for section in ("inputs", "outputs"):
            value = action[section]
            assert isinstance(value, dict), f"{section} must be a YAML mapping"
            for name, spec in value.items():
                assert isinstance(spec, dict), (
                    f"{section}.{name} must be a mapping (spec with "
                    f"description / default), got {type(spec).__name__}"
                )
                assert "description" in spec, (
                    f"{section}.{name} missing required `description` field"
                )


class TestInputs:
    """Every input the README documents must exist in action.yml,
    with the documented default."""

    @pytest.mark.parametrize(
        "name,default",
        [
            ("config", "whatifd.config.yaml"),
            ("profile", ""),
            ("comment-on-pr", "true"),
            ("fail-on-dont-ship", "true"),
        ],
    )
    def test_input_default(self, action: ActionYmlData, name: str, default: str) -> None:
        inputs = action["inputs"]
        assert name in inputs, f"action.yml missing input: {name}"
        assert inputs[name].get("default") == default, (
            f"input {name} default drifted: action.yml={inputs[name].get('default')!r}, "
            f"README documents {default!r}"
        )

    def test_github_token_input_default_pinned(self, action: ActionYmlData) -> None:
        # The default IS a YAML expression string `${{ github.token }}`
        # — yaml.safe_load preserves it verbatim because GitHub
        # expressions aren't standard YAML constructs. Pin the
        # literal so a future drift (e.g., default accidentally
        # blanked, or changed to a hardcoded PAT) surfaces here.
        assert "github-token" in action["inputs"]
        assert action["inputs"]["github-token"].get("default") == "${{ github.token }}", (
            "github-token default drifted away from `${{ github.token }}`. "
            "Callers expect the workflow's automatic token; a blank or "
            "hardcoded default would silently change comment-author identity "
            "or break the comment step entirely."
        )


class TestOutputs:
    """Every output the README documents must exist in action.yml
    and reference a step output."""

    @pytest.mark.parametrize(
        "name",
        ["verdict", "exit-code", "report-json", "report-md"],
    )
    def test_output_present(self, action: ActionYmlData, name: str) -> None:
        outputs = action["outputs"]
        assert name in outputs, f"action.yml missing output: {name}"
        # The value field must reference a step output expression.
        value = outputs[name].get("value", "")
        assert "${{ steps." in value, (
            f"output {name} value must reference a step output, got: {value!r}"
        )


class TestIfExpressionWrapping:
    """Multi-line `if:` expressions with `&&` operators must use
    `${{ }}` interpolation per GitHub's safe-form recommendation.
    A bare multi-line `if: |\\n  expr1\\n  && expr2` block scalar
    can produce ambiguous evaluation depending on the runner
    version; `${{ }}` is the explicit, documented form.
    """

    @staticmethod
    def _step_by_name(action: ActionYmlData, name_prefix: str) -> Mapping[str, Any]:
        for step in action["runs"]["steps"]:
            if step.get("name", "").startswith(name_prefix):
                return step
        raise AssertionError(f"step starting with {name_prefix!r} not found")

    def test_pr_comment_if_uses_interpolation_wrapper(self, action: ActionYmlData) -> None:
        step = self._step_by_name(action, "Post PR comment")
        guard = step.get("if", "")
        assert guard.startswith("${{") and guard.rstrip().endswith("}}"), (
            "PR-comment step's `if:` must be wrapped in `${{ ... }}` for "
            "explicit expression evaluation. Bare multi-line `if:` blocks "
            "with `&&` operators are evaluated ambiguously across runner "
            "versions; the wrapper makes the intent unambiguous."
        )

    def test_fail_step_if_uses_interpolation_wrapper(self, action: ActionYmlData) -> None:
        step = self._step_by_name(action, "Fail on Don't Ship")
        guard = step.get("if", "")
        assert guard.startswith("${{") and guard.rstrip().endswith("}}"), (
            "fail-on-dont-ship step's `if:` must be wrapped in `${{ ... }}`."
        )


class TestPathDiscoveryErrorHandling:
    """Cardinal #1: path discovery must distinguish "no reports/
    directory" (legitimate empty case) from "reports/ exists but
    unreadable" (real bug → surface ::error + exit non-zero).
    """

    def test_discover_propagates_real_errors(self, action: ActionYmlData) -> None:
        for step in action["runs"]["steps"]:
            if step.get("id") == "fork":
                run = step["run"]
                # The discovery script must surface a real error
                # via ::error annotation + non-zero exit, not
                # silently swallow with `2>/dev/null || true`.
                assert "::error title=whatifd path discovery" in run, (
                    "Path discovery must surface real errors (PermissionError, "
                    "I/O failures distinct from missing-directory) as ::error "
                    "annotations + non-zero exit. Cardinal #1 — failure-as-data."
                )
                # And no blanket `2>/dev/null || true` swallow.
                assert "2>/dev/null || true" not in run, (
                    "Blanket `2>/dev/null || true` swallow on path discovery "
                    "masks real errors. Use the discriminating shell from the "
                    "current implementation."
                )
                return
        raise AssertionError("fork step not found")


class TestStepGuards:
    """The PR-comment + fail-on-dont-ship steps have load-bearing
    `if:` guards. A future refactor that drops the guard would
    silently post comments on push events (noisy) or fail every
    workflow (broken)."""

    @staticmethod
    def _step_by_name(action: ActionYmlData, name_prefix: str) -> Mapping[str, Any]:
        for step in action["runs"]["steps"]:
            if step.get("name", "").startswith(name_prefix):
                return step
        raise AssertionError(f"step starting with {name_prefix!r} not found")

    def test_pr_comment_guard_includes_pull_request_event(self, action: ActionYmlData) -> None:
        step = self._step_by_name(action, "Post PR comment")
        guard = step.get("if", "")
        assert "github.event_name == 'pull_request'" in guard, (
            "PR-comment step must guard on github.event_name == 'pull_request' "
            "so push events don't trigger spurious comments."
        )
        assert "inputs.comment-on-pr == 'true'" in guard, (
            "PR-comment step must respect the `comment-on-pr` input toggle."
        )

    def test_pr_comment_guard_skips_when_no_report(self, action: ActionYmlData) -> None:
        step = self._step_by_name(action, "Post PR comment")
        guard = step.get("if", "")
        assert "steps.fork.outputs.report_md != ''" in guard, (
            "PR-comment step must skip when no Markdown report was emitted "
            "(setup-failure path, where the CLI exits before writing artifacts)."
        )

    def test_fail_step_guard_respects_input_and_exit_code(self, action: ActionYmlData) -> None:
        step = self._step_by_name(action, "Fail on Don't Ship")
        guard = step.get("if", "")
        assert "inputs.fail-on-dont-ship == 'true'" in guard, (
            "fail-on-dont-ship step must respect the input toggle."
        )
        assert "steps.fork.outputs.exit_code != '0'" in guard, (
            "fail-on-dont-ship step must only fire when the CLI exit code is non-zero."
        )


class TestExitCodeMapping:
    """The shell script in the `Run whatifd fork` step maps exit
    codes 0/1/2 to verdict strings ship/dont_ship/inconclusive.
    A future contributor adding a new exit code (or renaming a
    verdict) must update both the CLI and this mapping in lockstep.
    """

    @staticmethod
    def _fork_step_run(action: ActionYmlData) -> str:
        for step in action["runs"]["steps"]:
            if step.get("id") == "fork":
                return step["run"]
        raise AssertionError("fork step not found")

    def test_exit_zero_maps_to_ship(self, action: ActionYmlData) -> None:
        run = self._fork_step_run(action)
        assert '0) verdict="ship"' in run

    def test_exit_one_maps_to_dont_ship(self, action: ActionYmlData) -> None:
        run = self._fork_step_run(action)
        assert '1) verdict="dont_ship"' in run

    def test_exit_other_maps_to_inconclusive(self, action: ActionYmlData) -> None:
        run = self._fork_step_run(action)
        # Exit 2 (and any future non-0/1) → inconclusive. Pinned
        # via the `*)` catch-all branch.
        assert '*) verdict="inconclusive"' in run


class TestCrossPlatformPathDiscovery:
    """Path discovery must work on Linux and macOS runners. Windows
    support is conditional: the action declares `shell: bash`
    everywhere, which works on `windows-latest` because Git Bash
    is preinstalled and the runner respects the explicit shell
    override. PowerShell-only runners would not work; documented
    in the README's status table.

    GNU `find -printf` is not available on macOS (BSD find);
    `stat`'s format spec diverges between GNU and BSD. Python is
    on every GitHub runner.
    """

    def test_path_discovery_does_not_use_gnu_find_printf(self, action: ActionYmlData) -> None:
        for step in action["runs"]["steps"]:
            if step.get("id") == "fork":
                run = step["run"]
                assert "-printf" not in run, (
                    "Path discovery must not use `find -printf` — that's GNU-only "
                    "and silently produces empty output on macOS runners (BSD "
                    "find). Use the Python fallback (portable across every GitHub "
                    "runner)."
                )
                # And the Python fallback must actually be present.
                assert "python3 -c" in run, (
                    "Path discovery must use a Python one-liner for portability "
                    "across Linux / macOS / Windows runners."
                )
                return
        raise AssertionError("fork step not found")


class TestPRCommentDeduplication:
    """Repeated pushes to the same PR must produce one rolling
    whatifd comment, not a stack. `gh pr comment --edit-last`
    updates the most recent comment authored by the token; if no
    prior comment exists, it falls back to creating a new one.
    """

    def test_pr_comment_step_uses_edit_last(self, action: ActionYmlData) -> None:
        for step in action["runs"]["steps"]:
            if step.get("name", "").startswith("Post PR comment"):
                run = step["run"]
                assert "--edit-last" in run, (
                    "PR-comment step must use `gh pr comment --edit-last` so "
                    "repeated pushes update the existing whatifd comment instead "
                    "of accumulating a stack."
                )
                return
        raise AssertionError("Post PR comment step not found")

    def test_pr_comment_step_distinguishes_edit_failure_classes(
        self, action: ActionYmlData
    ) -> None:
        # Cardinal #1: the fallback path must distinguish "no prior
        # comment" (legitimate first-run case → fall through and
        # create) from real failures (403, network, validation →
        # surface non-zero). A blanket `|| gh pr comment ...` would
        # silently create a duplicate on a 403, masking the real
        # failure.
        for step in action["runs"]["steps"]:
            if step.get("name", "").startswith("Post PR comment"):
                run = step["run"]
                assert "edit_status" in run, (
                    "PR-comment step must capture --edit-last's exit status "
                    "into `edit_status` so the fallback path can distinguish "
                    "first-run from real failure."
                )
                # Tautological-or-fix: the prior version had two
                # branches both checking the same string. Pin the
                # single shape that's actually used.
                assert 'exit "$edit_status"' in run, (
                    "PR-comment step must surface non-first-run failures by "
                    "exiting with the captured edit_status. Cardinal #1: "
                    "structured failure-as-data, not silent retry."
                )
                return
        raise AssertionError("Post PR comment step not found")


class TestNoHardcodedTmpPath:
    """The PR-comment step uses a per-job temp directory rather
    than a hardcoded `/tmp` path — concurrent matrix-job collisions
    would silently corrupt comment bodies otherwise. This test
    pins the structural guarantee documented in the cascade catalog.
    """

    def test_pr_comment_step_uses_runner_temp(self, action: ActionYmlData) -> None:
        for step in action["runs"]["steps"]:
            if step.get("name", "").startswith("Post PR comment"):
                run = step["run"]
                # `RUNNER_TEMP` is GitHub Actions' per-job temp
                # directory; `mktemp -d` is the documented fallback
                # for self-hosted runners that don't export it.
                assert "$RUNNER_TEMP" in run or "${RUNNER_TEMP" in run, (
                    "PR-comment step must reference $RUNNER_TEMP for matrix-safe "
                    "temp file paths. A hardcoded /tmp path would silently collide "
                    "across concurrent matrix jobs on the same runner."
                )
                # And no hardcoded `/tmp/` path that bypasses the
                # safety pattern.
                assert "/tmp/whatifd-pr-comment" not in run, (
                    "PR-comment step contains a hardcoded /tmp path. Use "
                    "$RUNNER_TEMP (or `mktemp -d` fallback) so concurrent matrix "
                    "jobs don't collide."
                )
                return
        raise AssertionError("Post PR comment step not found")


class TestFailStepDoesNotDuplicateAnnotation:
    """The fork step already emits `::error` for dont_ship and
    inconclusive verdicts. The fail step's job is to set the exit
    code, not re-emit the annotation — duplicates would show up
    twice in the Actions UI annotation list.
    """

    def test_fail_step_has_no_error_echo(self, action: ActionYmlData) -> None:
        for step in action["runs"]["steps"]:
            if step.get("name", "").startswith("Fail on Don't Ship"):
                run = step["run"]
                assert "::error" not in run, (
                    "Fail step must not emit ::error — the fork step already "
                    "emitted one for dont_ship/inconclusive verdicts. A duplicate "
                    "annotation shows up twice in the Actions UI."
                )
                return
        raise AssertionError("Fail step not found")


class TestExampleWorkflow:
    def test_example_workflow_present(self) -> None:
        # The .example suffix prevents GitHub Actions from running
        # this workflow on the whatifd repo itself (which lacks the
        # adapter credentials the example uses).
        example = _REPO_ROOT / ".github" / "workflows" / "example-whatifd-fork.yml.example"
        assert example.is_file()

    def test_example_uses_local_action_path(self) -> None:
        example = _REPO_ROOT / ".github" / "workflows" / "example-whatifd-fork.yml.example"
        text = example.read_text(encoding="utf-8")
        # Repo-relative path so the example works as a self-contained
        # demonstration. Operators copying the workflow can either
        # vendor the action or switch to a published-Marketplace
        # reference once Phase I.x ships that.
        assert "uses: ./.github/actions/whatifd-fork" in text
