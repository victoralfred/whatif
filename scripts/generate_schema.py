"""`scripts/generate_schema.py` — derive JSON Schema from `ReportV01`.

Phase 5.5 of the v0.1 implementation plan. The generator walks
`ReportV01` (and every nested frozen dataclass it transitively
references) via `typing.get_type_hints` + `dataclasses.fields` and
emits a JSON Schema document with `$defs` for nested types.

## Why generate, not hand-write

Cardinal #6 says public schema is hand-written; that doctrine is
satisfied by hand-writing `ReportV01` (the Python dataclass). The
JSON Schema FILE is then a derived artifact that mirrors the
hand-written shape. Generating from the dataclass eliminates a class
of drift bugs (schema says one thing, dataclass says another) and
makes schema review = code review of `models_v01.py`.

The committed `v0.1.schema.json` in `src/whatifd/report/schema/` is
the output of this script. The drift test
(`tests/unit/whatifd/report/test_schema.py`) re-runs the generator
and asserts byte equality with the committed file. A schema change
that isn't accompanied by a regenerate produces a failing CI.

## CLI

- `python scripts/generate_schema.py` — write to canonical path under
  `src/whatifd/report/schema/v0.1.schema.json`.
- `python scripts/generate_schema.py --stdout` — print to stdout
  (used by the drift test and `diff` workflows).

## Type-to-schema mapping

| Python                                | JSON Schema                                        |
|---------------------------------------|----------------------------------------------------|
| `str` / `NewType("X", str)`           | `{"type": "string"}`                               |
| `int`                                 | `{"type": "integer"}`                              |
| `float`                               | `{"type": "number"}`                               |
| `bool`                                | `{"type": "boolean"}`                              |
| `None`                                | `{"type": "null"}`                                 |
| `Literal["a", "b"]`                   | `{"enum": ["a", "b"]}`                             |
| ``A | B`` / `Union[A, B]`             | `{"oneOf": [<A>, <B>]}`                            |
| `list[T]` / `tuple[T, ...]`           | `{"type": "array", "items": <T>}`                  |
| `Mapping[str, T]` / `dict[str, T]`    | `{"type": "object", "additionalProperties": <T>}`  |
| `@dataclass D`                        | `{"$ref": "#/$defs/D"}`                            |

Required = every field whose `dataclasses.Field.default` and
`default_factory` are both `MISSING`. Other fields are optional.
`additionalProperties: false` on every dataclass `$def` keeps the
wire shape closed — adding a field requires a schema bump.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import types
import typing
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

# Ensure src/ is importable when run as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from whatifd.report.models_v01 import (  # noqa: E402
    REPORT_SCHEMA_URI,
    REPORT_SCHEMA_VERSION,
    ReportV01,
)

_SCHEMA_FILE = _REPO_ROOT / "src" / "whatifd" / "report" / "schema" / "v0.1.schema.json"

# Top-level fields annotated `x-deterministic: false` per cardinal #4.
# Everything else defaults to deterministic. Per-field annotations
# inside `runtime` aren't carried — the whole subtree is excluded.
_NON_DETERMINISTIC_TOP_LEVEL = frozenset({"runtime"})


def _is_dataclass_type(obj: Any) -> bool:
    return isinstance(obj, type) and dataclasses.is_dataclass(obj)


def _newtype_supertype(tp: Any) -> Any | None:
    # NewType("X", str) carries a __supertype__ pointing at str.
    return getattr(tp, "__supertype__", None)


def _type_to_schema(tp: Any, defs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Convert a Python type annotation to a JSON Schema fragment.

    Mutates `defs` to register dataclass `$defs` as it encounters
    them. Returns a fragment suitable for use as a property value or
    a `oneOf` arm.
    """
    # Unwrap NewType to its supertype for schema purposes.
    super_tp = _newtype_supertype(tp)
    if super_tp is not None:
        return _type_to_schema(super_tp, defs)

    if tp is type(None):
        return {"type": "null"}
    if tp is str:
        return {"type": "string"}
    if tp is bool:
        return {"type": "boolean"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}

    origin = get_origin(tp)
    args = get_args(tp)

    if origin is Literal:
        # Literal values are always JSON-primitive (str/int/bool/None).
        return {"enum": list(args)}

    if origin is Union or origin is types.UnionType:
        return {"oneOf": [_type_to_schema(a, defs) for a in args]}

    if origin in (list, tuple):
        # tuple[T, ...] (variadic) and list[T] both project as arrays.
        # The variadic tuple is the only tuple shape used in the wire
        # types — fixed-length tuples would need positional schemas.
        if origin is tuple and not (len(args) == 2 and args[1] is Ellipsis):
            raise NotImplementedError(
                f"Fixed-length tuples not supported in schema generation: {tp!r}. "
                "Wire types use variadic `tuple[T, ...]` only."
            )
        item_tp = args[0]
        return {"type": "array", "items": _type_to_schema(item_tp, defs)}

    if origin in (dict, Mapping) or (isinstance(origin, type) and issubclass(origin, Mapping)):
        if len(args) != 2 or args[0] is not str:
            raise NotImplementedError(
                f"Only `Mapping[str, T]` / `dict[str, T]` supported: {tp!r}. "
                "Cardinal #6 forbids non-str keys at the wire boundary."
            )
        return {
            "type": "object",
            "additionalProperties": _type_to_schema(args[1], defs),
        }

    if _is_dataclass_type(tp):
        if tp.__name__ not in defs:
            # Insert placeholder BEFORE recursing so cycles terminate.
            defs[tp.__name__] = {}
            defs[tp.__name__] = _dataclass_to_schema(tp, defs)
        return {"$ref": f"#/$defs/{tp.__name__}"}

    raise NotImplementedError(f"Unsupported type in schema generation: {tp!r}")


