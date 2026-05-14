"""PII-attribute registry and wrapping helper — cardinal #5 boundary
discipline for adapter metadata fields.

`RawTrace.metadata` is a free-form dict the adapter populates from
its source tracer (Langfuse trace.metadata, OpenInference span
attributes, etc.). The contract has always been "input.value and
output.value are wrapped `Sensitive[str]`; everything else passes
through unwrapped because it's *expected* to be tooling state."

That expectation is a comment, not structural enforcement. In
practice, OpenInference and Langfuse both routinely surface
attributes like `user.id`, `session.id`, `user.email`, and arbitrary
custom keys — content that may be PII even though it's not the
canonical input/output pair. The doctrine bot flagged this gap
repeatedly on PR #86 (whatifd-phoenix). Issue #87 tracks the
project-wide fix.

This module ships the fix:

1. **`PII_ATTRIBUTE_KEYS`** — a frozen registry of known-PII
   attribute names spanning OpenInference, Langfuse, and generic
   conventions. Single source of truth across adapters.

2. **`wrap_pii_attributes(metadata)`** — helper that walks an
   adapter-emitted metadata dict and wraps any value at a known-PII
   key as `Sensitive[str]` with the canonical classification
   `"user_content"`. Adapter authors call this once at the
   projection boundary instead of remembering the rule per key.

3. **Conformance contract** — `tests/adapters/conformance.py`'s
   `TestPIIAttributeWrapping` asserts every emitted `RawTrace` whose
   `metadata` contains a `PII_ATTRIBUTE_KEYS` member has
   `Sensitive[str]` at that key. Adapter implementations that
   forget to call the helper fail the conformance harness on first
   run, not at the serialization boundary downstream.

## Cardinal alignment

- **#5 (sensitive data wrapped, never raw):** the load-bearing
  cardinal. The registry + helper move enforcement from layer (b)
  (graph walk) to layer (a) (type-level + boundary helper). Per
  `references/enforcement.md`'s hierarchy of strength: type-level
  prevention > property test > runtime assertion > convention.
- **#1 (failures-as-data):** `wrap_pii_attributes` raises
  `PIIAttributeTypeError` (typed) if a known-PII key holds a
  non-string non-None value — the adapter cannot silently emit a
  number or list at `user.id`.
- **#6 (public schema hand-written; internal types refactor
  freely):** the registry is hand-curated, not derived from
  external schemas. Adding a new key is a deliberate decision
  recorded in the cascade catalog.

## What's in scope for v0.2

The initial registry covers the conventions surfaced by the two
shipped adapter packages (`whatifd-langfuse`, `whatifd-phoenix`)
plus a small set of cross-vendor common keys. Custom
adapter-specific keys can be added via a future
`register_pii_attribute()` API in v0.3+ — for now the static
frozenset is the canonical surface.

## What's NOT in scope

- `tool_spans` is a separate cardinal-#5 conversation. Tool I/O
  is typed `list[dict[str, Any]]` for parity with
  `whatifd.contract.ReplayOutput.tool_spans`; tightening it
  requires coordinated change to the runner contract, tracked
  separately.
- Adapter-supplied custom-attribute registration. The static
  frozenset is intentional v0.2 scope.
- Per-attribute classification beyond `"user_content"`. The
  `Sensitive` wrapper supports richer classifications (e.g.,
  `"credential"`, `"location"`); the wrapping helper uses
  `"user_content"` uniformly because every key in the registry is
  user-identifying or session-identifying. Future classifications
  can specialize via the registration API.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from whatifd.types.sensitive import Sensitive

__all__ = [
    "PII_ATTRIBUTE_KEYS",
    "PIIAttributeTypeError",
    "wrap_pii_attributes",
]


PII_ATTRIBUTE_KEYS: frozenset[str] = frozenset(
    {
        # OpenInference span-attribute conventions (Phoenix-shipped).
        # Reference: https://github.com/Arize-ai/openinference/blob/main/spec/semantic_conventions.md
        "user.id",
        "user.name",
        "user.email",
        "session.id",
        "session.user",
        # Langfuse trace-metadata conventions. Langfuse SDKs emit
        # `user_id` / `userId` and `session_id` / `sessionId`
        # depending on language and version; the registry covers
        # both spellings so adapters don't need spelling-normalization
        # of their own.
        "user_id",
        "userId",
        "session_id",
        "sessionId",
        # Generic / cross-vendor keys commonly attached to tracer
        # metadata. `email` and `phone` are obvious PII; `ip_address`
        # is a regulatory concern under GDPR (Recital 30) and is
        # routinely PII in practice.
        "email",
        "phone",
        "ip_address",
    }
)
"""Registry of attribute names whose values MUST be wrapped as
`Sensitive[str]` when emitted from an adapter.

