"""Tests for `whatifd.cache.storage.v1` — Phase 3.2 cache storage.

Coverage axes:

1. **Init idempotence** — `init_cache` on an existing cache returns
   the recorded meta without overwriting; on a mismatched version,
   raises.
2. **Round-trip integrity** — write_entry → read_entry returns the
   same `CacheEntry` value.
3. **Sharding** — entries land at `entries/<digest[0:2]>/<digest>.json`.
4. **Cache miss** — read_entry returns None for missing keys.
5. **Schema mismatch** — both write and read paths refuse mismatched
   `cache_schema_version`.
6. **Key version mismatch** — looking up a `v2:` key against v1
   storage raises.
7. **Canonical encoding** — entries on disk are byte-identical for
   identical inputs (cache verify will diff bytes).

Tests use `tmp_path` so no shared state. The non-deterministic
`created_at` is monkeypatched where determinism matters.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from whatifd.cache.keying import CACHE_KEY_VERSION, CacheKeyComponents, build_cache_key
from whatifd.cache.storage import (
    CACHE_SCHEMA_VERSION,
    CacheEntry,
    CacheMeta,
    CacheResult,
    CacheSchemaMismatchError,
    init_cache,
    read_entry,
    read_meta,
    write_entry,
)
from whatifd.exceptions import InvariantViolationError
from whatifd.serialization import canonical_json_bytes

# Tests use `canonical_json_bytes` rather than `json.dumps` directly to
# match the production write path AND to stay forward-compatible with
# the Phase 5 banned-import lint (`references/enforcement.md` row 2).
# `json.loads` is not banned (it's an input-side concern, not the
# cardinal #5 artifact-write boundary the lint enforces).


def _components() -> CacheKeyComponents:
    return CacheKeyComponents(
        whatif_schema_version="0.1",
        whatif_scorer_adapter_version="0.1.0",
        scorer_type="inspect_ai.Faithfulness",
        scorer_package_version="0.3.5",
        judge_provider="anthropic",
        judge_model_id="claude-sonnet-4-6",
        judge_model_snapshot="20251001",
        rendered_prompt_hash="aa" * 32,
        rubric_hash="bb" * 32,
        scoring_parameters_hash="cc" * 32,
        score_case_serialization_version="v1",
        score_case_hash="dd" * 32,
    )


def _entry(components: CacheKeyComponents | None = None) -> CacheEntry:
    components = components or _components()
    return CacheEntry(
        cache_key_version=CACHE_KEY_VERSION,
        cache_schema_version=CACHE_SCHEMA_VERSION,
        created_at="2026-05-05T12:00:00Z",
        key_components=components,
        result=CacheResult(
            score_delta="0.310",
            verdict="improved",
            confidence="0.850",
            flags=(),
            rationale=None,
        ),
    )


class TestInitCache:
    def test_creates_layout_when_absent(self, tmp_path: Path) -> None:
        meta = init_cache(tmp_path)
        assert meta.cache_schema_version == CACHE_SCHEMA_VERSION
        assert meta.cache_key_version == CACHE_KEY_VERSION
        assert (tmp_path / "meta.json").exists()
        assert (tmp_path / "entries").is_dir()

    def test_idempotent_on_existing_cache(self, tmp_path: Path) -> None:
        first = init_cache(tmp_path)
        second = init_cache(tmp_path)
        # Same meta returned (created_at not overwritten).
        assert first.created_at == second.created_at

    def test_raises_on_schema_version_mismatch(self, tmp_path: Path) -> None:
        # Manually write a meta.json with a mismatched version.
        (tmp_path / "entries").mkdir()
        (tmp_path / "meta.json").write_bytes(
            canonical_json_bytes(
                {
                    "cache_schema_version": "v0",
                    "cache_key_version": "v1",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            )
        )
        with pytest.raises(CacheSchemaMismatchError, match="v0"):
            init_cache(tmp_path)


class TestWriteRead:
    def test_round_trip(self, tmp_path: Path) -> None:
        init_cache(tmp_path)
        components = _components()
        key = build_cache_key(components)
        entry = _entry(components)
        write_entry(tmp_path, key, entry)
        readback = read_entry(tmp_path, key)
        assert readback == entry

    def test_round_trip_with_rationale(self, tmp_path: Path) -> None:
        # full_judge_io profile populates rationale; storage layer
        # writes whatever the caller hands it.
        init_cache(tmp_path)
        components = _components()
        key = build_cache_key(components)
        entry = CacheEntry(
            cache_key_version=CACHE_KEY_VERSION,
            cache_schema_version=CACHE_SCHEMA_VERSION,
            created_at="2026-05-05T12:00:00Z",
            key_components=components,
            result=CacheResult(
                score_delta="0.500",
                verdict="improved",
                confidence="0.900",
                flags=("flag_a", "flag_b"),
                rationale="The model showed clear improvement on factual claims.",
            ),
        )
        write_entry(tmp_path, key, entry)
        readback = read_entry(tmp_path, key)
        assert readback is not None
        assert readback.result.rationale == entry.result.rationale
        assert readback.result.flags == ("flag_a", "flag_b")

    def test_cache_miss_returns_none(self, tmp_path: Path) -> None:
        init_cache(tmp_path)
        # Build a key that hasn't been written.
        key = build_cache_key(_components())
        assert read_entry(tmp_path, key) is None

    def test_cache_miss_with_existing_shard_dir(self, tmp_path: Path) -> None:
        # Partial filesystem state: the shard directory exists (from a
        # previously-written entry that shares the first 2 hex chars)
        # but the specific .json file is absent. Pin: read_entry must
        # return None on file absence regardless of whether the parent
        # directory exists. A naive `if not parent.exists(): return None`
        # implementation would fail this test.
        init_cache(tmp_path)
        components = _components()
        key = build_cache_key(components)
        write_entry(tmp_path, key, _entry(components))
        # Delete the JSON file but leave the shard directory.
        digest = key.split(":", 1)[1]
        entry_path = tmp_path / "entries" / digest[:2] / f"{digest}.json"
        entry_path.unlink()
        assert entry_path.parent.is_dir()  # shard dir still there
        assert read_entry(tmp_path, key) is None

    def test_overwrite_existing_entry(self, tmp_path: Path) -> None:
        # Write twice with different results at the same key.
        init_cache(tmp_path)
        components = _components()
        key = build_cache_key(components)
        first = _entry(components)
        write_entry(tmp_path, key, first)
        second = CacheEntry(
            cache_key_version=CACHE_KEY_VERSION,
            cache_schema_version=CACHE_SCHEMA_VERSION,
            created_at=first.created_at,
            key_components=components,
            result=CacheResult(
                score_delta="0.999",
                verdict="improved",
                confidence="1.000",
            ),
        )
        write_entry(tmp_path, key, second)
        readback = read_entry(tmp_path, key)
        assert readback == second


class TestSharding:
    def test_entry_lands_in_two_char_shard(self, tmp_path: Path) -> None:
        init_cache(tmp_path)
        components = _components()
        key = build_cache_key(components)
        # Key is "v1:<digest>"; shard is digest[0:2].
        digest = key.split(":", 1)[1]
        shard = digest[:2]
        path = write_entry(tmp_path, key, _entry(components))
        # Path: <root>/entries/<shard>/<digest>.json
        assert path.parent.name == shard
        assert path.parent.parent.name == "entries"
        assert path.name == f"{digest}.json"

    def test_filename_excludes_version_prefix(self, tmp_path: Path) -> None:
        # The `v1:` prefix MUST NOT be in the filename — `:` is
        # invalid on Windows. The version lives in entry JSON +
        # meta.json, not in the path.
        init_cache(tmp_path)
        components = _components()
        key = build_cache_key(components)
        path = write_entry(tmp_path, key, _entry(components))
        assert ":" not in path.name


class TestVersionMismatch:
    """Cardinal #1 split: programmer-bug paths raise
    `InvariantViolationError`; data-condition paths (the disk surprised
    us) raise `CacheSchemaMismatchError`. Catch sites read the type
    to know whether to fail-fast (bug) or wrap-as-FailureRecord (data).
    """

    # ----- Programmer-bug paths (InvariantViolationError) -----

    def test_write_rejects_mismatched_entry_version_as_bug(self, tmp_path: Path) -> None:
        # Caller constructed an entry with the wrong declared version
        # and handed it to write_entry. Programmer bug — they should
        # have constructed it with CACHE_SCHEMA_VERSION.
        init_cache(tmp_path)
        bad = CacheEntry(
            cache_key_version=CACHE_KEY_VERSION,
            cache_schema_version="v0",
            created_at="2026-05-05T12:00:00Z",
            key_components=_components(),
            result=CacheResult(score_delta="0.0", verdict="unchanged", confidence="0.5"),
        )
        with pytest.raises(InvariantViolationError, match="v0"):
            write_entry(tmp_path, build_cache_key(_components()), bad)

    def test_lookup_rejects_v2_key_as_bug(self, tmp_path: Path) -> None:
        # Caller passed a key with the wrong version prefix. Programmer
        # bug — they should have built the key with this version's
        # build_cache_key.
        init_cache(tmp_path)
        with pytest.raises(InvariantViolationError, match="v2"):
            read_entry(tmp_path, "v2:" + "a" * 64)

    def test_lookup_rejects_bare_digest_as_bug(self, tmp_path: Path) -> None:
        # No version prefix on the key. The bare-digest path was
        # speculative forward-compat in an earlier revision; removed
        # because it bypassed version validation. Caller MUST go
        # through build_cache_key.
        init_cache(tmp_path)
        with pytest.raises(InvariantViolationError, match="no `<version>:` prefix"):
            read_entry(tmp_path, "a" * 64)

    def test_lookup_rejects_empty_digest_as_bug(self, tmp_path: Path) -> None:
        # `v1:` (correct prefix, empty digest) would otherwise produce
        # a path of `entries//.json` — meaningless filesystem state.
        # Pin: digest length+shape is validated.
        init_cache(tmp_path)
        with pytest.raises(InvariantViolationError, match="64 lowercase hex chars"):
            read_entry(tmp_path, "v1:")

    def test_lookup_rejects_short_digest_as_bug(self, tmp_path: Path) -> None:
        # Truncated digest: correct prefix but not 64 chars.
        init_cache(tmp_path)
        with pytest.raises(InvariantViolationError, match="64 lowercase hex chars"):
            read_entry(tmp_path, "v1:" + "a" * 32)

    def test_lookup_rejects_uppercase_hex_as_bug(self, tmp_path: Path) -> None:
        # Uppercase hex: case sensitivity matters; canonical form is
        # lowercase per Phase 3.1's hashlib hexdigest output.
        init_cache(tmp_path)
        with pytest.raises(InvariantViolationError, match="64 lowercase hex chars"):
            read_entry(tmp_path, "v1:" + "A" * 64)

    # ----- Data-condition paths (CacheSchemaMismatchError) -----

    def test_read_rejects_mismatched_on_disk_version_as_data(self, tmp_path: Path) -> None:
        # The disk says v0 but this module is v1. Caller did everything
        # right; the disk surprised us. Convert to FailureRecord.
        init_cache(tmp_path)
        components = _components()
        key = build_cache_key(components)
        path = write_entry(tmp_path, key, _entry(components))
        raw = json.loads(path.read_text())
        raw["cache_schema_version"] = "v0"
        path.write_bytes(canonical_json_bytes(raw))
        with pytest.raises(CacheSchemaMismatchError, match="v0"):
            read_entry(tmp_path, key)

    def test_read_rejects_unexpected_key_components_field_as_data(self, tmp_path: Path) -> None:
        # On-disk entry has an unexpected key in key_components (e.g.,
        # a v2 keying schema field accidentally written into a v1
        # entry). Surfaces as CacheSchemaMismatchError, not raw
        # TypeError from the kwargs splat. Cardinal #1 split: the disk
        # surprised us → data condition → wrappable as FailureRecord.
        init_cache(tmp_path)
        components = _components()
        key = build_cache_key(components)
        path = write_entry(tmp_path, key, _entry(components))
        raw = json.loads(path.read_text())
        raw["key_components"]["unexpected_v2_field"] = "value"
        path.write_bytes(canonical_json_bytes(raw))
        with pytest.raises(
            CacheSchemaMismatchError, match="shape this storage module cannot reconstruct"
        ):
            read_entry(tmp_path, key)

    def test_read_rejects_missing_key_components_field_as_data(self, tmp_path: Path) -> None:
        # On-disk entry is missing a required key_components field.
        # Same classification as the unexpected-field case.
        init_cache(tmp_path)
        components = _components()
        key = build_cache_key(components)
        path = write_entry(tmp_path, key, _entry(components))
        raw = json.loads(path.read_text())
        del raw["key_components"]["rubric_hash"]
        path.write_bytes(canonical_json_bytes(raw))
        with pytest.raises(
            CacheSchemaMismatchError, match="shape this storage module cannot reconstruct"
        ):
            read_entry(tmp_path, key)

    def test_init_cache_rejects_mismatched_meta_as_data(self, tmp_path: Path) -> None:
        # Same as the existing init test, made explicit about
        # data-condition classification.
        (tmp_path / "entries").mkdir()
        (tmp_path / "meta.json").write_bytes(
            canonical_json_bytes(
                {
                    "cache_schema_version": "v0",
                    "cache_key_version": "v1",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            )
        )
        with pytest.raises(CacheSchemaMismatchError, match="v0"):
            init_cache(tmp_path)


class TestExtraOverlapRejected:
    """`_write_meta` refuses to write a `CacheMeta` whose `extra` would
    shadow a known top-level key. Defends against corrupted on-disk
    meta or a buggy caller that smuggled a version field through extra.
    """

    def test_write_meta_refuses_overlap(self, tmp_path: Path) -> None:
        from whatifd.cache.storage.v1 import _write_meta

        init_cache(tmp_path)
        bad = CacheMeta(
            cache_schema_version=CACHE_SCHEMA_VERSION,
            cache_key_version=CACHE_KEY_VERSION,
            created_at="2026-05-05T12:00:00Z",
            extra={"cache_schema_version": "v0"},  # smuggled override
        )
        with pytest.raises(InvariantViolationError, match="reserved top-level key"):
            _write_meta(tmp_path, bad)


class TestCanonicalOnDisk:
    def test_byte_identical_for_same_input(self, tmp_path: Path, monkeypatch) -> None:
        # Two writes of the same entry to two separate caches must
        # produce byte-identical files (`whatifd cache verify` will
        # diff bytes for integrity).
        monkeypatch.setattr(
            "whatifd.cache.storage.v1._utc_now_iso",
            lambda: "2026-05-05T12:00:00Z",
        )
        a = tmp_path / "a"
        b = tmp_path / "b"
        init_cache(a)
        init_cache(b)
        components = _components()
        key = build_cache_key(components)
        entry = _entry(components)
        path_a = write_entry(a, key, entry)
        path_b = write_entry(b, key, entry)
        assert path_a.read_bytes() == path_b.read_bytes()


class TestMeta:
    def test_meta_roundtrip(self, tmp_path: Path) -> None:
        init_cache(tmp_path)
        meta = read_meta(tmp_path)
        assert meta.cache_schema_version == CACHE_SCHEMA_VERSION
        assert meta.cache_key_version == CACHE_KEY_VERSION
        # created_at is non-deterministic but well-formed ISO-8601.
        assert meta.created_at.endswith("Z")
        assert "T" in meta.created_at

    def test_read_meta_uninitialized_root_raises(self, tmp_path: Path) -> None:
        # read_meta is the low-level reader; it does NOT call init_cache.
        # Pinning FileNotFoundError per the docstring's contract:
        # callers wanting idempotence use init_cache; callers wanting
        # to fail loud on a missing cache use read_meta directly.
        with pytest.raises(FileNotFoundError):
            read_meta(tmp_path)

    def test_meta_byte_identical_under_same_timestamp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Companion to test_byte_identical_for_same_input: verifies
        # meta.json itself is byte-stable when the timestamp is fixed.
        # Foundation for `whatifd cache verify` byte-diffing meta as a
        # cross-cache integrity check.
        monkeypatch.setattr(
            "whatifd.cache.storage.v1._utc_now_iso",
            lambda: "2026-05-05T12:00:00Z",
        )
        a = tmp_path / "a"
        b = tmp_path / "b"
        init_cache(a)
        init_cache(b)
        assert (a / "meta.json").read_bytes() == (b / "meta.json").read_bytes()

    def test_extra_keys_round_trip(self, tmp_path: Path) -> None:
        # Forward-compat: a future minor that adds an informational key
        # to meta.json (e.g., tenant_id) lands as a v1 extension. Older
        # readers preserve the new field via CacheMeta.extra rather than
        # dropping it. Test simulates this by writing meta.json with an
        # unknown key and verifying it survives a read+re-init.
        init_cache(tmp_path)
        # Manually mutate meta.json to add a forward-compat field.
        raw = json.loads((tmp_path / "meta.json").read_text())
        raw["future_field"] = "future_value"
        meta_path = tmp_path / "meta.json"
        meta_path.write_bytes(canonical_json_bytes(raw))
        # Read picks up the unknown key into `extra`.
        meta = read_meta(tmp_path)
        assert meta.extra == {"future_field": "future_value"}
        # init_cache (idempotent) doesn't strip it on re-init.
        # Mechanism check: the re-init path must NOT re-write meta.json
        # (which would lose any unknown keys not represented in
        # CacheMeta.extra at write time). mtime sentinel pins this:
        # if init_cache silently re-wrote, mtime would advance.
        mtime_before = meta_path.stat().st_mtime_ns
        init_cache(tmp_path)
        assert meta_path.stat().st_mtime_ns == mtime_before, (
            "init_cache re-wrote meta.json on re-init; the idempotence "
            "contract requires it to be a pure no-op when versions match."
        )
        meta_again = read_meta(tmp_path)
        assert meta_again.extra == {"future_field": "future_value"}

    def test_read_meta_corrupted_json_raises_data_error(self, tmp_path: Path) -> None:
        # Pin the FileNotFoundError vs JSONDecodeError vs
        # CacheSchemaMismatchError contract on read_meta:
        #   - file absent → FileNotFoundError (caller wants idempotence
        #     uses init_cache instead)
        #   - file present but unparseable → CacheSchemaMismatchError
        #     (data condition; cardinal #1)
        init_cache(tmp_path)
        (tmp_path / "meta.json").write_text("{not valid json")
        with pytest.raises(CacheSchemaMismatchError, match="corrupted"):
            read_meta(tmp_path)

    def test_read_meta_missing_required_key_raises_data_error(self, tmp_path: Path) -> None:
        # JSON-parses but is missing a required top-level key. Per
        # cardinal #1, this is a data condition (the disk surprised
        # us), not a programmer bug.
        (tmp_path / "entries").mkdir()
        (tmp_path / "meta.json").write_bytes(canonical_json_bytes({"cache_schema_version": "v1"}))
        with pytest.raises(CacheSchemaMismatchError, match="corrupted or missing"):
            read_meta(tmp_path)

    def test_read_entry_corrupted_json_raises_data_error(self, tmp_path: Path) -> None:
        # Pair to test_read_meta_corrupted_json: a corrupted entry
        # surfaces as CacheSchemaMismatchError, not raw JSONDecodeError.
        init_cache(tmp_path)
        components = _components()
        key = build_cache_key(components)
        path = write_entry(tmp_path, key, _entry(components))
        path.write_text("{not valid json")
        with pytest.raises(CacheSchemaMismatchError, match="corrupted"):
            read_entry(tmp_path, key)
