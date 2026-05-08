"""Shared constants for `tests/unit/whatifd/decision/` registry tests.

Extracted from individual test files to keep registry-key conventions
in one place. The leading-underscore filename keeps pytest from
collecting this module as a test file.
"""

from __future__ import annotations

import re

# Lowercase snake_case regex for registry keys. All three decision
# registries (failure codes, finding codes, fix suggestions) enforce the
# same key format; this is the single source of truth.
CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
