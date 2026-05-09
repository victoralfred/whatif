"""Tests for `whatifd.report.projection` — Phase 5.2 wire-format projection.

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

from whatifd.decision.failure_codes import make_failure_record
from whatifd.decision.floor import FloorFailureSet, evaluate_floor
from whatifd.decision.verdict import compute_verdict
from whatifd.report.models_v01 import REPORT_SCHEMA_URI, REPORT_SCHEMA_VERSION
from whatifd.report.projection import _flatten_verdict, project_to_report_v01
from whatifd.types.cohort import CohortResult, FloorFailure
from whatifd.types.failure import FailureRecord
from whatifd.types.verdict import DontShip, Inconclusive, Ship

from ._fixtures import (
    cache_summary,
    decision_policy,
    dont_ship,
    dont_ship_with_observation,
    inconclusive,
    methodology,
    runtime,
    ship,
    trust_floor,
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
        #
        # Python-version note: `Ship | DontShip | Inconclusive` (PEP
        # 604, 3.10+) produces `types.UnionType` — distinct from the
        # legacy `typing.Union[...]` (`typing._SpecialGenericAlias`).
        # `typing.get_args` handles BOTH forms uniformly (returns the
        # variants tuple in both cases). If a future refactor ever
        # converted `Verdict` to a bare `TypeAlias = X | Y`, get_args
        # would still see through the alias because PEP 695 type
        # aliases preserve the union shape. The assertion below works
        # against any of those representations on Python 3.11+ (the
        # project's minimum).
        verdict_hint = hints["verdict"]
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
                "lock_path": ".whatifd/cache/.lock",
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

    def test_failures_is_fresh_list_not_aliased(self, failure: FailureRecord) -> None:
        # Pin the defensive-copy contract explicitly: when the caller
        # passes a list (not a tuple), the output's `failures` field
        # must be a NEW list, not the same object. Otherwise a caller
        # mutating their original list (e.g., appending more failures
        # after projection) would silently mutate the report's state
        # — broken cardinal #1 boundary.
        input_failures: list[FailureRecord] = [failure]
        report = project_to_report_v01(
            ship(),
            failures=input_failures,
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        assert report.failures is not input_failures, (
            "project_to_report_v01 must defensively copy `failures` — "
            "aliasing would let post-projection mutations of the input "
            "list silently mutate the report's failures list."
        )
        # Mutating the original must not affect the report.
        input_failures.clear()
        assert len(report.failures) == 1


# ---------------------------------------------------------------------------
# End-to-end cardinal #2 chain (defense-in-depth)
# ---------------------------------------------------------------------------


class TestFloorFailureNeverProjectsToShip:
    """Walk the cardinal #2 chain from bad cohorts → no Ship → no
    `verdict_state="ship"` on the wire. Each link is pinned in its
    own layer's tests (test_floor.py for #1, test_verdict.py for
    #2's witness-token requirement, TestCardinalTwoChokepoint above
    for #3's signature contract). This class is an integration view
    that demonstrates the chain end-to-end so a reader of
    test_projection.py sees the whole property in one place.
    """

    def test_failing_cohort_yields_floor_failure_set_not_proof(self) -> None:
        # Link #1: bad cohorts → evaluate_floor returns
        # FloorFailureSet, NOT FloorPassedProof. Pinned upstream in
        # test_floor.py; re-asserted here so the integration story
        # is self-contained.
        bad_cohort = CohortResult(
            name="failure",
            selected=2,  # below the floor's min_selected = 5
            replayed=2,
            scored=2,
            ci_computable=True,
            ci_unavailable_reason=None,
            median_delta=None,
            ci_lower=None,
            ci_upper=None,
            floor_passed=False,
        )
        result = evaluate_floor(
            [bad_cohort],
            trust_floor(),
            required_cohorts=("failure",),
        )
        assert isinstance(result, FloorFailureSet), (
            f"link #1 broken: bad cohort produced {type(result).__name__}, expected FloorFailureSet"
        )

    def test_failing_floor_runs_through_inconclusive_not_ship(self) -> None:
        # Links #2 + #3 via the REAL pipeline (no fixture shortcut):
        # build a failing cohort, run compute_verdict (which calls
        # evaluate_floor internally and constructs Inconclusive when
        # the floor returns FloorFailureSet), then project. The wire
        # state must be "inconclusive", never "ship". Each link runs
        # against actual production code:
        #
        #   evaluate_floor(bad cohort) → FloorFailureSet (link #1)
        #   compute_verdict(...) → Inconclusive (link #2; cannot be
        #                                       Ship without proof)
        #   project_to_report_v01(...) → verdict_state="inconclusive"
        #                                (link #3)
        bad_cohort = CohortResult(
            name="failure",
            selected=2,  # below floor's min_selected=5
            replayed=2,
            scored=2,
            ci_computable=True,
            ci_unavailable_reason=None,
            median_delta=None,
            ci_lower=None,
            ci_upper=None,
            floor_passed=False,
        )
        verdict = compute_verdict(
            [bad_cohort],
            trust_floor(),
            decision_policy(),
        )
        # compute_verdict for a failing floor MUST produce Inconclusive
        # (the only Verdict variant available without FloorPassedProof).
        assert isinstance(verdict, Inconclusive), (
            f"link #2 broken: bad cohort produced {type(verdict).__name__}, "
            "expected Inconclusive (Ship is structurally unavailable when "
            "evaluate_floor returns FloorFailureSet)"
        )
        # Project the Inconclusive — link #3 must flatten to
        # verdict_state="inconclusive".
        report = project_to_report_v01(
            verdict,
            failures=[],
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        assert report.verdict_state == "inconclusive"
        assert report.verdict_state != "ship"


# ---------------------------------------------------------------------------
# Floor-failures projection pin (cardinal #1, intentional drop)
# ---------------------------------------------------------------------------


class TestFloorFailuresProjection:
    """Pin the v0.1 wire-format design choice for `Inconclusive.floor_failures`.

    `Inconclusive` carries a run-level `floor_failures` list that
    aggregates structural failures across cohorts. v0.1 `ReportV01`
    has no top-level `floor_failures` field — per-cohort failures
    flow through `cohort_results[].floor_failures`, but the
    run-level aggregate is dropped. These tests pin both halves
    (preserved + dropped) so the design choice is intentional, not
    accidental. Cascade-tracked under "Run-level FloorFailure
    projection" for v0.2 schema decision.
    """

    def test_per_cohort_floor_failures_preserved_via_cohort_results(self) -> None:
        # The cohort's own floor_failures travel via the wire's
        # cohort_results[].floor_failures field.
        bad_cohort = CohortResult(
            name="failure",
            selected=2,
            replayed=2,
            scored=2,
            ci_computable=True,
            ci_unavailable_reason=None,
            median_delta=None,
            ci_lower=None,
            ci_upper=None,
            floor_passed=False,
            floor_failures=[
                FloorFailure(
                    rule="min_selected_per_required_cohort",
                    observed=2,
                    threshold=5,
                    severity="blocks_all",
                ),
            ],
        )
        verdict = Inconclusive(
            cohort_results=[bad_cohort],
            findings=[],
            blocking_findings=[],
            floor_failures=[],
        )
        report = project_to_report_v01(
            verdict,
            failures=[],
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        # Cohort's floor_failures preserved.
        assert len(report.cohort_results[0].floor_failures) == 1
        assert report.cohort_results[0].floor_failures[0].rule == (
            "min_selected_per_required_cohort"
        )

    def test_run_level_floor_failures_dropped_v01(self) -> None:
        # Inconclusive.floor_failures is the run-level aggregate.
        # v0.1 ReportV01 has no top-level floor_failures field; the
        # aggregate is dropped on the wire. This is intentional
        # (cascade-tracked) — pin the behavior so a future change
        # adding the field surfaces here as a deliberate update.
        verdict = Inconclusive(
            cohort_results=[],  # no cohorts at all (extreme case)
            findings=[],
            blocking_findings=[],
            floor_failures=[
                FloorFailure(
                    rule="required_cohort_present",
                    observed="missing",
                    threshold=1,
                    severity="blocks_all",
                ),
            ],
        )
        report = project_to_report_v01(
            verdict,
            failures=[],
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        # Verdict still flattens to "inconclusive".
        assert report.verdict_state == "inconclusive"
        # ReportV01 has no `floor_failures` attribute — the run-level
        # aggregate is dropped on the wire by design.
        assert not hasattr(report, "floor_failures")
