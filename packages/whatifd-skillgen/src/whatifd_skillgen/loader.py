"""Parse a ``skill.md`` file into a ``(SkillManifest, body_str)`` tuple.

A ``skill.md`` file uses YAML frontmatter fenced by ``---`` lines, followed
by a markdown body that becomes the implementation-context section in the
generated docstring.

```
---
name: my_adapter
description: "Does something useful."
kind: scorer
---

## What this adapter does
<markdown prose describing the adapter>
```

The loader:
1. Reads the file (FileNotFoundError → SkillManifestError with path hint).
2. Splits on the ``---`` fence (missing/malformed fence → SkillManifestError).
3. Parses the YAML frontmatter via ``yaml.safe_load`` (YAML errors → SkillManifestError).
4. Validates the parsed dict as ``SkillManifest`` (Pydantic errors → SkillManifestError).
5. Returns ``(manifest, body)`` where ``body`` is the raw markdown string.

All failures surface as typed ``SkillManifestError`` with actionable messages.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from whatifd_skillgen.errors import SkillManifestError
from whatifd_skillgen.schema import SkillManifest


def load_skill(skill_md_path: Path) -> tuple[SkillManifest, str]:
    """Parse and validate a ``skill.md`` file.

    :param skill_md_path: Absolute or relative path to the ``skill.md`` file.
    :returns: ``(manifest, body)`` — validated manifest and the raw markdown body.
    :raises SkillManifestError: On any read, parse, or validation failure.
    """
    try:
        raw = skill_md_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SkillManifestError(
            f"skill.md not found: {skill_md_path}. "
            "Create the file with YAML frontmatter. "
            "See .claude/skills/capabilities/templates/skill-template.md for the template."
        )
    except OSError as exc:
        raise SkillManifestError(
            f"Error reading {skill_md_path}: {exc}. Check file permissions."
        ) from exc

    frontmatter_str, body = _split_frontmatter(raw, skill_md_path)
    frontmatter_dict = _parse_yaml(frontmatter_str, skill_md_path)
    manifest = _validate_manifest(frontmatter_dict, skill_md_path)
    return manifest, body


def _split_frontmatter(raw: str, path: Path) -> tuple[str, str]:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillManifestError(
            f"{path}: skill.md must begin with a YAML frontmatter block "
            "fenced by '---' lines. Example:\n"
            "---\n"
            "name: my_adapter\n"
            "kind: scorer\n"
            "---\n"
        )
    close_idx: int | None = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            close_idx = i
            break
    if close_idx is None:
        raise SkillManifestError(
            f"{path}: YAML frontmatter block is not closed. "
            "Add a '---' line after the last frontmatter key."
        )
    frontmatter_str = "\n".join(lines[1:close_idx])
    body_str = "\n".join(lines[close_idx + 1:]).strip()
    return frontmatter_str, body_str


def _parse_yaml(frontmatter_str: str, path: Path) -> object:
    try:
        parsed = yaml.safe_load(frontmatter_str)
    except yaml.YAMLError as exc:
        raise SkillManifestError(
            f"{path}: YAML frontmatter parse error: {exc}. "
            "Ensure the frontmatter is valid YAML (no tabs, proper indentation)."
        ) from exc
    if not isinstance(parsed, dict):
        raise SkillManifestError(
            f"{path}: YAML frontmatter must be a mapping (key: value pairs). "
            f"Got {type(parsed).__name__!r}."
        )
    return parsed


def _validate_manifest(frontmatter_dict: object, path: Path) -> SkillManifest:
    try:
        return SkillManifest.model_validate(frontmatter_dict)
    except ValidationError as exc:
        errors = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) if err["loc"] else "<root>"
            errors.append(f"    {loc}: {err['msg']}")
        raise SkillManifestError(
            f"{path}: skill manifest validation failed:\n"
            + "\n".join(errors)
            + "\nSee .claude/skills/capabilities/SKILL.md for the full schema."
        ) from exc


__all__ = ["load_skill"]
