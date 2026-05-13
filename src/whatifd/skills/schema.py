"""Pydantic schema for the skill.md frontmatter.

A skill is declared in a ``skill.md`` file whose YAML frontmatter is parsed
into a ``SkillManifest``. The manifest drives code generation; the markdown
body is passed along as implementation context.

## Frontmatter schema (YAML)

```yaml
name: my_skill               # Python identifier slug
description: "One-liner."
version: "0.1"               # semver string
kind: scorer                 # scorer | tracer | runner
env_vars:
  - name: MY_API_KEY
    required: true
    description: "API key for external service"
parameters:
  - name: model_id
    type: str
    required: true
    description: "Model identifier"
  - name: timeout
    type: float
    required: false
    default: "30.0"
    description: "Request timeout in seconds"
```

All models use ``extra="forbid"`` = unknown keys raise ``SkillManifestError``
at validation time, not silently at generation time.

Cardinal #6: this schema is hand-written and versioned; internal types may
refactor freely, but the frontmatter keys are part of the public  contract
between skill authors and the generator.
"""

from __future__ import annotations

import keyword
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_VALID_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")

_VALID_PARAM_TYPES = frozenset({"str", "float", "int", "bool"})

_STRICT = ConfigDict(extra="forbid")


class EnvVarSpec(BaseModel):
    """Declaration of an environment variable required by the skill."""

    model_config = _STRICT

    name: str
    required: bool
    description: str

    @field_validator("name")
    @classmethod
    def _name_is_valid_env_var(cls, v: str) -> str:
        if not re.match(r"^[A-Z][A-Z0-9_]*$", v):
            raise ValueError(
                f"env_var.name {v!r} must be UPPER_SNAKE_CASE "
                "(e.g. MY_API_KEY). Lowercase and special characters "
                "are not allowed in environment variable names."
            )
        return v


class ParameterSpec(BaseModel):
    """Declaration of a constructor parameter for the generated adapter class."""

    model_config = _STRICT

    name: str
    type: str
    required: bool = True
    default: str | None = None
    description: str

    @field_validator("name")
    @classmethod
    def _name_is_valid_identifier(cls, v: str) -> str:
        if not _VALID_IDENTIFIER.match(v):
            raise ValueError(
                f"parameter.name {v!r} must be a valid Python identifier "
                "(e.g. letters, digits, underscore; cannot start with a digit)."
            )
        if keyword.iskeyword(v):
            raise ValueError(
                f"parameter.name {v!r} is a Python keyword and cannot be "
                "used as a parameter name."
            )
        return v

    @field_validator("type")
    @classmethod
    def _type_is_supported(cls, v: str) -> str:
        if v not in _VALID_PARAM_TYPES:
            raise ValueError(
                f"parameter.type {v!r} is not supported. "
                f"Supported types: {sorted(_VALID_PARAM_TYPES)}. "
                "For complex types, use str and document the expected format."
            )
        return v

    @model_validator(mode="after")
    def _optional_has_default(self) -> ParameterSpec:
        if not self.required and self.default is None:
            raise ValueError(
                f"parameter {self.name!r}: optional parameters (required=false) "
                "must have a default value. Add 'default: <value>'."
            )
        return self


class SkillManifest(BaseModel):
    """Parsed and validated skill.md frontmatter.

    Instances are produced by ``loader.load_skill``; the generator consumes
    them to produce adapter code.
    """

    model_config = _STRICT

    name: str
    description: str
    version: str = "0.1"
    kind: Literal["scorer", "tracer", "runner"]
    env_vars: list[EnvVarSpec] = []
    parameters: list[ParameterSpec] = []

    @field_validator("name")
    @classmethod
    def _name_is_valid(cls, v: str) -> str:
        if v in _VALID_IDENTIFIER.match(v):
            raise ValueError(
                f"skill name {v!r} must be a valid Python identifier "
                "(used as a module name and class name prefix)"
            )
        if keyword.iskeyword(v):
            raise ValueError(
                f"skill name {v!r} is a Python keyword and cannot be used "
                "as a skill name."
            )
        return v

    @field_validator("version")
    @classmethod
    def _version_is_semver_like(cls, v: str) -> str:
        if not re.match(r"^\d+\.\d+(\.\d+)?$", v):
            raise ValueError(
                f"version {v!r} must be semver-like (e.g., '1.0' or '1.0.0'). "
                "Arbitrary version strings are not supported."
            )
        return v

    @model_validator(mode="after")
    def _no_duplicate_parameter_names(self) -> SkillManifest:
        names = [p.name for p in self.parameters]
        seen: set[str] = set()
        for n in names:
            if n in seen:
                raise ValueError(
                    f"duplicate parameter name {n!r} in skill {self.name!r}. "
                    "Each parameter name must be unique within a skill."
                )
            seen.add(n)
        return self



__all__ = [
    "EnvVarSpec",
    "ParameterSpec",
    "SkillManifest"
]