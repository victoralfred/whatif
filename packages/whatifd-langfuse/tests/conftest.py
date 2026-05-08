"""Make the parent repo's adapter conformance harness importable.

Phase 4B.1: the conformance harness lives at
`<repo>/tests/adapters/conformance.py` (under the parent `whatif`
project's test tree, not yet promoted to a public module — see
`whatif-features/references/deferred-refactors.md` entry #1).
This conftest adds that directory to `sys.path` so any package
test can `from conformance import TraceSourceConformance`.

If the harness is ever promoted to `whatifd.testing`, drop this
conftest and switch imports to the public surface in the same PR.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HARNESS_DIR = _REPO_ROOT / "tests" / "adapters"

_HARNESS_MISSING_MESSAGE = (
    "whatifd-langfuse conftest cannot locate the conformance harness at "
    f"{_HARNESS_DIR / 'conformance.py'}. Either the parent whatif repo "
    "is missing (out-of-tree consumer?) or the path-resolution depth "
    "(parents[3]) doesn't match this layout. See "
    "`.claude/skills/whatif-features/references/deferred-refactors.md` "
    "entry #1 for the public-promotion path that removes this seam."
)

if (_HARNESS_DIR / "conformance.py").is_file():
    if str(_HARNESS_DIR) not in sys.path:
        sys.path.insert(0, str(_HARNESS_DIR))
else:
    # Skip the package's tests rather than blocking the rest of the
    # suite. Collection-time `pytest.skip(allow_module_level=True)`
    # in the package's test files needs the harness path; here we
    # surface the missing-harness state as a pytest-aware skip via
    # `collect_ignore` so the parent suite proceeds even when this
    # package can't be exercised. CI failures still surface via the
    # printed warning; an out-of-tree consumer with the harness
    # missing gets the same treatment.
    import warnings

    warnings.warn(_HARNESS_MISSING_MESSAGE, RuntimeWarning, stacklevel=2)
    # Belt-and-suspenders: print to stderr too. CI logs swallow
    # PytestUnraisableExceptionWarning by default, but stderr is
    # always visible in the job output. An out-of-tree CI that
    # silently skips this package's tests would otherwise need a
    # contributor to grep `pytest -W error` output to see the gap.
    print(f"[whatifd-langfuse conftest] WARNING: {_HARNESS_MISSING_MESSAGE}", file=sys.stderr)
    collect_ignore = ["test_conformance.py"]
