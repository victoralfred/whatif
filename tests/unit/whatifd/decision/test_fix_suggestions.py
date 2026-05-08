"""Tests for `whatifd.decision.fix_suggestions` — Phase 2.4 registry + coverage gate.

Cardinal rule #8: Inconclusive must be actionable. The fix-suggestion
registry is the source of truth for "what should the user do about a
blocking finding". Coverage tests enforce:

- **Positive coverage**: every `blocks_ship` and `blocks_all` finding
  code in `FINDING_CODE_REGISTRY` has a matching entry here.
- **Negative coverage**: no `info`-severity finding code is in this
  registry. Info codes describe observations and need no fix.
- **Self-consistency**: `FixSuggestion.finding_code` matches its dict key.
- **Shape**: every entry has non-empty `summary`, at least one step,
  steps are strings, registry is `MappingProxyType`-immutable.

The cross-registry coverage assertion was staged as `xfail(strict=True)`
in `test_finding_codes.py` during Phase 2.3. Phase 2.4 lifts that test —
this file owns the canonical version; the placeholder there is removed
in the same PR.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping

import pytest

from whatifd.decision.finding_codes import FINDING_CODE_REGISTRY
from whatifd.decision.fix_suggestions import FIX_SUGGESTION_REGISTRY, FixSuggestion

from ._constants import CODE_RE

# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


class TestRegistryShape:
    def test_registry_is_non_empty(self) -> None:
        assert len(FIX_SUGGESTION_REGISTRY) >= 1

    def test_registry_is_immutable(self) -> None:
        with pytest.raises(TypeError):
            FIX_SUGGESTION_REGISTRY["forged"] = FixSuggestion(  # type: ignore[index]
                finding_code="forged",
                summary="x",
                steps=("x",),
                description="x",
            )

    def test_registry_is_typed_as_mapping(self) -> None:
        assert isinstance(FIX_SUGGESTION_REGISTRY, Mapping)

    def test_keys_are_lowercase_snake_case(self) -> None:
        for code in FIX_SUGGESTION_REGISTRY:
            assert CODE_RE.match(code), f"key {code!r} is not lowercase snake_case"

    def test_finding_code_matches_dict_key(self) -> None:
        # Catches the "renamed key but forgot to update finding_code" bug.
        for key, suggestion in FIX_SUGGESTION_REGISTRY.items():
            assert suggestion.finding_code == key, (
                f"key={key!r} has finding_code={suggestion.finding_code!r} — must match"
            )

    def test_every_entry_has_non_empty_summary(self) -> None:
        for code, suggestion in FIX_SUGGESTION_REGISTRY.items():
            assert suggestion.summary.strip(), f"code={code!r} has empty summary"

    def test_every_entry_has_at_least_one_step(self) -> None:
        # Cardinal #8: actionable. A suggestion with zero steps is by
        # definition not actionable.
        for code, suggestion in FIX_SUGGESTION_REGISTRY.items():
            assert len(suggestion.steps) >= 1, f"code={code!r} has no steps"

    def test_steps_are_non_empty_strings(self) -> None:
        for code, suggestion in FIX_SUGGESTION_REGISTRY.items():
            for i, step in enumerate(suggestion.steps):
                assert isinstance(step, str), f"code={code!r} step[{i}] is not a string"
                assert step.strip(), f"code={code!r} step[{i}] is empty"

    def test_steps_is_tuple(self) -> None:
        # Stable order matters for renderer output.
        for code, suggestion in FIX_SUGGESTION_REGISTRY.items():
            assert isinstance(suggestion.steps, tuple), f"code={code!r} steps must be tuple"

    def test_every_entry_has_non_empty_description(self) -> None:
        for code, suggestion in FIX_SUGGESTION_REGISTRY.items():
            assert suggestion.description.strip(), f"code={code!r} has empty description"

    def test_suggestion_dataclass_is_frozen(self) -> None:
        suggestion = next(iter(FIX_SUGGESTION_REGISTRY.values()))
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            suggestion.summary = "forged"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Cross-registry coverage (cardinal #8 gate)
# ---------------------------------------------------------------------------


class TestCrossRegistryCoverage:
    """The cardinal #8 enforcement point.

    Every blocking finding code MUST have a fix suggestion. Every fix
    suggestion MUST point at a real blocking finding code. No info-
    severity codes appear here.
    """

    @staticmethod
    def _blocking_finding_codes() -> set[str]:
        return {
            code
            for code, spec in FINDING_CODE_REGISTRY.items()
            if spec.severity in ("blocks_ship", "blocks_all")
        }

    @staticmethod
    def _info_finding_codes() -> set[str]:
        return {code for code, spec in FINDING_CODE_REGISTRY.items() if spec.severity == "info"}

    def test_every_blocking_finding_has_a_fix_suggestion(self) -> None:
        blocking = self._blocking_finding_codes()
        registered = set(FIX_SUGGESTION_REGISTRY)
        missing = blocking - registered
        assert not missing, (
            f"blocking finding codes without fix suggestions: {sorted(missing)}. "
            "Cardinal #8: every blocks_ship / blocks_all finding must be actionable. "
            "Add an entry to FIX_SUGGESTION_REGISTRY in fix_suggestions.py."
        )

    def test_every_fix_suggestion_targets_a_real_finding_code(self) -> None:
        # Catches the inverse drift: a fix suggestion for a deleted or
        # renamed finding code.
        registered = set(FIX_SUGGESTION_REGISTRY)
        all_finding_codes = set(FINDING_CODE_REGISTRY)
        orphaned = registered - all_finding_codes
        assert not orphaned, (
            f"fix suggestions for unknown finding codes: {sorted(orphaned)}. "
            "Either add the code to FINDING_CODE_REGISTRY or remove the suggestion."
        )

    def test_no_info_finding_code_in_fix_suggestion_registry(self) -> None:
        # PR #17 review suggestion: info codes describe observations, not
        # actionable issues. They must not appear here.
        info_codes = self._info_finding_codes()
        registered = set(FIX_SUGGESTION_REGISTRY)
        misplaced = info_codes & registered
        assert not misplaced, (
            f"info finding codes in fix-suggestion registry: {sorted(misplaced)}. "
            "Info findings describe observations, not actionable issues. Remove these "
            "from FIX_SUGGESTION_REGISTRY."
        )

    def test_blocking_and_registry_are_exact_match(self) -> None:
        # The composite of the three preceding tests: registry == blocking.
        # If this fires alone but the others pass, something subtle drifted.
        assert set(FIX_SUGGESTION_REGISTRY) == self._blocking_finding_codes()
