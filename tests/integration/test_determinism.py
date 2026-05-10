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
from importlib.resources import files
from unittest import mock

import pytest

from whatifd.pipeline import run_pipeline
from whatifd.serialization.canonical import canonical_json_bytes
from whatifd.serialization.determinism import (
    DeterministicSubsetWarning,
    deterministic_field_names,
    extract_deterministic_subset,
    extract_deterministic_subset_from_report,
)
from whatifd.serialization.encoder import encode_report_v01
from whatifd.types.policy import DecisionPolicy, TrustFloor

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
    # `encode_report_v01` returns `bytes` (utf-8 ASCII per the
    # canonical encoder contract); `json.loads` accepts both bytes
    # and str natively, so a future refactor that flips the return
    # type to str would still work here. The comment is the
    # resilient signal for a reader who doesn't want to chase the
    # encoder's contract from this seam.
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
    #
    # **Scope limit:** both invocations run sequentially in the
    # SAME process. Process-local caches (the `lru_cache` on the
    # schema loader, any future `lru_cache` on a pipeline helper,
    # Python's interned strings) survive between calls. Real
    # cross-process determinism (two separate `whatifd fork`
    # invocations on different machines producing byte-equal
    # subsets) is the Phase 9B / Phase 10 CI-gate concern — that
    # workflow runs in a fresh subprocess and exercises the
    # cross-process path. A regression that's same-process-stable
    # but cross-process-unstable would NOT be caught here; the CI
    # gate (cascade-tracked under "Deterministic-subset extractor")
    # closes that hole.
    subset_a = _run_and_extract_subset(scenario_factory())
    subset_b = _run_and_extract_subset(scenario_factory())

    # Route re-encoding through `canonical_json_bytes` rather than
    # raw `json.dumps` so the banned-import lint stays clean (the
    # serialization package is the single source of canonical JSON
    # encoding per cardinal #5's three-layer defense).
    assert canonical_json_bytes(subset_a) == canonical_json_bytes(subset_b)


def test_extract_from_report_matches_round_trip() -> None:
    # The typed `extract_deterministic_subset_from_report` helper
    # MUST produce the same dict as the round-trip path
    # (encode → json.loads → extract_deterministic_subset). Pin it
    # so a future divergence between the two surfaces (e.g., the
    # typed helper drifts from the encoder's canonical kwargs) fails
    # loudly. CI diff gates downstream rely on this equivalence.
    fx = scenario_clean_ship()
    report = run_pipeline(
        fx.trace_source,
        delta_fn=fx.delta_fn,
        floor=TrustFloor(),
        policy=DecisionPolicy(),
        runtime=fx.runtime,
        methodology=fx.methodology,
        cache_summary=fx.cache_summary,
    )
    via_helper = extract_deterministic_subset_from_report(report)
    via_round_trip = extract_deterministic_subset(json.loads(encode_report_v01(report)))
    assert via_helper == via_round_trip


def test_runtime_deterministic_subfields_warns_on_missing_annotations() -> None:
    """Phase J: the schema-walking helper that backs the extractor's
    runtime descent emits `DeterministicSubsetWarning` when the
    schema lacks per-field annotations (e.g., consumer running an
    older bundled schema). Cardinal #1: the silent-degrade path is
    observable via warning, not invisible.
    """
    from whatifd.serialization.determinism import (
        DeterministicSubsetWarning,
        _runtime_deterministic_subfields,
    )

    # Patch the schema-properties cache to return a runtime entry
    # without a `$ref`, simulating a pre-Phase-J or hand-rolled
    # schema.
    with (
        mock.patch(
            "whatifd.serialization.determinism._schema_properties",
            return_value={"runtime": {"x-deterministic": False}},  # no $ref
        ),
        pytest.warns(DeterministicSubsetWarning, match="no \\$ref"),
    ):
        result = _runtime_deterministic_subfields()
    assert result == frozenset()


def test_runtime_deterministic_subfields_warns_on_empty_annotations() -> None:
    """Companion to the above: the `$def` exists but has no fields
    tagged `x-deterministic: true`. Same warning class, different
    message; same fallback (empty frozenset).
    """
    from whatifd.serialization.determinism import (
        DeterministicSubsetWarning,
        _runtime_deterministic_subfields,
    )

    # _schema_properties returns the runtime $ref pointer; the
    # subsequent json.load of the schema file picks up an empty
    # $def (none of its properties tagged true). Patch the file
    # read to control what comes back.
    fake_doc = {
        "properties": {"runtime": {"$ref": "#/$defs/RunManifest"}},
        "$defs": {"RunManifest": {"properties": {"x": {"x-deterministic": False}}}},
    }
    with (
        mock.patch(
            "whatifd.serialization.determinism._schema_document",
            return_value=fake_doc,
        ),
        mock.patch(
            "whatifd.serialization.determinism._schema_properties",
            return_value=fake_doc["properties"],
        ),
        pytest.warns(DeterministicSubsetWarning, match="no properties tagged"),
    ):
        result = _runtime_deterministic_subfields()
    assert result == frozenset()


