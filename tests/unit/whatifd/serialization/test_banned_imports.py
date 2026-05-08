"""Phase 5.3 banned-import lint scaffolding.

Per `references/enforcement.md` row 2 (cardinal #5 boundary):

> Banned-import lint blocks `json.dumps` outside `whatif/serialization/`.

Implementation: walk the AST of every module under `src/whatifd/`,
flag any `Call` whose function reference is `json.dumps` (whether
imported as `json.dumps`, `from json import dumps`, or aliased) and
whose containing module is NOT under `whatifd.serialization.*`.

Why an AST walk rather than a ruff custom rule:

- Ruff's custom-rule extension is preview-only and version-locked;
  introducing it adds a maintenance surface beyond what cardinal #5
  enforcement needs.
- The AST walk is ~30 lines of stdlib code, runs in pytest with no
  extra dependency, and catches every `json.dumps` invocation form
  (`json.dumps(...)`, `dumps(...)` after `from json import dumps`,
  aliased `dumps as _dumps`, etc.).
- Phase 5.3 prefers the lighter mechanism that satisfies the
  enforcement contract.

The `_ALLOWED_PACKAGE_PREFIX` is `whatifd.serialization` (and its
sub-modules). Adding a new sanctioned location requires updating
this constant AND a corresponding `references/enforcement.md` row
update. The test fails loudly if anyone tries to use `json.dumps`
elsewhere in `src/whatifd/`.

`json.loads` is NOT banned — only `json.dumps` (the cardinal #5
artifact-write boundary) per `enforcement.md` row 2. Reads have no
Sensitive[T] redaction concern.
"""

from __future__ import annotations

import ast
from pathlib import Path

import whatifd

_SRC_ROOT = Path(whatifd.__file__).resolve().parent
_ALLOWED_PACKAGE_PREFIX = "whatifd.serialization"


def _module_name_for(path: Path) -> str:
    """Compute the dotted module name for a file under `src/whatifd/`."""
    rel = path.relative_to(_SRC_ROOT.parent)  # rel to `src/`
    parts = rel.with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_serialization_module(module_name: str) -> bool:
    return module_name == _ALLOWED_PACKAGE_PREFIX or module_name.startswith(
        _ALLOWED_PACKAGE_PREFIX + "."
    )


def _find_json_dumps_calls(tree: ast.AST, module_name: str) -> list[tuple[int, str]]:
    """Walk `tree` and return a list of `(line, expr_repr)` tuples
    for every `json.dumps(...)` call (in any import form).

    Detection forms:
    - `json.dumps(...)`: `Call.func` is an `Attribute` with `attr="dumps"`
      and `value=Name(id="json")`.
    - `from json import dumps; dumps(...)`: `Call.func` is `Name(id="dumps")`
      AND a top-level `from json import ... dumps ...` exists in the
      module.
    - `from json import dumps as X; X(...)`: walk import statements,
      record any `dumps`-derived alias, then check Name.id against
      that set.
    """
    aliases: set[str] = set()  # names that resolve to json.dumps via import
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "json":
            for alias in node.names:
                if alias.name == "dumps":
                    aliases.add(alias.asname or alias.name)

    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Form 1: json.dumps(...)
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "dumps"
                and isinstance(func.value, ast.Name)
                and func.value.id == "json"
            ):
                hits.append((node.lineno, "json.dumps"))
            # Forms 2/3: aliased dumps after `from json import dumps [as X]`
            elif isinstance(func, ast.Name) and func.id in aliases:
                hits.append((node.lineno, func.id))
    return hits


def test_no_json_dumps_outside_serialization_package() -> None:
    """Walk every `.py` file under `src/whatifd/` and assert no
    `json.dumps` calls exist in modules outside `whatifd.serialization.*`.

    The serialization package is the cardinal #5 artifact-write
    boundary; everywhere else hashes inputs through
    `canonical_json_bytes` (also in serialization/) or uses
    `WhatifJSONEncoder` for artifact writes. New violations fail
    this test with a clear file:line citation.
    """
    violations: list[str] = []
    for py_file in _SRC_ROOT.rglob("*.py"):
        module_name = _module_name_for(py_file)
        if _is_serialization_module(module_name):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError as e:  # pragma: no cover (would fail mypy/ruff first)
            raise AssertionError(f"could not parse {py_file}: {e}") from e
        for line, expr in _find_json_dumps_calls(tree, module_name):
            violations.append(f"{py_file}:{line}: {expr}(...)")

    assert not violations, (
        "json.dumps used outside whatif/serialization/ "
        "(references/enforcement.md row 2 — cardinal #5 boundary):\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_serialization_package_uses_json_dumps() -> None:
    """Sanity: the serialization package itself MUST use json.dumps
    (otherwise the encoder / canonical helper is dead code). Pinned
    here so a refactor that accidentally moved the json call out of
    the package — and thus broke the enforcement boundary's premise —
    surfaces here, not just in the boundary test above.
    """
    found_in_serialization = False
    for py_file in _SRC_ROOT.rglob("*.py"):
        module_name = _module_name_for(py_file)
        if not _is_serialization_module(module_name):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        if _find_json_dumps_calls(tree, module_name):
            found_in_serialization = True
            break

    assert found_in_serialization, (
        "expected at least one json.dumps call inside whatif/serialization/ "
        "(canonical.py and encoder.py both use it); none found. The "
        "boundary test would pass vacuously without this sanity check."
    )


def test_module_name_resolution() -> None:
    """Defensive: ensure _module_name_for handles `__init__.py` and
    nested modules correctly. Otherwise the boundary test could
    silently classify a file outside whatif/serialization/ as inside.
    """
    init_path = _SRC_ROOT / "serialization" / "__init__.py"
    assert _module_name_for(init_path) == "whatifd.serialization"

    submodule = _SRC_ROOT / "serialization" / "encoder.py"
    assert _module_name_for(submodule) == "whatifd.serialization.encoder"

    nested = _SRC_ROOT / "cache" / "keying" / "v1.py"
    assert _module_name_for(nested) == "whatifd.cache.keying.v1"

    assert _is_serialization_module("whatifd.serialization")
    assert _is_serialization_module("whatifd.serialization.encoder")
    assert not _is_serialization_module("whatifd.cache.keying.v1")
    assert not _is_serialization_module("whatifd.serialization_helpers")  # prefix trap
