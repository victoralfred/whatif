"""`ReportV01` — the v0.1 public report schema.

Hand-written per cardinal #6: public schema is hand-written; internal
types refactor freely. This module is the wire-format contract for
the `whatif fork` output. The shape committed here is what
`schemas/report/v0.1.schema.json` will derive from in a later sub-
phase, and what consumer tooling (dashboards, alerting, schema-
validation in third-party tools) will read.

## What lives here vs. `whatif/types/`

`whatif/types/` carries INTERNAL types — the concrete dataclasses the
decision pipeline operates on (Verdict sealed union, FloorPassedProof
witness token, internal Sensitive[T] wrappers, etc.). These can change
between minor versions; the only consumers are in-tree.

`whatif/report/models_v01.py` (this module) carries PUBLIC types —
the wire shape consumed by external tooling. These cannot change
without a schema-version bump (`v0.1` → `v0.2`). Per
`references/contracts.md` §"Schema versioning":

- Adding a NEW field with a default → patch (`0.1.0` → `0.1.1`).
- Renaming/removing a field, tightening a type, changing semantics
  of an existing field → minor (`0.1` → `0.2`) with a
  `whatif report-migrate` migration stub.
- Removing a verdict state, breaking the schema-validation contract
  → major (`v0.1` → `v1.0`).

The `projection.py` module (later sub-phase) translates internal
types → ReportV01 for serialization. Internal Verdict (sealed union)
becomes wire `verdict_state: Literal[...]` plus flattened
`cohort_results` / `decision_findings` siblings — the wire format
favors flat schema-friendly shapes over algebraic types.

## Cardinal alignment

- **#1 (failures-as-data):** `failures: list[FailureRecord]` is a
  required field; an empty list is valid (clean run), `None` is not.
  Schema validation enforces presence.
- **#2 (floor cannot be bypassed):** `verdict_state` is a closed
  literal; a `Ship` value cannot be constructed in `projection.py`
  without a `FloorPassedProof` (the witness token is consumed by the
  internal `Verdict` type before projection runs).
- **#4 (determinism opt-in):** the schema generation step (later
  sub-phase) annotates each field with `x-deterministic: true|false`.
  `runtime` is annotated `false`; everything else defaults to `true`.
- **#5 (sensitive data wrapped):** `ReportV01` itself never holds
  `Sensitive[T]` — by the time projection runs, all sensitive content
  has been redacted by the artifact-bundle profile (Phase 8) or
  unwrapped via audited `.unwrap(reason=...)` calls. The pre-
  serialization graph walk (`assert_no_unredacted_sensitive`, later
  sub-phase) is the structural defense.
- **#6 (public schema hand-written):** every field below is
  hand-written. No `dict[str, Any]` crosses this boundary; nested
  shapes are typed dataclasses.
- **#10 (statistical claims match design):** `methodology:
  MethodologyDisclosure` is a REQUIRED field. The renderer-test in
  Phase 7 asserts the methodology block appears in every full-form
  rendered report.

## Schema constants

`REPORT_SCHEMA_VERSION = "0.1"` and `REPORT_SCHEMA_URI =
"https://whatif.codes/schema/report/v0.1.json"` are stamped into
every `ReportV01` instance. Bumping these requires:

1. Migrating in-tree consumer code (renderer, projection).
2. Authoring a `whatif report-migrate` stub for v0.1 → v0.2.
3. Republishing the schema URI.
4. Updating `references/contracts.md` § "Schema versioning" with the
   change record.

The constants are deliberately exported at the package level so
projection code references them without re-deriving.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from whatif.cache.summary import CacheSummary
from whatif.types.cohort import CohortResult
from whatif.types.failure import FailureRecord
from whatif.types.finding import DecisionFinding
from whatif.types.manifest import RunManifest
from whatif.types.policy import DecisionPolicy, TrustFloor
from whatif.types.statistical import MethodologyDisclosure

REPORT_SCHEMA_VERSION = "0.1"
REPORT_SCHEMA_URI = "https://whatif.codes/schema/report/v0.1.json"

VerdictState = Literal["ship", "dont_ship", "inconclusive"]
"""Wire-format verdict literal. The internal `Verdict` sealed union
(`Ship | DontShip | Inconclusive`) projects to one of these three
strings; the witness-token machinery (cardinal #2) operates on the
internal union, not on the wire format. JSON schema can express
literal strings but not Python sealed unions, so the wire shape
flattens.

## Cardinal #2 contract for projection.py implementers

When `whatif/report/projection.py` lands (Phase 5.2), the
`project_to_report_v01(...)` function MUST take an internal `Verdict`
(union of `Ship | DontShip | Inconclusive`) as input — not a bare
`VerdictState` string and not the components of a Ship. The reason is
structural: the only way to get a `Ship` instance is to have called
`evaluate_floor()` and consumed its `FloorPassedProof` token. By
making projection accept `Verdict` rather than `verdict_state: str`,
the caller is forced through that witness-token path. A `Verdict`
input → `verdict_state="ship"` output mapping is then trivially
sound. Any other shape (e.g., `project_to_report_v01(verdict_state:
str, ...)`) re-opens the cardinal #2 bypass that the witness pattern
exists to close.
"""

# Type-level pins for schema_version / schema_uri: callers cannot
# construct a `ReportV01` with a stale or wrong version. mypy strict
# catches assignments of any other string literal at type-check time;
# the schema-validation pass at read time catches the rare runtime
# `cast(...)` bypass. v0.2 will introduce a `ReportV02` module with
# its own constants; a future `whatif report-migrate` consumes the
# wire JSON without instantiating the typed dataclass, so this pin
# does not block migration paths.
_SchemaVersion = Literal["0.1"]
_SchemaUri = Literal["https://whatif.codes/schema/report/v0.1.json"]


@dataclass(frozen=True, slots=True)
class ReportV01:
    """The v0.1 wire-format report.

    Field ordering follows `references/type-model.md` for stability
    across renderers. Every field is required: there is no
    `Optional[...]` hiding unset state behind `None`. A clean run
    populates `failures=[]` and `decision_findings=[]` rather than
    omitting them.

    Sub-shape sources (all internal types — projection.py reuses them
    directly because their dataclass shapes happen to be wire-stable
    AND because cardinal #6 governs the WHATIF-emitted schema, not
    the universe of types it composes from):

    - `cohort_results: list[CohortResult]` — `whatif.types.cohort`.
    - `failures: list[FailureRecord]` — `whatif.types.failure`.
    - `decision_findings: list[DecisionFinding]` — `whatif.types.finding`.
    - `cache_summary: CacheSummary` — `whatif.cache.summary` (Phase 3.5).
    - `trust_floor: TrustFloor` — `whatif.types.policy`.
    - `decision_policy: DecisionPolicy` — `whatif.types.policy`.
    - `methodology: MethodologyDisclosure` — `whatif.types.statistical`.
    - `runtime: RunManifest` — `whatif.types.manifest`. Annotated
      `x-deterministic: false` at schema-gen time.

    Determinism subset (cardinal #4): all fields except `runtime`
    are part of the determinism budget. Two runs with identical
    inputs produce byte-identical JSON for the deterministic subset.
    """

    schema_version: _SchemaVersion
    schema_uri: _SchemaUri

    verdict_state: VerdictState

    cohort_results: list[CohortResult]
    failures: list[FailureRecord]
    decision_findings: list[DecisionFinding]

    cache_summary: CacheSummary
    trust_floor: TrustFloor
    decision_policy: DecisionPolicy
    methodology: MethodologyDisclosure

    runtime: RunManifest