def test_runtime_subfield_annotations_match_dataclass_optin() -> None:
    """Phase J — Determinism widening: the schema's per-field
    annotations on `RunManifest`'s `$def` MUST match the dataclass's
    `_DETERMINISTIC_FIELDS` opt-in. Catches a future refactor that
    moves the dataclass attribute without regenerating the schema
    (or vice versa) before the cross-platform CI job notices.
    """
    from whatifd.types.manifest import RunManifest

    schema_resource = files("whatifd.report.schema").joinpath("v0.2.schema.json")
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    runtime_def = schema["$defs"]["RunManifest"]

    schema_deterministic = frozenset(
        name
        for name, prop in runtime_def["properties"].items()
        if prop.get("x-deterministic") is True
    )
    dataclass_deterministic = RunManifest._DETERMINISTIC_FIELDS

    assert schema_deterministic == dataclass_deterministic, (
        "Schema-vs-dataclass drift on RunManifest determinism opt-in. "
        f"Schema: {sorted(schema_deterministic)}. "
        f"Dataclass: {sorted(dataclass_deterministic)}. "
        "Run `uv run python scripts/generate_schema.py` to regenerate."
    )


def test_runtime_field_partial_subset_per_field_determinism() -> None:
    # Phase J — Determinism widening: `runtime` is no longer
    # excluded as a whole. The schema's `$def` for RunManifest
    # carries per-field `x-deterministic` annotations (Phase J
    # extension to the schema generator); the extractor descends
    # into runtime and keeps only the sub-fields tagged true.
    #
    # The non-deterministic sub-fields (timestamps, environment
    # fingerprint, sensitive-unwrap audit log) MUST stay excluded;
    # the documented-deterministic ones (config_hash, selection_seed,
    # source, target, trust_floor, decision_policy, experiment_id,
    # whatif_version, experiment_shape) MUST be present.
    subset = _run_and_extract_subset(scenario_clean_ship())
    assert "runtime" in subset, "Phase J: runtime is now partial-subset, not excluded"
    runtime = subset["runtime"]

    # Deterministic sub-fields present.
    deterministic_subfields = {
        "experiment_id",
        "whatif_version",
        "config_hash",
        "selection_seed",
        "source",
        "target",
        "trust_floor",
        "decision_policy",
        "experiment_shape",
    }
    for name in deterministic_subfields:
        assert name in runtime, f"deterministic runtime sub-field {name!r} missing from subset"

    # Non-deterministic sub-fields excluded.
    non_deterministic_subfields = {
        "started_at",
        "finished_at",
        "duration_ms",
        "environment",
        "agent_identity",
        "redaction",
        "sensitive_unwraps",
    }
    for name in non_deterministic_subfields:
        assert name not in runtime, (
            f"non-deterministic runtime sub-field {name!r} leaked into deterministic subset"
        )


def test_runtime_explicitly_tagged_false_in_schema() -> None:
    # Stronger pin than the exclusion test above: the schema MUST
    # carry `x-deterministic: false` on `runtime`, not just omit
    # the annotation. A schema edit that drops the annotation
    # entirely would silently start letting `runtime` through any
    # consumer that defaults to "include unless tagged true",
    # which is a different (and dangerous) default than the
    # extractor's "include only if tagged true". Catching the
    # negation here keeps the schema's explicit-opt-in contract
    # intact (cardinal #4: determinism is opt-in per field).
    schema_resource = files("whatifd.report.schema").joinpath("v0.1.schema.json")
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    runtime_property = schema["properties"]["runtime"]
    assert runtime_property.get("x-deterministic") is False, (
        "runtime field must carry `x-deterministic: false` explicitly. "
        f"Got: {runtime_property.get('x-deterministic')!r}"
    )


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
    #
    # The `expected` literal is DELIBERATELY hardcoded, not derived
    # from `deterministic_field_names()`. A self-deriving check would
    # silently rubber-stamp a schema-only edit (extractor reads new
    # field → `deterministic_field_names() == deterministic_field_names()`
    # always passes), which is exactly the failure mode this test
    # exists to catch. The friction of updating two places (schema +
    # this literal) is the load-bearing tripwire that forces a
    # contributor to ALSO extend the byte-equality parametrization
    # below with a fixture that exercises the new field. Auto-derive
    # was suggested in review and explicitly declined for this reason.
    expected = {
        "schema_version",
        "schema_uri",
        "experiment_shape",
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
