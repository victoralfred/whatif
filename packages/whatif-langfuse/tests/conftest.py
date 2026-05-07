"""Make the parent repo's adapter conformance harness importable.

Phase 4B.1: the conformance harness lives at
`<repo>/tests/adapters/conformance.py` (under the parent `whatif`
project's test tree, not yet promoted to a public module — see
`whatif-features/references/deferred-refactors.md` entry #1).
This conftest adds that directory to `sys.path` so any package
test can `from conformance import TraceSourceConformance`.

If the harness is ever promoted to `whatif.testing`, drop this
conftest and switch imports to the public surface in the same PR.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HARNESS_DIR = _REPO_ROOT / "tests" / "adapters"

if str(_HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(_HARNESS_DIR))