The set is conservative: it covers the conventions surfaced by the
two shipped adapter packages (`whatifd-langfuse`,
`whatifd-phoenix`) plus a small cross-vendor common set. Custom
keys can be added in a future v0.3 `register_pii_attribute()`
API; for v0.2 the static frozenset is the canonical surface.
"""


class PIIAttributeTypeError(TypeError):
    """Raised by `wrap_pii_attributes` when a registered PII key
    holds a value that is neither a string nor `None`.

    Cardinal #1 (failures-as-data): the adapter cannot silently emit
    a number, list, or dict at a key the registry declares PII. The
    structural shape of a PII-bearing attribute is a string
    identifier; anything else indicates either an adapter bug or a
    mismatched registry entry, both of which should surface loudly
    rather than degrade to a passthrough.
    """


def wrap_pii_attributes(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Wrap registered PII-attribute values as `Sensitive[str]`.

    Walks `metadata` once. For each key in `PII_ATTRIBUTE_KEYS`:
      * If the value is already a `Sensitive` instance, it passes
        through unchanged (idempotent — calling twice is safe).
      * If the value is a `str`, it is wrapped as
        `Sensitive(value=str_value, classification="user_content")`.
      * If the value is `None`, it passes through as `None` (a
        missing identifier is not PII to wrap).
      * If the value is anything else (int, list, dict, ...),
        `PIIAttributeTypeError` is raised naming the offending key
        and the actual type. This is cardinal #1: the adapter must
        not silently pass through a wrong-shape value at a PII key.

    Keys not in `PII_ATTRIBUTE_KEYS` pass through unchanged. The
    returned dict is a fresh `dict` (input is treated as read-only)
    so adapter callers can pass an immutable mapping in without
    mutation concerns.

    ## Typical adapter usage

    ```python
    from whatifd.adapters.pii import wrap_pii_attributes

    def _project(self, raw) -> RawTrace:
        ...
        return RawTrace(
            ...,
            metadata=wrap_pii_attributes(raw.attributes),
        )
    ```

    The helper is idempotent: passing a metadata dict through
    `wrap_pii_attributes` twice produces the same result as passing
    it through once. This matters for tests and for any pipeline
    stage that re-wraps defensively.
    """
    result: dict[str, Any] = {}
    for key, value in metadata.items():
        if key not in PII_ATTRIBUTE_KEYS:
            result[key] = value
            continue
        if isinstance(value, Sensitive):
            result[key] = value
            continue
        if value is None:
            result[key] = None
            continue
        if isinstance(value, str):
            result[key] = Sensitive(value=value, classification="user_content")
            continue
        raise PIIAttributeTypeError(
            f"metadata key {key!r} is registered as PII "
            f"(`PII_ATTRIBUTE_KEYS`) but the value is "
            f"{type(value).__name__}, not str. PII-bearing attribute "
            "values must be strings (identifiers) so they can be "
            "wrapped as `Sensitive[str]` at the adapter boundary. If "
            "this attribute is structured (e.g., a JSON object), the "
            "adapter must either flatten the identifier out and emit "
            "it under a different key, or extend `PII_ATTRIBUTE_KEYS` "
            "with a specialized classification (v0.3+ API)."
        )
    return result
