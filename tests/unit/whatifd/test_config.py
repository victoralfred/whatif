"""Tests for `whatifd.config` — Phase 8.1.

Pin properties:

1. Top-level `WhatifConfig` constructs with all required sections.
2. Strict mode rejects unknown fields at every nesting level.
3. Range constraints rejected (negative limit, ratio > 1).
4. Forensic profile without acknowledgment block fails at the
   config validator (cardinal #7 config half).
5. Two-affirmation rule enforced cross-surface
   (config-says-forensic + cli-not-forensic, and vice versa).
6. Hint generator produces a structured message naming the field
   path + a suggestion for registered codes.
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from pydantic import ValidationError

from whatifd.config import (
    ConfigFileError,
    ForensicAcknowledgment,
    ForensicAffirmationError,
    TwoAffirmationProof,
    WhatifConfig,
    assert_two_affirmation,
    format_validation_errors,
    load_config,
)


def _minimal_config_dict() -> dict:
    # decision/reporting/timeouts are required at WhatifConfig
    # level; pass `{}` to opt in to each sub-model's field
    # defaults (which still validate via Pydantic).
    return {
        "source": {"adapter": "langfuse"},
        "target": {"runner": "python:my_agent.replay:run"},
        "selection": {
            "failure_cohort": {"limit": 20},
            "baseline_cohort": {"limit": 20},
        },
        "change": {"system_prompt": "be concise"},
        "scorer": {"adapter": "stub", "cache_mode": "auto"},
        "decision": {},
        "reporting": {},
        "timeouts": {},
    }


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_minimal_config_validates(self) -> None:
        cfg = WhatifConfig(**_minimal_config_dict())
        assert cfg.source.adapter == "langfuse"
        assert cfg.target.runner == "python:my_agent.replay:run"
        assert cfg.selection.failure_cohort.limit == 20
        # Defaults applied when sections omitted.
        assert cfg.decision.max_baseline_regression_ratio == 0.10
        assert cfg.timeouts.replay_seconds == 60.0
        assert cfg.reporting.profile == "default"


# ---------------------------------------------------------------------------
# Strict mode (extra="forbid") at every level
# ---------------------------------------------------------------------------


class TestStrictMode:
    def test_unknown_top_level_field_rejected(self) -> None:
        d = _minimal_config_dict()
        d["unknown_section"] = {}
        with pytest.raises(ValidationError) as exc:
            WhatifConfig(**d)
        assert any(e["type"] == "extra_forbidden" for e in exc.value.errors())

    def test_unknown_nested_field_rejected(self) -> None:
        # Typo in `cache_mode` (e.g., `cach_mode`) must fail.
        d = _minimal_config_dict()
        d["scorer"]["cach_mode"] = "auto"  # typo
        with pytest.raises(ValidationError):
            WhatifConfig(**d)

    def test_unknown_acknowledgment_field_rejected(self) -> None:
        # Cardinal #7 defense: a typo in the acknowledgment block
        # (e.g., `accepted_b` missing y) must NOT silently produce
        # a half-populated forensic enablement.
        d = _minimal_config_dict()
        d["reporting"] = {
            "profile": "forensic",
            "forensic_acknowledgment": {
                "accepted_b": "ops",  # typo
                "accepted_at": "2026-05-07",
                "reason": "audit",
            },
        }
        with pytest.raises(ValidationError):
            WhatifConfig(**d)


# ---------------------------------------------------------------------------
# Range constraints
# ---------------------------------------------------------------------------


class TestRangeConstraints:
    def test_negative_limit_rejected(self) -> None:
        d = _minimal_config_dict()
        d["selection"]["failure_cohort"]["limit"] = 0
        with pytest.raises(ValidationError):
            WhatifConfig(**d)

    def test_ratio_above_one_rejected(self) -> None:
        d = _minimal_config_dict()
        d["decision"] = {"max_baseline_regression_ratio": 1.5}
        with pytest.raises(ValidationError):
            WhatifConfig(**d)

    def test_zero_timeout_rejected(self) -> None:
        d = _minimal_config_dict()
        d["timeouts"] = {"replay_seconds": 0.0}
        with pytest.raises(ValidationError):
            WhatifConfig(**d)


# ---------------------------------------------------------------------------
# Forensic profile config-side enforcement (cardinal #7)
# ---------------------------------------------------------------------------


class TestForensicConfigSide:
    def test_forensic_without_acknowledgment_block_fails(self) -> None:
        # Cardinal #7: profile='forensic' alone is insufficient
        # at the config level. The model_validator catches this
        # before reaching the CLI two-affirmation check.
        d = _minimal_config_dict()
        d["reporting"] = {"profile": "forensic"}
        with pytest.raises(ValidationError, match="forensic_acknowledgment"):
            WhatifConfig(**d)

    def test_forensic_with_acknowledgment_block_validates(self) -> None:
        d = _minimal_config_dict()
        d["reporting"] = {
            "profile": "forensic",
            "forensic_acknowledgment": {
                "accepted_by": "ops",
                "accepted_at": "2026-05-07",
                "reason": "regulatory audit",
            },
        }
        cfg = WhatifConfig(**d)
        assert cfg.reporting.profile == "forensic"
        assert cfg.reporting.forensic_acknowledgment is not None


# ---------------------------------------------------------------------------
# Two-affirmation rule (cardinal #7 cross-surface)
# ---------------------------------------------------------------------------


def _forensic_config() -> WhatifConfig:
    d = _minimal_config_dict()
    d["reporting"] = {
        "profile": "forensic",
        "forensic_acknowledgment": {
            "accepted_by": "ops",
            "accepted_at": "2026-05-07",
            "reason": "regulatory audit",
        },
    }
    return WhatifConfig(**d)


class TestTwoAffirmation:
    def test_both_surfaces_forensic_returns_active_proof(self) -> None:
        cfg = _forensic_config()
        proof = assert_two_affirmation(cfg, cli_profile="forensic")
        assert isinstance(proof, TwoAffirmationProof)
        assert proof.forensic_active is True

    def test_config_forensic_cli_not_fails(self) -> None:
        cfg = _forensic_config()
        with pytest.raises(ForensicAffirmationError, match="CLI invocation did not include"):
            assert_two_affirmation(cfg, cli_profile=None)

    def test_cli_forensic_config_not_fails(self) -> None:
        cfg = WhatifConfig(**_minimal_config_dict())  # default profile
        with pytest.raises(ForensicAffirmationError, match="CLI flag alone is insufficient"):
            assert_two_affirmation(cfg, cli_profile="forensic")

    def test_neither_forensic_returns_inactive_proof(self) -> None:
        cfg = WhatifConfig(**_minimal_config_dict())
        # Both nullary surfaces: returns a proof with
        # forensic_active=False so downstream code still
        # type-checks against the witness API but takes the
        # default-redaction branch.
        proof_none = assert_two_affirmation(cfg, cli_profile=None)
        assert proof_none.forensic_active is False
        proof_default = assert_two_affirmation(cfg, cli_profile="default")
        assert proof_default.forensic_active is False

    def test_acknowledgment_fields_required_non_empty(self) -> None:
        # ForensicAcknowledgment.min_length=1 — empty strings fail.
        with pytest.raises(ValidationError):
            ForensicAcknowledgment(accepted_by="", accepted_at="2026-05-07", reason="x")

    def test_accepted_at_must_match_iso_8601_pattern(self) -> None:
        # Free-text values (e.g., "yesterday", "x") in accepted_at
        # are an obvious-misconfiguration smell that the
        # forensic-acknowledgment block exists to prevent.
        with pytest.raises(ValidationError):
            ForensicAcknowledgment(accepted_by="ops", accepted_at="yesterday", reason="audit")
        with pytest.raises(ValidationError):
            ForensicAcknowledgment(accepted_by="ops", accepted_at="x", reason="audit")

    def test_accepted_at_accepts_iso_8601_canonical_forms(self) -> None:
        # Each form an operator might reasonably write in YAML.
        for valid in (
            "2026-05-07",  # date only
            "2026-05-07T13:45:30",  # datetime, no tz
            "2026-05-07T13:45:30Z",  # UTC
            "2026-05-07T13:45:30.123Z",  # fractional
            "2026-05-07T13:45:30+00:00",  # offset with colon
            "2026-05-07T13:45:30-05:00",  # negative offset
            "2026-05-07 13:45:30",  # space separator
        ):
            ForensicAcknowledgment(accepted_by="ops", accepted_at=valid, reason="audit")

    def test_proof_cannot_be_constructed_externally(self) -> None:
        # Witness-token defense: only `assert_two_affirmation` can
        # produce a valid `TwoAffirmationProof`. Direct construction
        # without the module-private sentinel raises RuntimeError.
        # Mirrors cardinal #2's `FloorPassedProof` enforcement.
        with pytest.raises(RuntimeError, match="closure-capture"):
            TwoAffirmationProof(forensic_active=True, _token=object())


# ---------------------------------------------------------------------------
# Hint generator
# ---------------------------------------------------------------------------


class TestHintGenerator:
    def test_hint_emitted_for_registered_code(self) -> None:
        # Trigger a known misconfiguration: limit=0 on
        # failure_cohort. The hint table has an entry for
        # ("limit", "greater_than_equal").
        d = _minimal_config_dict()
        d["selection"]["failure_cohort"]["limit"] = 0
        try:
            WhatifConfig(**d)
        except ValidationError as exc:
            msg = format_validation_errors(exc)
            assert "selection.failure_cohort.limit" in msg
            assert (
                "Hint: selection.failure_cohort.limit must be >= 1; use a positive integer." in msg
            )
        else:
            pytest.fail("Expected ValidationError")

    def test_no_hint_for_unregistered_code(self) -> None:
        # An unknown-top-level-field error has no registered hint;
        # the generator emits the path + Pydantic message but no
        # "Hint:" line.
        d = _minimal_config_dict()
        d["mystery_section"] = {}
        try:
            WhatifConfig(**d)
        except ValidationError as exc:
            msg = format_validation_errors(exc)
            assert "mystery_section" in msg
            assert "Hint:" not in msg
        else:
            pytest.fail("Expected ValidationError")

    def test_multi_error_output_lists_each(self) -> None:
        # Two simultaneous errors → two blocks in the output.
        d = _minimal_config_dict()
        d["selection"]["failure_cohort"]["limit"] = 0
        d["timeouts"] = {"replay_seconds": 0.0}
        try:
            WhatifConfig(**d)
        except ValidationError as exc:
            msg = format_validation_errors(exc)
            assert "selection.failure_cohort.limit" in msg
            assert "timeouts.replay_seconds" in msg
        else:
            pytest.fail("Expected ValidationError")

    def test_model_validator_error_gets_hint(self) -> None:
        # Cardinal-#7 model_validator path: forensic profile with
        # no acknowledgment block. Pydantic emits this with
        # `loc=('reporting',)` and `type='value_error'`; the
        # ('reporting', 'value_error') hint entry covers it.
        d = _minimal_config_dict()
        d["reporting"] = {"profile": "forensic"}
        try:
            WhatifConfig(**d)
        except ValidationError as exc:
            msg = format_validation_errors(exc)
            assert "reporting:" in msg
            assert "Hint: model-level validation on `reporting`" in msg
        else:
            pytest.fail("Expected ValidationError")

    def test_empty_loc_renders_as_root(self) -> None:
        # The format_validation_errors fallback renders empty
        # `loc` as "(root)". No production path currently produces
        # empty loc (the model_validator emits loc=('reporting',)),
        # but the fallback branch exists defensively and must be
        # tested.
        #
        # The test uses pydantic_core internals to synthesize a
        # ValidationError with loc=(). These names are part of
        # pydantic-core's documented validation-error construction
        # API, but they could move between versions. Guarded with
        # `importorskip` + `hasattr` so a future pydantic-core
        # API change skips this test rather than crashing the
        # suite — the defensive branch in format_validation_errors
        # is a one-liner; an outage of this test isn't load-bearing.
        pydantic_core = pytest.importorskip("pydantic_core")
        if not hasattr(pydantic_core, "InitErrorDetails") or not hasattr(
            pydantic_core, "PydanticCustomError"
        ):
            pytest.skip("pydantic_core API changed; synthetic-error path unavailable")

        try:
            raise ValidationError.from_exception_data(
                "Synthetic",
                [
                    pydantic_core.InitErrorDetails(
                        type=pydantic_core.PydanticCustomError(
                            "value_error", "synthetic root error"
                        ),
                        loc=(),
                        input=None,
                    ),
                ],
            )
        except ValidationError as exc:
            msg = format_validation_errors(exc)
            assert "(root):" in msg


# ---------------------------------------------------------------------------
# Type coercion (lax mode — strict=True dropped to accept YAML int->float)
# ---------------------------------------------------------------------------


class TestCoercion:
    def test_int_coerces_to_float_for_timeouts(self) -> None:
        # YAML parses `60` as int; the field is `replay_seconds:
        # float`. Without strict mode, Pydantic coerces. Pin this
        # so a future re-introduction of `strict=True` would fail
        # this test rather than break operator YAML files.
        d = _minimal_config_dict()
        d["timeouts"] = {"replay_seconds": 60, "score_seconds": 30}
        cfg = WhatifConfig(**d)
        assert cfg.timeouts.replay_seconds == 60.0
        assert cfg.timeouts.score_seconds == 30.0
        assert isinstance(cfg.timeouts.replay_seconds, float)


# ---------------------------------------------------------------------------
# load_config — file -> WhatifConfig boundary (cardinal #1)
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_load_yaml_file(self, tmp_path) -> None:
        p = tmp_path / "whatifd.yaml"
        p.write_text(
            "source:\n  adapter: langfuse\n"
            "target:\n  runner: python:my_agent.replay:run\n"
            "selection:\n"
            "  failure_cohort:\n    limit: 20\n"
            "  baseline_cohort:\n    limit: 20\n"
            "change:\n  system_prompt: be concise\n"
            "scorer:\n  adapter: stub\n  cache_mode: auto\n"
            "decision: {}\n"
            "reporting: {}\n"
            "timeouts: {}\n",
            encoding="utf-8",
        )
        cfg = load_config(p)
        assert cfg.source.adapter == "langfuse"

    def test_load_json_file(self, tmp_path) -> None:
        p = tmp_path / "whatifd.json"
        p.write_text(json.dumps(_minimal_config_dict()), encoding="utf-8")
        cfg = load_config(p)
        assert cfg.source.adapter == "langfuse"

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX permission semantics; Windows file ACLs differ",
    )
    @pytest.mark.skipif(
        os.geteuid() == 0 if hasattr(os, "geteuid") else False,
        reason="root bypasses chmod 0o000; can't simulate permission denied",
    )
    def test_permission_denied_raises_config_file_error(self, tmp_path) -> None:
        # Pin the OSError -> ConfigFileError branch in load_config.
        # chmod 000 makes the file unreadable; load_config wraps the
        # PermissionError raised by Path.read_text into a typed
        # ConfigFileError naming the path.
        p = tmp_path / "unreadable.yaml"
        p.write_text("source:\n  adapter: langfuse\n", encoding="utf-8")
        os.chmod(p, 0o000)
        try:
            with pytest.raises(ConfigFileError, match="cannot read config"):
                load_config(p)
        finally:
            # Restore permissions so pytest's tmp_path cleanup
            # doesn't fail trying to remove the file.
            os.chmod(p, 0o644)

    def test_missing_file_raises_config_file_error(self, tmp_path) -> None:
        with pytest.raises(ConfigFileError, match="not found"):
            load_config(tmp_path / "does-not-exist.yaml")

    def test_yaml_parse_error_raises_config_file_error(self, tmp_path) -> None:
        p = tmp_path / "broken.yaml"
        # Invalid YAML: unclosed bracket.
        p.write_text("source:\n  adapter: [unclosed", encoding="utf-8")
        with pytest.raises(ConfigFileError, match="YAML parse error"):
            load_config(p)

    def test_json_parse_error_raises_config_file_error(self, tmp_path) -> None:
        p = tmp_path / "broken.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ConfigFileError, match="JSON parse error"):
            load_config(p)

    def test_unsupported_extension_raises(self, tmp_path) -> None:
        p = tmp_path / "config.toml"
        p.write_text("", encoding="utf-8")
        with pytest.raises(ConfigFileError, match="unsupported config extension"):
            load_config(p)

    def test_non_mapping_root_raises(self, tmp_path) -> None:
        p = tmp_path / "list.yaml"
        p.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(ConfigFileError, match="must parse to a mapping"):
            load_config(p)

    def test_forensic_yaml_to_proof_end_to_end(self, tmp_path) -> None:
        # File→config→affirmation seam: write a YAML with the
        # forensic profile + acknowledgment block, load it, and
        # assert_two_affirmation with --profile forensic should
        # produce a TwoAffirmationProof with forensic_active=True.
        # This pins the integration the cascade-catalog entry
        # warns about: Phase 8.2 CLI must call assert_two_affirmation
        # after load_config; no test was previously exercising the
        # full file-load→witness path.
        p = tmp_path / "forensic.yaml"
        p.write_text(
            "source:\n  adapter: langfuse\n"
            "target:\n  runner: python:my_agent.replay:run\n"
            "selection:\n"
            "  failure_cohort:\n    limit: 20\n"
            "  baseline_cohort:\n    limit: 20\n"
            "change: {}\n"
            "scorer:\n  adapter: stub\n"
            "decision: {}\n"
            "reporting:\n"
            "  profile: forensic\n"
            "  forensic_acknowledgment:\n"
            "    accepted_by: ops\n"
            "    accepted_at: '2026-05-07'\n"
            "    reason: regulatory audit\n"
            "timeouts: {}\n",
            encoding="utf-8",
        )
        cfg = load_config(p)
        proof = assert_two_affirmation(cfg, cli_profile="forensic")
        assert proof.forensic_active is True

        # Cross-check: the same loaded config with --profile NOT
        # forensic raises (CLI half missing).
        with pytest.raises(ForensicAffirmationError):
            assert_two_affirmation(cfg, cli_profile=None)

    def test_validation_error_propagates(self, tmp_path) -> None:
        # File loads, parses, but schema is invalid → propagates
        # `ValidationError` (NOT wrapped in ConfigFileError). This
        # is the documented split: file/parse errors are
        # ConfigFileError; field/schema errors are ValidationError.
        p = tmp_path / "invalid.yaml"
        p.write_text(
            "source:\n  adapter: langfuse\n"
            "target:\n  runner: python:x:y\n"
            "selection:\n"
            "  failure_cohort:\n    limit: 0\n"  # invalid: ge=1
            "  baseline_cohort:\n    limit: 20\n"
            "change: {}\n"
            "scorer:\n  adapter: stub\n"
            "decision: {}\n"
            "reporting: {}\n"
            "timeouts: {}\n",
            encoding="utf-8",
        )
        with pytest.raises(ValidationError):
            load_config(p)


# ---------------------------------------------------------------------------
# Phase B: scorer.score_fn + judge fields + scoring_parameters round-trip
# ---------------------------------------------------------------------------


class TestInspectAiScorerConfig:
    """v0.2 config-loaded inspect_ai pin."""

    def _inspect_ai_config_dict(self) -> dict:
        d = _minimal_config_dict()
        d["scorer"] = {
            "adapter": "inspect_ai",
            "score_fn": "python:my_pkg.scorers:faithfulness",
            "judge_provider": "anthropic",
            "judge_model_id": "claude-haiku-4-5",
            "rubric_id": "faith-v1",
            "rubric_text": "Score 0-1 by faithfulness.",
            "scoring_parameters": {
                "temperature": 0.0,
                "max_tokens": 1024,
                "deterministic": True,
                "system_prompt_suffix": "be concise",
                "stop_token": None,
            },
            "cache_mode": "auto",
        }
        return d

    def test_inspect_ai_full_config_validates(self) -> None:
        cfg = WhatifConfig(**self._inspect_ai_config_dict())
        assert cfg.scorer.adapter == "inspect_ai"
        assert cfg.scorer.score_fn == "python:my_pkg.scorers:faithfulness"
        assert cfg.scorer.judge_provider == "anthropic"

    def test_scoring_parameters_round_trip_mixed_json_primitives(self) -> None:
        # Pin: every JsonPrimitive variant survives the Pydantic
        # boundary unchanged. A future regression that silently
        # coerces (e.g., float -> int, None -> "") would fail this
        # test.
        cfg = WhatifConfig(**self._inspect_ai_config_dict())
        params = cfg.scorer.scoring_parameters
        assert params["temperature"] == 0.0 and isinstance(params["temperature"], float)
        assert params["max_tokens"] == 1024 and isinstance(params["max_tokens"], int)
        assert params["deterministic"] is True
        assert params["system_prompt_suffix"] == "be concise"
        assert params["stop_token"] is None

    def test_inspect_ai_missing_score_fn_rejected(self) -> None:
        d = self._inspect_ai_config_dict()
        d["scorer"].pop("score_fn")
        with pytest.raises(ValidationError, match="score_fn"):
            WhatifConfig(**d)

    def test_inspect_ai_missing_judge_provider_rejected(self) -> None:
        d = self._inspect_ai_config_dict()
        d["scorer"].pop("judge_provider")
        with pytest.raises(ValidationError, match="judge_provider"):
            WhatifConfig(**d)

    def test_stub_silently_ignores_inspect_ai_fields(self) -> None:
        # Pure ScorerConfig pin (no factory): the docstring promises
        # inspect_ai-specific fields are silently accepted when
        # adapter='stub' so a config block can be retargeted with one
        # keystroke during development. Pinned independently of the
        # factory test (which exercises the StubScorer construction
        # path) so the docstring claim stands on its own.
        from whatifd.config import ScorerConfig

        cfg = ScorerConfig(
            adapter="stub",
            score_fn="python:my_pkg:scorer",
            judge_provider="anthropic",
            judge_model_id="claude-haiku-4-5",
            rubric_id="r-v1",
            rubric_text="Score 0-1.",
            scoring_parameters={"temperature": 0.0},
        )
        assert cfg.adapter == "stub"
        # Fields preserved (silent-ignore != silent-drop).
        assert cfg.score_fn == "python:my_pkg:scorer"
        assert cfg.scoring_parameters == {"temperature": 0.0}

    def test_scoring_parameters_rejects_nested_structures(self) -> None:
        # The validator catches nested values at config-load with a
        # single named-field error instead of Pydantic's 4-arm union
        # rejection.
        from whatifd.config import ScorerConfig

        # Exhaustive: list, dict, tuple, set — the four collection
        # types the pre-validator rejects.
        for bad_value in ([1, 2, 3], {"nested": True}, (1, 2, 3), {1, 2, 3}):
            with pytest.raises(ValidationError, match="nested structures not allowed"):
                ScorerConfig(adapter="stub", scoring_parameters={"k": bad_value})


# ---------------------------------------------------------------------------
# Phase C completion (#84): experiment_shape config field
# ---------------------------------------------------------------------------


class TestExperimentShapeConfig:
    """Issue #84: WhatifConfig.experiment_shape closes the regression-
    check loop end-to-end. Without this field, regression-check was
    reachable only by programmatic RunManifest construction; now CLI
    YAML users can select it.
    """

    def test_default_is_failure_rescue(self) -> None:
        # Back-compat: existing v0.1 configs (no experiment_shape
        # key) get failure_rescue automatically.
        cfg = WhatifConfig(**_minimal_config_dict())
        assert cfg.experiment_shape == "failure_rescue"

    def test_regression_check_accepted(self) -> None:
        # regression_check requires baseline_cohort only; failure_cohort
        # MUST be omitted (D-1 validator).
        d = _minimal_config_dict()
        d["experiment_shape"] = "regression_check"
        del d["selection"]["failure_cohort"]
        cfg = WhatifConfig(**d)
        assert cfg.experiment_shape == "regression_check"
        assert cfg.selection.failure_cohort is None

    def test_failure_rescue_accepted_explicit(self) -> None:
        d = _minimal_config_dict()
        d["experiment_shape"] = "failure_rescue"
        cfg = WhatifConfig(**d)
        assert cfg.experiment_shape == "failure_rescue"

    def test_regression_check_rejects_failure_cohort(self) -> None:
        # D-1 (docs audit): docs/reference/config.md:47 promises
        # `failure_cohort is rejected at config-load with a named-field
        # error if present` under regression_check. Pre-fix the check
        # was missing and the cohort was silently ignored. Pin the
        # rejection here so a future refactor that drops the validator
        # surfaces the doc-promise gap immediately.
        d = _minimal_config_dict()
        d["experiment_shape"] = "regression_check"
        # failure_cohort still present from _minimal_config_dict
        with pytest.raises(ValidationError, match="failure_cohort"):
            WhatifConfig(**d)

    def test_failure_rescue_rejects_missing_failure_cohort(self) -> None:
        # Symmetric pin: failure_rescue without failure_cohort is the
        # other half of D-1's cross-field contract.
        d = _minimal_config_dict()
        # default shape == failure_rescue
        del d["selection"]["failure_cohort"]
        with pytest.raises(ValidationError, match="failure_cohort"):
            WhatifConfig(**d)

    def test_unknown_shape_rejected(self) -> None:
        # Literal-typed: unknown values fail at config-load with a
        # named-field error rather than silently flowing to the
        # verdict layer.
        d = _minimal_config_dict()
        d["experiment_shape"] = "exploratory_ab"
        with pytest.raises(ValidationError, match="experiment_shape"):
            WhatifConfig(**d)
