"""Tests for `whatif.cache.policy` — Phase 3.4 cache mode resolution.

The load-bearing properties:

1. **Concrete inputs pass through unchanged** — user explicitly chose
   `on`/`off`/`read_only`/`refresh`, no inference, no finding.
2. **`auto` + CI signal → `on` with `cache_mode_inferred` finding** —
   the manifest discloses what was used.
3. **`auto` + no CI signal → `auto` unchanged** — interactive default.
4. **CI signal detection is non-exhaustive but lowercased-truthy-aware**
   — accepts `CI=true`/`CI=1`, rejects `CI=false`/`CI=0` (operator
   opt-out).
"""

from __future__ import annotations

import pytest

from whatif.cache.policy import (
    CachePolicyResolution,
    _detected_ci_signal,
    resolve_cache_mode,
)
from whatif.types.policy import ScorerCacheMode

# ---------------------------------------------------------------------------
# Concrete-input pass-through
# ---------------------------------------------------------------------------


class TestConcreteModesPassThrough:
    @pytest.mark.parametrize("mode", ["on", "off", "read_only", "refresh"])
    def test_concrete_mode_returns_unchanged(self, mode: ScorerCacheMode) -> None:
        result = resolve_cache_mode(mode, env={})
        assert result.mode == mode
        assert result.findings == ()

    def test_concrete_mode_ignores_ci_env(self) -> None:
        # User explicitly chose `read_only`; CI signal must NOT
        # promote this to `on`. The user's explicit choice wins.
        result = resolve_cache_mode("read_only", env={"CI": "true"})
        assert result.mode == "read_only"
        assert result.findings == ()


# ---------------------------------------------------------------------------
# Auto + CI signal → on (with finding)
# ---------------------------------------------------------------------------


class TestAutoUnderCI:
    @pytest.mark.parametrize(
        "env_var",
        ["CI", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE", "JENKINS_URL"],
    )
    def test_auto_with_ci_signal_resolves_to_on(self, env_var: str) -> None:
        result = resolve_cache_mode("auto", env={env_var: "true"})
        assert result.mode == "on"
        assert len(result.findings) == 1

    def test_finding_carries_required_details(self) -> None:
        result = resolve_cache_mode("auto", env={"CI": "true"})
        finding = result.findings[0]
        assert finding.code == "cache_mode_inferred"
        assert finding.severity == "info"
        assert finding.details["input_mode"] == "auto"
        assert finding.details["resolved_mode"] == "on"
        assert finding.details["env_signal"] == "CI"

    def test_first_truthy_signal_wins(self) -> None:
        # Multiple truthy CI vars: the iteration order in
        # _CI_ENV_VARS picks the first one. CI is checked first.
        result = resolve_cache_mode(
            "auto",
            env={"GITHUB_ACTIONS": "true", "CI": "true"},
        )
        assert result.findings[0].details["env_signal"] == "CI"

    def test_alternate_truthy_value_accepted(self) -> None:
        # CI=1 is also truthy (some older runners use this).
        result = resolve_cache_mode("auto", env={"CI": "1"})
        assert result.mode == "on"


# ---------------------------------------------------------------------------
# Auto + no CI signal → auto unchanged
# ---------------------------------------------------------------------------


class TestAutoInteractive:
    def test_auto_no_env_stays_auto(self) -> None:
        result = resolve_cache_mode("auto", env={})
        assert result.mode == "auto"
        assert result.findings == ()

    def test_auto_with_ci_false_stays_auto(self) -> None:
        # Operator opt-out: CI=false is rejected.
        result = resolve_cache_mode("auto", env={"CI": "false"})
        assert result.mode == "auto"
        assert result.findings == ()

    def test_auto_with_ci_zero_stays_auto(self) -> None:
        # CI=0 also rejected.
        result = resolve_cache_mode("auto", env={"CI": "0"})
        assert result.mode == "auto"

    def test_auto_with_empty_string_stays_auto(self) -> None:
        # Empty value is falsy.
        result = resolve_cache_mode("auto", env={"CI": ""})
        assert result.mode == "auto"

    def test_auto_with_unrelated_env_stays_auto(self) -> None:
        # Random unrelated env vars don't trigger inference.
        result = resolve_cache_mode(
            "auto",
            env={"PATH": "/usr/bin", "HOME": "/home/user"},
        )
        assert result.mode == "auto"


# ---------------------------------------------------------------------------
# _detected_ci_signal direct coverage
# ---------------------------------------------------------------------------


class TestDetectedCiSignal:
    @pytest.mark.parametrize(
        "env, expected",
        [
            ({"CI": "true"}, "CI"),
            ({"GITHUB_ACTIONS": "true"}, "GITHUB_ACTIONS"),
            ({"GITLAB_CI": "true"}, "GITLAB_CI"),
            ({"BUILDKITE": "true"}, "BUILDKITE"),
            ({"JENKINS_URL": "http://j"}, "JENKINS_URL"),
        ],
    )
    def test_each_supported_signal_detected(self, env: dict[str, str], expected: str) -> None:
        # Parametrized rather than packed-asserts so a single
        # signal-detection regression points at the offending var
        # directly.
        assert _detected_ci_signal(env) == expected

    def test_returns_none_on_empty_env(self) -> None:
        assert _detected_ci_signal({}) is None

    def test_case_insensitive_truthy_check(self) -> None:
        # The truthy comparator lowercases value before checking
        # against "false"/"0", so "FALSE" and "False" both reject.
        assert _detected_ci_signal({"CI": "False"}) is None
        assert _detected_ci_signal({"CI": "FALSE"}) is None
        # And accepts other case forms of truthy strings.
        assert _detected_ci_signal({"CI": "True"}) == "CI"


# ---------------------------------------------------------------------------
# Type / structure pins
# ---------------------------------------------------------------------------


class TestResolutionShape:
    def test_resolution_is_frozen(self) -> None:
        import dataclasses

        result = resolve_cache_mode("on", env={})
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.mode = "off"  # type: ignore[misc]

    def test_findings_is_tuple_not_list(self) -> None:
        # Tuple → immutable; callers can't accidentally append into the
        # resolution's findings collection.
        result = resolve_cache_mode("auto", env={"CI": "true"})
        assert isinstance(result.findings, tuple)

    def test_resolution_dataclass_returned(self) -> None:
        result = resolve_cache_mode("auto", env={})
        assert isinstance(result, CachePolicyResolution)
