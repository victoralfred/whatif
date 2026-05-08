"""Tests for `whatifd.decision.failure_codes` — Phase 2.2 registry + factory.

Cardinal rule #1 (failure-as-data): the registry is the source of truth
for what counts as an expected failure. These tests cover:

- Registry coverage: every entry has valid stage/scope, non-empty
  description, immutable storage.
- Factory positive: makes records for every code with synthetic details.
- Factory contract violations: unknown code, missing required details,
  scope/identifier mismatches all raise `ValueError`.
- Default propagation: stage, scope, and retryable resolve from the spec
  when not overridden.
- Scope override: aggregation use-case (trace-default code emitted as
  cohort-scope after Phase 2.7 rolls failures up).
"""

from __future__ import annotations

import pytest

from whatifd.decision.failure_codes import (
    FAILURE_CODE_REGISTRY,
    FailureCodeSpec,
    make_failure_record,
)
from whatifd.types.failure import FailureRecord, Scope, Stage

from ._constants import CODE_RE

_VALID_STAGES: frozenset[Stage] = frozenset(
    {"ingest", "selection", "replay", "score", "diff", "decision", "report"}
)
_VALID_SCOPES: frozenset[Scope] = frozenset({"trace", "cohort", "run"})


def _synthetic_details(spec: FailureCodeSpec) -> dict[str, str]:
    """Build a details dict satisfying spec.required_details with stub values."""
    return {key: f"stub-{key}" for key in spec.required_details}


def _identifiers_for(scope: Scope) -> dict[str, str | None]:
    if scope == "trace":
        return {"trace_id": "t_001"}
    if scope == "cohort":
        return {"cohort": "failure"}
    return {}  # run


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------


class TestRegistryShape:
    def test_registry_is_non_empty(self) -> None:
        assert len(FAILURE_CODE_REGISTRY) >= 1

    def test_registry_is_immutable(self) -> None:
        # MappingProxyType raises TypeError on mutation.
        with pytest.raises(TypeError):
            FAILURE_CODE_REGISTRY["forged"] = FailureCodeSpec(  # type: ignore[index]
                stage="ingest",
                default_scope="trace",
                required_details=(),
                retryable_default=False,
                description="x",
            )

    def test_codes_use_lowercase_snake_case(self) -> None:
        for code in FAILURE_CODE_REGISTRY:
            assert CODE_RE.match(code), f"code {code!r} is not lowercase snake_case"

    def test_every_entry_has_valid_stage_and_scope(self) -> None:
        for code, spec in FAILURE_CODE_REGISTRY.items():
            assert spec.stage in _VALID_STAGES, f"code={code!r} has invalid stage"
            assert spec.default_scope in _VALID_SCOPES, f"code={code!r} has invalid scope"

    def test_every_entry_has_non_empty_description(self) -> None:
        for code, spec in FAILURE_CODE_REGISTRY.items():
            assert spec.description.strip(), f"code={code!r} has empty description"

    def test_required_details_is_tuple(self) -> None:
        # Stable order matters — tests, schemas, and renderers iterate this.
        for code, spec in FAILURE_CODE_REGISTRY.items():
            assert isinstance(spec.required_details, tuple), (
                f"code={code!r} required_details must be tuple, not {type(spec.required_details).__name__}"
            )

    def test_required_details_keys_are_lowercase_snake_case(self) -> None:
        for code, spec in FAILURE_CODE_REGISTRY.items():
            for key in spec.required_details:
                assert CODE_RE.match(key), (
                    f"code={code!r} required-detail key {key!r} is not snake_case"
                )

    def test_spec_dataclass_is_frozen(self) -> None:
        # Python 3.13+ raises FrozenInstanceError on frozen dataclass mutation;
        # earlier versions raise AttributeError when slots intercepts first.
        import dataclasses

        spec = next(iter(FAILURE_CODE_REGISTRY.values()))
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            spec.stage = "selection"  # type: ignore[misc]


