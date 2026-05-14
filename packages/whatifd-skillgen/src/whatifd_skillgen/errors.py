"""Typed errors for the whatifd-skillgen scaffolding tool.

All expected failures surface as one of these typed exceptions with an
actionable message. No raw exceptions escape the public API boundary.
"""

from __future__ import annotations


class SkillError(Exception):
    """Base class for all whatifd-skillgen errors."""


class SkillManifestError(SkillError):
    """Raised when a skill.md file cannot be parsed or validated.

    The message names the file, the specific field or section that failed,
    and what to fix.
    """


class SkillGenerationError(SkillError):
    """Raised when code generation or file writing fails.

    Covers template rendering failures, output-path conflicts, and OS-level
    write errors. The message names the skill, the step that failed, and the
    corrective action.
    """


__all__ = [
    "SkillError",
    "SkillManifestError",
    "SkillGenerationError",
]
