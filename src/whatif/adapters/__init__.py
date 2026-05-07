"""`whatif.adapters` — adapter protocol surface.

Phase 4A of the v0.1 implementation plan. Adapters bridge `whatif`
core to external trace-source backends (Langfuse) and scorer
backends (Inspect AI). The protocols and result types live here;
concrete adapters live in separate, lazy-loaded packages.

## Phase 4 split (per `references/phases.md`)

- **4A.1 — protocols (this module).** Defines `TraceSource`,
  `Scorer`, and the result types (`RawTrace`, `JudgeResult`,
  `AdapterMetadata`). No implementation.
- **4A.2 — conformance harness.** Parameterized test suite that
  any concrete adapter must pass. Lives in `tests/adapters/`.
- **4A.3 — synthetic stub adapter.** `whatif/adapters/stub.py`.
  Drives Phase 9A integration tests.
- **4B — real adapters.** `whatif-langfuse`, `whatif-inspect-ai`
  as separate packages. Lazy-loaded; never imported by core.

## Why a separate adapter package vs. importing into core

Cardinal-#5 Sensitive[T] discipline lives at the adapter boundary:
external SDKs return raw text, the adapter wraps it in `Sensitive`
before any `whatif` code sees it. Co-locating adapters with core
would invite shortcut imports that bypass the wrap. The lazy-load
test (`python -c "import whatif"` doesn't import any adapter)
enforces the boundary.
"""

from whatif.adapters.protocols import (
    AdapterMetadata,
    JudgeResult,
    RawTrace,
    Scorer,
    TraceSource,
)

__all__ = [
    "AdapterMetadata",
    "JudgeResult",
    "RawTrace",
    "Scorer",
    "TraceSource",
]
