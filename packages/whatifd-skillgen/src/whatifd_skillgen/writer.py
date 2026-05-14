"""Write generated adapter code to disk.

``write_skill`` takes the output of ``generate_skill`` and:
1. Writes ``<output_dir>/__init__.py`` (fails if it already exists unless
   ``overwrite=True`` is passed).
2. Returns the path written and the patch instructions for printing.

Config and factory patches are NOT applied automatically — the caller prints
``config_patch_hint`` and ``factory_patch_hint`` and the adapter author applies
them by hand after reviewing. This keeps whatifd-skillgen as a read-only advisor
rather than a mutator of another project's source tree.

All OS-level errors surface as ``SkillGenerationError`` with actionable messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from whatifd_skillgen.errors import SkillGenerationError
from whatifd_skillgen.generator import GeneratedSkill


@dataclass(frozen=True, slots=True)
class WriteResult:
    """Result of a successful ``write_skill`` call."""

    path_written: Path
    config_patch_hint: str
    factory_patch_hint: str


def write_skill(
    output_dir: Path,
    generated: GeneratedSkill,
    *,
    overwrite: bool = False,
) -> WriteResult:
    """Write ``__init__.py`` into ``output_dir``.

    :param output_dir: Directory where ``__init__.py`` is written. Typically
        the package directory inside the new adapter (e.g.
        ``packages/whatifd-myadapter/src/whatifd_myadapter/``).
    :param generated: Output from ``generate_skill``.
    :param overwrite: When ``True``, overwrite an existing ``__init__.py``.
        Default ``False`` raises ``SkillGenerationError`` to protect existing
        implementation work.
    :returns: ``WriteResult`` containing the path written and patch hints.
    :raises SkillGenerationError: If the file already exists (when
        ``overwrite=False``) or on any OS-level write error.
    """
    out_path = output_dir / "__init__.py"

    if out_path.exists() and not overwrite:
        raise SkillGenerationError(
            f"{out_path} already exists. Pass --overwrite to replace it. "
            "Inspect the existing file before overwriting to avoid losing "
            "manual implementation work."
        )

    try:
        out_path.write_text(generated.skill_code, encoding="utf-8")
    except OSError as exc:
        raise SkillGenerationError(
            f"Failed to write {out_path}: {exc}. "
            "Check that the directory exists and is writable."
        ) from exc

    return WriteResult(
        path_written=out_path,
        config_patch_hint=generated.config_patch_hint,
        factory_patch_hint=generated.factory_patch_hint,
    )


__all__ = ["WriteResult", "write_skill"]
