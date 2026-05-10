"""Regression test for issue #85 — circular import between
`whatifd.serialization` and `whatifd.cache.lock`.

The full test suite passes regardless of the cycle because earlier-
loaded modules preload `whatifd.serialization` before any cache code
runs. A single-test invocation (e.g., the decision tests) imports
`whatifd.decision.floor` first, which imports `whatifd.serialization`,
which used to trigger the chain that re-entered `whatifd.serialization`
mid-init via `cache.lock`.

This test imports `whatifd.serialization` in a **subprocess** so it
runs against a fresh interpreter — no pytest collection has had a
chance to preload anything. If the cycle reappears, this test fails
with the same `ImportError: cannot import name 'parse_lock_file_content'
from partially initialized module 'whatifd.serialization'` that issue
#85 documented.

Subprocess isolation is the only way to honestly assert the no-cycle
property: `sys.modules` is process-wide and any prior import in this
test session would mask the bug.
"""

from __future__ import annotations

import subprocess
import sys


def test_whatifd_serialization_imports_cleanly_in_a_fresh_interpreter() -> None:
    # Order matters: serialization first matches the decision-path
    # reproducer in issue #85's "Surface" section.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import whatifd.serialization; import whatifd.cache.lock; print('OK')",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"circular import reappeared (issue #85). stderr:\n{result.stderr}"
    )
    assert result.stdout.strip() == "OK"


def test_whatifd_reverse_order_imports_cleanly_in_a_fresh_interpreter() -> None:
    # Inverse of the first test: cache.lock before serialization.
    # The cycle could in principle reappear from either direction
    # if a future refactor adds a serialization → cache import at
    # the top level. Pinning both orders means a regression has to
    # break *neither* test, not just the documented reproducer.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import whatifd.cache.lock; import whatifd.serialization; print('OK')",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"reverse-order circular import reappeared (issue #85). stderr:\n{result.stderr}"
    )
    assert result.stdout.strip() == "OK"


def test_whatifd_decision_floor_imports_cleanly_in_a_fresh_interpreter() -> None:
    # The exact reproducer from issue #85: importing the decision
    # surface used to fail because `floor.py` pulls
    # `whatifd.serialization` which used to trigger the cycle.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from whatifd.decision import verdict; print('OK')",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"decision-path circular import reappeared (issue #85). stderr:\n{result.stderr}"
    )
    assert result.stdout.strip() == "OK"
