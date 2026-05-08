"""Tests for `whatifd.types.failure` — Phase 1.3 operational types."""

from __future__ import annotations

import dataclasses

import pytest

from whatifd.types import FailureRecord, Scope, Stage


def _record(**overrides: object) -> FailureRecord:
    """Construct a FailureRecord with sensible defaults; override per test."""
    defaults: dict[str, object] = {
        "id": "failure_001",
        "code": "cache_miss",
        "stage": "replay",
        "scope": "trace",
        "message": "tool 'search' not in cache for trace t_4a91f",
        "trace_id": "t_4a91f",
        "cohort": None,
        "retryable": False,
    }
    defaults.update(overrides)
    return FailureRecord(**defaults)  # type: ignore[arg-type]


class TestConstruction:
    def test_minimal_trace_scope(self) -> None:
        r = _record()
        assert r.id == "failure_001"
        assert r.scope == "trace"
        assert r.trace_id == "t_4a91f"
        assert r.cohort is None
        assert r.details == {}
        assert r.aggregated_into is None

    def test_cohort_scope(self) -> None:
        r = _record(
            scope="cohort",
            trace_id=None,
            cohort="baseline",
            code="scorer_unavailable",
            message="73% of baseline cohort hit 503 from scorer API",
        )
        assert r.scope == "cohort"
        assert r.cohort == "baseline"
        assert r.trace_id is None

    def test_run_scope(self) -> None:
        r = _record(
            scope="run",
            trace_id=None,
            cohort=None,
            code="cache_lock_unavailable",
            stage="score",
            message="could not acquire scorer cache lock",
        )
        assert r.scope == "run"

    def test_with_details(self) -> None:
        r = _record(details={"tool_name": "search", "expected_args_hash": "abc123"})
        assert r.details == {"tool_name": "search", "expected_args_hash": "abc123"}

    def test_aggregated_into_links_to_cohort_record(self) -> None:
        r = _record(aggregated_into="failure_cohort_001")
        assert r.aggregated_into == "failure_cohort_001"


class TestFrozenness:
    def test_cannot_assign_field(self) -> None:
        r = _record()
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.code = "different_code"  # type: ignore[misc]

    def test_cannot_add_arbitrary_attribute(self) -> None:
        r = _record()
        # `frozen=True` + `slots=True` blocks novel attribute setting, but
        # the exact error type varies across Python versions due to a known
        # interaction between dataclass-generated __setattr__ and slots-
        # rebuilt classes (TypeError from super() mismatch on 3.14, vs
        # AttributeError or FrozenInstanceError on earlier versions).
        # The point of the test is that the assignment fails — accept any
        # of the three.
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError, TypeError)):
            r.smuggled = "extra"  # type: ignore[attr-defined]


class TestEquality:
    def test_structural_equality(self) -> None:
        r1 = _record()
        r2 = _record()
        assert r1 == r2

    def test_inequality_on_field_diff(self) -> None:
        r1 = _record()
        r2 = _record(code="different")
        assert r1 != r2

    def test_hashable(self) -> None:
        # frozen=True dataclasses are hashable by default IF all fields are
        # hashable. `details` is a Mapping (defaults to dict, which is NOT
        # hashable). Confirm that records with a non-empty details map are
        # NOT hashable, and document the constraint.
        r = _record()
        # Empty dict in details — still a dict, still unhashable
        with pytest.raises(TypeError, match="unhashable"):
            hash(r)


class TestStageScopeLiterals:
    @pytest.mark.parametrize(
        "stage",
        ["ingest", "selection", "replay", "score", "diff", "decision", "report"],
    )
    def test_all_stages_accepted(self, stage: Stage) -> None:
        r = _record(stage=stage)
        assert r.stage == stage

    @pytest.mark.parametrize("scope", ["trace", "cohort", "run"])
    def test_all_scopes_accepted(self, scope: Scope) -> None:
        r = _record(scope=scope, trace_id=None, cohort=None)
        assert r.scope == scope
