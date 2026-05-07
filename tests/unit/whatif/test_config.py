"""Tests for `whatif.config` — Phase 8.1.

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

import pytest
from pydantic import ValidationError

from whatif.config import (
    ForensicAcknowledgment,
    ForensicAffirmationError,
    WhatifConfig,
    assert_two_affirmation,
    format_validation_errors,
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
        "scorer": {"adapter": "inspect_ai", "cache_mode": "auto"},
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
    def test_both_surfaces_forensic_passes(self) -> None:
        cfg = _forensic_config()
        # No raise.
        assert_two_affirmation(cfg, cli_profile="forensic")

    def test_config_forensic_cli_not_fails(self) -> None:
        cfg = _forensic_config()
        with pytest.raises(ForensicAffirmationError, match="CLI invocation did not include"):
            assert_two_affirmation(cfg, cli_profile=None)

    def test_cli_forensic_config_not_fails(self) -> None:
        cfg = WhatifConfig(**_minimal_config_dict())  # default profile
        with pytest.raises(ForensicAffirmationError, match="CLI flag alone is insufficient"):
            assert_two_affirmation(cfg, cli_profile="forensic")

    def test_neither_forensic_passes(self) -> None:
        cfg = WhatifConfig(**_minimal_config_dict())
        assert_two_affirmation(cfg, cli_profile=None)
        assert_two_affirmation(cfg, cli_profile="default")

    def test_acknowledgment_fields_required_non_empty(self) -> None:
        # ForensicAcknowledgment.min_length=1 — empty strings fail.
        with pytest.raises(ValidationError):
            ForensicAcknowledgment(accepted_by="", accepted_at="x", reason="x")


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
