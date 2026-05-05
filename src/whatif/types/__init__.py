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

from whatif.types.cohort import CIUnavailableReason, CohortResult, FloorFailure
from whatif.types.failure import FailureRecord, Scope, Stage
from whatif.types.finding import DecisionFinding, Severity
from whatif.types.manifest import EnvironmentFingerprint, RunManifest
from whatif.types.policy import (
    DecisionPolicy,
    EndpointDirection,
    PrimaryEndpoint,
    ScorerCacheMode,
    ScorerCacheStorageProfile,
    TrustFloor,
)
from whatif.types.primitives import DecimalString, JsonPrimitive
from whatif.types.sensitive import (
    Sensitive,
    SensitiveSerializationError,
    SensitiveUnwrap,
    UnredactedSensitiveError,
)
from whatif.types.statistical import (
    BootstrapMethodDisclosure,
    ClusteringPolicy,
    ClusterKeySupport,
    ClusterSelection,
    EffectSizeDisclosure,
    JudgeMethodDisclosure,
    MethodologyDisclosure,
    MultiplicityDisclosure,
    TraceDelta,
    TraceDeltaReportV01,
)
from whatif.types.verdict import DontShip, Inconclusive, Ship, Verdict

__all__ = [  # noqa: RUF022 — grouped by Phase for readability, not alphabetical
    # 1.1 primitives
    "DecimalString",
    "JsonPrimitive",
    # 1.2 sensitive
    "Sensitive",
    "SensitiveSerializationError",
    "SensitiveUnwrap",
    "UnredactedSensitiveError",
    # 1.3 operational
    "CIUnavailableReason",
    "CohortResult",
    "DecisionFinding",
    "FailureRecord",
    "FloorFailure",
    "Scope",
    "Severity",
    "Stage",
    # 1.4 verdict (FloorPassedProof lives in whatif.decision.floor —
    # closure-capture requires producer + type in the same module)
    "DontShip",
    "Inconclusive",
    "Ship",
    "Verdict",
    # 1.5 policy
    "DecisionPolicy",
    "EndpointDirection",
    "PrimaryEndpoint",
    "ScorerCacheMode",
    "ScorerCacheStorageProfile",
    "TrustFloor",
    # 1.6 manifest (SensitiveUnwrap re-exported from 1.2 sensitive)
    "EnvironmentFingerprint",
    "RunManifest",
    # 1.7 statistical (cardinal #10)
    "BootstrapMethodDisclosure",
    "ClusterKeySupport",
    "ClusterSelection",
    "ClusteringPolicy",
    "EffectSizeDisclosure",
    "JudgeMethodDisclosure",
    "MethodologyDisclosure",
    "MultiplicityDisclosure",
    "TraceDelta",
    "TraceDeltaReportV01",
]
