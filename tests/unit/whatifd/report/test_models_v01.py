"""Tests for `whatifd.report.models_v01` — Phase 5.1 ReportV01 wire-format.

Pins the typed shape of the v0.1 wire format. Schema-validation
enforcement (schema match, byte-stable JSON, walkthrough fidelity)
lands in later sub-phases of Phase 5; this PR covers the type
contract.

Coverage:
- All 11 required fields construct end-to-end with realistic fixtures.
- Frozen-dataclass immutability.
- Schema constants are exactly `"0.1"` and the canonical URI.
- `VerdictState` literal accepts the three documented values and
  rejects others at the type level (mypy strict catches; runtime
  doesn't validate by design — that's the schema's job).
- The `runtime` field is the only non-deterministic field (per
  `references/type-model.md` "x-deterministic: false") — pinned
  here so the determinism budget extractor (later sub-phase) has a
  fixed shape to read against.
"""

from __future__ import annotations

import dataclasses
import typing

import pytest

from whatifd.cache.summary import CachePolicySnapshot, CacheSummary
from whatifd.report.models_v01 import (
    REPORT_SCHEMA_URI,
    REPORT_SCHEMA_VERSION,
    ReportV01,
    VerdictState,
)
from whatifd.types.cohort import CohortResult
from whatifd.types.failure import FailureRecord
from whatifd.types.finding import DecisionFinding
from whatifd.types.manifest import EnvironmentFingerprint, RunManifest
from whatifd.types.policy import (
    DecisionPolicy,
    PrimaryEndpoint,
    TrustFloor,
)
from whatifd.types.primitives import DecimalString
from whatifd.types.statistical import (
    BootstrapMethodDisclosure,
    EffectSizeDisclosure,
    JudgeMethodDisclosure,
    MethodologyDisclosure,
    MultiplicityDisclosure,
)

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _trust_floor() -> TrustFloor:
    return TrustFloor()


def _decision_policy() -> DecisionPolicy:
    return DecisionPolicy(
        primary_endpoints=(
            PrimaryEndpoint(
                cohort="failure",
                direction="improvement_above_threshold",
            ),
        ),
    )


def _cohort(name: str) -> CohortResult:
    return CohortResult(
        name=name,
        selected=10,
        replayed=10,
        scored=10,
        ci_computable=True,
        ci_unavailable_reason=None,
        median_delta=DecimalString("0.250"),
        ci_lower=DecimalString("0.150"),
        ci_upper=DecimalString("0.350"),
        floor_passed=True,
    )


def _cache_summary() -> CacheSummary:
    return CacheSummary(
        schema_version="v1",
        key_version="v1",
        mode="on",
        storage_profile="normalized_result_only",
        storage_path=".whatifd/cache",
        hits=8,
        misses=2,
        writes=2,
        stale_hits=0,
        corrupted_entries=0,
        policy=CachePolicySnapshot(
            mode="on",
            warn_after_days=30,
            block_after_days=90,
            storage_profile="normalized_result_only",
        ),
    )


def _methodology() -> MethodologyDisclosure:
    return MethodologyDisclosure(
        unit_of_analysis="paired_trace_delta",
        primary_metric="faithfulness",
        primary_endpoints=("failure_improvement_above_0.50",),
        cohorts=("failure", "baseline"),
        bootstrap=BootstrapMethodDisclosure(
            method="paired_percentile_bootstrap",
            resamples=10000,
            seed=42,
            sample_unit="paired_trace_delta",
            ci_level=DecimalString("0.95"),
            cluster_key=None,
            assumptions=("trace_independence",),
        ),
        multiplicity=MultiplicityDisclosure(
            primary_endpoint_count=1,
            correction="none",
            reason="single primary metric per cohort; no correction applied",
        ),
        judge=JudgeMethodDisclosure(
            scorer="inspect_ai.Faithfulness",
            scorer_version="0.3.5",
            judge_provider="anthropic",
            judge_model="claude-sonnet-4-6",
            judge_model_version="20251001",
            rendered_prompt_hash="aa" * 32,
            rubric_hash="bb" * 32,
            scorer_cache_enabled=True,
            scorer_cache_mode="on",
            scorer_cache_hits=8,
            scorer_cache_misses=2,
            reproducibility_addressed=True,
            reliability_measured=False,
            validity_measured=False,
            calibration_measured=False,
            bias_audit_measured=False,
        ),
        effect_size=EffectSizeDisclosure(
            practical_delta=DecimalString("0.050"),
            practical_delta_source="policy",
            judge_noise_floor=None,
        ),
        per_trace_inference="descriptive_only",
        causal_claim_scope="associated_under_cached_tool_replay",
    )


