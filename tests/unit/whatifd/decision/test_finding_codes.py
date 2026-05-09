"""Tests for `whatifd.decision.finding_codes` — Phase 2.3 registry + factory.

Mirror of `test_failure_codes.py` for the policy-conclusion side. Coverage:

- Registry shape: lowercase snake_case codes, valid Severity literal,
  non-empty descriptions and message templates, `MappingProxyType`
  immutability, frozen `FindingCodeSpec`.
- Factory positive: makes findings for every code with synthetic details.
- Factory contract violations: unknown code, missing required details,
  derived_from_failures expectation breaches.
- Severity is non-overrideable (the only registry where the factory
  refuses to let callers change a field).
- Cross-registry: every blocking finding code (blocks_ship/blocks_all)
  has a matching entry in the eventual fix-suggestion registry — that
  test is xfail today and lifts in Phase 2.4.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from typing import get_args

import pytest

from whatifd.decision.finding_codes import (
    FINDING_CODE_REGISTRY,
    FindingCodeSpec,
    make_decision_finding,
)
from whatifd.types.finding import DecisionFinding, Severity

from ._constants import CODE_RE

_VALID_SEVERITIES: frozenset[Severity] = frozenset(get_args(Severity))


def _synthetic_details(spec: FindingCodeSpec) -> dict[str, str]:
    return {key: f"stub-{key}" for key in spec.required_details}


def _derived_for(spec: FindingCodeSpec) -> list[str]:
    """Match the spec's derived_from_failures expectation with stub ids."""
    if spec.derived_from_failures_expectation == "always":
        return ["failure_001"]
    return []


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


class TestRegistryShape:
    def test_registry_is_non_empty(self) -> None:
        assert len(FINDING_CODE_REGISTRY) >= 1

    def test_registry_is_immutable(self) -> None:
        with pytest.raises(TypeError):
            FINDING_CODE_REGISTRY["forged"] = FindingCodeSpec(  # type: ignore[index]
                severity="info",
                message_template="x",
                required_details=(),
                derived_from_failures_expectation="never",
                description="x",
            )

    def test_codes_use_lowercase_snake_case(self) -> None:
        for code in FINDING_CODE_REGISTRY:
            assert CODE_RE.match(code), f"code {code!r} is not lowercase snake_case"

    def test_every_entry_has_valid_severity(self) -> None:
        for code, spec in FINDING_CODE_REGISTRY.items():
            assert spec.severity in _VALID_SEVERITIES, f"code={code!r} has invalid severity"

    def test_every_entry_has_non_empty_description(self) -> None:
        for code, spec in FINDING_CODE_REGISTRY.items():
            assert spec.description.strip(), f"code={code!r} has empty description"

    def test_every_entry_has_non_empty_message_template(self) -> None:
        for code, spec in FINDING_CODE_REGISTRY.items():
            assert spec.message_template.strip(), f"code={code!r} has empty message_template"

    def test_required_details_is_tuple(self) -> None:
        for code, spec in FINDING_CODE_REGISTRY.items():
            assert isinstance(spec.required_details, tuple), (
                f"code={code!r} required_details must be tuple"
            )

    def test_required_details_keys_are_lowercase_snake_case(self) -> None:
        for code, spec in FINDING_CODE_REGISTRY.items():
            for key in spec.required_details:
                assert CODE_RE.match(key), (
                    f"code={code!r} required-detail key {key!r} is not snake_case"
                )

    def test_message_template_placeholders_match_required_details(self) -> None:
        # Every {placeholder} in the template must appear in required_details,
        # and every required_details key must appear in the template. Catches
        # template/details drift on registry updates.
        placeholder_re = re.compile(r"\{([a-z][a-z0-9_]*)\}")
        for code, spec in FINDING_CODE_REGISTRY.items():
            placeholders = set(placeholder_re.findall(spec.message_template))
            required = set(spec.required_details)
            assert placeholders == required, (
                f"code={code!r}: template placeholders {placeholders} != "
                f"required_details {required}"
            )

    def test_spec_dataclass_is_frozen(self) -> None:
        spec = next(iter(FINDING_CODE_REGISTRY.values()))
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            spec.severity = "info"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Severity-specific shape rules
# ---------------------------------------------------------------------------


class TestSeveritySemantics:
    def test_blocks_all_codes_expect_failure_derivation(self) -> None:
        # blocks_all findings represent operational catastrophes (cache
        # corruption, lock failures, systemic cohort failures). Each one
        # should wrap at least one FailureRecord — otherwise the run is
        # forced Inconclusive without operational evidence, which is the
        # bypass cardinal #2 forbids.
        for code, spec in FINDING_CODE_REGISTRY.items():
            if spec.severity == "blocks_all":
                assert spec.derived_from_failures_expectation == "always", (
                    f"blocks_all code {code!r} should expect derived_from_failures "
                    f"(got {spec.derived_from_failures_expectation!r}) — otherwise "
                    "Inconclusive can fire without operational evidence."
                )

    def test_info_codes_do_not_expect_failure_derivation(self) -> None:
        # info findings are observations about the run itself (improvement
        # observed, etc.) — they shouldn't carry failure references.
        for code, spec in FINDING_CODE_REGISTRY.items():
            if spec.severity == "info":
                assert spec.derived_from_failures_expectation == "never", (
                    f"info code {code!r} should not derive from failures "
                    f"(got {spec.derived_from_failures_expectation!r})."
                )


