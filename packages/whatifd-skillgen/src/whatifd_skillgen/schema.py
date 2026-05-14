"""Pydantic schema for the skill.md frontmatter.

A skill is declared in a ``skill.md`` file whose YAML frontmatter is parsed
into a ``SkillManifest``. The manifest drives code generation; the markdown
body is passed along as implementation context in the generated docstring.

## Frontmatter schema (YAML)

```yaml
name: my_skill               # Python identifier slug (underscored)
description: "One-liner."
version: "0.1"               # semver-like string
kind: scorer                 # scorer | tracer | runner

env_vars:
  - name: MY_API_KEY         # UPPER_SNAKE_CASE only
    required: true
    description: "API key for the external service."

parameters:
  - name: model_id           # valid Python identifier
    type: str                # str | int | float | bool only
    required: true
    description: "Model identifier."
  - name: timeout
    type: float
    required: false
    default: "30.0"          # required when required=false
    description: "Request timeout in seconds."
```

All models use ``extra="forbid"``: unknown keys raise ``SkillManifestError``
at validation time, not silently at generation time.
"""

from __future__ import annotations

import keyword
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

_VALID_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_VALID_PARAM_TYPES = frozenset({"str", "float", "int", "bool"})
_STRICT = ConfigDict(extra="forbid")


class EnvVarSpec(BaseModel):
    """Declaration of an environment variable required by the adapter."""

    model_config = _STRICT

    name: str
    required: bool = True
    description: str

    @field_validator("name")
    @classmethod
    def _name_is_upper_snake(cls, v: str) -> str:
        if not re.match(r"^[A-Z][A-Z0-9_]*$", v):
            raise ValueError(
                f"env_var.name {v!r} must be UPPER_SNAKE_CASE "
                "(e.g. MY_API_KEY). Lowercase letters and special characters "
                "are not allowed."
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
                "(letters, digits, underscores; cannot start with a digit)."
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
    def _optional_requires_default(self) -> ParameterSpec:
        if not self.required and self.default is None:
            raise ValueError(
                f"parameter {self.name!r}: optional parameters (required=false) "
                "must supply a default value. Add 'default: <value>'."
            )
        return self


class SkillManifest(BaseModel):
    """Parsed and validated skill.md frontmatter.

    Produced by ``loader.load_skill``; consumed by ``generator.generate_skill``.
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
        if not _VALID_IDENTIFIER.match(v):
            raise ValueError(
                f"skill name {v!r} must be a valid Python identifier "
                "(used as the module name and class name prefix)."
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
                f"version {v!r} must be semver-like (e.g. '0.1' or '1.0.0'). "
                "Arbitrary version strings are not supported."
            )
        return v

    @model_validator(mode="after")
    def _no_duplicate_parameter_names(self) -> SkillManifest:
        seen: set[str] = set()
        for p in self.parameters:
            if p.name in seen:
                raise ValueError(
                    f"duplicate parameter name {p.name!r} in skill {self.name!r}. "
                    "Each parameter name must be unique within a skill."
                )
            seen.add(p.name)
        return self


__all__ = ["EnvVarSpec", "ParameterSpec", "SkillManifest"]
