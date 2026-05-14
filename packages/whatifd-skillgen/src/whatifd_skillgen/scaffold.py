"""Orchestrate the full skill scaffolding pipeline.

``scaffold_skill(skill_dir)`` runs:
    loader → generator → writer

and returns a ``ScaffoldResult``. All typed errors from the sub-layers
(``SkillManifestError``, ``SkillGenerationError``) propagate unchanged so the
CLI can present them with consistent formatting and exit codes.

This is the public entry point for programmatic use (tests, scripts).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from whatifd_skillgen.generator import generate_skill
from whatifd_skillgen.loader import load_skill
from whatifd_skillgen.schema import SkillManifest
from whatifd_skillgen.writer import WriteResult, write_skill


@dataclass(frozen=True, slots=True)
class ScaffoldResult:
    """Result of a ``scaffold_skill`` call."""

    manifest: SkillManifest
    write_result: WriteResult

    @property
    def path_written(self) -> Path:
        return self.write_result.path_written

    @property
    def config_patch_hint(self) -> str:
        return self.write_result.config_patch_hint

    @property
    def factory_patch_hint(self) -> str:
        return self.write_result.factory_patch_hint


def scaffold_skill(
    skill_dir: Path,
    *,
    overwrite: bool = False,
) -> ScaffoldResult:
    """Generate adapter code from ``<skill_dir>/skill.md``.

    Reads ``<skill_dir>/skill.md``, validates the manifest, generates
    protocol-compliant adapter code, and writes ``<skill_dir>/__init__.py``.

    The ``skill_dir`` should be the adapter package's source directory (e.g.
    ``packages/whatifd-myadapter/src/whatifd_myadapter/``), not a directory
    inside whatifd's own source tree.

    :param skill_dir: Directory containing ``skill.md``. The generated
        ``__init__.py`` is written to the same directory.
    :param overwrite: When ``True``, overwrite an existing ``__init__.py``.
    :returns: ``ScaffoldResult`` with the manifest and write result.
    :raises SkillManifestError: On parse or validation failure.
    :raises SkillGenerationError: On template rendering or file-write failure.
    """
    manifest, body = load_skill(skill_dir / "skill.md")
    generated = generate_skill(manifest, body)
    result = write_skill(skill_dir, generated, overwrite=overwrite)
    return ScaffoldResult(manifest=manifest, write_result=result)


__all__ = ["ScaffoldResult", "scaffold_skill"]
