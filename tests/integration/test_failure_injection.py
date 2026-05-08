"""Phase 9A.4 — failure injection covering every FAILURE_CODE_REGISTRY entry.

Cardinal #1: every expected failure surfaces as structured data
(`FailureRecord`), not as an unhandled exception. Phase 9A.4 closes
the registry-coverage half of the contract: for every code in
`FAILURE_CODE_REGISTRY`, prove a valid `FailureRecord` can be
constructed via `make_failure_record` with the spec's required
details, and that the resulting records flow cleanly through
`project_to_report_v01` into `ReportV01.failures`.

## Scope and what this test does NOT do

This test is a **construction + projection** coverage test, not a
behavioral simulation. It does NOT exercise the specific
adapter/runner/scorer paths that produce each code in production.
That coverage lives in:

- `tests/unit/whatifd/cache/test_recovery.py` for cache-corruption
  paths.
- Adapter-package tests (Phase 4B) for ingest / replay / score
  failure modes (the conformance harness defines the contract;
  per-adapter tests inject specific failures).
- `tests/integration/test_pipeline_ship.py::TestPipelineFailurePaths`
  for the live `scorer_unavailable` path that the 9A.1 pipeline
  emits.

What 9A.4 pins is the **registry contract**: every documented code
must construct cleanly with realistic details, and every
constructed record must round-trip through the report shape
without losing fields. A future contributor adding a new code to
`FAILURE_CODE_REGISTRY` MUST also add a row to
`_DETAILS_FOR_CODE` below — the exhaustiveness test
(`test_every_registered_code_is_covered`) catches the gap.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from whatifd.decision.failure_codes import (
    FAILURE_CODE_REGISTRY,
    make_failure_record,
)
from whatifd.report.projection import project_to_report_v01
from whatifd.types.failure import FailureRecord
from whatifd.types.policy import DecisionPolicy, TrustFloor
from whatifd.types.primitives import JsonPrimitive
from whatifd.types.verdict import Inconclusive

from ._fixtures import (
    _default_cache_summary,
    _default_methodology,
    _default_runtime,
)

# Realistic details payloads for every registered code. Each value
# satisfies the spec's `required_details` contract; extra keys are
# allowed (extension-point per cardinal #6) but kept minimal here.
# Adding a new code to `FAILURE_CODE_REGISTRY` MUST add a row here
# or `test_every_registered_code_is_covered` fails loudly.
# Some entries below carry the registry's MINIMUM viable details
# (e.g., a single key for `trace_schema_mismatch` and `trace_invalid`).
# `make_failure_record` enforces `required_details` ⊆ supplied keys;
# if the registry expands `required_details` for any code, the
# `test_make_failure_record_succeeds_for_every_code` parametrization
# raises `ValueError` for the affected code with a clear missing-keys
# message. That's the canonical drift surface — not the entry
# minimality. Adding more keys here pre-emptively isn't load-bearing;
# tracking the registry's contract IS.
_DETAILS_FOR_CODE: Mapping[str, Mapping[str, JsonPrimitive]] = {
    "trace_schema_mismatch": {"missing_field": "user_message"},
    "trace_invalid": {"reason": "empty user_message"},
    "tool_cache_miss": {"tool_name": "search"},
    "runner_timeout": {"timeout_seconds": 30},
    "runner_exception": {"exception_type": "RuntimeError", "message": "boom"},
    "scorer_unavailable": {"provider": "stub", "reason": "503 Service Unavailable"},
    "scorer_invalid_output": {"provider": "stub"},
    "ci_uncomputable_for_required_cohort": {
        "cohort": "baseline",
        "reason": "sample_too_small",
    },
    "cache_lock_unavailable": {"lock_path": ".whatif/cache/.lock"},
    "cache_corruption_detected": {"cache_path": ".whatif/cache/entries"},
}


def _identifier_kwargs_for_scope(spec_scope: str) -> dict[str, str]:
    """Pick scope-appropriate identifier kwargs for the factory."""
    if spec_scope == "trace":
        return {"trace_id": "t-injected"}
    if spec_scope == "cohort":
        return {"cohort": "baseline"}
    return {}  # run-scope: neither


class TestRegistryCoverage:
    def test_every_registered_code_is_covered(self) -> None:
        # Exhaustiveness pin. A future code added to the registry
        # without a corresponding _DETAILS_FOR_CODE entry fails this
        # test immediately. Keeps the failure-injection coverage
        # honest as the registry grows.
        registered = set(FAILURE_CODE_REGISTRY.keys())
        covered = set(_DETAILS_FOR_CODE.keys())
        assert registered == covered, (
            f"Registry/coverage drift. registered-only: {sorted(registered - covered)}; "
            f"covered-only: {sorted(covered - registered)}."
        )

    @pytest.mark.parametrize("code", sorted(FAILURE_CODE_REGISTRY.keys()))
    def test_make_failure_record_succeeds_for_every_code(self, code: str) -> None:
        spec = FAILURE_CODE_REGISTRY[code]
        record = make_failure_record(
            code,
            id=f"injected-{code}",
            message=f"injected {code} for failure-coverage test",
            details=_DETAILS_FOR_CODE[code],
            **_identifier_kwargs_for_scope(spec.default_scope),
        )
        assert isinstance(record, FailureRecord)
        assert record.code == code
        assert record.stage == spec.stage
        assert record.scope == spec.default_scope
        assert record.retryable == spec.retryable_default
        # Every required detail key is present in the resolved record.
        for required_key in spec.required_details:
            assert required_key in record.details

    def test_all_codes_round_trip_through_projection(self) -> None:
        # Inject one record per registered code, project an
        # Inconclusive verdict (floor failed; cohort_results empty),
        # and assert every record lands in ReportV01.failures with
        # its code and stage intact. The pipeline doesn't currently
        # emit every code — but the projection path is the contract
        # surface every adapter-emitted failure must traverse.
        records = [
            make_failure_record(
                code,
                id=f"injected-{code}",
                message=f"injected {code}",
                details=_DETAILS_FOR_CODE[code],
                **_identifier_kwargs_for_scope(spec.default_scope),
            )
            for code, spec in FAILURE_CODE_REGISTRY.items()
        ]
        floor = TrustFloor()
        policy = DecisionPolicy()
        # Inconclusive verdict with no cohort results — exercises
        # the projection path without needing to construct a
        # full pipeline run. Findings/cohort coverage lives in
        # the scenario tests; this test owns the failures pipe.
        verdict = Inconclusive(cohort_results=[], findings=[])
        report = project_to_report_v01(
            verdict,
            failures=records,
            cache_summary=_default_cache_summary(),
            methodology=_default_methodology(),
            runtime=_default_runtime(floor=floor, policy=policy),
        )
        assert len(report.failures) == len(FAILURE_CODE_REGISTRY)
        emitted_codes = {f.code for f in report.failures}
        assert emitted_codes == set(FAILURE_CODE_REGISTRY.keys())
        # Stage/scope round-trip: the projection must NOT lose these.
        for record in report.failures:
            spec = FAILURE_CODE_REGISTRY[record.code]
            assert record.stage == spec.stage
            assert record.scope == spec.default_scope
