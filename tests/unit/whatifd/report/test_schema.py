"""Tests for the generated `v0.1.schema.json` — Phase 5.5.

Pin properties:

1. **Drift test:** regenerating the schema produces bytes byte-equal to
   the committed file. A schema change that isn't accompanied by a
   regenerate fails CI.
2. **Top-level required fields:** every dataclass field on `ReportV01`
   appears in the top-level `required` list. A future contributor
   adding an `Optional` field to the wire shape would fail this test
   and have to think about whether the field is truly optional.
3. **`x-deterministic` annotation:** `runtime` is `false`; every other
   top-level property is `true`. Per cardinal #4.
4. **`$defs` completeness:** every nested dataclass referenced from
   `ReportV01` (transitively) appears as a `$def` entry.
5. **Encoded fixture validates structurally:** an encoded `ReportV01`
   has every required top-level key (smoke; full jsonschema-library
   validation deferred to Phase 9 integration).
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import pytest

from whatifd.report.models_v01 import REPORT_SCHEMA_VERSION, ReportV01
from whatifd.report.projection import project_to_report_v01
from whatifd.serialization import encode_report_v01

from ._fixtures import (
    cache_summary,
    methodology,
    runtime,
    ship,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCHEMA_FILE = (
    _REPO_ROOT / "src" / "whatifd" / "report" / "schema" / f"v{REPORT_SCHEMA_VERSION}.schema.json"
)
_GENERATOR = _REPO_ROOT / "scripts" / "generate_schema.py"


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(_SCHEMA_FILE.read_bytes())


@pytest.fixture(scope="module")
def encoded_ship_report() -> dict:
    """Encoded `ReportV01` from the `ship()` fixture, parsed back to
    dict. Module-scoped so the projection + encode pair runs once
    across the smoke tests rather than per-test."""
    report = project_to_report_v01(
        ship(),
        failures=[],
        cache_summary=cache_summary(),
        methodology=methodology(),
        runtime=runtime(),
    )
    return json.loads(encode_report_v01(report))


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


class TestSchemaDrift:
    def test_committed_schema_byte_equals_regenerated(self) -> None:
        # Re-run the generator; assert byte equality with the committed
        # file. Catches: a contributor edited `models_v01.py` without
        # running `python scripts/generate_schema.py`.
        try:
            result = subprocess.run(
                [sys.executable, str(_GENERATOR), "--stdout"],
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            # Distinguish generator failure (e.g., a new unsupported
            # type added to the wire shape — `NotImplementedError` from
            # `_type_to_schema`) from drift. The drift message would
            # mislead a reader debugging a generator crash.
            raise AssertionError(
                f"Schema generator failed (exit {exc.returncode}). This is "
                "NOT a drift failure — the generator itself errored. "
                f"stderr:\n{exc.stderr.decode('utf-8', errors='replace')}"
            ) from exc
        committed = _SCHEMA_FILE.read_bytes()
        assert result.stdout == committed, (
            "Schema drift detected. Run `python scripts/generate_schema.py` "
            f"to regenerate, then commit the updated v{REPORT_SCHEMA_VERSION}.schema.json."
        )


# ---------------------------------------------------------------------------
# Top-level structure
# ---------------------------------------------------------------------------


class TestTopLevelShape:
    def test_schema_has_required_meta_keys(self, schema: dict) -> None:
        for key in ("$schema", "$id", "title", "schema_version", "$defs", "properties", "required"):
            assert key in schema, f"missing top-level key: {key}"

    def test_schema_id_matches_report_uri(self, schema: dict) -> None:
        from whatifd.report.models_v01 import REPORT_SCHEMA_URI

        assert schema["$id"] == REPORT_SCHEMA_URI

    def test_schema_version_matches_constant(self, schema: dict) -> None:
        assert schema["schema_version"] == REPORT_SCHEMA_VERSION

    def test_every_report_field_is_required(self, schema: dict) -> None:
        # ReportV01 has zero defaulted fields — the wire shape is
        # closed (no implicit nulls). A future field with a default
        # would either need an explicit Optional schema arm or this
        # test must be relaxed deliberately.
        report_field_names = {f.name for f in dataclasses.fields(ReportV01)}
        assert set(schema["required"]) == report_field_names

    def test_additional_properties_false(self, schema: dict) -> None:
        # Wire shape is closed — a producer that adds an unknown field
        # is a contract violation, not a forward-compat extension.
        assert schema["additionalProperties"] is False


# ---------------------------------------------------------------------------
# x-deterministic annotation (cardinal #4)
# ---------------------------------------------------------------------------


class TestDeterminismAnnotation:
    def test_runtime_is_non_deterministic(self, schema: dict) -> None:
        assert schema["properties"]["runtime"]["x-deterministic"] is False

    def test_all_other_top_level_are_deterministic(self, schema: dict) -> None:
        for name, prop in schema["properties"].items():
            if name == "runtime":
                continue
            assert prop.get("x-deterministic") is True, (
                f"top-level property {name!r} missing x-deterministic: true. "
                "Cardinal #4: every wire field is in the determinism budget "
                "unless explicitly excluded."
            )


# ---------------------------------------------------------------------------
# $defs coverage
# ---------------------------------------------------------------------------


class TestDefsCoverage:
    def test_known_nested_dataclasses_in_defs(self, schema: dict) -> None:
        # Sanity: a sample of nested dataclasses must appear under $defs.
        # If a future refactor inlines one of these, this test surfaces
        # the change for explicit review.
        expected = {
            "CohortResult",
            "FloorFailure",
            "FailureRecord",
            "DecisionFinding",
            "CacheSummary",
            "TrustFloor",
            "DecisionPolicy",
            "MethodologyDisclosure",
            "BootstrapMethodDisclosure",
            "JudgeMethodDisclosure",
            "RunManifest",
            "EnvironmentFingerprint",
            "SensitiveUnwrap",
        }
        assert expected.issubset(schema["$defs"].keys())

    def test_report_v01_not_in_defs(self, schema: dict) -> None:
        # ReportV01 is the root document, not a $def entry. The
        # generator pops it after collection.
        assert "ReportV01" not in schema["$defs"]

    def test_every_def_is_object_with_properties(self, schema: dict) -> None:
        for name, definition in schema["$defs"].items():
            assert definition.get("type") == "object", f"{name} is not an object"
            assert "properties" in definition, f"{name} has no properties"
            assert definition.get("additionalProperties") is False, (
                f"{name} allows additionalProperties — wire shapes must be closed"
            )


# ---------------------------------------------------------------------------
# Encoded fixture smoke-validation
# ---------------------------------------------------------------------------


class TestEncodedFixtureMatchesSchema:
    """Smoke test: an encoded `ReportV01` has every required top-level
    key. Full `jsonschema`-library validation is deferred to Phase 9
    integration (the dep isn't pulled in for unit tests here).
    """

    def test_encoded_ship_has_all_required_top_level_keys(
        self, schema: dict, encoded_ship_report: dict
    ) -> None:
        for key in schema["required"]:
            assert key in encoded_ship_report, f"encoded report missing required key: {key}"

    def test_encoded_verdict_state_is_in_enum(
        self, schema: dict, encoded_ship_report: dict
    ) -> None:
        # The wire-format verdict_state literal must be one of the
        # three documented strings (cardinal #2 contract).
        verdict_enum = schema["properties"]["verdict_state"]["enum"]
        assert encoded_ship_report["verdict_state"] in verdict_enum


class TestDataclassToSchemaPerFieldDeterminism:
    """Phase J: `_dataclass_to_schema` emits per-field `x-deterministic`
    annotations on dataclasses that opt in via `_DETERMINISTIC_FIELDS`.
    Direct unit-level coverage of the generator (the existing schema-
    drift test catches regressions only after regeneration; this test
    catches generator-logic regressions before that step).
    """

    def test_emits_per_field_annotations_for_optin_dataclass(self) -> None:
        # Functional `make_dataclass` rather than `@dataclass` decorator:
        # this file has `from __future__ import annotations`, which makes
        # decorator-form annotations strings. Resolving `ClassVar[...]`
        # from a function-local scope at field-resolution time is brittle.
        # `make_dataclass` takes type objects directly and the namespace
        # dict carries the class attribute as-is — exactly the shape the
        # generator reads via `getattr`.
        from dataclasses import make_dataclass

        repo_root = Path(__file__).resolve().parents[4]
        sys.path.insert(0, str(repo_root / "scripts"))
        try:
            from generate_schema import _dataclass_to_schema  # type: ignore[import-not-found]
        finally:
            sys.path.pop(0)

        opt_in_cls = make_dataclass(
            "opt_in_cls",
            [("a", str), ("b", str), ("c", int)],
            namespace={"_DETERMINISTIC_FIELDS": frozenset({"a", "c"})},
            frozen=True,
        )

        defs: dict[str, dict] = {}
        schema = _dataclass_to_schema(opt_in_cls, defs)
        props = schema["properties"]
        assert props["a"]["x-deterministic"] is True
        assert props["b"]["x-deterministic"] is False
        assert props["c"]["x-deterministic"] is True

    def test_no_annotations_for_dataclass_without_optin(self) -> None:
        from dataclasses import make_dataclass

        repo_root = Path(__file__).resolve().parents[4]
        sys.path.insert(0, str(repo_root / "scripts"))
        try:
            from generate_schema import _dataclass_to_schema  # type: ignore[import-not-found]
        finally:
            sys.path.pop(0)

        plain_cls = make_dataclass("plain_cls", [("a", str), ("b", int)], frozen=True)

        defs: dict[str, dict] = {}
        schema = _dataclass_to_schema(plain_cls, defs)
        # Without _DETERMINISTIC_FIELDS the generator MUST NOT emit
        # per-field x-deterministic — the top-level annotator owns
        # that decision for non-opt-in dataclasses.
        assert "x-deterministic" not in schema["properties"]["a"]
        assert "x-deterministic" not in schema["properties"]["b"]
