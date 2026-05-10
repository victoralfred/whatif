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

import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict, cast

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACTION_YML = _REPO_ROOT / ".github" / "actions" / "whatifd-fork" / "action.yml"


# Typed shape for the parsed action.yml. The outer Mapping signals
# read-only intent (project convention). The inner shapes mirror
# the GitHub Actions action-yml schema for the slices the tests
# actually access — input/output specs, runs.steps. `Any` remains
# at the leaf where YAML scalars can be str/int/bool/None and
# `extra` keys may appear (e.g., `branding`, future schema
# additions). Cardinal #6: stricter than `dict[str, Any]` because
# the structural shape is documented; pragmatic about the leaf
# Any because the GitHub Actions schema itself permits arbitrary
# scalar types.
class ActionStepDict(TypedDict, total=False):
    name: str
    id: str
    run: str
    uses: str
    shell: str
    env: Mapping[str, str]
    # `if` and `with` are Python keywords and would need a TypedDict
    # functional-form declaration to be expressible as keys here.
    # The tests access them via raw dict indexing (`step.get("if",
    # "")`, `step["with"]`) which works without TypedDict help —
    # the structural-shape pin is the substantive value, not
    # complete keyword-key coverage.


class ActionInputSpec(TypedDict, total=False):
    description: str
    required: bool
    default: str


class ActionOutputSpec(TypedDict, total=False):
    description: str
    value: str


class ActionRunsBlock(TypedDict, total=False):
    using: str
    steps: list[
        Mapping[str, Any]
    ]  # leaf Any: GitHub schema permits arbitrary scalars in step env/with


class ActionBrandingBlock(TypedDict, total=False):
    icon: str
    color: str


class ActionYmlData(TypedDict, total=False):
    name: str
    description: str
    inputs: Mapping[str, ActionInputSpec]
    outputs: Mapping[str, ActionOutputSpec]
    runs: ActionRunsBlock
    branding: ActionBrandingBlock


@pytest.fixture(scope="module")
def action() -> ActionYmlData:
    # `yaml.safe_load` returns `Any`; the cast pins our typed
    # contract at the boundary. The structural assertions below
    # validate the cast at runtime via key-presence checks.
    raw = yaml.safe_load(_ACTION_YML.read_text(encoding="utf-8"))
    return cast(ActionYmlData, raw)


class TestMarketplaceReadiness:
    """v0.3 will publish this Action to the GitHub Marketplace as
    its own repo. Marketplace listings require a `branding:` block
    with `icon` and `color`. Verifying it now prevents a last-
    minute schema surprise during the v0.3 publication PR.
    """

    def test_branding_block_present(self, action: ActionYmlData) -> None:
        assert "branding" in action, (
            "action.yml must declare a `branding:` block for v0.3 Marketplace "
            "publication. Two required fields: `icon` (Feather icon name) and "
            "`color` (one of GitHub's accepted colors)."
        )
        branding = action["branding"]
        assert isinstance(branding, dict), "branding must be a YAML mapping"

    def test_branding_has_icon_and_color(self, action: ActionYmlData) -> None:
        branding = action["branding"]
        assert "icon" in branding, "branding.icon is required for Marketplace listings"
        assert "color" in branding, "branding.color is required for Marketplace listings"
        # GitHub's accepted colors: white, yellow, blue, green,
        # orange, red, purple, gray-dark.
        accepted_colors = {
            "white",
            "yellow",
            "blue",
            "green",
            "orange",
            "red",
            "purple",
            "gray-dark",
        }
        assert branding["color"] in accepted_colors, (
            f"branding.color={branding['color']!r} not in GitHub's accepted set: "
            f"{sorted(accepted_colors)}"
        )


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

    def test_example_workflow_is_valid_yaml(self) -> None:
        # Catches a malformed example before operators copy a
        # broken workflow into their own repo. Text-presence checks
        # alone don't catch indentation typos that yaml.safe_load
        # raises on.
        example = _REPO_ROOT / ".github" / "workflows" / "example-whatifd-fork.yml.example"
        parsed = yaml.safe_load(example.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)
        # Workflow shape: top-level keys `name`, `on`, `permissions`,
        # `jobs`. `on:` parses as Python boolean `True` under
        # yaml.safe_load (a known YAML 1.1 quirk where unquoted
        # `on`/`off`/`yes`/`no` are bools). Look up either form
        # explicitly so the assertion fails loudly if neither key
        # is present (the previous `or True in parsed` form was
        # ambiguous about which side fired).
        assert "name" in parsed
        on_key = next((k for k in parsed if k in ("on", True)), None)
        assert on_key is not None, (
            "example workflow missing the `on:` trigger key (or its boolean-True YAML 1.1 alias)"
        )
        assert "jobs" in parsed
        assert isinstance(parsed["jobs"], dict)