def _runtime() -> RunManifest:
    return RunManifest(
        experiment_id="exp-001",
        started_at="2026-05-06T10:00:00Z",
        finished_at="2026-05-06T10:01:00Z",
        duration_ms=60000,
        whatif_version="0.0.1",
        config_hash="cc" * 32,
        selection_seed=42,
        source="langfuse://test",
        target="my_agent.replay:run",
        trust_floor=_trust_floor(),
        decision_policy=_decision_policy(),
        environment=EnvironmentFingerprint(
            python="3.13.0",
            platform="linux-x86_64",
            whatif_version="0.0.1",
        ),
    )


def _report(
    *,
    verdict_state: VerdictState = "ship",
    cohort_results: list[CohortResult] | None = None,
    failures: list[FailureRecord] | None = None,
    decision_findings: list[DecisionFinding] | None = None,
) -> ReportV01:
    """Build a fully-typed `ReportV01` fixture.

    Explicit keyword args (rather than the previous **dict[str, object]
    pattern) so mypy strict catches wrong-type fixture errors at
    test-write time. The four overridable fields cover what existing
    tests vary; if a future test needs to override more, add a kwarg
    — don't drop the typing.
    """
    return ReportV01(
        schema_version=REPORT_SCHEMA_VERSION,
        schema_uri=REPORT_SCHEMA_URI,
        verdict_state=verdict_state,
        cohort_results=cohort_results
        if cohort_results is not None
        else [_cohort("failure"), _cohort("baseline")],
        failures=failures if failures is not None else [],
        decision_findings=decision_findings if decision_findings is not None else [],
        cache_summary=_cache_summary(),
        trust_floor=_trust_floor(),
        decision_policy=_decision_policy(),
        methodology=_methodology(),
        runtime=_runtime(),
    )


# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------


class TestSchemaConstants:
    def test_version_is_pinned(self) -> None:
        # Pinning the literal value: a rename would break wire
        # compatibility for every downstream consumer.
        assert REPORT_SCHEMA_VERSION == "0.1"

    def test_uri_is_canonical(self) -> None:
        assert REPORT_SCHEMA_URI == "https://whatif.codes/schema/report/v0.1.json"

    def test_uri_contains_version(self) -> None:
        # Defends against the URI and version drifting apart.
        assert f"v{REPORT_SCHEMA_VERSION}" in REPORT_SCHEMA_URI


# ---------------------------------------------------------------------------
# ReportV01 construction
# ---------------------------------------------------------------------------


class TestReportV01Construction:
    def test_constructs_with_all_required_fields(self) -> None:
        report = _report()
        assert report.schema_version == REPORT_SCHEMA_VERSION
        assert report.schema_uri == REPORT_SCHEMA_URI
        assert report.verdict_state == "ship"
        assert len(report.cohort_results) == 2
        assert report.failures == []
        assert report.decision_findings == []

    @pytest.mark.parametrize("state", ["ship", "dont_ship", "inconclusive"])
    def test_each_verdict_state_accepted(self, state: VerdictState) -> None:
        report = _report(verdict_state=state)
        assert report.verdict_state == state

    def test_failures_can_be_populated(self) -> None:
        from whatifd.decision.failure_codes import make_failure_record

        report = _report(
            failures=[
                make_failure_record(
                    "ci_uncomputable_for_required_cohort",
                    id="fail-1",
                    message="sample too small",
                    cohort="failure",
                    details={"cohort": "failure", "reason": "sample_too_small"},
                ),
            ],
        )
        assert len(report.failures) == 1


# ---------------------------------------------------------------------------
# Frozen / typed-boundary pins
# ---------------------------------------------------------------------------


