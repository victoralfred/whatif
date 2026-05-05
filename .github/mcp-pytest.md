MCP server: Pytest (suggested configuration)

Purpose: provide a minimal, reproducible command set an MCP server can call to run tests for this Python project.

Commands the MCP server should support:

- Full test suite: ./project/.mcp/run_pytest.sh
- Single test by path: ./project/.mcp/run_pytest.sh tests/path/to/test_file.py::test_name
- Single test by keyword: ./project/.mcp/run_pytest.sh -k "pattern"

Suggested CI matrix (if running across interpreters): python 3.11, 3.12, 3.13. Use the project's `uv` helper to ensure the environment matches dev tooling (`uv sync --all-extras --dev` before running tests).

Notes:
- Prefer recorded-fixture tests for offline runs to avoid network and secret dependencies.
- The helper script delegates to `uv run pytest` so local devs can run tests identically.
