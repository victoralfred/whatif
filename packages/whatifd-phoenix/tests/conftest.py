"""Make the parent repo's adapter conformance harness importable.

Mirrors `packages/whatifd-langfuse/tests/conftest.py`; the conformance
harness lives at `<repo>/tests/adapters/conformance.py`. If the
harness is ever promoted to `whatifd.testing`, drop both conftests
and switch imports to the public surface in the same PR.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_HARNESS_DIR = _REPO_ROOT / "tests" / "adapters"

_HARNESS_MISSING_MESSAGE = (
    "whatifd-phoenix conftest cannot locate the conformance harness at "
    f"{_HARNESS_DIR / 'conformance.py'}. Either the parent whatifd repo "
    "is missing (out-of-tree consumer?) or the path-resolution depth "
    "(parents[3]) doesn't match this layout."
)

if (_HARNESS_DIR / "conformance.py").is_file():
    if str(_HARNESS_DIR) not in sys.path:
        sys.path.insert(0, str(_HARNESS_DIR))
else:
    import warnings

    warnings.warn(_HARNESS_MISSING_MESSAGE, RuntimeWarning, stacklevel=2)
    print(f"[whatifd-phoenix conftest] WARNING: {_HARNESS_MISSING_MESSAGE}", file=sys.stderr)
    collect_ignore = ["test_conformance.py"]