def _dataclass_to_schema(cls: type, defs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build a JSON Schema object for a frozen dataclass."""
    # `include_extras=True` would surface `Annotated` metadata; the v0.1
    # types don't use Annotated, so the default is fine.
    hints = typing.get_type_hints(cls)
    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for field in dataclasses.fields(cls):
        # General rule: skip computed fields (`init=False`). They are
        # derived in `__post_init__` from other fields, so they don't
        # form part of the inbound wire contract — a consumer sending
        # them in is over-specifying state the producer would
        # recompute. (Concrete current example: the internal
        # `TraceDelta.delta` field; the wire-shape
        # `TraceDeltaReportV01.delta` is `init=True` because the wire
        # carries the already-computed value.)
        if not field.init:
            continue
        field_tp = hints[field.name]
        properties[field.name] = _type_to_schema(field_tp, defs)
        if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
            required.append(field.name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        # `required` is sorted alphabetically because JSON Schema treats
        # it as a SET (order is semantically irrelevant), and a sorted
        # list is byte-stable across Python versions / dataclass field
        # reorderings. `properties` is left in dataclass-declaration
        # order — the top-level `json.dumps(..., sort_keys=True)` in
        # `render_schema_bytes` re-sorts it alphabetically at emit
        # time, so the wire bytes stay deterministic regardless of the
        # in-memory dict order.
        schema["required"] = sorted(required)
    return schema


def build_schema() -> dict[str, Any]:
    """Build the full JSON Schema document for `ReportV01`.

    The top-level schema embeds the `ReportV01` definition inline (not
    via `$ref`) so consumers can validate without dereferencing.
    Nested dataclasses live under `$defs`. The `x-deterministic`
    annotation on top-level properties marks the determinism budget
    (cardinal #4) — `runtime` is excluded; everything else is in.
    """
    defs: dict[str, dict[str, Any]] = {}
    root = _dataclass_to_schema(ReportV01, defs)
    # ReportV01 itself shouldn't appear as a $def — it's the root.
    defs.pop("ReportV01", None)

    # Annotate top-level properties with x-deterministic per cardinal #4.
    for name, prop in root["properties"].items():
        prop["x-deterministic"] = name not in _NON_DETERMINISTIC_TOP_LEVEL

    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": REPORT_SCHEMA_URI,
        "title": "WhatifReportV01",
        "description": (
            "v0.1 wire-format report emitted by `whatif fork`. "
            "Hand-written types in `whatifd/report/models_v01.py`; this "
            "schema is generated from them by `scripts/generate_schema.py`."
        ),
        "schema_version": REPORT_SCHEMA_VERSION,
        **root,
        "$defs": defs,
    }
    return schema


def render_schema_bytes(schema: dict[str, Any]) -> bytes:
    """Canonicalize the schema dict to bytes.

    `sort_keys=True` + `indent=2` + trailing newline produces a
    human-readable, byte-stable file. Determinism does NOT require
    `separators=(",", ":")` here (that's the hash-input form);
    readability matters more for a committed schema file. Stability
    comes from `sort_keys=True`.
    """
    return (json.dumps(schema, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the schema to stdout instead of writing the canonical file.",
    )
    args = parser.parse_args()

    schema = build_schema()
    payload = render_schema_bytes(schema)

    if args.stdout:
        sys.stdout.buffer.write(payload)
        return 0

    _SCHEMA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SCHEMA_FILE.write_bytes(payload)
    print(f"Wrote {_SCHEMA_FILE.relative_to(_REPO_ROOT)} ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
