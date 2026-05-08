"""Structural test enforcing the guards-emit-via-factory discipline.

The package docstring at `whatifd.decision.guards.__init__` says:
"A guard only ever emits findings via `make_decision_finding`, never
via `DecisionFinding(...)` directly — the registry-level severity is
load-bearing per cardinal #2."

This test makes the discipline structural rather than doc-only by
scanning every guard module's source and asserting it contains no
direct `DecisionFinding(...)` constructor call. Type annotations like
`list[DecisionFinding]` are fine — those don't use parens after the
name.

If a future contributor genuinely needs to construct a `DecisionFinding`
without the registry (the contract-violation path is the only legit
one I can think of, and it shouldn't live in a guard), they need to
update this test with a justified `# allow-direct-construction`
exemption — which a reviewer will catch.
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path

import pytest

# Modules under `whatifd.decision.guards` that implement Guard callables.
# Excludes `protocol.py` (Protocol class only; no findings emitted) and
# `__init__.py` (re-exports only). Discovered dynamically so new guards
# that follow the naming convention are picked up automatically.
_GUARDS_PACKAGE = "whatifd.decision.guards"


def _guard_module_paths() -> list[Path]:
    pkg = importlib.import_module(_GUARDS_PACKAGE)
    pkg_dir = Path(inspect.getfile(pkg)).parent
    skip = {"__init__.py", "protocol.py"}
    return sorted(p for p in pkg_dir.glob("*.py") if p.name not in skip)


# `DecisionFinding(` (open paren immediately after the name) — only
# constructor calls trigger this; type annotations like
# `list[DecisionFinding]` and bare names don't.
_DIRECT_CONSTRUCTION_RE = re.compile(r"\bDecisionFinding\s*\(")


class TestGuardEmitsViaFactoryOnly:
    @pytest.mark.parametrize("path", _guard_module_paths(), ids=lambda p: p.name)
    def test_no_direct_decisionfinding_construction(self, path: Path) -> None:
        # Cardinal #2 / discipline: guards must emit only via
        # `make_decision_finding` so registry-level severity stays
        # load-bearing. A direct `DecisionFinding(...)` call bypasses
        # the registry — caught here.
        source = path.read_text()
        match = _DIRECT_CONSTRUCTION_RE.search(source)
        assert match is None, (
            f"{path.name} contains direct `DecisionFinding(...)` construction. "
            "Guards must emit findings via `make_decision_finding(...)` so the "
            "registry-level severity stays load-bearing per cardinal #2. "
            "See guards/__init__.py discipline note."
        )

    @pytest.mark.parametrize("path", _guard_module_paths(), ids=lambda p: p.name)
    def test_imports_make_decision_finding(self, path: Path) -> None:
        # Positive structural assertion: a guard that emits findings
        # MUST import `make_decision_finding`. The negative test above
        # rules out direct construction; this one rules out a guard
        # that emits findings via some other path (third-party
        # factory, etc.) — there should be exactly one factory.
        source = path.read_text()
        # Match either single-line or parenthesized multi-line import.
        imports_factory = "make_decision_finding" in source
        assert imports_factory, (
            f"{path.name} does not import `make_decision_finding`. Every guard "
            "module that emits findings must use the registry factory. If this "
            "module deliberately emits no findings, document that and add an "
            "exemption to this test."
        )


def test_guard_modules_discovered() -> None:
    # Sanity: parametrize discovery isn't silently empty (which would
    # make the parametrized tests pass vacuously).
    assert len(_guard_module_paths()) >= 2, (
        "expected at least two guard modules (practical_delta, "
        "improvement_observation); something is wrong with discovery"
    )
