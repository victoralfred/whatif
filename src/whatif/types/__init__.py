"""Internal types for whatif.

Public types live in `whatif/contract/` (runner-contract boundary) and
`whatif/report/models_v01.py` (public report shape; lands in Phase 5).

This package holds the frozen-dataclass internal types. Per cardinal
rule #6 (public schema hand-written), nothing here is part of the
public API; internal types refactor freely behind the projection layer.

Phase 1 ordering (per `.claude/skills/whatif-design/phases.md`):
  1.1 primitives    — DecimalString, JsonPrimitive (this file's siblings)
  1.2 sensitive     — Sensitive[T] wrapper (cardinal #5)
  1.3 operational   — FailureRecord, DecisionFinding, CohortResult
  1.4 verdict       — Ship/DontShip/Inconclusive + FloorPassedProof witness
  1.5 policy        — TrustFloor (versioned), DecisionPolicy
  1.6 manifest      — RunManifest, EnvironmentFingerprint, SensitiveUnwrap
  1.7 statistical   — TraceDelta, MethodologyDisclosure (cardinal #10)
"""

from whatif.types.primitives import DecimalString, JsonPrimitive

__all__ = [
    "DecimalString",
    "JsonPrimitive",
]
