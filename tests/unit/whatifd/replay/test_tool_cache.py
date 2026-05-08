"""Tests for `whatifd.replay.tool_cache` — Phase 6.2 strict per-trace
tool cache.

Pin properties:

1. `make_strict_tool_cache` returns a `StrictToolCache` (a `ToolCache`
   subclass — Liskov: user code annotated `ToolCache` accepts it).
2. `StrictToolCache.lookup` returns the cached value on hit.
3. `StrictToolCache.lookup` raises `CacheMissError` on TRUE miss
   (key absent from cache).
4. `StrictToolCache.lookup` returns `None` for a key whose cached
   value IS `None` — sentinel-vs-None disambiguation, NOT a miss.
5. `CacheMissError` carries `trace_id`, `tool_name`, `arg_count`
   ONLY — args VALUES are NOT stored on the exception (cardinal #5).
6. `CacheMissError.details_for_failure()` returns the
   `Mapping[str, JsonPrimitive]` shape with only `tool_name`.
7. The factory rejects empty `trace_id`.
8. Direct construction of `StrictToolCache` (bypassing the factory)
   raises `InvariantViolationError` on first miss.
9. Cardinal #1 alignment with `FAILURE_CODE_REGISTRY["tool_cache_miss"]`:
   the projected details satisfy `required_details`.
"""

from __future__ import annotations

import pytest

from whatifd.contract import ToolCache
from whatifd.exceptions import InvariantViolationError
from whatifd.replay.tool_cache import (
    CacheMissError,
    StrictToolCache,
    make_strict_tool_cache,
)

# ---------------------------------------------------------------------------
# Factory + Liskov substitutability
# ---------------------------------------------------------------------------


class TestFactory:
    def test_factory_returns_strict_subclass(self) -> None:
        c = make_strict_tool_cache({}, trace_id="t-1")
        assert isinstance(c, StrictToolCache)
        assert isinstance(c, ToolCache)

    def test_factory_captures_trace_id(self) -> None:
        c = make_strict_tool_cache({}, trace_id="t-42")
        assert c._trace_id == "t-42"

    def test_factory_uses_use_original_policy(self) -> None:
        c = make_strict_tool_cache({}, trace_id="t-1")
        assert c.policy == "use-original"

    def test_factory_copies_entries(self) -> None:
        entries: dict[str, object] = {"k": "v"}
        c = make_strict_tool_cache(entries, trace_id="t-1")
        entries["k"] = "mutated"
        assert c.cache["k"] == "v"

    def test_factory_rejects_empty_trace_id(self) -> None:
        # Empty trace_id would silently produce un-cross-
        # referenceable failure records. Cardinal #1: fail loudly at
        # the factory boundary, not silently when the miss fires.
        with pytest.raises(ValueError, match="trace_id must be non-empty"):
            make_strict_tool_cache({}, trace_id="")


# ---------------------------------------------------------------------------
# Strict lookup behavior
# ---------------------------------------------------------------------------


class TestStrictLookup:
    def test_hit_returns_value(self) -> None:
        parent = ToolCache(cache={}, policy="use-original")
        key = parent._key("get_weather", {"city": "Tokyo"})
        c = make_strict_tool_cache({key: {"temp": 20}}, trace_id="t-1")

        result = c.lookup("get_weather", {"city": "Tokyo"})
        assert result == {"temp": 20}

    def test_cached_none_returned_not_misclassified(self) -> None:
        # Cardinal #1: a tool that legitimately returns None (e.g., a
        # "find user" tool with not-found semantics) must NOT be
        # misclassified as a cache miss. Sentinel-vs-None
        # disambiguation: dict.get(key, _MISSING) distinguishes
        # "key absent" from "key present, value None".
        parent = ToolCache(cache={}, policy="use-original")
        key = parent._key("find_user", {"id": "u-1"})
        c = make_strict_tool_cache({key: None}, trace_id="t-1")

        result = c.lookup("find_user", {"id": "u-1"})
        assert result is None

    def test_miss_raises_cache_miss_error(self) -> None:
        c = make_strict_tool_cache({}, trace_id="t-1")
        with pytest.raises(CacheMissError) as excinfo:
            c.lookup("get_weather", {"city": "Tokyo"})
        assert excinfo.value.trace_id == "t-1"
        assert excinfo.value.tool_name == "get_weather"
        assert excinfo.value.arg_count == 1

    def test_miss_with_different_args_raises(self) -> None:
        parent = ToolCache(cache={}, policy="use-original")
        key_a = parent._key("get_weather", {"city": "Tokyo"})
        c = make_strict_tool_cache({key_a: {"temp": 20}}, trace_id="t-1")

        assert c.lookup("get_weather", {"city": "Tokyo"}) == {"temp": 20}
        with pytest.raises(CacheMissError) as excinfo:
            c.lookup("get_weather", {"city": "Paris"})
        assert excinfo.value.tool_name == "get_weather"
        assert excinfo.value.arg_count == 1


