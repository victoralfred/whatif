"""Tests for `whatifd.serialization.canonical` — Phase 3.1 hash-input
canonical encoding.

Pins the contract that downstream hash-input code (cache keying today,
content-addressed identifiers tomorrow) depends on. The canonical
encoding MUST be:

1. Deterministic (same value → same bytes, on every platform).
2. Sorted-key (dict-insertion-order does not affect output).
3. Whitespace-free (default `json.dumps` whitespace must not leak in).
4. ASCII-only (locale and platform character encoding cannot leak in).

A drift in any of these properties silently invalidates every
downstream hash. The tests pin all four.
"""

from __future__ import annotations

import pytest

from whatifd.serialization import canonical_json_bytes
from whatifd.types.sensitive import Sensitive, UnredactedSensitiveError


class TestCanonicalJsonBytes:
    def test_returns_ascii_bytes(self) -> None:
        out = canonical_json_bytes({"a": 1})
        assert isinstance(out, bytes)
        # ASCII subset of UTF-8: every byte < 128.
        assert all(b < 128 for b in out)

    def test_sorted_keys(self) -> None:
        # Insertion order Z, A, M but encoding is A, M, Z.
        out = canonical_json_bytes({"z": 1, "a": 2, "m": 3})
        assert out == b'{"a":2,"m":3,"z":1}'

    def test_no_whitespace(self) -> None:
        out = canonical_json_bytes({"a": 1, "b": [1, 2]})
        assert b" " not in out
        assert b"\n" not in out
        assert b"\t" not in out

    def test_non_ascii_escaped(self) -> None:
        # Default json.dumps with ensure_ascii=True escapes non-ASCII.
        # Pin: a future change to ensure_ascii=False would shift bytes
        # in a locale-dependent way and break every downstream hash.
        out = canonical_json_bytes({"name": "café"})
        assert out == b'{"name":"caf\\u00e9"}'

    def test_nested_dicts_also_sorted(self) -> None:
        out = canonical_json_bytes({"outer": {"z": 1, "a": 2}, "another": 3})
        assert out == b'{"another":3,"outer":{"a":2,"z":1}}'

    def test_none_distinct_from_empty_string(self) -> None:
        assert canonical_json_bytes({"k": None}) != canonical_json_bytes({"k": ""})

    def test_int_vs_float_distinct(self) -> None:
        # Pin: 1 and 1.0 produce different canonical bytes. A future
        # encoder that normalized them would silently merge cache
        # entries that used different numeric types.
        assert canonical_json_bytes({"k": 1}) != canonical_json_bytes({"k": 1.0})

    def test_list_order_preserved(self) -> None:
        # Lists are ORDERED — sort_keys only sorts dict keys.
        # [1, 2] and [2, 1] MUST produce different bytes.
        assert canonical_json_bytes([1, 2]) != canonical_json_bytes([2, 1])

    def test_deterministic_repeated_calls(self) -> None:
        obj = {"a": [1, 2, 3], "b": {"nested": True}}
        first = canonical_json_bytes(obj)
        second = canonical_json_bytes(obj)
        assert first == second


class TestSensitiveRejection:
    """Top-level cardinal #5 boundary: passing a `Sensitive[T]` directly
    raises `UnredactedSensitiveError`. Nested `Sensitive` inside a
    dict/list is NOT walked here — Phase 5's
    `assert_no_unredacted_sensitive` is the structural defense for
    that case. Until Phase 5 lands, the v0.1 fallback for nested
    Sensitive is the stdlib `TypeError` (no `__json__` hook on
    Sensitive). The fallback is best-effort, not a hard structural
    guarantee — a future Sensitive variant that gained a JSON hook
    returning its redacted repr would silently leak it; the
    canonical helper's docstring tracks this caveat explicitly.
    """

    def test_top_level_sensitive_raises(self) -> None:
        s = Sensitive("password123", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError, match="cardinal #5"):
            canonical_json_bytes(s)

    def test_nested_sensitive_raises_via_stdlib(self) -> None:
        # TODO(phase-5): re-review this test when
        # `assert_no_unredacted_sensitive` (graph walk) and
        # `WhatifJSONEncoder.default()` land. At that point the
        # expected exception flips from a generic stdlib TypeError to
        # a domain-specific `UnredactedSensitiveError` raised by the
        # graph walk BEFORE the encoder is reached. The grep-marker
        # `TODO(phase-5)` is the deletion/update trigger.
        #
        # Current v0.1 fallback: stdlib json.dumps raises TypeError
        # because Sensitive has no __json__ hook. This is best-effort
        # — a future Sensitive variant that gained a JSON hook
        # returning its redacted repr would silently leak it past
        # this test. The full structural defense is Phase 5's
        # graph walk; until then, the pre-hash contract on
        # CacheKeyComponents is the load-bearing protection.
        s = Sensitive("password123", classification="user_secret")
        with pytest.raises(TypeError):
            canonical_json_bytes({"creds": s})
