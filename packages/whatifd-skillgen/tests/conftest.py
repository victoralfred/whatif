"""Shared fixtures for whatifd-skillgen tests."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from whatifd_skillgen.schema import EnvVarSpec, ParameterSpec, SkillManifest


@pytest.fixture()
def minimal_scorer_manifest() -> SkillManifest:
    return SkillManifest(
        name="my_scorer",
        description="A test scorer.",
        kind="scorer",
    )


@pytest.fixture()
def full_scorer_manifest() -> SkillManifest:
    return SkillManifest(
        name="my_scorer",
        description="A test scorer.",
        kind="scorer",
        version="0.2",
        env_vars=[EnvVarSpec(name="MY_API_KEY", required=True, description="API key.")],
        parameters=[
            ParameterSpec(name="model_id", type="str", required=True, description="Model."),
            ParameterSpec(
                name="timeout", type="float", required=False, default="30.0",
                description="Timeout in seconds.",
            ),
        ],
    )


@pytest.fixture()
def minimal_tracer_manifest() -> SkillManifest:
    return SkillManifest(
        name="my_tracer",
        description="A test tracer.",
        kind="tracer",
    )


@pytest.fixture()
def minimal_runner_manifest() -> SkillManifest:
    return SkillManifest(
        name="my_runner",
        description="A test runner.",
        kind="runner",
    )


@pytest.fixture()
def skill_dir(tmp_path: Path) -> Path:
    """A temporary directory containing a minimal valid skill.md."""
    skill_md = textwrap.dedent("""\
        ---
        name: test_adapter
        description: "A test adapter."
        kind: scorer
        ---

        ## What this adapter does

        Just a test.
    """)
    (tmp_path / "skill.md").write_text(skill_md, encoding="utf-8")
    return tmp_path
