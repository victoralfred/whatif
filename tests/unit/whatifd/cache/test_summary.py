"""Tests for `whatifd.cache.summary` — Phase 3.5 CacheSummary.

Pin properties:

1. **All required fields must be supplied** — frozen dataclass with
   no defaults on required fields; mypy + dataclass constructor
   enforce.
2. **Optional fields default sanely** — `policy_violations=()`,
   `oldest_hit_age_days=None`, `models_distribution=MappingProxyType({})`.
3. **Frozen + immutable view of mappings** — `policy_violations` is
   tuple; `models_distribution` is Mapping (specifically
   `MappingProxyType` by default), not `dict`.
4. **`PolicyViolationRecord` shape parallels `FloorFailure`** — same
   `rule`/`observed`/`threshold` triple, mixed types on observed.
5. **`CachePolicySnapshot` carries the runtime cache-policy fields** —
   `mode`, `warn_after_days`, `block_after_days`, `storage_profile`.

These pins anchor the schema-validation work that lands in Phase 5
(`ReportV01` requires `cache_summary` populated).
"""

from __future__ import annotations

import dataclasses
from types import MappingProxyType

import pytest

from whatifd.cache.summary import (
    CachePolicySnapshot,
    CacheSummary,
    PolicyViolationRecord,
)


def _policy() -> CachePolicySnapshot:
    return CachePolicySnapshot(
        mode="on",
        warn_after_days=30,
        block_after_days=90,
        storage_profile="normalized_result_only",
    )


def _summary(**overrides: object) -> CacheSummary:
    base: dict[str, object] = {
        "schema_version": "v1",
        "key_version": "v1",
        "mode": "on",
        "storage_profile": "normalized_result_only",
        "storage_path": ".whatif/cache",
        "hits": 0,
        "misses": 0,
        "writes": 0,
        "stale_hits": 0,
        "corrupted_entries": 0,
        "policy": _policy(),
    }
    base.update(overrides)
    return CacheSummary(**base)  # type: ignore[arg-type]


class TestCacheSummaryConstruction:
    def test_minimal_required_fields(self) -> None:
        summary = _summary()
        assert summary.schema_version == "v1"
        assert summary.key_version == "v1"
        assert summary.mode == "on"
        assert summary.storage_profile == "normalized_result_only"
        assert summary.storage_path == ".whatif/cache"
        assert summary.hits == 0
        assert summary.misses == 0
        assert summary.writes == 0
        assert summary.stale_hits == 0
        assert summary.corrupted_entries == 0

    def test_optional_fields_default(self) -> None:
        summary = _summary()
        assert summary.policy_violations == ()
        assert summary.oldest_hit_age_days is None
        assert dict(summary.models_distribution) == {}

    def test_full_population(self) -> None:
        violation = PolicyViolationRecord(
            rule="scorer_cache_warn_after_days",
            observed=45,
            threshold=30,
        )
        summary = _summary(
            hits=100,
            misses=12,
            writes=12,
            stale_hits=2,
            corrupted_entries=1,
            policy_violations=(violation,),
            oldest_hit_age_days=45,
            models_distribution=MappingProxyType({"claude-sonnet-4-6": 80, "claude-haiku-4-5": 20}),
        )
        assert summary.hits == 100
        assert summary.policy_violations == (violation,)
        assert summary.oldest_hit_age_days == 45
        assert dict(summary.models_distribution) == {
            "claude-sonnet-4-6": 80,
            "claude-haiku-4-5": 20,
        }


class TestCacheSummaryFrozen:
    def test_summary_is_frozen(self) -> None:
        summary = _summary()
        with pytest.raises(dataclasses.FrozenInstanceError):
            summary.hits = 99  # type: ignore[misc]

    def test_policy_snapshot_is_frozen(self) -> None:
        snapshot = _policy()
        with pytest.raises(dataclasses.FrozenInstanceError):
            snapshot.mode = "off"  # type: ignore[misc]

    def test_policy_violation_is_frozen(self) -> None:
        violation = PolicyViolationRecord(rule="x", observed=1, threshold=2)
        with pytest.raises(dataclasses.FrozenInstanceError):
            violation.rule = "y"  # type: ignore[misc]

    def test_policy_violations_is_tuple_not_list(self) -> None:
        # Cardinal #6: structured records in an immutable container.
        # A list would let callers append after construction.
        summary = _summary()
        assert isinstance(summary.policy_violations, tuple)

    def test_models_distribution_is_mapping(self) -> None:
        # Returning Mapping (specifically MappingProxyType) instead of
        # dict prevents callers from mutating the runtime state.
        summary = _summary()
        from collections.abc import Mapping

        assert isinstance(summary.models_distribution, Mapping)


class TestPolicyViolationRecord:
    def test_int_observed(self) -> None:
        v = PolicyViolationRecord(rule="warn_after_days", observed=45, threshold=30)
        assert v.observed == 45
        assert v.threshold == 30

    def test_float_observed(self) -> None:
        # Used by future ratio-based violations (e.g., corruption rate).
        v = PolicyViolationRecord(
            rule="corruption_rate",
            observed=0.15,
            threshold=0.10,
        )
        assert v.observed == 0.15

    def test_string_observed(self) -> None:
        # Descriptor-style observations for non-numeric rules.
        v = PolicyViolationRecord(
            rule="storage_profile_mismatch",
            observed="full_judge_io",
            threshold="normalized_result_only",  # type: ignore[arg-type]
        )
        assert v.observed == "full_judge_io"

    def test_value_equality(self) -> None:
        # Frozen dataclasses compare value-wise; useful for set
        # operations and de-duplication of violation records.
        a = PolicyViolationRecord(rule="x", observed=1, threshold=2)
        b = PolicyViolationRecord(rule="x", observed=1, threshold=2)
        assert a == b


class TestCachePolicySnapshot:
    def test_carries_all_runtime_policy_fields(self) -> None:
        snapshot = CachePolicySnapshot(
            mode="read_only",
            warn_after_days=15,
            block_after_days=60,
            storage_profile="full_judge_io",
        )
        assert snapshot.mode == "read_only"
        assert snapshot.warn_after_days == 15
        assert snapshot.block_after_days == 60
        assert snapshot.storage_profile == "full_judge_io"

    def test_value_equality(self) -> None:
        a = _policy()
        b = _policy()
        assert a == b


class TestCardinalSixTypedBoundaries:
    """Cardinal #6 pins: no `dict[str, Any]` crosses the boundary."""

    def test_policy_violations_field_type_is_tuple(self) -> None:
        # Ensures the field annotation says tuple (immutable), not
        # list. A future refactor that flipped this would surface
        # as a type-checker complaint at callers passing tuples.
        import typing

        hints = typing.get_type_hints(CacheSummary)
        assert "policy_violations" in hints
        # tuple[PolicyViolationRecord, ...] — origin is tuple.
        origin = typing.get_origin(hints["policy_violations"])
        assert origin is tuple

    def test_models_distribution_field_type_is_mapping(self) -> None:
        import collections.abc
        import typing

        hints = typing.get_type_hints(CacheSummary)
        origin = typing.get_origin(hints["models_distribution"])
        # collections.abc.Mapping (NOT dict) — Mapping is read-only
        # at the type level.
        assert origin is collections.abc.Mapping
