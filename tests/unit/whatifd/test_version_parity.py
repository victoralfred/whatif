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

It additionally pins **cross-package version parity** — all three
distributions in the workspace release together (see `release.yml`),
so a sub-package whose `pyproject.toml` `version` drifts out of lockstep
is a release-correctness bug that this gate catches at PR time.
"""

from __future__ import annotations

from collections.abc import Generator
from importlib.metadata import PackageNotFoundError, version

import pytest
import whatifd_inspect_ai
import whatifd_langfuse

import whatifd

_DISTRIBUTIONS = ("whatifd", "whatifd-langfuse", "whatifd-inspect-ai")


@pytest.fixture(autouse=True, scope="module")
def _require_distributions_installed() -> Generator[None, None, None]:
    """Precondition gate: the parity tests are only meaningful when the
    three distributions are actually installed. A misconfigured CI that
    runs the suite via raw PYTHONPATH (no install) would otherwise show
    the metadata tests as confusing failures with no obvious root
    cause. This fixture probes `importlib.metadata` once per module and
    fails the whole module with an actionable message if any package is
    missing.

    Module-scope autouse rather than a `conftest.py` so the guard is
    co-located with the tests it protects — `conftest.py` would broaden
    the precondition to every test under this directory, which isn't
    the intent. `pytest.importorskip` is deliberately NOT used; skipping
    would let CI go green on a broken install.

    Control flow: the precondition runs BEFORE `yield`. On failure,
    `pytest.fail(...)` raises and the fixture never yields — pytest
    handles that as a setup error and skips teardown, which is exactly
    what we want (no setup happened, nothing to tear down). On success
    the unconditional `yield` runs and there's no teardown body, so
    the fixture is clean either way."""
    missing = []
    for dist in _DISTRIBUTIONS:
        try:
            version(dist)
        except PackageNotFoundError:
            missing.append(dist)
    if missing:
        pytest.fail(
            f"version-parity gate requires all three packages installed; "
            f"missing: {missing!r}. Run "
            f"`uv sync --all-extras --dev --group workspace`.",
            pytrace=False,
        )
    yield


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


def test_all_workspace_packages_share_the_same_version() -> None:
    """Cross-package parity: the three workspace distributions release
    together via `.github/workflows/release.yml` on a single `v*.*.*`
    tag push, and the adapters declare `whatifd>=<version>` lower
    bounds that match their own version. A sub-package whose
    `pyproject.toml` `version` field drifts out of lockstep with the
    others is a release-correctness bug — the tag would ship three
    distributions that disagree about which release they belong to.
    Pin equality here so any future bump that touches one
    `pyproject.toml` but forgets the other two fails CI before merge."""
    versions = {
        "whatifd": whatifd.__version__,
        "whatifd-langfuse": whatifd_langfuse.__version__,
        "whatifd-inspect-ai": whatifd_inspect_ai.__version__,
    }
    distinct = set(versions.values())
    assert len(distinct) == 1, (
        f"workspace packages disagree on version: {versions!r}. "
        f"All three pyproject.toml `version` fields must be bumped "
        f"in lockstep — see RELEASING.md."
    )