class TestStageScopeReachability:
    """Catch drift between scope and stage on registry updates.

    The two-type scope rule (failure.py) and the pipeline order combine
    to constrain which (stage, scope) pairs make sense:

    - `default_scope=="trace"` requires per-trace context, which exists
      from ingest through diff. Decision and report run after
      aggregation; trace-scope codes there would imply context the core
      doesn't have.
    - `default_scope=="cohort"` requires cohorts to exist (post-
      selection, post-aggregation). Decision and report are the natural
      places; selection itself COULD emit cohort-scope (e.g., empty
      cohort), but v0.1 keeps the rule narrow until that pattern arises.
    - `default_scope=="run"` is run-level and can fire at any stage
      since the run encompasses all of them.
    """

    _TRACE_STAGES = frozenset({"ingest", "selection", "replay", "score", "diff"})
    _COHORT_STAGES = frozenset({"decision", "report"})

    def test_trace_default_scope_implies_per_trace_stage(self) -> None:
        for code, spec in FAILURE_CODE_REGISTRY.items():
            if spec.default_scope == "trace":
                assert spec.stage in self._TRACE_STAGES, (
                    f"code={code!r} has default_scope='trace' but stage={spec.stage!r} "
                    f"— trace context only exists in {sorted(self._TRACE_STAGES)}."
                )

    def test_cohort_default_scope_implies_post_aggregation_stage(self) -> None:
        for code, spec in FAILURE_CODE_REGISTRY.items():
            if spec.default_scope == "cohort":
                assert spec.stage in self._COHORT_STAGES, (
                    f"code={code!r} has default_scope='cohort' but stage={spec.stage!r} "
                    f"— cohort context exists only in {sorted(self._COHORT_STAGES)}."
                )

    def test_run_default_scope_unconstrained(self) -> None:
        # Smoke: run-scope codes can sit anywhere. This test exists to
        # document the asymmetry (no constraint) so the absence of one
        # isn't taken as oversight.
        run_codes = [
            code for code, spec in FAILURE_CODE_REGISTRY.items() if spec.default_scope == "run"
        ]
        assert run_codes, "expected at least one run-scope code (cache subsystem)"


# ---------------------------------------------------------------------------
# Factory: positive sweep over every registered code
# ---------------------------------------------------------------------------


class TestFactoryProducesRecordForEveryCode:
    def test_every_registered_code_constructs_with_synthetic_details(self) -> None:
        # Phase 9 integration tests run a stronger version of this sweep
        # against the real failure-injection harness; this unit test pins
        # the registry/factory contract.
        for code, spec in FAILURE_CODE_REGISTRY.items():
            ids = _identifiers_for(spec.default_scope)
            record = make_failure_record(
                code,
                id=f"failure_{code}",
                message=f"synthetic test for {code}",
                details=_synthetic_details(spec),
                **ids,  # type: ignore[arg-type]
            )
            assert isinstance(record, FailureRecord)
            assert record.code == code
            assert record.stage == spec.stage
            assert record.scope == spec.default_scope
            assert record.retryable == spec.retryable_default
            for key in spec.required_details:
                assert key in record.details


# ---------------------------------------------------------------------------
# Factory: default propagation + override
# ---------------------------------------------------------------------------


class TestFactoryDefaults:
    def test_stage_propagates_from_spec(self) -> None:
        record = make_failure_record(
            "tool_cache_miss",
            id="failure_001",
            message="msg",
            trace_id="t_001",
            details={"tool_name": "search"},
        )
        assert record.stage == "replay"

    def test_scope_propagates_from_spec_when_not_overridden(self) -> None:
        record = make_failure_record(
            "tool_cache_miss",
            id="failure_001",
            message="msg",
            trace_id="t_001",
            details={"tool_name": "search"},
        )
        assert record.scope == "trace"

    def test_retryable_propagates_from_spec(self) -> None:
        # scorer_unavailable defaults to retryable=True
        record = make_failure_record(
            "scorer_unavailable",
            id="failure_001",
            message="msg",
            trace_id="t_001",
            details={"provider": "anthropic", "reason": "503"},
        )
        assert record.retryable is True

    def test_retryable_override(self) -> None:
        record = make_failure_record(
            "scorer_unavailable",
            id="failure_001",
            message="msg",
            trace_id="t_001",
            retryable=False,
            details={"provider": "anthropic", "reason": "503"},
        )
        assert record.retryable is False

    def test_scope_override_for_aggregation(self) -> None:
        # Phase 2.7 rolls trace-default codes into cohort-scope records
        # via an aggregation pass. The factory must accept the override.
        record = make_failure_record(
            "tool_cache_miss",
            id="failure_aggregate_001",
            message="73% of failure cohort traces had cache misses on 'search'",
            cohort="failure",
            scope="cohort",
            details={"tool_name": "search"},
        )
        assert record.scope == "cohort"
        assert record.cohort == "failure"
        assert record.trace_id is None


# ---------------------------------------------------------------------------
# Factory: contract violations
# ---------------------------------------------------------------------------


