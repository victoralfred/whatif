"""Deterministic-subset extraction — Phase 9A.3.

Reads the committed JSON Schema (`v0.1.schema.json`) to discover
which top-level `ReportV01` fields are tagged `x-deterministic: true`
and projects a serialized report down to that subset. The
deterministic subset is what the determinism CI test compares
byte-for-byte across re-runs of the same fixture; non-deterministic
fields (timestamps, environment fingerprints, sensitive-unwrap
audit logs) live under `runtime` and are excluded.

## Why schema-driven, not a hardcoded list

The `x-deterministic` annotations live on the schema; the schema
is the source of truth (cardinal #4: determinism is opt-in per
field). Hardcoding a list here would drift the moment the schema
adds or removes a tagged field — the extractor must follow the
schema, not the other way around.

## Cardinal #4 alignment

Determinism is opt-in **per field**, not per object. v0.1 ships
top-level scalar/list fields tagged `x-deterministic: true` and
the entire `runtime` subtree tagged `false`. The extractor
operates at the top level only — nested-field determinism (e.g.,
`runtime.config_hash` is deterministic even though `runtime` is
not) is the determinism *claim*, not the comparison surface. The
report's deterministic subset is the part that should be byte-
equal across re-runs; for v0.1 that's everything except `runtime`.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from typing import Any, TypedDict

# Functional TypedDict form because `x-deterministic` carries a
# hyphen and isn't a valid Python identifier. `total=False` because
# the schema's per-property keys are optional — a property may
# carry `type` OR `$ref`, `x-deterministic` may be absent on legacy
# fields, etc. The extractor uses `.get("x-deterministic")` so
# absence is safe; the typed shape exists so callers don't see
# `dict[str, Any]` bleed across the internal/boundary line.
# Self-recursive: a schema property's `items` is itself a property
# (the element schema for an array), and `properties` maps names to
# nested property definitions. Forward-referencing via the string
# `"SchemaProperty"` closes the loop. `additionalProperties` accepts
# either a bool (true/false) or another SchemaProperty per JSON
# Schema. The recursive shape eliminates the `dict[str, Any]` surface
# the prior version carried; only the JSON-loaded value type from
# `json.loads` (which is fundamentally `Any`) remains, and that's
# bounded to the `_schema_properties` cast.
SchemaProperty = TypedDict(
    "SchemaProperty",
    {
        "type": str,
        "$ref": str,
        "items": "SchemaProperty",
        "properties": dict[str, "SchemaProperty"],
        "additionalProperties": "bool | SchemaProperty",
        "description": str,
        "x-deterministic": bool,
    },
    total=False,
)


class DeterministicSubsetWarning(UserWarning):
    """Emitted by `extract_deterministic_subset` when the input dict
    carries keys not present in the schema's top-level properties.

    Triggered by schema drift — typically a producer running a newer
    `ReportV01` shape than the consumer's bundled schema. Warning
    (not raise) because dropping the extra key is the safer
    extraction default; raising would block byte-equality comparisons
    on otherwise-compatible reports. Future schema-bump migrations
    can promote this to an error if drift becomes a load-bearing
    failure mode.
    """


@lru_cache(maxsize=1)
def _schema_properties() -> dict[str, SchemaProperty]:
    """Load the v0.1 schema's `properties` map once.

    `importlib.resources.files` is the forward-compatible loader —
    works under zipimport, namespace packages, and editable installs
    without depending on `__file__` resolution.
    """
    schema_resource = files("whatif.report.schema").joinpath("v0.1.schema.json")
    schema = json.loads(schema_resource.read_text(encoding="utf-8"))
    properties: dict[str, SchemaProperty] = schema.get("properties", {})
    return properties


@lru_cache(maxsize=1)
def _deterministic_field_names() -> frozenset[str]:
    """Cache the set of top-level field names tagged
    `x-deterministic: true`. Schema is committed; doesn't change at
    runtime."""
    return frozenset(
        name for name, prop in _schema_properties().items() if prop.get("x-deterministic") is True
    )


def deterministic_field_names() -> frozenset[str]:
    """Public accessor for the cached set. Tests use this to assert
    coverage against the schema (e.g., \"the determinism test must
    cover every field tagged True\")."""
    return _deterministic_field_names()


def extract_deterministic_subset(report_dict: Mapping[str, Any]) -> dict[str, Any]:
    """Project `report_dict` down to the deterministic subset.

    `report_dict` is the JSON-serialized form (a `dict[str, Any]`) of
    a `ReportV01`. Returns a new dict containing only the keys whose
    schema property carries `x-deterministic: true`. Non-deterministic
    keys (currently just `runtime`) are dropped.

    Emits `DeterministicSubsetWarning` for any input key not present
    in the schema's top-level properties — typically schema drift
    (producer is newer than the consumer's bundled schema). Warning,
    not raise, so byte-equality comparisons on otherwise-compatible
    reports stay possible; the surfaced warning still flags the
    drift loudly.

    This function does NOT serialize — pass it the result of
    `json.loads(WhatifJSONEncoder.encode(report))` (or equivalent).
    Splitting serialization from extraction keeps the determinism
    test composable with any future JSON-shape changes.
    """
    schema_properties = _schema_properties()
    unknown = sorted(k for k in report_dict if k not in schema_properties)
    if unknown:
        warnings.warn(
            f"extract_deterministic_subset: keys not in schema (dropped): {unknown!r}. "
            "Likely schema drift — producer ahead of consumer's bundled v0.1 schema.",
            DeterministicSubsetWarning,
            stacklevel=2,
        )
    keep = _deterministic_field_names()
    return {k: v for k, v in report_dict.items() if k in keep}


__all__ = [
    "DeterministicSubsetWarning",
    "deterministic_field_names",
    "extract_deterministic_subset",
]
