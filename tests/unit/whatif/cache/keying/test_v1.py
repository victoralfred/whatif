"""Tests for `whatif.cache.keying.v1` — Phase 3.1 cache key construction.

The load-bearing properties:

1. **Determinism** — same components produce the same key, on every
   platform, every interpreter, every run. The test pins this against
   a known-input known-output pair so a future implementation change
   that broke determinism (e.g., switching to a non-canonical encoder)
   would fail loudly with a diff against the recorded digest.

2. **Sensitivity to every component** — changing any field changes the
   key. The parametrized test mutates each field in turn and asserts
   the key changes. A future "optimization" that dropped a field from
   the hash would surface here as a "key didn't change" failure.

3. **Version prefix** — the `v1:` prefix is part of the key contract.
   Storage code uses it to split entries across versions. Tests pin
   the prefix so a rename to `v01:` or similar drift fails.
"""

from __future__ import annotations

import dataclasses

import pytest

from whatif.cache.keying import (
    CACHE_KEY_VERSION,
    CacheKeyComponents,
    build_cache_key,
)

_SAMPLE = CacheKeyComponents(
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


class TestBuildCacheKey:
    def test_returns_versioned_format(self) -> None:
        key = build_cache_key(_SAMPLE)
        assert key.startswith(f"{CACHE_KEY_VERSION}:")
        # v1: + 64-char hex digest = 67 characters.
        assert len(key) == len(CACHE_KEY_VERSION) + 1 + 64

    def test_version_prefix_is_v1(self) -> None:
        # Pinning the literal value: a rename to "v01" or "1" would
        # break storage layout assumptions and cache-version-bump tests.
        assert CACHE_KEY_VERSION == "v1"

    def test_digest_is_lowercase_hex(self) -> None:
        key = build_cache_key(_SAMPLE)
        _, digest = key.split(":", 1)
        # All hex chars, all lowercase. Pin: a future Python
        # implementation that switched hexdigest casing would silently
        # double the cache (uppercase vs lowercase keys differ in
        # filenames on case-sensitive filesystems).
        assert digest == digest.lower()
        assert all(c in "0123456789abcdef" for c in digest)

    def test_deterministic_against_known_digest(self) -> None:
        # Recorded the known-input known-output pair so a future change
        # that broke determinism (canonical-JSON shape, encoder choice,
        # hash algorithm) fails with a diff against this literal.
        #
        # Recording context:
        #   - CPython 3.14 (CI matrix runs 3.11/3.12/3.13/3.14)
        #   - hashlib.sha256 from stdlib (mathematically defined; no
        #     Python-version dependency)
        #   - json.dumps with sort_keys=True, separators=(",", ":"),
        #     ensure_ascii=True (CPython contract stable since 2.6+)
        #
        # This digest SHOULD be invariant across all supported Python
        # versions and platforms. If a future stdlib change shifted
        # json.dumps output (whitespace, key ordering, ASCII handling)
        # this test fails with a clear diff pointing at the regression.
        # If the digest changes intentionally, every existing cache
        # entry is invalidated — the right response is to bump
        # CACHE_KEY_VERSION to v2, not update this literal in place.
        #
        # Recompute by running this test once with `print(key)` and
        # then pinning the new digest in a v2 module.
        key = build_cache_key(_SAMPLE)
        assert key == ("v1:96fd8933a0b54f3bd917ecb3bdc709b0348db8b130f61262db697607a277ed90")

    def test_same_components_same_key(self) -> None:
        # Two independent constructions of identical components produce
        # identical keys. Surfaces accidental in-process state (e.g.,
        # `random.seed`-dependent hashes) that would defeat the cache.
        copy = dataclasses.replace(_SAMPLE)
        assert build_cache_key(_SAMPLE) == build_cache_key(copy)


class TestEveryComponentAffectsKey:
    """Mutating any single field changes the key. If a future change
    drops a field from the hash, the corresponding test fails — the
    field is silently ignored, which is a cache-poisoning footgun.
    """

    @pytest.mark.parametrize(
        "field, mutated",
        [
            ("whatif_schema_version", "0.2"),
            ("whatif_scorer_adapter_version", "0.2.0"),
            ("scorer_type", "inspect_ai.Hallucination"),
            ("scorer_package_version", "0.4.0"),
            ("judge_provider", "openai"),
            ("judge_model_id", "claude-opus-4-7"),
            ("judge_model_snapshot", "20260101"),
            ("rendered_prompt_hash", "ee" * 32),
            ("rubric_hash", "ff" * 32),
            ("scoring_parameters_hash", "ee" * 32),
            ("score_case_serialization_version", "v2"),
            ("score_case_hash", "ee" * 32),
        ],
    )
    def test_mutating_field_changes_key(self, field: str, mutated: object) -> None:
        baseline = build_cache_key(_SAMPLE)
        changed = build_cache_key(dataclasses.replace(_SAMPLE, **{field: mutated}))
        assert baseline != changed, (
            f"Mutating {field!r} did not change the cache key — the field "
            "is being silently ignored, which would cause cache poisoning "
            "across configurations the field is supposed to distinguish."
        )

    def test_judge_model_snapshot_none_distinct_from_string(self) -> None:
        # Pin: None and the empty string MUST produce different keys.
        # Some encoders treat them as equivalent; canonical JSON does not.
        with_none = build_cache_key(dataclasses.replace(_SAMPLE, judge_model_snapshot=None))
        with_empty = build_cache_key(dataclasses.replace(_SAMPLE, judge_model_snapshot=""))
        assert with_none != with_empty


class TestCanonicalEncoding:
    """Pin the canonical-JSON contract: sorted keys, no whitespace,
    ASCII-only. A future change to any of these would silently shift
    the digest space and invalidate every existing cache entry.
    """

    def test_field_order_does_not_affect_key(self) -> None:
        # CacheKeyComponents is a frozen dataclass so field order is
        # fixed by definition; this test is the canary for a refactor
        # that switched to TypedDict or dict-of-fields, where
        # construction order would matter without sort_keys.
        forward = build_cache_key(_SAMPLE)
        # Reconstruct with kwargs in different order — frozen dataclass
        # accepts kwargs in any order.
        reordered = build_cache_key(
            CacheKeyComponents(
                score_case_hash=_SAMPLE.score_case_hash,
                score_case_serialization_version=_SAMPLE.score_case_serialization_version,
                scoring_parameters_hash=_SAMPLE.scoring_parameters_hash,
                rubric_hash=_SAMPLE.rubric_hash,
                rendered_prompt_hash=_SAMPLE.rendered_prompt_hash,
                judge_model_snapshot=_SAMPLE.judge_model_snapshot,
                judge_model_id=_SAMPLE.judge_model_id,
                judge_provider=_SAMPLE.judge_provider,
                scorer_package_version=_SAMPLE.scorer_package_version,
                scorer_type=_SAMPLE.scorer_type,
                whatif_scorer_adapter_version=_SAMPLE.whatif_scorer_adapter_version,
                whatif_schema_version=_SAMPLE.whatif_schema_version,
            )
        )
        assert forward == reordered