class TestReportV01Frozen:
    def test_report_is_frozen(self) -> None:
        report = _report()
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.verdict_state = "dont_ship"  # type: ignore[misc]

    def test_no_dict_str_any_fields(self) -> None:
        # Cardinal #6: every field on ReportV01 — AND on every
        # dataclass it composes — must be typed. No `dict[..., Any]`
        # at any depth. The walker:
        #   - recurses through generic-alias args (list[X],
        #     tuple[X, ...], Union[...], etc.);
        #   - descends into dataclass sub-shapes by reading THEIR
        #     `typing.get_type_hints`, so a future
        #     `CohortResult.metadata: dict[str, Any]` slips would be
        #     caught here. `_seen` tracks visited dataclasses to break
        #     reference cycles cheaply.
        #
        # Forward-reference note: typing.get_type_hints resolves PEP
        # 563 string annotations at call time. If a future sub-shape
        # introduces unresolvable forward refs (e.g., a TYPE_CHECKING-
        # only import used in an annotation that survives to runtime),
        # this test will fail loudly with NameError. The right fix is
        # to add the missing TYPE_CHECKING guard or move the import
        # to runtime — NOT to silently disable this test, which is the
        # cardinal #6 boundary defense for the wire format.
        seen: set[type] = set()
        hints = typing.get_type_hints(ReportV01)
        for name, hint in hints.items():
            self._assert_no_any_dict(f"ReportV01.{name}", hint, seen)

    def _assert_no_any_dict(self, location: str, hint: object, seen: set[type]) -> None:
        origin = typing.get_origin(hint)
        args = typing.get_args(hint)
        if origin is dict and len(args) == 2 and args[1] is typing.Any:
            raise AssertionError(
                f"{location} contains dict[..., Any] in its type "
                "annotation — cardinal #6 forbids untyped boundaries "
                "on the public schema, at any depth."
            )
        # Recurse through every generic-alias argument first (lists,
        # tuples, unions, etc. all surface their inner types here).
        for arg in args:
            self._assert_no_any_dict(location, arg, seen)
        # Then descend into dataclass sub-shapes. The frozen, slot
        # dataclasses we use throughout don't carry forward refs that
        # would break here, but `seen` cycle-protects regardless.
        target = origin if origin is not None else hint
        if isinstance(target, type) and dataclasses.is_dataclass(target):
            if target in seen:
                return
            seen.add(target)
            sub_hints = typing.get_type_hints(target)
            for sub_name, sub_hint in sub_hints.items():
                self._assert_no_any_dict(
                    f"{location}::{target.__name__}.{sub_name}",
                    sub_hint,
                    seen,
                )


# ---------------------------------------------------------------------------
# Determinism subset pins (cardinal #4)
# ---------------------------------------------------------------------------


class TestDeterminismFieldList:
    """The schema-generation step (later Phase 5 sub-phase) annotates
    each ReportV01 field with `x-deterministic: true | false`. Per
    `references/type-model.md`, only `runtime` is non-deterministic.
    Pin the field list here so the schema-gen test has a stable
    expectation; if a contributor adds a non-deterministic field
    without annotating it, a future test that diffs the deterministic
    subset across runs will fail.
    """

    def test_runtime_is_a_field(self) -> None:
        # runtime carries timestamps + duration_ms — non-deterministic
        # by definition. Schema gen marks it x-deterministic: false.
        fields = {f.name for f in dataclasses.fields(ReportV01)}
        assert "runtime" in fields

    def test_all_non_runtime_fields_present(self) -> None:
        # Pinning the field SET so a future addition surfaces here as
        # "test failure: please update the determinism budget."
        expected = {
            "schema_version",
            "schema_uri",
            "verdict_state",
            "cohort_results",
            "failures",
            "decision_findings",
            "cache_summary",
            "trust_floor",
            "decision_policy",
            "methodology",
            "runtime",
        }
        actual = {f.name for f in dataclasses.fields(ReportV01)}
        assert actual == expected, (
            f"ReportV01 field set drift detected: "
            f"added={actual - expected}, removed={expected - actual}. "
            "Update this test AND the determinism-budget annotation in "
            "schema generation."
        )


