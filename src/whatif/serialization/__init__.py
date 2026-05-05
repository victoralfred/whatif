"""Serialization layer — Phase 5 in full; some helpers ship earlier.

The full serialization module lands in Phase 5 and includes:
  - `WhatifJSONEncoder` (banned outside this package; cardinal #5)
  - `assert_no_unredacted_sensitive` (graph walk; cardinal #5)
  - `format_decimal_string` (the format half of the determinism budget)
  - `parse_decimal_string` (the parse half — already here)
  - `extract_deterministic_subset` (reads `x-deterministic`; cardinal #4)

`parse_decimal_string` ships ahead of the rest because Phase 2.5+ guards
need it to enforce structural integrity on `CohortResult.median_delta`.
The early delivery is intentional; Phase 5 fills in the surrounding
helpers without disturbing the parse contract.
"""

from whatif.serialization.decimal import FieldLabel, parse_decimal_string

__all__ = ["FieldLabel", "parse_decimal_string"]
