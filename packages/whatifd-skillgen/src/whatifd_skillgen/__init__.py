"""whatifd-skillgen: adapter scaffolding tool for whatifd.

Generates protocol-compliant adapter stubs from a declarative ``skill.md``
manifest. Install as a standalone dev tool — it is not part of whatifd core.

Public API
----------
    from whatifd_skillgen import scaffold_skill

    result = scaffold_skill(Path("packages/whatifd-myadapter/src/whatifd_myadapter/"))
    print(result.path_written)
    print(result.config_patch_hint)
    print(result.factory_patch_hint)

CLI entry point: ``whatifd-skillgen generate <skill_dir>``
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

try:
    __version__ = _dist_version("whatifd-skillgen")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

from whatifd_skillgen.errors import SkillError, SkillGenerationError, SkillManifestError
from whatifd_skillgen.scaffold import ScaffoldResult, scaffold_skill
from whatifd_skillgen.schema import EnvVarSpec, ParameterSpec, SkillManifest

__all__ = [
    "SkillError",
    "SkillGenerationError",
    "SkillManifestError",
    "ScaffoldResult",
    "scaffold_skill",
    "EnvVarSpec",
    "ParameterSpec",
    "SkillManifest",
]
