"""Loader tests.

Pins:
- Valid skill.md parses correctly
- Missing file raises SkillManifestError (not FileNotFoundError)
- Malformed YAML raises SkillManifestError (not yaml.YAMLError)
- Missing frontmatter fence raises SkillManifestError
- Unclosed frontmatter fence raises SkillManifestError
- Pydantic validation failure raises SkillManifestError (not ValidationError)
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from whatifd_skillgen.errors import SkillManifestError
from whatifd_skillgen.loader import load_skill
from whatifd_skillgen.schema import SkillManifest


def write_skill_md(directory: Path, content: str) -> Path:
    path = directory / "skill.md"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


class TestLoadSkillValid:
    def test_minimal_scorer(self, tmp_path: Path) -> None:
        path = write_skill_md(tmp_path, """\
            ---
            name: my_scorer
            description: "A scorer."
            kind: scorer
            ---
        """)
        manifest, body = load_skill(path)
        assert isinstance(manifest, SkillManifest)
        assert manifest.name == "my_scorer"
        assert manifest.kind == "scorer"
        assert body == ""

    def test_body_is_returned(self, tmp_path: Path) -> None:
        path = write_skill_md(tmp_path, """\
            ---
            name: my_tracer
            description: "A tracer."
            kind: tracer
            ---

            ## What it does

            Something useful.
        """)
        _, body = load_skill(path)
        assert "Something useful" in body

    def test_parameters_parsed(self, tmp_path: Path) -> None:
        path = write_skill_md(tmp_path, """\
            ---
            name: my_scorer
            description: "A scorer."
            kind: scorer
            parameters:
              - name: model_id
                type: str
                required: true
                description: "Model."
            ---
        """)
        manifest, _ = load_skill(path)
        assert len(manifest.parameters) == 1
        assert manifest.parameters[0].name == "model_id"


class TestLoadSkillErrors:
    def test_missing_file_raises_manifest_error(self, tmp_path: Path) -> None:
        with pytest.raises(SkillManifestError, match="not found"):
            load_skill(tmp_path / "nonexistent.md")

    def test_missing_file_does_not_leak_file_not_found_error(self, tmp_path: Path) -> None:
        with pytest.raises(SkillManifestError):
            load_skill(tmp_path / "nonexistent.md")

    def test_missing_frontmatter_fence_raises(self, tmp_path: Path) -> None:
        path = write_skill_md(tmp_path, """\
            name: my_scorer
            description: "A scorer."
            kind: scorer
        """)
        with pytest.raises(SkillManifestError, match="frontmatter"):
            load_skill(path)

    def test_unclosed_frontmatter_raises(self, tmp_path: Path) -> None:
        path = (tmp_path / "skill.md")
        path.write_text("---\nname: my_scorer\ndescription: x\nkind: scorer\n", encoding="utf-8")
        with pytest.raises(SkillManifestError, match="not closed"):
            load_skill(path)

    def test_malformed_yaml_raises_manifest_error(self, tmp_path: Path) -> None:
        path = (tmp_path / "skill.md")
        path.write_text("---\n: invalid: yaml:\n---\n", encoding="utf-8")
        with pytest.raises(SkillManifestError):
            load_skill(path)

    def test_invalid_manifest_raises_manifest_error_not_validation_error(
        self, tmp_path: Path
    ) -> None:
        path = write_skill_md(tmp_path, """\
            ---
            name: my-scorer
            description: "A scorer."
            kind: scorer
            ---
        """)
        with pytest.raises(SkillManifestError, match="validation failed"):
            load_skill(path)

    def test_unknown_key_raises_manifest_error(self, tmp_path: Path) -> None:
        path = write_skill_md(tmp_path, """\
            ---
            name: my_scorer
            description: "A scorer."
            kind: scorer
            surprise: "bad"
            ---
        """)
        with pytest.raises(SkillManifestError, match="validation failed"):
            load_skill(path)
