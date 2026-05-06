"""Cache storage — v1.

On-disk file layout for the scorer cache. Phase 3.2 of the v0.1
implementation plan; pairs with `whatif/cache/keying/v1.py` (Phase 3.1).

## Layout

```
.whatif/cache/
├── meta.json               (cache_schema_version, cache_key_version, created_at)
├── .lock                   (Phase 3.3 — not written here)
└── entries/
    └── <digest[0:2]>/
        └── <digest>.json   (one entry per cache key)
```

`<digest>` is the 64-char hex portion of the cache key (the part after
the `v1:` prefix from `build_cache_key`). Sharding by the first 2 hex
chars gives 256 directories at saturation, avoiding filesystem-level
slowdowns at scale. The `v1:` prefix is intentionally NOT in the
filename — `:` is invalid on Windows filesystems, and the
`cache_key_version` lives inside the entry JSON anyway.

## Entry shape

Per `references/contracts.md` §"Entry format":

```json
{
  "cache_key_version": "v1",
  "cache_schema_version": "v1",
  "created_at": "2026-04-01T...",
  "key_components": { ... full asdict of CacheKeyComponents ... },
  "result": {
    "score_delta": "0.310",
    "verdict": "improved",
    "rationale": "<redacted-or-stored-per-profile>",
    "confidence": "0.850",
    "flags": []
  }
}
```

`rationale` is stored only when the storage profile is `full_judge_io`
(per `references/contracts.md`); the default profile
(`normalized_result_only`) has `rationale: null`. The profile gating
is the CALLER'S responsibility — this storage layer writes whatever
`CacheEntry` the caller hands it. The cardinal #5 boundary
(no `Sensitive[T]` in entry contents) is enforced by the
`canonical_json_bytes` top-level guard plus the `CacheKeyComponents`
hex-validation invariant from Phase 3.1.

## Versioning

`CACHE_SCHEMA_VERSION = "v1"` is written into `meta.json` at cache
init, and into every entry. PRs that change the on-disk file format
(entry shape, directory layout, `meta.json` schema) MUST introduce a
`v2` module rather than mutate `v1`. Reading an entry whose
`cache_schema_version` does not match this module's
`CACHE_SCHEMA_VERSION` raises `CacheSchemaMismatchError` — a typed
failure that downstream code can convert to a `FailureRecord`. The
cache version-bump test (Phase 3 gate) asserts a diff under
`whatif/cache/storage/v1.py` either bumps the constant or is
rejected.

## What this module does NOT do

- **Locking** — Phase 3.3 (`whatif/cache/lock.py`).
- **Mode resolution** — Phase 3.4 (`whatif/cache/policy.py`).
- **CacheSummary aggregation** — Phase 3.5 (`whatif/cache/summary.py`).
- **Profile gating on `rationale`** — caller's responsibility.

This module is a pure I/O layer over a typed entry shape. Tests run
against `tmp_path`; no shared state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from whatif.cache.keying import CACHE_KEY_VERSION
from whatif.serialization import canonical_json_bytes

CACHE_SCHEMA_VERSION = "v1"

_ENTRIES_DIRNAME = "entries"
_META_FILENAME = "meta.json"


class CacheSchemaMismatchError(Exception):
    """Raised when an on-disk entry's `cache_schema_version` does not
    match this module's `CACHE_SCHEMA_VERSION`.

    Distinct from a missing-file (cache miss) — schema mismatch is a
    structural integrity concern that must surface, not a normal miss.
    Callers convert this to a `FailureRecord` at the appropriate
    scope (per cardinal #1, expected failures are data, not exceptions
    leaving the boundary).
    """


@dataclass(frozen=True, slots=True)
class CacheResult:
    """The judge result stored alongside a cache key.

    `score_delta`, `confidence` are `DecimalString` for cross-platform
    determinism (cardinal #4); `flags` is the list of judge-emitted
    flags as bare strings (no domain typing in v0.1; the judge schema
    treats them opaquely).

    `rationale` is `str | None`. The caller decides whether to populate
    it — `full_judge_io` profile populates; `normalized_result_only`
    sets None. The storage layer does not gate; it writes what it gets.
    """

    score_delta: str
    verdict: str
    confidence: str
    flags: tuple[str, ...] = ()
    rationale: str | None = None


@dataclass(frozen=True, slots=True)
class CacheEntry:
    """One cache entry as written to disk.

    `key_components` is the full `asdict(CacheKeyComponents)` from
    Phase 3.1, stored as a dict for human-readable provenance. The
    cache key (the hash) is what's used for lookup; the components
    are stored so a debugger can reconstruct the inputs without
    re-running the adapter.

    `created_at` is an ISO-8601 UTC timestamp produced at write time.
    Non-deterministic; not part of the cache key.
    """

    cache_key_version: str
    cache_schema_version: str
    created_at: str
    key_components: dict[str, Any]
    result: CacheResult


@dataclass(frozen=True, slots=True)
class CacheMeta:
    """Top-level `meta.json` content. One per cache directory.

    Records the versions the cache directory was initialized with.
    Reading code uses this to decide whether to migrate, refuse, or
    proceed. Cache-version-bump tests assert the entries match the
    meta-recorded versions.

    `extra` is the forward-compatibility escape hatch: any keys present
    in `meta.json` that this module does not recognize are collected
    here on read and re-emitted on write. A future minor that adds a
    new informational field to `meta.json` (e.g., `tenant_id`,
    `last_verified_at`) can land that field as a v1 extension without
    breaking existing v1 caches — older code preserves the new field
    via `extra` round-trip rather than dropping it. Breaking changes
    (new required fields, semantic changes to existing fields) still
    require a `v2` schema bump.
    """

    cache_schema_version: str
    cache_key_version: str
    created_at: str
    extra: dict[str, Any] = field(default_factory=dict)


def init_cache(root: Path) -> CacheMeta:
    """Create the cache directory layout if it doesn't exist; return
    the existing or newly-written `meta.json` content.

    Idempotent: calling `init_cache` on an already-initialized cache
    returns the recorded meta without overwriting it. Calling on a
    cache whose recorded versions do not match this module's constants
    raises `CacheSchemaMismatchError` — schema migration is not
    automatic.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / _ENTRIES_DIRNAME).mkdir(exist_ok=True)
    meta_path = root / _META_FILENAME
    if meta_path.exists():
        meta = read_meta(root)
        if meta.cache_schema_version != CACHE_SCHEMA_VERSION:
            raise CacheSchemaMismatchError(
                f"Cache at {root} was initialized with cache_schema_version="
                f"{meta.cache_schema_version!r}; this module expects "
                f"{CACHE_SCHEMA_VERSION!r}. Migration is not automatic in v0.1; "
                "rebuild the cache via `whatif cache rebuild --force`."
            )
        return meta
    meta = CacheMeta(
        cache_schema_version=CACHE_SCHEMA_VERSION,
        cache_key_version=CACHE_KEY_VERSION,
        created_at=_utc_now_iso(),
    )
    _write_meta(root, meta)
    return meta


