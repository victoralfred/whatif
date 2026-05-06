"""Tests for `whatif.report.projection` — Phase 5.2 wire-format projection.

The load-bearing properties:

1. **Each Verdict variant projects to its expected `verdict_state`** —
   Ship → "ship", DontShip → "dont_ship", Inconclusive → "inconclusive".
2. **Cardinal #2 chokepoint**: the function takes `Verdict` (sealed
   union); a caller cannot synthesize `verdict_state="ship"` without
   first obtaining a `Ship` instance, which requires a
   `FloorPassedProof` from `evaluate_floor()`. The signature itself
   IS the enforcement.
3. **Findings flatten cleanly**: `decision_findings` contains the
   verdict's own `findings` list (NOT the derived `blocking_findings`
   subset; consumers compute that view from severity).
4. **Manifest fields propagate**: `trust_floor` and `decision_policy`
   are read from `runtime` (single source of truth) — drift between
   manifest content and report top-level fields is structurally
   prevented.
5. **Inputs are passed-through unmodified**: `cache_summary`,
   `methodology`, `failures`, and `runtime` appear in the output as
   the same instance the caller supplied. Projection is field-
   copying, not transformation.
"""

from __future__ import annotations

import inspect
import typing

import pytest

from whatif.decision.failure_codes import make_failure_record
from whatif.report.models_v01 import REPORT_SCHEMA_URI, REPORT_SCHEMA_VERSION
from whatif.report.projection import _flatten_verdict, project_to_report_v01
from whatif.types.failure import FailureRecord
from whatif.types.verdict import DontShip, Inconclusive, Ship

from ._fixtures import (
    cache_summary,
    dont_ship,
    dont_ship_with_observation,
    inconclusive,
    methodology,
    runtime,
    ship,
)

# ---------------------------------------------------------------------------
# Verdict-state mapping
# ---------------------------------------------------------------------------


