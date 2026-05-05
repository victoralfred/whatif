"""`FloorFailure` and `CohortResult` — per-cohort artifacts.

Cardinal rule #2 doctrine: the trust floor is about evidence existence,
not evidence quality. Below the floor, no verdict can be rendered (the
run is `Inconclusive`); above the floor, evidence exists but its quality
is a policy concern.

`CohortResult` is the per-cohort artifact carrying both the raw counts
(selected/replayed/scored) and the floor evaluation outcome. One of these
is produced per required cohort during `evaluate_floor()` (Phase 2).

`FloorFailure` is the structured record of a single floor-rule violation.
Replaces an earlier prose-only "list of failed rules" with a typed shape
so renderers and downstream consumers don't have to re-parse strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from whatif.types.primitives import DecimalString


@dataclass(frozen=True, slots=True)
class FloorFailure:
    """One trust-floor rule that did not pass for one cohort.

    `severity` is constrained to the two values that make sense for floor
    rules: `blocks_ship` for quality-floor failures, `blocks_all` for
    evidence-existence failures (e.g., zero scored traces). Floor failures
    never produce `info` or `degrades_trust` severity — the floor exists
    precisely to refuse rendering verdicts when these conditions hit.

    `observed` accepts `float | int | str` to handle:
    - integer counts (selected, replayed, scored)
    - decimal-formatted ratios (replay validity ratio as DecimalString)
    - string descriptors when the failure mode isn't numeric
    """

    rule: str
    observed: float | int | str
    threshold: float | int
    severity: Literal["blocks_ship", "blocks_all"]


CIUnavailableReason = Literal[
    "sample_too_small",
    "zero_variance",
    "computation_failed",
]


@dataclass(frozen=True, slots=True)
class CohortResult:
    """Per-cohort stats + floor evaluation outcome.

    The unit of statistical inference per cardinal rule #10 — verdicts
    derive from per-cohort primary endpoints, not per-trace observations.

    `ci_available` indicates whether bootstrap CI was computed for this
    cohort. When False, `ci_unavailable_reason` carries the structured
    reason so the renderer can produce specific text (e.g., "CI not
    computed: sample too small") rather than a generic disclaimer. When
    True, `ci_unavailable_reason` is None.

    Numeric fields in the determinism budget (`median_delta`, `ci_lower`,
    `ci_upper`) are typed `DecimalString` per cardinal rule #4. Float
    arithmetic happens internally; emission via `format(value, '.3f')`
    in `whatif/serialization/decimal.py` (Phase 5) is platform-stable.

    `floor_passed` is True iff `floor_failures` is empty.
    """

    name: str  # "failure", "baseline", or future
    selected: int
    replayed: int
    scored: int

    ci_available: bool
    ci_unavailable_reason: CIUnavailableReason | None

    median_delta: DecimalString | None
    ci_lower: DecimalString | None
    ci_upper: DecimalString | None

    floor_passed: bool
    floor_failures: list[FloorFailure] = field(default_factory=list)