# ---------------------------------------------------------------------------
# Sub-shape integration smoke
# ---------------------------------------------------------------------------


class TestSubshapesAcceptInternalTypes:
    """Pin the cardinal-#6 boundary contract: ReportV01's sub-fields
    accept the existing internal types directly. A future refactor
    that introduced a parallel "wire-format" copy of (e.g.)
    CohortResult would surface here when this test fails to import.
    """

    def test_cohort_results_accepts_internal_cohort_result(self) -> None:
        report = _report(cohort_results=[_cohort("failure")])
        assert isinstance(report.cohort_results[0], CohortResult)

    def test_cache_summary_accepts_internal_cache_summary(self) -> None:
        report = _report()
        assert isinstance(report.cache_summary, CacheSummary)

    def test_methodology_accepts_internal_methodology(self) -> None:
        report = _report()
        assert isinstance(report.methodology, MethodologyDisclosure)

    def test_runtime_accepts_run_manifest(self) -> None:
        report = _report()
        assert isinstance(report.runtime, RunManifest)


# ---------------------------------------------------------------------------
# Mapping-import pin (defensive)
# ---------------------------------------------------------------------------


class TestSchemaConstantEnforcement:
    """The `_SchemaVersion` and `_SchemaUri` Literal types are the
    enforcement layer for schema-stamp correctness — a stale
    `schema_version="0.5"` cannot be supplied without a `cast(...)`
    or `# type: ignore`.

    Python doesn't enforce Literal at runtime (the constructor accepts
    any string), so the runtime test below documents the actual
    semantics: the type system is the enforcement layer; bypassing it
    requires explicit, reviewable opt-out. Operators reading this
    test learn that the guarantee is type-level, not runtime, and
    that bypassing requires a `cast` they can't sneak past code
    review.
    """

    def test_runtime_accepts_anything_with_explicit_cast(self) -> None:
        # `cast` documents the bypass — a code reviewer sees "you are
        # asserting this is correct against the type system" and can
        # push back. mypy strict catches the bypass at type-check
        # time; this runtime test confirms there is no second
        # enforcement layer for the curious reader.
        from typing import cast

        from whatifd.report.models_v01 import _SchemaUri, _SchemaVersion

        # The cast lies to the type-checker — at runtime, Python
        # accepts the string regardless. mypy's enforcement is what
        # prevents this from happening accidentally in real code.
        bad_version = cast(_SchemaVersion, "0.99")
        bad_uri = cast(_SchemaUri, "https://malicious.example/schema.json")
        # Must construct without raising: the type system is the gate;
        # __post_init__ does not duplicate the check.
        report = _report()
        # Replace via dataclasses.replace which preserves the typed shape.
        mutated = dataclasses.replace(
            report,
            schema_version=bad_version,
            schema_uri=bad_uri,
        )
        assert mutated.schema_version == "0.99"
        # Pin the design choice: enforcement is at type-check time, not
        # construction time. A future contributor wanting runtime
        # validation must add __post_init__ guards AND update this test.

    def test_normal_construction_uses_module_constants(self) -> None:
        # The fixture path picks up the constants; if a future refactor
        # diverged the test fixtures from REPORT_SCHEMA_VERSION, this
        # would surface as a constants/fixture mismatch.
        report = _report()
        assert report.schema_version == REPORT_SCHEMA_VERSION
        assert report.schema_uri == REPORT_SCHEMA_URI


class TestImportShape:
    """Defends the public-import surface from accidental change."""

    def test_module_exports(self) -> None:
        from whatifd import report as pkg

        assert pkg.REPORT_SCHEMA_VERSION == "0.1"
        assert pkg.REPORT_SCHEMA_URI == REPORT_SCHEMA_URI
        assert pkg.ReportV01 is ReportV01
        # `VerdictState` is a typing alias (`Literal[...]`), not a
        # runtime object. `is not None` would be vacuously true even
        # for `Optional[X]`. `hasattr` is the right check: it asserts
        # the symbol is reachable through the package, which is what
        # downstream tooling actually depends on.
        assert hasattr(pkg, "VerdictState")
