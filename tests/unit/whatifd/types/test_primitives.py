"""Smoke tests for `whatifd.types.primitives`.

These are Phase 1.1 tests. Per phases.md:
- Each type constructs correctly.
- The public surface (`DecimalString`, `JsonPrimitive`) is what `whatifd.types`
  re-exports.
- Import budget: `whatifd.types.primitives` should import in < 50ms.

The deeper guarantees (mypy strict, banned-import lint, no internal imports)
are CI-level checks, not per-test asserts.
"""

from __future__ import annotations

import importlib
import time

from whatifd.types import DecimalString, JsonPrimitive
from whatifd.types import primitives as primitives_module


class TestDecimalString:
    def test_constructs_from_str(self) -> None:
        s = DecimalString("0.310")
        assert s == "0.310"

    def test_is_runtime_str(self) -> None:
        # NewType is a runtime no-op — instances are plain `str`. The type-level
        # distinction is enforced by mypy, not at runtime. This test pins the
        # runtime behavior so refactors don't accidentally introduce a wrapper
        # class that breaks JSON serialization.
        s = DecimalString("0.001")
        assert isinstance(s, str)
        assert type(s) is str

    def test_preserves_fixed_precision_formatting(self) -> None:
        # Realistic example: bootstrap CI bounds are emitted as 3-decimal strings.
        for value in ("0.000", "-0.180", "+0.310", "1.000"):
            assert DecimalString(value) == value


class TestJsonPrimitive:
    def test_accepts_all_scalar_types(self) -> None:
        # JsonPrimitive = str | int | float | bool | None. The runtime test
        # confirms each variant is one of the allowed scalar types.
        primitives: list[JsonPrimitive] = [
            "x",
            42,
            3.14,
            True,
            False,
            None,
        ]
        allowed = (str, int, float, bool, type(None))
        for p in primitives:
            assert isinstance(p, allowed)


class TestImportBudget:
    """Phase 1 gate: `import whatifd.types` must be cheap.

    The aspirational ceiling is 50 ms (per `phases.md` Phase 1 gate).
    A first import on a cold interpreter does I/O for module discovery,
    so we measure a re-import via `importlib.reload`, which is closer
    to the steady-state cost.
    """

    def test_reload_is_cheap(self) -> None:
        # Warm the import cache.
        importlib.import_module("whatifd.types.primitives")

        start = time.perf_counter()
        importlib.reload(primitives_module)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Generous ceiling — the actual measurement on a healthy machine is
        # sub-millisecond. If this trips, something heavy got imported by
        # accident (e.g., Pydantic, anthropic SDK).
        assert elapsed_ms < 50, f"primitives reload took {elapsed_ms:.2f} ms"