def read_meta(root: Path) -> CacheMeta:
    """Read `meta.json` from a cache root.

    Raises `FileNotFoundError` if the cache hasn't been initialized;
    callers should use `init_cache` first if they want idempotent
    behavior.
    """
    meta_path = root / _META_FILENAME
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    known = {"cache_schema_version", "cache_key_version", "created_at"}
    return CacheMeta(
        cache_schema_version=raw["cache_schema_version"],
        cache_key_version=raw["cache_key_version"],
        created_at=raw["created_at"],
        extra={k: v for k, v in raw.items() if k not in known},
    )


def write_entry(root: Path, key: str, entry: CacheEntry) -> Path:
    """Write `entry` to its sharded path under `root` and return the
    written path.

    Overwrites any existing entry at the same key (caller is
    responsible for coordinating concurrent writers via the Phase 3.3
    lock). Uses `canonical_json_bytes` for the on-disk encoding so
    entries written by different platforms compare byte-equal — useful
    for cache integrity verification (`whatif cache verify`).

    The entry's `cache_key_version` and `cache_schema_version` MUST
    match this module's constants; mismatch is an
    `InvariantViolationError` (cardinal #1: a write with the wrong
    versions is a programmer bug, not a runtime data condition).
    """
    if entry.cache_schema_version != CACHE_SCHEMA_VERSION:
        raise CacheSchemaMismatchError(
            f"CacheEntry.cache_schema_version={entry.cache_schema_version!r} "
            f"does not match storage CACHE_SCHEMA_VERSION={CACHE_SCHEMA_VERSION!r}. "
            "Entries written by this module must declare the matching version."
        )
    digest = _digest_from_key(key)
    shard_dir = root / _ENTRIES_DIRNAME / digest[:2]
    shard_dir.mkdir(parents=True, exist_ok=True)
    entry_path = shard_dir / f"{digest}.json"
    entry_path.write_bytes(canonical_json_bytes(_entry_to_dict(entry)))
    return entry_path