class TestFactoryRejectsUnknownCode:
    def test_unknown_code_raises_with_helpful_message(self) -> None:
        with pytest.raises(ValueError, match="unknown failure code"):
            make_failure_record(
                "code_that_was_never_registered",
                id="failure_001",
                message="x",
                trace_id="t_001",
            )

    def test_unknown_code_message_lists_known_codes(self) -> None:
        with pytest.raises(ValueError, match="tool_cache_miss"):
            make_failure_record(
                "totally_made_up",
                id="failure_001",
                message="x",
                trace_id="t_001",
            )


class TestFactoryRejectsMissingRequiredDetails:
    def test_missing_required_detail_raises(self) -> None:
        with pytest.raises(ValueError, match="missing"):
            make_failure_record(
                "tool_cache_miss",
                id="failure_001",
                message="x",
                trace_id="t_001",
                details={},  # missing tool_name
            )

    def test_partial_required_details_raises(self) -> None:
        # runner_exception requires both exception_type and message
        with pytest.raises(ValueError, match="missing"):
            make_failure_record(
                "runner_exception",
                id="failure_001",
                message="x",
                trace_id="t_001",
                details={"exception_type": "TimeoutError"},  # missing 'message'
            )

    def test_extra_details_keys_allowed(self) -> None:
        # Cardinal #6: details is an extension point; extra keys ride along.
        record = make_failure_record(
            "tool_cache_miss",
            id="failure_001",
            message="x",
            trace_id="t_001",
            details={"tool_name": "search", "diagnostic_extra": "value"},
        )
        assert record.details["diagnostic_extra"] == "value"

    def test_no_details_when_none_required(self) -> None:
        # cache_corruption_detected requires only cache_path; no details
        # at all should still raise (cache_path is required).
        with pytest.raises(ValueError, match="missing"):
            make_failure_record(
                "cache_corruption_detected",
                id="failure_001",
                message="x",
            )


class TestFactoryEnforcesScopeIdentifierConsistency:
    def test_trace_scope_requires_trace_id(self) -> None:
        with pytest.raises(ValueError, match="scope='trace' requires trace_id"):
            make_failure_record(
                "tool_cache_miss",
                id="failure_001",
                message="x",
                # trace_id omitted
                details={"tool_name": "search"},
            )

    def test_trace_scope_forbids_cohort(self) -> None:
        with pytest.raises(ValueError, match="scope='trace' forbids cohort"):
            make_failure_record(
                "tool_cache_miss",
                id="failure_001",
                message="x",
                trace_id="t_001",
                cohort="failure",
                details={"tool_name": "search"},
            )

    def test_cohort_scope_requires_cohort(self) -> None:
        with pytest.raises(ValueError, match="scope='cohort' requires cohort"):
            make_failure_record(
                "ci_uncomputable_for_required_cohort",
                id="failure_001",
                message="x",
                # cohort omitted
                details={"cohort": "failure", "reason": "sample too small"},
            )

    def test_cohort_scope_forbids_trace_id(self) -> None:
        with pytest.raises(ValueError, match="scope='cohort' forbids trace_id"):
            make_failure_record(
                "ci_uncomputable_for_required_cohort",
                id="failure_001",
                message="x",
                cohort="failure",
                trace_id="t_001",
                details={"cohort": "failure", "reason": "sample too small"},
            )

    def test_run_scope_forbids_both(self) -> None:
        with pytest.raises(ValueError, match="scope='run' forbids trace_id"):
            make_failure_record(
                "cache_lock_unavailable",
                id="failure_001",
                message="x",
                trace_id="t_001",
                details={"lock_path": ".whatif/cache/scorer/.lock"},
            )
        with pytest.raises(ValueError, match="scope='run' forbids cohort"):
            make_failure_record(
                "cache_lock_unavailable",
                id="failure_001",
                message="x",
                cohort="failure",
                details={"lock_path": ".whatif/cache/scorer/.lock"},
            )


# ---------------------------------------------------------------------------
# Aggregated-into linkage
# ---------------------------------------------------------------------------


class TestAggregatedInto:
    def test_aggregated_into_is_optional(self) -> None:
        record = make_failure_record(
            "tool_cache_miss",
            id="failure_001",
            message="x",
            trace_id="t_001",
            details={"tool_name": "search"},
        )
        assert record.aggregated_into is None

    def test_aggregated_into_threads_through(self) -> None:
        # Phase 2.7 sets aggregated_into on the trace record after
        # rolling it up; the factory just needs to pass it through.
        record = make_failure_record(
            "tool_cache_miss",
            id="failure_001",
            message="x",
            trace_id="t_001",
            details={"tool_name": "search"},
            aggregated_into="failure_cohort_aggregate_001",
        )
        assert record.aggregated_into == "failure_cohort_aggregate_001"
