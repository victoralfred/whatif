"""DecimalString parse helper — early-shipped subset of Phase 5 serialization.

Phase 5 will land both halves of the determinism boundary:
  - `format_decimal_string(value: float) -> DecimalString` (Phase 5)
  - `parse_decimal_string(value: DecimalString, *, field: str) -> float` (here)

The parse half ships in Phase 2.5 because guards and the verdict layer
need to validate structural integrity on `DecimalString` fields before
the format half is needed (format is for emission; parse is for
ingestion of already-stored deterministic values).

Per cardinal #1, a `DecimalString` that doesn't parse is an upstream
contract violation, not a runtime data condition. The helper raises
`InvariantViolationError` (typed; not stdlib `ValueError`) so call-site
intent is legible.

The current implementation accepts anything `float()` parses, including
scientific notation and bare integers. Phase 5 will tighten this to
match the canonical fixed-precision shape emitted by
`format_decimal_string`. See cascade-catalog "`parse_decimal_string`
permissiveness — tighten at Phase 5" for the deferral rationale and
the test changes that flip when it lands.
"""

from __future__ import annotations

from whatif.exceptions import InvariantViolationError
from whatif.types.primitives import DecimalString


def parse_decimal_string(value: DecimalString, *, field: str) -> float:
    """Parse a `DecimalString` to `float`; raise `InvariantViolationError`
    if the string cannot be parsed.

    `field` is a caller-provided label (e.g., `"CohortResult.median_delta"`,
    `"trace_delta on cohort='failure'"`) that appears in the error
    message for diagnostic clarity. It does NOT affect parse logic — it's
    metadata only.

    Returns: the parsed float value.

    Raises: `InvariantViolationError` if `value` is not parseable as a
    decimal. The underlying `ValueError` is chained via `__cause__`.
    """
    try:
        return float(value)
    except ValueError as e:
        raise InvariantViolationError(
            f"DecimalString must be parseable as a number; got {value!r} (field={field!r})"
        ) from e