def read_entry(root: Path, key: str) -> CacheEntry | None:
    """Read the entry at `key` and return `CacheEntry`, or `None` on
    cache miss (file does not exist).

    Raises `CacheSchemaMismatchError` if the on-disk entry's
    `cache_schema_version` does not match this module's constant —
    schema mismatch is a structural concern that must surface, not a
    silent miss.
    """
    digest = _digest_from_key(key)
    entry_path = root / _ENTRIES_DIRNAME / digest[:2] / f"{digest}.json"
    if not entry_path.exists():
        return None
    raw = json.loads(entry_path.read_text(encoding="utf-8"))
    if raw.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
        raise CacheSchemaMismatchError(
            f"Entry {entry_path} has cache_schema_version="
            f"{raw.get('cache_schema_version')!r}; this module expects "
            f"{CACHE_SCHEMA_VERSION!r}. Migration is not automatic in v0.1."
        )
    result = raw["result"]
    return CacheEntry(
        cache_key_version=raw["cache_key_version"],
        cache_schema_version=raw["cache_schema_version"],
        created_at=raw["created_at"],
        key_components=raw["key_components"],
        result=CacheResult(
            score_delta=result["score_delta"],
            verdict=result["verdict"],
            confidence=result["confidence"],
            flags=tuple(result.get("flags", ())),
            rationale=result.get("rationale"),
        ),
    )


def _digest_from_key(key: str) -> str:
    """Strip the `v1:` prefix and return the 64-char digest.

    Tolerates a bare digest (no prefix) for forward-compat with future
    callers that pre-strip; rejects a key with the wrong version
    prefix (e.g., `v2:` against the v1 storage module).
    """
    if ":" not in key:
        return key
    prefix, digest = key.split(":", 1)
    if prefix != CACHE_KEY_VERSION:
        raise CacheSchemaMismatchError(
            f"Cache key version mismatch: key prefix={prefix!r}; "
            f"this storage module expects {CACHE_KEY_VERSION!r}. "
            "A v2 key cannot be looked up in v1 storage."
        )
    return digest


def _entry_to_dict(entry: CacheEntry) -> dict[str, Any]:
    """Convert a `CacheEntry` to the on-disk dict shape.

    Uses field-by-field copy rather than `asdict()` so the on-disk
    schema is decoupled from the dataclass shape — a future field on
    `CacheEntry` is opt-in into the wire format, not auto-included.
    """
    r = entry.result
    return {
        "cache_key_version": entry.cache_key_version,
        "cache_schema_version": entry.cache_schema_version,
        "created_at": entry.created_at,
        "key_components": entry.key_components,
        "result": {
            "score_delta": r.score_delta,
            "verdict": r.verdict,
            "confidence": r.confidence,
            "flags": list(r.flags),
            "rationale": r.rationale,
        },
    }


def _write_meta(root: Path, meta: CacheMeta) -> None:
    payload = {
        "cache_schema_version": meta.cache_schema_version,
        "cache_key_version": meta.cache_key_version,
        "created_at": meta.created_at,
        **meta.extra,
    }
    (root / _META_FILENAME).write_bytes(canonical_json_bytes(payload))


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp with `Z` suffix.

    Wrapped so tests can monkeypatch this single function rather than
    the broader `datetime.now`. Non-deterministic by construction.
    """
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
