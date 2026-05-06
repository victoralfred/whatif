"""Cache key construction — v1.

Builds a deterministic cache key for a (scorer-configuration, score-case)
pair. The same components MUST produce the same key on every machine,
every Python interpreter, every run. A drift here is a cache-poisoning
footgun.

## What goes into the key

Per `references/contracts.md` ("The `cache_key_components()` method is
critical for determinism"), the key MUST include:

- whatif report schema version
- whatif scorer adapter version
- scorer type and package version
- judge provider
- judge model identifier
- judge model snapshot/version (if available)
- rendered judge prompt hash (NOT template hash — the actual final string)
- rubric hash
- scoring parameters
- ScoreCase serialization version
- per-case content hash (so two cases with the same scorer config get
  different keys)

## How the key is constructed

1. Serialize `CacheKeyComponents` to canonical JSON: sorted keys, no
   whitespace, ensure_ascii (no platform-dependent encoding).
2. SHA-256 the canonical bytes.
3. Prefix the hex digest with the version literal:
   `v1:<64-char hex digest>`. The prefix lets storage code split keys
   across versions without ambiguity and makes mismatches grep-able.

## Why a hash, not a structured tuple

The key is used as a filename component (storage layout puts entries at
`.whatif/cache/entries/<hash[0:2]>/<hash>.json`). A hash gives
fixed-length, filesystem-safe, low-collision keys regardless of how
long the underlying components grow. SHA-256 is overkill for collision
resistance at v0.1 scale; the property we actually need is determinism
across platforms, which SHA-256 provides via stdlib without binary
deps.

## Versioning

`CACHE_KEY_VERSION = "v1"`. PRs that change the component set, the
canonical-JSON shape, or the hashing algorithm MUST introduce a `v2`
module — never mutate `v1`. The version-bump test asserts that any
diff under `whatif/cache/keying/v1.py` triggers a constant change OR
the diff is rejected (cascade-tracked).

A `v1` key and a `v2` key MUST NOT collide; the version prefix
guarantees this even if the hashes happened to match.

## Banned-import lint scope (Phase 5 reconciliation)

`references/enforcement.md` row 2 documents that the banned-import
lint will block `json.dumps` outside `whatif/serialization/`. The
rule exists to enforce cardinal #5 — no accidental `Sensitive[T]`
serialization on artifact paths. This module's `json.dumps` is NOT an
artifact path:

- The output is a hash input, not bytes that leave the process.
- Every component is pre-hashed by the adapter (`rendered_prompt_hash`,
  `rubric_hash`, etc.); no `Sensitive[T]` ever reaches this code.
- The encoded JSON never escapes the function — `hashlib.sha256()`
  consumes it and emits a hex digest.

When the Phase 5 banned-import lint lands, this file needs either an
explicit allowlist entry OR a `canonical_json_bytes()` helper in
`whatif/serialization/` that this module imports. Cascade entry
"Banned-import lint scope: cache keying canonical JSON" tracks the
v0.1 reconciliation. The decision (allowlist vs. helper) belongs to
the Phase 5 PR that introduces the lint, not Phase 3.1.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

CACHE_KEY_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class CacheKeyComponents:
    """All inputs needed for a deterministic cache key.

    Adapter authors construct one of these per (scorer-config,
    score-case) pair via `Scorer.cache_key_components()`. Every field
    contributes to the hash; reordering fields does NOT change the key
    because canonical JSON sorts keys before serialization.

    Hash fields (`rendered_prompt_hash`, `rubric_hash`,
    `scoring_parameters_hash`, `score_case_hash`) are pre-hashed by the
    adapter so this module never sees raw judge prompts or
    user-content. That keeps the key construction free of any
    `Sensitive[T]` exposure (cardinal #5).

    `judge_model_snapshot` is `str | None` because not every provider
    exposes a snapshot/version pin; absent providers MUST pass None
    explicitly so the field's presence in the key shape is constant.
    """

    whatif_schema_version: str
    whatif_scorer_adapter_version: str
    scorer_type: str
    scorer_package_version: str
    judge_provider: str
    judge_model_id: str
    judge_model_snapshot: str | None
    rendered_prompt_hash: str
    rubric_hash: str
    scoring_parameters_hash: str
    score_case_serialization_version: str
    score_case_hash: str


def build_cache_key(components: CacheKeyComponents) -> str:
    """Return the versioned, content-addressed cache key.

    Output format: `v1:<64-char hex digest>`. The prefix is the active
    `CACHE_KEY_VERSION`; the digest is SHA-256 over canonical JSON of
    the components.

    Determinism: the function is pure. Same components → same key on
    every platform. JSON encoding uses `sort_keys=True`, no whitespace,
    `ensure_ascii=True` so the byte stream is platform-independent.
    """
    canonical = json.dumps(
        asdict(components),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest = hashlib.sha256(canonical.encode("ascii")).hexdigest()
    return f"{CACHE_KEY_VERSION}:{digest}"