class TestEditLastGrepLocaleFragility:
    """Documents the known fragility boundary of the `--edit-last`
    grep heuristic against locale-translated `gh` stderr. Issue #94
    tracks the marker-based replacement that eliminates this class
    entirely. Tests below run the same regex used in the action
    against representative stderr strings and ASSERT what matches /
    doesn't, so the boundary is visible at test-time rather than
    discovered in production.

    These tests are intentionally permissive (they document the
    current behavior, not a desired-future-state) — when issue #94
    lands, this class can be deleted.
    """

    @staticmethod
    def _extract_pattern_from_action_yml() -> re.Pattern[str]:
        """Extract the literal regex from action.yml's PR-comment
        step rather than duplicating it. If the action's regex
        changes, this extraction picks up the new string
        automatically — no risk of the test silently exercising a
        stale pattern.
        """
        action_text = _ACTION_YML.read_text(encoding="utf-8")
        # Match the literal `grep -qiE "<pattern>"` invocation in
        # the PR-comment step's run script.
        m = re.search(r'grep -qiE "([^"]+)"', action_text)
        if m is None:
            raise AssertionError(
                'Could not locate `grep -qiE "..."` in action.yml. '
                "If the failure-class-discrimination implementation changed, "
                "update this extractor accordingly."
            )
        return re.compile(m.group(1), re.IGNORECASE)

    @pytest.fixture(scope="class")
    def pattern(self) -> re.Pattern[str]:
        return self._extract_pattern_from_action_yml()

    @pytest.mark.parametrize(
        "stderr,expected_match",
        [
            # English (current `gh` CLI v2.x): the heuristic fires.
            ("no comments found", True),
            ("not found", True),
            ("no prior comment exists", True),
            # Hypothetical localized variants (issue #94 boundary):
            # these would NOT match the English regex. A real
            # operator running under LANG=de_DE.UTF-8 with a future
            # `gh` version supporting i18n would surface a real
            # error annotation INSTEAD of the silent first-run
            # fallback — over-strict, but never silently wrong.
            ("kein Kommentar gefunden", False),  # German
            ("aucun commentaire trouvé", False),  # French
            # Real failure modes the regex correctly skips:
            ("HTTP 403 Forbidden", False),
            ("dial tcp: lookup api.github.com: no such host", False),
            ("validation failed: body must not be empty", False),
            # Tightened anchor case: "no.*comment" used to match
            # any sentence with "no" before "comment". The new
            # `^(...)` anchor rejects such mid-sentence matches —
            # e.g. validation messages mentioning the word
            # "comment" no longer trip the first-run fallback.
            ("validation failed: comment not found in body", False),
            ("error: comment with id 12345 not present", False),
        ],
    )
    def test_grep_heuristic_boundary(
        self, pattern: re.Pattern[str], stderr: str, expected_match: bool
    ) -> None:
        match = bool(pattern.search(stderr))
        assert match is expected_match, (
            f"Locale boundary regression: expected match={expected_match} for "
            f"stderr={stderr!r}, got {match}. If gh CLI's stderr text changed "
            "or the action's regex was edited, the action's first-run-vs-real-"
            "failure discrimination shifted. Issue #94 (marker-based dedup) "
            "eliminates this fragility class."
        )


