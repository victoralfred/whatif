"""`whatif.cache` — scorer cache subsystem.

Phase 3 (cache subsystem) per the v0.1 implementation plan. The cache
addresses *reproducibility* — the same trace + same scorer config
produces the same cached judge result, so the verdict's evidence is
stable across runs. Per cardinal #10, scorer caching is NOT a claim
about reliability, validity, or calibration; that distinction is
disclosed in `MethodologyDisclosure.judge_state`.

Sub-packages (filled in across Phase 3 sub-phases):

- `keying.v1` — cache key construction (Phase 3.1)
- `storage.v1` — file layout and metadata (Phase 3.2)
- `lock` — single-writer enforcement (Phase 3.3)
- `policy` — mode resolution from config + environment (Phase 3.4)
- `summary` — `CacheSummary` typed object for `ReportV01` (Phase 3.5)

Versioned packages (`keying.v1`, `storage.v1`) carry the
`CACHE_KEY_VERSION` and `CACHE_SCHEMA_VERSION` constants. PRs touching
these directories MUST bump the version — the cache-version-bump test
asserts this, and a stale version is the cache-poisoning footgun.

The most-used surface (`acquire_cache_lock`, `CacheLock`,
`CacheLockedError`) is re-exported here so callers can write
`from whatif.cache import acquire_cache_lock` instead of reaching
into the submodule. The submodule (`whatif.cache.lock`) remains
the source of truth and is what tooling will rename if the lock
implementation is ever swapped (e.g., for a network-coordinated v0.3
multi-tenant lock).
"""

from whatif.cache.lock import (
    LOCK_FAILURE_CODE,
    CacheLock,
    CacheLockedError,
    acquire_cache_lock,
)

__all__ = (
    "LOCK_FAILURE_CODE",
    "CacheLock",
    "CacheLockedError",
    "acquire_cache_lock",
)
