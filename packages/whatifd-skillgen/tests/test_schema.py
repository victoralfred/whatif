"""Schema validation tests.

Pins:
- extra="forbid" rejects unknown keys at parse time
- required-field validation catches missing name/description/kind
- optional parameters require a default value
- env_var names must be UPPER_SNAKE_CASE
- duplicate parameter names are rejected
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from whatifd_skillgen.schema import EnvVarSpec, ParameterSpec, SkillManifest


class TestSkillManifestForbidsUnknownKeys:
    def test_unknown_top_level_key_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            SkillManifest.model_validate({
                "name": "my_scorer",
                "description": "A scorer.",
                "kind": "scorer",
                "unknown_field": "oops",
            })
        assert "extra" in str(exc_info.value) or "Extra inputs" in str(exc_info.value)

    def test_unknown_env_var_key_raises(self) -> None:
        with pytest.raises(ValidationError):
            EnvVarSpec.model_validate({
                "name": "MY_KEY",
                "required": True,
                "description": "A key.",
                "surprise": "nope",
            })

    def test_unknown_parameter_key_raises(self) -> None:
        with pytest.raises(ValidationError):
            ParameterSpec.model_validate({
                "name": "model_id",
                "type": "str",
                "required": True,
                "description": "A model.",
                "extra_key": "bad",
            })


class TestSkillManifestRequiredFields:
    def test_missing_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            SkillManifest.model_validate({"description": "x", "kind": "scorer"})

    def test_missing_description_raises(self) -> None:
        with pytest.raises(ValidationError):
            SkillManifest.model_validate({"name": "my_scorer", "kind": "scorer"})

    def test_missing_kind_raises(self) -> None:
        with pytest.raises(ValidationError):
            SkillManifest.model_validate({"name": "my_scorer", "description": "x"})

    def test_invalid_kind_raises(self) -> None:
        with pytest.raises(ValidationError):
            SkillManifest.model_validate(
                {"name": "my_scorer", "description": "x", "kind": "classifier"}
            )


class TestSkillManifestNameValidation:
    def test_hyphenated_name_raises(self) -> None:
        with pytest.raises(ValidationError, match="valid Python identifier"):
            SkillManifest.model_validate(
                {"name": "my-scorer", "description": "x", "kind": "scorer"}
            )

    def test_keyword_name_raises(self) -> None:
        with pytest.raises(ValidationError, match="keyword"):
            SkillManifest.model_validate(
                {"name": "class", "description": "x", "kind": "scorer"}
            )

    def test_digit_start_raises(self) -> None:
        with pytest.raises(ValidationError, match="valid Python identifier"):
            SkillManifest.model_validate(
                {"name": "1scorer", "description": "x", "kind": "scorer"}
            )


class TestSkillManifestVersionValidation:
    def test_valid_short_version(self) -> None:
        m = SkillManifest.model_validate(
            {"name": "my_scorer", "description": "x", "kind": "scorer", "version": "1.0"}
        )
        assert m.version == "1.0"

    def test_valid_long_version(self) -> None:
        m = SkillManifest.model_validate(
            {"name": "my_scorer", "description": "x", "kind": "scorer", "version": "1.2.3"}
        )
        assert m.version == "1.2.3"

    def test_non_semver_version_raises(self) -> None:
        with pytest.raises(ValidationError, match="semver"):
            SkillManifest.model_validate(
                {"name": "my_scorer", "description": "x", "kind": "scorer", "version": "v1.0"}
            )


class TestParameterSpecValidation:
    def test_optional_without_default_raises(self) -> None:
        with pytest.raises(ValidationError, match="default"):
            ParameterSpec.model_validate({
                "name": "timeout",
                "type": "float",
                "required": False,
                "description": "Timeout.",
            })

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(ValidationError, match="not supported"):
            ParameterSpec.model_validate({
                "name": "items",
                "type": "list",
                "required": True,
                "description": "A list.",
            })

    def test_valid_optional_with_default(self) -> None:
        p = ParameterSpec.model_validate({
            "name": "timeout",
            "type": "float",
            "required": False,
            "default": "30.0",
            "description": "Timeout.",
        })
        assert p.default == "30.0"


class TestEnvVarSpecValidation:
    def test_lowercase_name_raises(self) -> None:
        with pytest.raises(ValidationError, match="UPPER_SNAKE_CASE"):
            EnvVarSpec.model_validate(
                {"name": "my_key", "required": True, "description": "A key."}
            )

    def test_valid_upper_snake_case(self) -> None:
        ev = EnvVarSpec.model_validate(
            {"name": "MY_API_KEY", "required": True, "description": "A key."}
        )
        assert ev.name == "MY_API_KEY"


class TestDuplicateParameterNames:
    def test_duplicate_names_raise(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            SkillManifest.model_validate({
                "name": "my_scorer",
                "description": "x",
                "kind": "scorer",
                "parameters": [
                    {"name": "model_id", "type": "str", "required": True, "description": "m"},
                    {"name": "model_id", "type": "str", "required": True, "description": "m2"},
                ],
            })
