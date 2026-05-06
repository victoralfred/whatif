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
from whatif.exceptions import InvariantViolationError

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
        #   - Verification authority: the supported CI matrix
        #     (3.11, 3.12, 3.13 — all stable releases; authoritative
        #     list at .github/workflows/ci.yml's matrix.python-version).
        #     This test passing on every matrix version IS the
        #     determinism proof. The recording-environment Python
        #     version is irrelevant to the guarantee — what matters
        #     is that the digest matches on every version we ship
        #     against.
        #   - hashlib.sha256 from stdlib (mathematically defined; no
        #     Python-version dependency)
        #   - canonical_json_bytes (whatif.serialization.canonical) which
        #     wraps json.dumps with sort_keys=True, separators=(",", ":"),
        #     ensure_ascii=True (CPython contract stable since 2.6+)
        #
        # If a future Python version (e.g., 3.14) were added to the
        # CI matrix and shifted the digest, this test would fail in
        # that one version's job with a clear diff — the right response
        # would be a CACHE_KEY_VERSION bump to v2, NOT updating this
        # literal in place (which would silently invalidate every
        # existing cache entry).
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
            # Distinct hex sentinels per hash field so the test's
            # diagnostic output makes it obvious which field's mutation
            # is being tested. The values differ from each other AND
            # from the baseline _SAMPLE values (aa/bb/cc/dd).
            ("rendered_prompt_hash", "e1" * 32),
            ("rubric_hash", "e2" * 32),
            ("scoring_parameters_hash", "e3" * 32),
            ("score_case_serialization_version", "v2"),
            ("score_case_hash", "e4" * 32),
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


class TestPreHashedContractEnforced:
    """`CacheKeyComponents.__post_init__` rejects non-hex values in
    hash fields. The pre-hash contract is structural (cardinal #5) —
    raw user content cannot reach a cache filename.
    """

    @pytest.mark.parametrize(
        "field",
        [
            "rendered_prompt_hash",
            "rubric_hash",
            "scoring_parameters_hash",
            "score_case_hash",
        ],
    )
    def test_raw_text_raises(self, field: str) -> None:
        with pytest.raises(InvariantViolationError, match="not a lowercase hex digest"):
            dataclasses.replace(_SAMPLE, **{field: "what is the capital of France?"})

    @pytest.mark.parametrize(
        "field",
        [
            "rendered_prompt_hash",
            "rubric_hash",
            "scoring_parameters_hash",
            "score_case_hash",
        ],
    )
    def test_uppercase_hex_raises(self, field: str) -> None:
        # Uppercase hex is rejected: case-insensitive filesystems would
        # collapse different cases into the same filename, and our
        # canonical form is lowercase.
        with pytest.raises(InvariantViolationError):
            dataclasses.replace(_SAMPLE, **{field: "AA" * 32})

    @pytest.mark.parametrize(
        "field",
        [
            "rendered_prompt_hash",
            "rubric_hash",
            "scoring_parameters_hash",
            "score_case_hash",
        ],
    )
    def test_too_short_raises(self, field: str) -> None:
        # 8 chars (truncated MD5-ish) — below the conservative 16-char
        # minimum that catches "definitely not a digest" inputs.
        with pytest.raises(InvariantViolationError):
            dataclasses.replace(_SAMPLE, **{field: "deadbeef"})

    def test_empty_string_raises(self) -> None:
        with pytest.raises(InvariantViolationError):
            dataclasses.replace(_SAMPLE, rendered_prompt_hash="")

    def test_sha1_length_accepted(self) -> None:
        # SHA-1 hex is 40 chars — algorithm-agnostic acceptance.
        # Build the key end-to-end (not just construct) so the test
        # exercises both __post_init__ validation AND the downstream
        # canonical-encode + hash path with this length.
        components = dataclasses.replace(_SAMPLE, rendered_prompt_hash="a" * 40)
        key = build_cache_key(components)
        assert key.startswith("v1:")

    def test_sha512_length_accepted(self) -> None:
        # SHA-512 hex is 128 chars — algorithm-agnostic acceptance.
        # End-to-end like the SHA-1 case above.
        components = dataclasses.replace(_SAMPLE, rendered_prompt_hash="b" * 128)
        key = build_cache_key(components)
        assert key.startswith("v1:")

    def test_error_names_offending_field(self) -> None:
        # Diagnostic: the field name appears in the error so a caller
        # debugging a wired-wrong adapter knows which input is wrong.
        with pytest.raises(InvariantViolationError, match="rubric_hash"):
            dataclasses.replace(_SAMPLE, rubric_hash="not a hash")
