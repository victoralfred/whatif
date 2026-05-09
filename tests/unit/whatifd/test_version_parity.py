"""Version-parity guard: `__version__` must come from distribution metadata.

Regression test for the `0.0.1` vs `0.1.0rc1` drift caught during the
TestPyPI dry-run (see PR #76). A hardcoded `__version__` literal in
`__init__.py` silently desyncs from the `pyproject.toml` `version` field
because `uv build` reads pyproject but `import whatifd` reads the
literal — and PyPI version slots cannot be republished, so a release
tagged with the drift would ship the wrong `__version__` forever.

The fix is to read the version from `importlib.metadata.version(<dist>)`
at import time. This test pins that approach: when the package is
installed (which it is in any test run that uses `uv sync`),
`pkg.__version__` MUST equal `importlib.metadata.version(<dist-name>)`.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import pytest
import whatifd_inspect_ai
import whatifd_langfuse

import whatifd

# Precondition: the parity gate is only meaningful when the three
# distributions are actually installed. If any are missing,
# `importlib.metadata.version(...)` raises `PackageNotFoundError` and
# the body tests would fail with a confusing error — but a
# misconfigured CI that ran the tests via PYTHONPATH (no install) would
# fail at import-time, before this module loads, hiding the real cause.
# We probe metadata up-front and fail loudly with an explicit message
# so a broken install can't masquerade as a passing version-parity
# gate (and `pytest.importorskip` is deliberately NOT used — skipping
# would let CI go green on a broken install).
for _dist in ("whatifd", "whatifd-langfuse", "whatifd-inspect-ai"):
    try:
        version(_dist)
    except PackageNotFoundError:
        pytest.fail(
            f"{_dist!r} is not installed; the version-parity gate "
            f"requires all three packages to be installed (run "
            f"`uv sync --all-extras --dev --group workspace`).",
            pytrace=False,
        )


def test_whatifd_version_matches_distribution_metadata() -> None:
    assert whatifd.__version__ == version("whatifd")


def test_whatifd_langfuse_version_matches_distribution_metadata() -> None:
    assert whatifd_langfuse.__version__ == version("whatifd-langfuse")


def test_whatifd_inspect_ai_version_matches_distribution_metadata() -> None:
    assert whatifd_inspect_ai.__version__ == version("whatifd-inspect-ai")


def test_no_package_reports_sentinel_when_installed() -> None:
    """`0.0.0+unknown` is the source-only fallback. In an installed
    test environment all three packages MUST report a real version —
    seeing the sentinel here means `importlib.metadata` couldn't find
    the distribution, which is exactly the failure mode this whole
    pattern exists to catch."""
    assert whatifd.__version__ != "0.0.0+unknown"
    assert whatifd_langfuse.__version__ != "0.0.0+unknown"
    assert whatifd_inspect_ai.__version__ != "0.0.0+unknown"
