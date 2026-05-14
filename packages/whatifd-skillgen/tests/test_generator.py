"""Generator tests.

Pins:
- Determinism: same manifest → identical output on repeated calls
- All three kinds (scorer, tracer, runner) produce non-empty skill_code
- scorer code does not contain iter_traces (wrong protocol)
- adapter_metadata() uses importlib.metadata.version(), not a hardcoded string
- config_patch_hint and factory_patch_hint are non-empty strings
- factory_patch_hint references the correct package import path (whatifd_<name>)
- Unhandled exceptions do not escape the public API boundary
- Error hierarchy: SkillGenerationError is a SkillError
"""

from __future__ import annotations

import pytest

from whatifd_skillgen.errors import SkillError, SkillGenerationError
from whatifd_skillgen.generator import GeneratedSkill, generate_skill
from whatifd_skillgen.schema import SkillManifest


class TestGeneratorDeterminism:
    def test_scorer_is_deterministic(self, minimal_scorer_manifest: SkillManifest) -> None:
        first = generate_skill(minimal_scorer_manifest, "")
        second = generate_skill(minimal_scorer_manifest, "")
        assert first.skill_code == second.skill_code
        assert first.config_patch_hint == second.config_patch_hint
        assert first.factory_patch_hint == second.factory_patch_hint

    def test_tracer_is_deterministic(self, minimal_tracer_manifest: SkillManifest) -> None:
        first = generate_skill(minimal_tracer_manifest, "body text")
        second = generate_skill(minimal_tracer_manifest, "body text")
        assert first.skill_code == second.skill_code

    def test_runner_is_deterministic(self, minimal_runner_manifest: SkillManifest) -> None:
        first = generate_skill(minimal_runner_manifest, "")
        second = generate_skill(minimal_runner_manifest, "")
        assert first.skill_code == second.skill_code

    def test_different_manifests_produce_different_output(
        self, minimal_scorer_manifest: SkillManifest, minimal_tracer_manifest: SkillManifest
    ) -> None:
        scorer_out = generate_skill(minimal_scorer_manifest, "")
        tracer_out = generate_skill(minimal_tracer_manifest, "")
        assert scorer_out.skill_code != tracer_out.skill_code


class TestGeneratorOutputShape:
    def test_scorer_produces_non_empty_code(self, minimal_scorer_manifest: SkillManifest) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        assert len(result.skill_code) > 100

    def test_tracer_produces_non_empty_code(self, minimal_tracer_manifest: SkillManifest) -> None:
        result = generate_skill(minimal_tracer_manifest, "")
        assert len(result.skill_code) > 100

    def test_runner_produces_non_empty_code(self, minimal_runner_manifest: SkillManifest) -> None:
        result = generate_skill(minimal_runner_manifest, "")
        assert len(result.skill_code) > 100

    def test_config_hint_is_non_empty(self, minimal_scorer_manifest: SkillManifest) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        assert result.config_patch_hint.strip()

    def test_factory_hint_is_non_empty(self, minimal_scorer_manifest: SkillManifest) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        assert result.factory_patch_hint.strip()


class TestGeneratorScorerProtocolCorrectness:
    def test_scorer_does_not_contain_iter_traces(
        self, minimal_scorer_manifest: SkillManifest
    ) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        # iter_traces is a TraceSource method, not a Scorer method.
        # The scorer stub must not include it.
        assert "def iter_traces" not in result.skill_code

    def test_scorer_contains_score_method(self, minimal_scorer_manifest: SkillManifest) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        assert "def score" in result.skill_code

    def test_scorer_contains_cache_key_components(
        self, minimal_scorer_manifest: SkillManifest
    ) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        assert "def cache_key_components" in result.skill_code

    def test_scorer_contains_protocol_witness(
        self, minimal_scorer_manifest: SkillManifest
    ) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        assert "_protocol_witness" in result.skill_code
        assert "Scorer" in result.skill_code


class TestGeneratorTracerProtocolCorrectness:
    def test_tracer_contains_iter_traces(self, minimal_tracer_manifest: SkillManifest) -> None:
        result = generate_skill(minimal_tracer_manifest, "")
        assert "def iter_traces" in result.skill_code

    def test_tracer_contains_cluster_key_support(
        self, minimal_tracer_manifest: SkillManifest
    ) -> None:
        result = generate_skill(minimal_tracer_manifest, "")
        assert "def cluster_key_support" in result.skill_code

    def test_tracer_contains_protocol_witness(
        self, minimal_tracer_manifest: SkillManifest
    ) -> None:
        result = generate_skill(minimal_tracer_manifest, "")
        assert "_protocol_witness" in result.skill_code
        assert "TraceSource" in result.skill_code


class TestGeneratorAdapterMetadata:
    def test_scorer_uses_importlib_metadata(self, minimal_scorer_manifest: SkillManifest) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        assert "_dist_version" in result.skill_code or "importlib.metadata" in result.skill_code
        assert "package_version" not in result.skill_code or "hardcoded" not in result.skill_code

    def test_scorer_does_not_have_todo_for_version(
        self, minimal_scorer_manifest: SkillManifest
    ) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        assert "TODO: replace package_version" not in result.skill_code

    def test_dist_name_is_hyphenated(self, minimal_scorer_manifest: SkillManifest) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        assert "whatifd-my-scorer" in result.skill_code


class TestGeneratorFactoryHint:
    def test_factory_hint_references_correct_import_path(
        self, minimal_scorer_manifest: SkillManifest
    ) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        # Must import from whatifd_my_scorer (the adapter package), not whatifd.skills.my_scorer
        assert "from whatifd_my_scorer import" in result.factory_patch_hint
        assert "whatifd.skills" not in result.factory_patch_hint

    def test_factory_hint_includes_lazy_import_note(
        self, minimal_scorer_manifest: SkillManifest
    ) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        assert "lazy" in result.factory_patch_hint.lower()

    def test_factory_hint_includes_adapter_factory_error(
        self, minimal_scorer_manifest: SkillManifest
    ) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        assert "AdapterFactoryError" in result.factory_patch_hint


class TestGeneratorErrorBoundary:
    def test_skill_generation_error_is_skill_error(self) -> None:
        assert issubclass(SkillGenerationError, SkillError)

    def test_generate_skill_returns_generated_skill_instance(
        self, minimal_scorer_manifest: SkillManifest
    ) -> None:
        result = generate_skill(minimal_scorer_manifest, "")
        assert isinstance(result, GeneratedSkill)

    def test_full_manifest_generates_without_error(
        self, full_scorer_manifest: SkillManifest
    ) -> None:
        result = generate_skill(full_scorer_manifest, "Some implementation notes.")
        assert result.skill_code
        assert result.config_patch_hint
        assert result.factory_patch_hint

    def test_body_appears_in_generated_docstring(
        self, minimal_scorer_manifest: SkillManifest
    ) -> None:
        result = generate_skill(minimal_scorer_manifest, "Custom implementation note.")
        assert "Custom implementation note." in result.skill_code
