"""whatifd - open experiment runner for LLM behavior changes.

`__version__` is read at import time from the installed
distribution metadata (the `version` field in `pyproject.toml`),
NOT hardcoded here. Single source of truth eliminates the
hardcode-vs-pyproject drift that PR #76 fixed after the
`v0.1.0rc1` TestPyPI dry-run caught it (the distribution
shipped as `0.1.0rc1` but `whatifd.__version__` still
reported `0.0.1`).

The fallback is a sentinel string for editable / source-only
contexts where `importlib.metadata.version("whatifd")` raises
`PackageNotFoundError` (e.g., a `pytest` invocation against a
checkout that hasn't been `pip install`-ed). Returning a sentinel
rather than re-raising keeps `import whatifd` non-fatal in
development setups.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("whatifd")
except PackageNotFoundError:
    # Editable / source-only install pre-`pip install`. Sentinel
    # so `import whatifd` succeeds; consumers reading the version
    # see the placeholder and know they're in a non-installed
    # context.
    __version__ = "0.0.0+unknown"