# ---------------------------------------------------------------------------
# Direct-construction defense
# ---------------------------------------------------------------------------


class TestDirectConstructionDefense:
    def test_direct_construction_with_unset_trace_id_raises_invariant(self) -> None:
        # Bypass the factory: instantiate StrictToolCache directly.
        # On miss, lookup detects the unset _trace_id sentinel and
        # raises InvariantViolationError rather than silently emitting
        # an empty-string trace_id in the CacheMissError. Defense
        # against the empty-string-fallback path.
        c = StrictToolCache(cache={}, policy="use-original")
        with pytest.raises(InvariantViolationError, match="_trace_id is unset"):
            c.lookup("get_weather", {"city": "Tokyo"})


# ---------------------------------------------------------------------------
# CacheMissError shape (cardinal #5)
# ---------------------------------------------------------------------------


class TestCacheMissError:
    def test_no_args_attribute_exposing_values(self) -> None:
        # Cardinal #5: the exception object MUST NOT carry the raw
        # args dict. Only arg_count is captured. A future contributor
        # adding `self.tool_args = dict(args)` back would fail this
        # test, surfacing the design choice for explicit review.
        e = CacheMissError(trace_id="t-1", tool_name="f", arg_count=2)
        assert not hasattr(e, "tool_args")
        assert not hasattr(e, "raw_args")

    def test_message_includes_trace_id_and_tool(self) -> None:
        e = CacheMissError(trace_id="t-1", tool_name="get_weather", arg_count=1)
        msg = str(e)
        assert "t-1" in msg
        assert "get_weather" in msg

    def test_message_only_carries_arg_count_not_values(self) -> None:
        # The constructor takes arg_count (int), not args (dict).
        # No path exists for arg VALUES to reach the exception, so
        # the diagnostic message is structurally safe.
        e = CacheMissError(trace_id="t-1", tool_name="f", arg_count=3)
        assert "3" in str(e)

    def test_details_for_failure_shape(self) -> None:
        e = CacheMissError(trace_id="t-1", tool_name="get_weather", arg_count=2)
        details = e.details_for_failure()
        assert details == {"tool_name": "get_weather"}
        assert "args" not in details
        assert "arg_count" not in details

    def test_isolated_subprocess_import_works(self) -> None:
        # The module-level `import whatifd.cache` prime in
        # `whatif/replay/tool_cache.py` is a load-order workaround for
        # the cascade-tracked "Serialization ↔ report ↔ cache import
        # cycle". This test pins that the prime is doing its job:
        # in a fresh subprocess with no prior imports, importing
        # `whatifd.replay.tool_cache` AND exercising the lookup path
        # (which transitively triggers `ToolCache._key`'s lazy
        # serialization import) succeeds. Without the prime, the
        # cycle bites and the import raises ImportError on
        # `parse_lock_file_content`.
        #
        # Cleanup signal: when the cascade entry's resolution lands
        # (v0.2 layering audit retiring the cycle), this test should
        # still pass — it doesn't depend on the prime being present,
        # only on imports working in isolation. To confirm the prime
        # itself is now redundant, manually comment out the
        # `import whatifd.cache` line in tool_cache.py and re-run THIS
        # test. If it still passes, the prime can be deleted in the
        # same PR that retires the other two cycle workarounds
        # (encoder TYPE_CHECKING, ToolCache._key lazy import).
        import subprocess
        import sys

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from whatifd.replay.tool_cache import "
                    "make_strict_tool_cache, CacheMissError; "
                    "c = make_strict_tool_cache({}, trace_id='t-1'); "
                    "import sys as _s; "
                    "raised = False\n"
                    "try:\n"
                    "    c.lookup('foo', {'a': 1})\n"
                    "except CacheMissError:\n"
                    "    raised = True\n"
                    "_s.exit(0 if raised else 1)"
                ),
            ],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"isolated import + lookup failed (exit {result.returncode}). "
            "The serialization↔cache import-cycle prime in "
            "tool_cache.py may have regressed. stderr:\n"
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )

    def test_details_for_failure_satisfies_registry(self) -> None:
        # Cardinal #1: the registry's `tool_cache_miss` spec lists
        # `required_details=("tool_name",)`. The details map produced
        # here MUST contain that key — `make_failure_record` would
        # raise otherwise at projection time.
        from whatifd.decision.failure_codes import FAILURE_CODE_REGISTRY

        spec = FAILURE_CODE_REGISTRY["tool_cache_miss"]
        e = CacheMissError(trace_id="t-1", tool_name="get_weather", arg_count=0)
        details = e.details_for_failure()
        for key in spec.required_details:
            assert key in details, (
                f"details_for_failure() missing required-details key {key!r} "
                "from FAILURE_CODE_REGISTRY['tool_cache_miss'] spec"
            )
