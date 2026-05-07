"""`_PROOF_TOKEN` isolation lint — cardinal #7 mechanical guarantee.

The cardinal-#7 witness pattern (`TwoAffirmationProof`) works only
if the closure-captured `_PROOF_TOKEN` sentinel stays
module-private to `whatif.config`. A re-export — accidental or
otherwise — would let any caller fabricate a proof and bypass the
two-affirmation check.

This module walks every `.py` under `src/whatif/` and asserts:

  1. Outside `whatif.config`, no module imports `_PROOF_TOKEN`.
  2. Inside `whatif.config`, `_PROOF_TOKEN` does NOT appear in
     `__all__` (would re-export it via `from whatif.config import *`).

Same lint pattern as the `json.dumps` ban
(`tests/unit/whatif/serialization/test_banned_imports.py`):
AST walk, no extra dependencies, ~30 lines.

## What this lint does NOT cover

Runtime access via `getattr(whatif.config, "_PROOF_TOKEN")` is
NOT detected — `ast.walk` sees the bare `getattr` call but can't
statically prove the second argument is `_PROOF_TOKEN`. This is
acceptable for v0.1 because:

- Static `import` and `Attribute` access are the natural ways to
  reference a module symbol; deliberate `getattr` evasion is a
  documented anti-pattern, not a routine refactor.
- A determined caller bypassing cardinal #7 via runtime
  introspection is outside the threat model — cardinal #7
  defends against ACCIDENTAL forensic-profile enablement, not
  against a malicious actor with full Python access.

A future hardening (v0.2+) could parse the dotted module
introspection patterns; not v0.1 scope.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_ROOT = _REPO_ROOT / "src" / "whatif"
_OWNER_MODULE = "whatif.config"
_TOKEN_NAME = "_PROOF_TOKEN"


def _module_name(py_file: Path) -> str:
    rel = py_file.relative_to(_SRC_ROOT.parent)
    parts = rel.with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports_token(tree: ast.AST) -> bool:
    """Return True if the AST has any reference that imports or
    re-exports `_PROOF_TOKEN`."""
    for node in ast.walk(tree):
        # `from whatif.config import _PROOF_TOKEN`
        if isinstance(node, ast.ImportFrom) and node.module == _OWNER_MODULE:
            for alias in node.names:
                if alias.name == _TOKEN_NAME:
                    return True
        # `import whatif.config as cfg; cfg._PROOF_TOKEN`
        # detected via Attribute access
        if isinstance(node, ast.Attribute) and node.attr == _TOKEN_NAME:
            return True
    return False


def _all_list_contains_token(tree: ast.AST) -> bool:
    """Return True if `__all__` is assigned a list/tuple containing
    `'_PROOF_TOKEN'` as a string element."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [t for t in node.targets if isinstance(t, ast.Name)]
            if not any(t.id == "__all__" for t in targets):
                continue
            value = node.value
            if isinstance(value, (ast.List, ast.Tuple)):
                for elt in value.elts:
                    if isinstance(elt, ast.Constant) and elt.value == _TOKEN_NAME:
                        return True
    return False


def test_proof_token_not_imported_outside_config_module() -> None:
    violations: list[str] = []
    for py_file in _SRC_ROOT.rglob("*.py"):
        module = _module_name(py_file)
        if module == _OWNER_MODULE:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        if _imports_token(tree):
            violations.append(module)

    assert not violations, (
        f"_PROOF_TOKEN imported outside {_OWNER_MODULE!r}: {violations}. "
        "Cardinal #7 witness-pattern guarantee depends on the token "
        "staying module-private. Move the proof-construction call "
        "inside whatif.config or refactor the witness API."
    )


def test_proof_token_not_in_config_all() -> None:
    config_path = _SRC_ROOT / "config.py"
    tree = ast.parse(config_path.read_text(encoding="utf-8"))
    assert not _all_list_contains_token(tree), (
        f"{_TOKEN_NAME} is in {_OWNER_MODULE}.__all__. Re-exporting "
        "the token via `from whatif.config import *` would let any "
        "caller fabricate a TwoAffirmationProof, defeating cardinal "
        "#7's witness-pattern guarantee. Remove from __all__."
    )


def test_lint_self_check() -> None:
    # Sanity: confirm the sentinel actually exists in
    # whatif.config — without it the lint above would be vacuously
    # passing (no token to leak).
    config_path = _SRC_ROOT / "config.py"
    tree = ast.parse(config_path.read_text(encoding="utf-8"))
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == _TOKEN_NAME:
                    found = True
                    break
    assert found, (
        f"{_TOKEN_NAME} not found in {_OWNER_MODULE}; the lint above "
        "is vacuously passing. Either restore the sentinel or remove "
        "this lint module."
    )
