"""Phase 9A.3 integration test — determinism byte-equality.

Cardinal #4: determinism is opt-in per field. The deterministic
subset of a `ReportV01` (every top-level field tagged
`x-deterministic: true` in the schema — currently everything
except `runtime`) MUST be byte-equal across re-runs of the same
fixture. This test runs all four of the Phase 9A scenarios twice
each, extracts the deterministic subset from both runs, and pins
byte-equality.

If a future change introduces non-determinism into a tagged field
(e.g., a guard that emits findings in iteration order without
sorting), this test fails first. The fix is either to make the
field deterministic OR to flip its `x-deterministic` annotation —
NEVER to relax this test's byte-equality assertion.

## Schema-coverage cross-check

`test_schema_deterministic_field_set_matches_extractor` asserts
the extractor's view of the deterministic field set matches the
top-level schema annotations. A future schema change that adds a
deterministic field MUST surface here; otherwise the
byte-equality assertion above silently stops covering the new
field.
"""

from __future__ import annotations

import json

import pytest

from whatif.pipeline import run_pipeline
from whatif.serialization.canonical import canonical_json_bytes
from whatif.serialization.determinism import (
    DeterministicSubsetWarning,
    deterministic_field_names,
    extract_deterministic_subset,
)
from whatif.serialization.encoder import encode_report_v01
from whatif.types.policy import DecisionPolicy, TrustFloor

from ._fixtures import (
    IntegrationFixture,
    scenario_clean_ship,
    scenario_dont_ship_failure_rescue_gap,
    scenario_dont_ship_regression,
    scenario_inconclusive_insufficient_sample,
)


def _run_and_extract_subset(fx: IntegrationFixture) -> dict[str, object]:
    report = run_pipeline(
        fx.trace_source,
        delta_fn=fx.delta_fn,
        floor=TrustFloor(),
        policy=DecisionPolicy(),
        runtime=fx.runtime,
        methodology=fx.methodology,
        cache_summary=fx.cache_summary,
    )
    serialized = json.loads(encode_report_v01(report))
    return extract_deterministic_subset(serialized)


@pytest.mark.parametrize(
    "scenario_factory",
    [
        scenario_clean_ship,
        scenario_dont_ship_regression,
        scenario_dont_ship_failure_rescue_gap,
        scenario_inconclusive_insufficient_sample,
    ],
    ids=[
        "clean_ship",
        "dont_ship_regression",
        "dont_ship_failure_rescue_gap",
        "inconclusive_insufficient_sample",
    ],
)
def test_deterministic_subset_byte_equal_across_runs(scenario_factory) -> None:
    # Each call constructs a FRESH fixture, runs the pipeline, and
    # extracts the deterministic subset. The subsets MUST be byte-
    # identical across the two runs. Re-using the same fixture
    # instance would mask non-determinism in fixture construction;
    # constructing fresh exercises the full path.
    subset_a = _run_and_extract_subset(scenario_factory())
    subset_b = _run_and_extract_subset(scenario_factory())

    # Route re-encoding through `canonical_json_bytes` rather than
    # raw `json.dumps` so the banned-import lint stays clean (the
    # serialization package is the single source of canonical JSON
    # encoding per cardinal #5's three-layer defense).
    assert canonical_json_bytes(subset_a) == canonical_json_bytes(subset_b)


def test_runtime_field_excluded_from_subset() -> None:
    # The `runtime` field is tagged x-deterministic: false because
    # it carries timestamps, environment fingerprint, and the
    # sensitive-unwrap audit log — all non-deterministic. Pin the
    # exclusion so a future "everything is deterministic" refactor
    # doesn't silently sweep `runtime` into the byte-equality check.
    subset = _run_and_extract_subset(scenario_clean_ship())
    assert "runtime" not in subset


def test_unknown_key_emits_drift_warning() -> None:
    # Pin schema-drift surfacing: an extra top-level key not in the
    # bundled schema's properties triggers DeterministicSubsetWarning
    # and is dropped from the subset. A future producer running a
    # newer ReportV01 shape than the consumer's schema would
    # otherwise lose the drift signal silently.
    drifted = {
        "schema_version": "0.1",
        "schema_uri": "https://whatif.codes/schema/report/v0.1.json",
        "verdict_state": "ship",
        "future_field": "produced by a newer schema",
    }
    with pytest.warns(DeterministicSubsetWarning, match="future_field"):
        subset = extract_deterministic_subset(drifted)
    assert "future_field" not in subset


def test_deterministic_field_set_matches_schema() -> None:
    # Schema-coverage cross-check: the extractor's set MUST match
    # the schema's top-level x-deterministic:true annotations. A
    # future schema change that adds a deterministic field surfaces
    # here so the byte-equality test above is updated to cover it
    # rather than silently dropping coverage.
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
    }
    actual = deterministic_field_names()
    added = actual - expected
    removed = expected - actual
    # Explicit drift message so a schema change surfaces actionable
    # information instead of a raw set-equality failure.
    assert actual == expected, (
        f"Deterministic-field-set drift detected.\n"
        f"  added (in schema, missing here): {sorted(added)!r}\n"
        f"  removed (here, missing in schema): {sorted(removed)!r}\n"
        f"\n"
        f"To fix:\n"
        f"  1. Update the `expected` literal in this test to match "
        f"the schema's current x-deterministic:true set.\n"
        f"  2. If a NEW field was added: extend "
        f"`test_deterministic_subset_byte_equal_across_runs` with at "
        f"least one fixture that exercises non-trivial values for "
        f"the field, so byte-equality actually covers it.\n"
        f"  3. If a field was REMOVED: confirm the removal is "
        f"intentional (a cardinal #4 retraction) and update the "
        f"cascade-catalog 'Deterministic-subset extractor' entry."
    )