# ---------------------------------------------------------------------------
# Factory: positive sweep
# ---------------------------------------------------------------------------


class TestFactoryProducesFindingForEveryCode:
    def test_every_registered_code_constructs_with_synthetic_details(self) -> None:
        for code, spec in FINDING_CODE_REGISTRY.items():
            finding = make_decision_finding(
                code,
                message=f"synthetic test for {code}",
                details=_synthetic_details(spec),
                derived_from_failures=_derived_for(spec),
            )
            assert isinstance(finding, DecisionFinding)
            assert finding.code == code
            assert finding.severity == spec.severity
            for key in spec.required_details:
                assert key in finding.details


# ---------------------------------------------------------------------------
# Factory: contract violations
# ---------------------------------------------------------------------------


class TestFactoryRejectsUnknownCode:
    def test_unknown_code_raises_with_helpful_message(self) -> None:
        with pytest.raises(ValueError, match="unknown finding code"):
            make_decision_finding(
                "code_that_was_never_registered",
                message="x",
            )

    def test_unknown_code_message_lists_known_codes(self) -> None:
        with pytest.raises(ValueError, match="improvement_observed"):
            make_decision_finding("totally_made_up", message="x")


class TestFactoryRejectsMissingRequiredDetails:
    def test_missing_required_detail_raises(self) -> None:
        with pytest.raises(ValueError, match="missing"):
            make_decision_finding(
                "baseline_regression_above_threshold",
                message="x",
                details={"observed": "0.20"},  # missing 'threshold'
            )

    def test_extra_details_keys_allowed(self) -> None:
        # Cardinal #6: details is an extension point.
        finding = make_decision_finding(
            "improvement_observed",
            message="x",
            details={
                "median_delta": "0.310",
                "threshold": "0.050",
                "extra_diagnostic": "value",
            },
        )
        assert finding.details["extra_diagnostic"] == "value"


class TestFactoryEnforcesDerivationExpectation:
    def test_never_rejects_non_empty_derivation(self) -> None:
        with pytest.raises(ValueError, match="stands alone"):
            make_decision_finding(
                "improvement_observed",
                message="x",
                details={"median_delta": "0.310", "threshold": "0.050"},
                derived_from_failures=["failure_001"],
            )

    def test_always_rejects_empty_derivation(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            make_decision_finding(
                "cache_corruption_detected",
                message="x",
                details={"cache_path": ".whatifd/cache"},
                derived_from_failures=[],
            )

    def test_always_rejects_omitted_derivation(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            make_decision_finding(
                "cache_corruption_detected",
                message="x",
                details={"cache_path": ".whatifd/cache"},
                # derived_from_failures omitted entirely
            )


class TestSeverityNonOverrideable:
    def test_factory_signature_does_not_accept_severity_kwarg(self) -> None:
        # Severity drives verdict (cardinal #2). The factory deliberately
        # does NOT accept severity as a kwarg — calling with one raises
        # TypeError at the function-signature level.
        with pytest.raises(TypeError):
            make_decision_finding(  # type: ignore[call-arg]
                "improvement_observed",
                message="x",
                details={"median_delta": "0.310", "threshold": "0.050"},
                severity="blocks_ship",
            )

    def test_severity_always_resolves_from_registry(self) -> None:
        # Even when the registry says blocks_all, the factory cannot be
        # talked into emitting blocks_ship. Pin the registry's authority.
        finding = make_decision_finding(
            "cache_corruption_detected",
            message="x",
            details={"cache_path": ".whatifd/cache"},
            derived_from_failures=["failure_001"],
        )
        assert finding.severity == "blocks_all"


# ---------------------------------------------------------------------------
# Cross-registry coverage moved to test_fix_suggestions.py
# ---------------------------------------------------------------------------
# Phase 2.3 staged a strict-xfail placeholder here for the cardinal #8
# gate ("every blocking finding has a fix suggestion"). Phase 2.4 ships
# the registry; the canonical coverage test lives in
# `test_fix_suggestions.py::TestCrossRegistryCoverage` so the assertion
# sits next to the registry it gates.


# ---------------------------------------------------------------------------
# Module-level invariants: registry returned as Mapping, not dict
# ---------------------------------------------------------------------------


def test_registry_is_typed_as_mapping() -> None:
    assert isinstance(FINDING_CODE_REGISTRY, Mapping)
