"""`EnvironmentFingerprint` and `RunManifest` — Phase 1.6 audit anchor.

The manifest is the audit anchor — it captures everything needed to
reproduce a run: floor version, policy, environment, redaction state,
sensitive-unwrap log. Every artifact bundle includes a manifest.

Most fields are non-deterministic (timestamps, host info, dependency
versions, sensitive-unwrap ordering). Per cardinal rule #4 (determinism
opt-in per field), the schema explicitly tags deterministic sub-fields
(`trust_floor`, `decision_policy`, `selection_seed`, `config_hash`,
`whatif_version`) with `x-deterministic: true`. Everything else defaults
to `x-deterministic: false`. The CI determinism test diffs only the
tagged subset.

`SensitiveUnwrap` lives in `whatif/types/sensitive.py` (Phase 1.2)
because it's intimately tied to the `Sensitive[T]` wrapper. Manifest
imports it from there.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from whatifd.types.policy import DecisionPolicy, TrustFloor
from whatifd.types.sensitive import SensitiveUnwrap


@dataclass(frozen=True, slots=True)
class EnvironmentFingerprint:
    """Run-time environment description.

    All fields are non-deterministic (vary per host / Python install /
    pip resolution). Captured for audit, not for byte-equality testing.

    `dependencies` is a `Mapping[str, str]` of package name → installed
    version. Includes the project's own optional extras (e.g.,
    `whatifd-langfuse`, `whatifd-inspect-ai`) plus their transitive deps.
    The shape is a Mapping for read-only intent; the default is `dict`
    (the inner mapping is technically mutable in v0.1; Phase 5
    serialization may switch to MappingProxyType for stronger immutability
    if a real bug surfaces).
    """

    python: str
    platform: str
    whatif_version: str
    dependencies: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunManifest:
    """The audit anchor for a single whatif run.

    The whole manifest is non-deterministic by default; the schema
    explicitly tags deterministic sub-fields (`trust_floor`,
    `decision_policy`, `selection_seed`, `config_hash`, `whatif_version`)
    with `x-deterministic: true`. Phase 5 serialization layer wires the
    tags; the determinism CI test diffs only the tagged subset.

    Fields:
    - `experiment_id` — caller-supplied identifier; used in artifact paths.
    - `started_at`, `finished_at` — ISO 8601 timestamps; NON-DETERMINISTIC.
    - `duration_ms` — derived; NON-DETERMINISTIC.
    - `whatif_version` — the version of the whatif package that ran;
      DETERMINISTIC for byte-equality diffs across runs.
    - `config_hash` — sha256 of the resolved config; DETERMINISTIC.
    - `selection_seed` — seeded RNG for trace selection; DETERMINISTIC.
    - `source`, `target` — adapter identifiers (e.g., "langfuse",
      "python:my_agent.replay:run"); DETERMINISTIC.
    - `trust_floor`, `decision_policy` — the structural and policy
      configurations used; DETERMINISTIC.
    - `environment` — host + dependencies; NON-DETERMINISTIC.
    - `agent_identity` — opt-in attribution for the agent under test
      (vendor, model, prompt-template ID). v0.1 optional; v1.0 required
      for a Ship verdict.
    - `redaction` — disclosure of redaction state per cardinal rule #5.
      Schema includes `profile`, `enabled`, and adapter-specific rule-
      version markers.
    - `sensitive_unwraps` — list of `SensitiveUnwrap` audit records
      drained from `whatif/types/sensitive.py:_audit_log` at end of run.
      NON-DETERMINISTIC ordering (depends on call order across threads).
    """

    experiment_id: str
    started_at: str
    finished_at: str
    duration_ms: int
    whatif_version: str
    config_hash: str
    selection_seed: int
    source: str
    target: str
    trust_floor: TrustFloor
    decision_policy: DecisionPolicy
    environment: EnvironmentFingerprint
    agent_identity: Mapping[str, str] | None = None
    redaction: Mapping[str, str | bool] = field(default_factory=dict)
    sensitive_unwraps: list[SensitiveUnwrap] = field(default_factory=list)
