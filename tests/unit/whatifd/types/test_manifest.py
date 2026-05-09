"""Tests for `whatifd.types.manifest` — Phase 1.6."""

from __future__ import annotations

import dataclasses

import pytest

from whatifd.types import (
    DecisionPolicy,
    EnvironmentFingerprint,
    RunManifest,
    SensitiveUnwrap,
    TrustFloor,
)

# --- EnvironmentFingerprint ---------------------------------------------


class TestEnvironmentFingerprint:
    def test_construction_minimal(self) -> None:
        env = EnvironmentFingerprint(
            python="3.12.3",
            platform="linux-x86_64",
            whatif_version="0.0.1",
        )
        assert env.python == "3.12.3"
        assert env.dependencies == {}

    def test_construction_with_dependencies(self) -> None:
        env = EnvironmentFingerprint(
            python="3.12.3",
            platform="linux-x86_64",
            whatif_version="0.0.1",
            dependencies={"whatifd-langfuse": "0.1.0", "anthropic": "0.40.0"},
        )
        assert env.dependencies == {
            "whatifd-langfuse": "0.1.0",
            "anthropic": "0.40.0",
        }

    def test_frozen(self) -> None:
        env = EnvironmentFingerprint(
            python="3.12.3", platform="linux-x86_64", whatif_version="0.0.1"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            env.python = "3.13.0"  # type: ignore[misc]

    def test_structural_equality(self) -> None:
        e1 = EnvironmentFingerprint(
            python="3.12.3", platform="linux-x86_64", whatif_version="0.0.1"
        )
        e2 = EnvironmentFingerprint(
            python="3.12.3", platform="linux-x86_64", whatif_version="0.0.1"
        )
        assert e1 == e2


# --- RunManifest --------------------------------------------------------


def _env() -> EnvironmentFingerprint:
    return EnvironmentFingerprint(
        python="3.12.3",
        platform="linux-x86_64",
        whatif_version="0.0.1",
    )


class TestRunManifest:
    def _minimal(self) -> RunManifest:
        return RunManifest(
            experiment_id="exp_2026_05_05_001",
            started_at="2026-05-05T07:00:00Z",
            finished_at="2026-05-05T07:01:30Z",
            duration_ms=90_000,
            whatif_version="0.0.1",
            config_hash="abc123def456",
            selection_seed=42,
            source="langfuse",
            target="python:my_agent.replay:run",
            trust_floor=TrustFloor(),
            decision_policy=DecisionPolicy(),
            environment=_env(),
        )

    def test_construction_with_required_fields(self) -> None:
        m = self._minimal()
        assert m.experiment_id == "exp_2026_05_05_001"
        assert m.selection_seed == 42
        assert m.agent_identity is None  # default
        assert m.redaction == {}  # default
        assert m.sensitive_unwraps == []  # default

    def test_construction_with_agent_identity(self) -> None:
        m = dataclasses.replace(
            self._minimal(),
            agent_identity={
                "vendor": "anthropic",
                "model": "claude-sonnet-4-6",
                "prompt_template_id": "v3",
            },
        )
        assert m.agent_identity is not None
        assert m.agent_identity["vendor"] == "anthropic"

    def test_construction_with_redaction_metadata(self) -> None:
        m = dataclasses.replace(
            self._minimal(),
            redaction={
                "profile": "review",
                "enabled": True,
                "adapter_rules_version": "langfuse-redaction-v1",
            },
        )
        assert m.redaction["profile"] == "review"
        assert m.redaction["enabled"] is True

    def test_construction_with_sensitive_unwraps(self) -> None:
        unwrap = SensitiveUnwrap(
            classification="user_input",
            reason="render evidence section",
            location="whatifd/render/markdown.py:render_evidence:147",
        )
        m = dataclasses.replace(
            self._minimal(),
            sensitive_unwraps=[unwrap],
        )
        assert len(m.sensitive_unwraps) == 1
        assert m.sensitive_unwraps[0].classification == "user_input"

    def test_carries_trust_floor_for_audit(self) -> None:
        # The trust_floor field is the audit record of WHICH floor version
        # this run was evaluated against. v0.2 may bump to floor v2; v0.1
        # runs continue to validate against v1 because the manifest pins it.
        m = self._minimal()
        assert m.trust_floor.version == "v1"

    def test_carries_decision_policy_for_reproducibility(self) -> None:
        # The full policy is captured so a future re-run with the same
        # config_hash + selection_seed + policy produces byte-identical
        # deterministic output.
        m = self._minimal()
        assert m.decision_policy.require_baseline is True
        assert m.decision_policy.scorer_cache_mode == "auto"

    def test_frozen(self) -> None:
        m = self._minimal()
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.experiment_id = "different"  # type: ignore[misc]

    def test_structural_equality(self) -> None:
        m1 = self._minimal()
        m2 = self._minimal()
        assert m1 == m2

    def test_inequality_on_seed_diff(self) -> None:
        m1 = self._minimal()
        m2 = dataclasses.replace(m1, selection_seed=43)
        assert m1 != m2