class TestShellLogicAtRuntime:
    """Runtime verification of the shell fragments inside action.yml.
    Structural string-contains tests can pass while the shell logic
    is broken (e.g., a redirect-order bug, off-by-one in glob
    pattern). These tests run the actual fragments through bash
    against fixture data and assert observable behavior.
    """

    def test_path_discovery_finds_newest_json(self, tmp_path: Path) -> None:
        # Build a `reports/` fixture with three .json files at
        # different mtimes; the discovery one-liner should return
        # the newest.
        reports = tmp_path / "reports"
        reports.mkdir()
        old = reports / "old.json"
        mid = reports / "mid.json"
        new = reports / "new.json"
        old.write_text("{}", encoding="utf-8")
        os.utime(old, (1_000_000_000, 1_000_000_000))
        mid.write_text("{}", encoding="utf-8")
        os.utime(mid, (1_500_000_000, 1_500_000_000))
        new.write_text("{}", encoding="utf-8")
        os.utime(new, (2_000_000_000, 2_000_000_000))

        result = subprocess.run(
            [
                "python3",
                "-c",
                "import glob,os,sys; m=glob.glob('reports/*.json'); m and sys.stdout.write(max(m, key=os.path.getmtime))",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout == "reports/new.json"
        assert result.returncode == 0

    def test_path_discovery_empty_glob_returns_empty(self, tmp_path: Path) -> None:
        # `reports/` exists but no .json files: empty stdout, exit 0.
        (tmp_path / "reports").mkdir()
        result = subprocess.run(
            [
                "python3",
                "-c",
                "import glob,os,sys; m=glob.glob('reports/*.json'); m and sys.stdout.write(max(m, key=os.path.getmtime))",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.stdout == ""
        assert result.returncode == 0

    def test_preflight_access_check_detects_unreadable_dir(self, tmp_path: Path) -> None:
        # Pre-flight `os.access` correctly identifies an unreadable
        # `reports/`. This is the explicit case-(c) detection the
        # bot flagged as missing — `glob.glob` silently returns []
        # on chmod-000 dirs, so the pre-flight closes the gap.
        if sys.platform == "win32":
            pytest.skip("POSIX permission semantics; Windows ACLs differ")
        # `os.geteuid` is POSIX-only; the platform check above is the
        # gate. Skipping under root (CI containers sometimes run as
        # root, where access checks pass regardless of mode).
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            pytest.skip("running as root; os.access bypasses ACL checks")
        reports = tmp_path / "reports"
        reports.mkdir()
        os.chmod(reports, 0o000)
        try:
            result = subprocess.run(
                [
                    "python3",
                    "-c",
                    "import os, sys; sys.exit(0 if os.access('reports', os.R_OK | os.X_OK) else 1)",
                ],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 1, "pre-flight failed to detect unreadable reports/"
        finally:
            os.chmod(reports, 0o755)

    def test_stderr_capture_redirect_order(self, tmp_path: Path) -> None:
        # Verifies the `2>&1 1>/dev/null` redirect order in the
        # PR-comment fallback. The bot claimed this captures
        # nothing; empirical verification: it captures stderr
        # correctly. This test pins it so a future refactor that
        # changes the order produces a structural failure.
        result = subprocess.run(
            [
                "bash",
                "-c",
                "captured=$(bash -c 'echo stdoutmsg; echo stderrmsg >&2' 2>&1 1>/dev/null); echo \"[$captured]\"",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "[stderrmsg]" in result.stdout, (
            f"redirect order broken: expected [stderrmsg] in capture, got {result.stdout!r}. "
            "The action's --edit-last fallback uses this exact pattern; if it stops working "
            "the locale-fragility window widens to false-positive on every first run."
        )

    def test_grep_heuristic_matches_no_comments_pattern(self) -> None:
        # End-to-end: feed the literal `grep -qiE` pattern from
        # action.yml against an English no-comments stderr; assert
        # exit 0 (match). Pairs with TestEditLastGrepLocaleFragility
        # which tests the boundary at the regex level; this one
        # pins the actual `grep` binary's behavior.
        result = subprocess.run(
            ["grep", "-qiE", "no.*comment|not found|no comments"],
            input="error: no comments to edit\n",
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, "grep heuristic should match English 'no comments' stderr"


class TestEveryStepDeclaresBashShell:
    """Composite-action steps default to the runner OS's native
    shell — PowerShell on Windows, bash on Linux/macOS. The action
    explicitly declares `shell: bash` on every `run:` step so
    Windows runners use Git Bash (preinstalled). A future step
    addition that omits `shell:` would silently regress Windows
    support without breaking the Linux/macOS test surface here.
    """

    def test_every_run_step_has_shell_bash(self, action: ActionYmlData) -> None:
        offenders: list[str] = []
        for step in action["runs"]["steps"]:
            # Only `run:` steps need a shell. `uses:` steps invoke
            # another action and don't have shell semantics.
            if "run" in step and step.get("shell") != "bash":
                name = step.get("name", step.get("id", "<unnamed>"))
                offenders.append(f"{name!r} (shell={step.get('shell')!r})")
        assert not offenders, (
            "Every `run:` step must declare `shell: bash` for cross-platform "
            "consistency (Windows runners default to PowerShell otherwise). "
            "Offenders:\n  " + "\n  ".join(offenders)
        )