class TestVerdictStateMapping:
    def test_ship_projects_to_ship_state(self) -> None:
        report = project_to_report_v01(
            ship(),
            failures=[],
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        assert report.verdict_state == "ship"

    def test_dont_ship_projects_to_dont_ship_state(self) -> None:
        report = project_to_report_v01(
            dont_ship(),
            failures=[],
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        assert report.verdict_state == "dont_ship"

    def test_inconclusive_projects_to_inconclusive_state(self) -> None:
        report = project_to_report_v01(
            inconclusive(),
            failures=[],
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        assert report.verdict_state == "inconclusive"


# ---------------------------------------------------------------------------
# _flatten_verdict direct coverage
# ---------------------------------------------------------------------------


class TestFlattenVerdict:
    def test_ship_produces_findings_not_blocking_subset(self) -> None:
        s = ship()
        state, cohorts, findings = _flatten_verdict(s)
        assert state == "ship"
        assert cohorts == s.cohort_results
        assert findings == s.findings

    def test_dont_ship_produces_full_findings_not_blocking_only(self) -> None:
        # Pin the wire contract: `decision_findings` contains the
        # verdict's full `findings` list, NOT the derived
        # `blocking_findings` subset. Use the
        # `dont_ship_with_observation` fixture which has TWO findings
        # (one info, one blocks_ship) so the assertion is load-bearing
        # — `findings != blocking_findings` here.
        ds = dont_ship_with_observation()
        assert ds.findings != ds.blocking_findings  # fixture invariant
        assert len(ds.findings) == 2 and len(ds.blocking_findings) == 1

        state, _cohorts, findings = _flatten_verdict(ds)
        assert state == "dont_ship"
        # The flatten contract: take `findings`, NOT `blocking_findings`.
        # If projection accidentally narrowed to blocking_findings, the
        # info-severity observation would be lost from the wire.
        assert findings == ds.findings
        assert findings != ds.blocking_findings

    def test_inconclusive_state(self) -> None:
        inc = inconclusive()
        state, _, _ = _flatten_verdict(inc)
        assert state == "inconclusive"


# ---------------------------------------------------------------------------
# Manifest single-source-of-truth pin
# ---------------------------------------------------------------------------


class TestManifestSourceOfTruth:
    """`trust_floor` and `decision_policy` are read from `runtime` (the
    `RunManifest`) so the report's top-level fields can't drift from
    what the manifest records.
    """

    def test_trust_floor_matches_runtime(self) -> None:
        rt = runtime()
        report = project_to_report_v01(
            ship(),
            failures=[],
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=rt,
        )
        assert report.trust_floor is rt.trust_floor

    def test_decision_policy_matches_runtime(self) -> None:
        rt = runtime()
        report = project_to_report_v01(
            ship(),
            failures=[],
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=rt,
        )
        assert report.decision_policy is rt.decision_policy


# ---------------------------------------------------------------------------
# Pass-through pins
# ---------------------------------------------------------------------------


class TestPassThrough:
    """Inputs flow through unmodified — projection is field-copying,
    not transformation.
    """

    def test_cache_summary_is_same_instance(self) -> None:
        cs = cache_summary()
        report = project_to_report_v01(
            ship(),
            failures=[],
            cache_summary=cs,
            methodology=methodology(),
            runtime=runtime(),
        )
        assert report.cache_summary is cs

    def test_methodology_is_same_instance(self) -> None:
        m = methodology()
        report = project_to_report_v01(
            ship(),
            failures=[],
            cache_summary=cache_summary(),
            methodology=m,
            runtime=runtime(),
        )
        assert report.methodology is m

    def test_runtime_is_same_instance(self) -> None:
        rt = runtime()
        report = project_to_report_v01(
            ship(),
            failures=[],
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=rt,
        )
        assert report.runtime is rt

    # `failures` tuple-input → list-output coverage moved to
    # TestFailuresAsData below, parametrized across all three verdict
    # branches per cardinal #1.


# ---------------------------------------------------------------------------
# Schema constants stamped
# ---------------------------------------------------------------------------


class TestSchemaConstants:
    def test_schema_version_stamped(self) -> None:
        report = project_to_report_v01(
            ship(),
            failures=[],
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        assert report.schema_version == REPORT_SCHEMA_VERSION
        assert report.schema_uri == REPORT_SCHEMA_URI


# ---------------------------------------------------------------------------
# Cardinal #2 enforcement at the type level
# ---------------------------------------------------------------------------


class TestCardinalTwoChokepoint:
    """The signature of `project_to_report_v01` IS the cardinal #2
    enforcement. There is no path to call it with `verdict_state="ship"`
    without first obtaining a `Ship` instance, which requires
    `FloorPassedProof`. Pin this with an inspection of the function's
    type annotations so a future refactor that loosened the signature
    (e.g., to `verdict_state: str`) fails this test.
    """

    def test_first_argument_is_typed_verdict(self) -> None:
        hints = typing.get_type_hints(project_to_report_v01)
        # The annotation is `Verdict` which is a Union alias; mypy
        # narrows to Ship | DontShip | Inconclusive. At runtime,
        # typing.get_type_hints resolves it to the underlying union.
        verdict_hint = hints["verdict"]
        # Verdict is `Ship | DontShip | Inconclusive`. typing.get_args
        # on a UnionType returns the variants.
        args = set(typing.get_args(verdict_hint))
        assert args == {Ship, DontShip, Inconclusive}, (
            f"project_to_report_v01's `verdict` parameter must be the sealed "
            f"`Verdict` union (Ship | DontShip | Inconclusive); got "
            f"args={args!r}. Loosening this signature (e.g., to "
            "`verdict_state: str`) would re-open the cardinal #2 bypass."
        )

    def test_no_verdict_state_string_parameter(self) -> None:
        # Defends against a refactor that added `verdict_state: str` as
        # a parallel input — that would be a cardinal #2 bypass.
        sig = inspect.signature(project_to_report_v01)
        assert "verdict_state" not in sig.parameters, (
            "project_to_report_v01 must NOT take a verdict_state string; "
            "the verdict argument (sealed Verdict union) is the only "
            "verdict-related input."
        )


# ---------------------------------------------------------------------------
# Cardinal #1: failures-as-data across all verdict branches
# ---------------------------------------------------------------------------


class TestFailuresAsData:
    """The `failures` parameter is `Sequence[FailureRecord]`; the
    output field is `list[FailureRecord]`. Tuple input → list output
    is a defensive copy, not aliasing. The conversion contract is
    independent of verdict variant — pin it across all three.
    """

    @pytest.fixture
    def failure(self) -> FailureRecord:
        return make_failure_record(
            "cache_lock_unavailable",
            id="fail-1",
            message="lock held",
            scope="run",
            details={
                "hostname": "ci-runner-7",
                "lock_pid": 12345,
                "lock_path": ".whatif/cache/.lock",
            },
        )

    def test_ship_with_failures(self, failure: FailureRecord) -> None:
        report = project_to_report_v01(
            ship(),
            failures=(failure,),
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        assert isinstance(report.failures, list)
        assert report.failures == [failure]

    def test_dont_ship_with_failures(self, failure: FailureRecord) -> None:
        report = project_to_report_v01(
            dont_ship(),
            failures=(failure,),
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        assert isinstance(report.failures, list)
        assert report.failures == [failure]

    def test_inconclusive_with_failures(self, failure: FailureRecord) -> None:
        report = project_to_report_v01(
            inconclusive(),
            failures=(failure,),
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        assert isinstance(report.failures, list)
        assert report.failures == [failure]
