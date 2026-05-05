#!/usr/bin/env bash
set -euo pipefail

# Helper to run pytest via the project's `uv` helper.
# Usage:
#  ./run_pytest.sh                -> run full test suite
#  ./run_pytest.sh tests/foo.py::test_name  -> run a single test

uv run pytest "$@"
