"""Tests for `whatifd.serialization.encoder` — Phase 5.3 artifact-write
JSON encoder.

Pin properties:

1. `Sensitive[T]` raises `UnredactedSensitiveError` (cardinal #5
   last line of defense).
2. Frozen dataclasses encode via recursive `asdict`.
3. `Mapping`/`MappingProxyType` encode as JSON objects.
4. `frozenset`/`set` encode as sorted lists (determinism).
5. Unknown types raise `TypeError` (failures-as-data).
6. `encode_report_v01` produces byte-identical output for identical
   input (same kwargs as `canonical_json_bytes`).
7. `encode_report_v01` end-to-end on a real `ReportV01` produces
   parseable JSON whose round-trip preserves verdict_state and
   structural fields.
"""

from __future__ import annotations

import dataclasses
import json
from types import MappingProxyType

import pytest

from whatifd.report.projection import project_to_report_v01
from whatifd.serialization import (
    WhatifJSONEncoder,
    encode_report_v01,
)
from whatifd.types.sensitive import Sensitive, UnredactedSensitiveError

from ..report._fixtures import (
    cache_summary,
    cohort,
    methodology,
    runtime,
    ship,
)

# ---------------------------------------------------------------------------
# Cardinal #5 last-line defense
# ---------------------------------------------------------------------------


class TestSensitiveLastLine:
    def test_top_level_sensitive_raises(self) -> None:
        s = Sensitive("password123", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError, match="Cardinal #5"):
            json.dumps(s, cls=WhatifJSONEncoder)

    def test_nested_sensitive_in_dict_raises(self) -> None:
        s = Sensitive("password", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError, match="Cardinal #5"):
            json.dumps({"creds": s}, cls=WhatifJSONEncoder)

    def test_nested_sensitive_in_list_raises(self) -> None:
        s = Sensitive("password", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError, match="Cardinal #5"):
            json.dumps([s], cls=WhatifJSONEncoder)

    def test_classification_in_error_message(self) -> None:
        # Operators see WHICH classification leaked — diagnostic value
        # for debugging which call site missed redaction.
        s = Sensitive("xxx", classification="judge_rationale")
        with pytest.raises(UnredactedSensitiveError, match="judge_rationale"):
            json.dumps(s, cls=WhatifJSONEncoder)


# ---------------------------------------------------------------------------
# Type-by-type default() coverage
# ---------------------------------------------------------------------------


class TestEncoderDispatch:
    def test_frozen_dataclass_encodes_via_shallow_field_projection(self) -> None:
        # The encoder dispatches frozen dataclasses by reading each
        # field via getattr(obj, field.name) — NOT dataclasses.asdict
        # (which deep-copies and chokes on MappingProxyType). Each
        # field's value flows back through default() via json's
        # recursive walk.
        c = cohort("failure")
        result = json.loads(json.dumps(c, cls=WhatifJSONEncoder))
        assert result["name"] == "failure"
        assert result["selected"] == 10
        assert result["ci_computable"] is True

    def test_nested_dataclass_recurses(self) -> None:
        # CohortResult contains a FloorFailure list. Verify nested
        # dataclasses round-trip through the recursive default()
        # dispatch (NOT dataclasses.asdict — see field-projection
        # docstring on the encoder). Populate a real FloorFailure so
        # the recursive path is actually exercised, not just asserted
        # for the empty-list case.
        from whatifd.types.cohort import FloorFailure

        c = cohort()
        ff = FloorFailure(
            rule="min_selected_per_required_cohort",
            observed=2,
            threshold=5,
            severity="blocks_all",
        )
        with_failure = dataclasses.replace(c, floor_failures=[ff])
        result = json.loads(json.dumps(with_failure, cls=WhatifJSONEncoder))
        # The nested FloorFailure dataclass also dispatches through
        # default() — not raised, fully encoded.
        assert isinstance(result["floor_failures"], list)
        assert len(result["floor_failures"]) == 1
        nested = result["floor_failures"][0]
        assert nested["rule"] == "min_selected_per_required_cohort"
        assert nested["observed"] == 2
        assert nested["threshold"] == 5
        assert nested["severity"] == "blocks_all"

    def test_empty_nested_collection_encodes_as_empty_list(self) -> None:
        # Pin the empty-collection path separately from the populated
        # one above. CohortResult.floor_failures defaults to []; the
        # recursive dispatch must produce [], not raise or omit.
        c = cohort()
        result = json.loads(json.dumps(c, cls=WhatifJSONEncoder))
        assert result["floor_failures"] == []

    def test_mapping_proxy_type_encodes_as_object(self) -> None:
        # MappingProxyType is the immutable view used by
        # CacheSummary.models_distribution and CacheMeta.extra.
        m = MappingProxyType({"claude-sonnet-4-6": 80, "claude-haiku-4-5": 20})
        result = json.loads(json.dumps(m, cls=WhatifJSONEncoder))
        assert result == {"claude-sonnet-4-6": 80, "claude-haiku-4-5": 20}

    def test_non_str_mapping_keys_coerced_via_str(self) -> None:
        # Pin the documented "best-effort emergency dispatch" for
        # non-str keys: encoder coerces via `str(k)` rather than
        # raising. This is NOT a sanctioned feature — the wire
        # boundary's typing contract is `Mapping[str, ...]` per
        # cardinal #6, and the type system catches non-str keys at
        # compile time. The runtime coercion is the rare-escape
        # safety net (e.g., dynamic CLI paths, REPL usage).
        #
        # Note: plain `dict` with non-str keys does NOT exercise the
        # coercion path — json's stdlib encoder handles `dict`
        # natively without dispatching through `default()`, and it
        # rejects non-str keys with a TypeError BEFORE our encoder
        # sees them. The coercion path fires for `Mapping`
        # NON-dict-instances (MappingProxyType, custom dict
        # subclasses). Using MappingProxyType wraps the non-str-keyed
        # dict so json's encoder treats it as opaque and calls
        # `default()`, which is where the coercion lives.
        m = MappingProxyType({1: "one", 2: "two", 3: "three"})
        result = json.loads(json.dumps(m, cls=WhatifJSONEncoder))
        # Pin the coercion is LOSSLESS-by-str-repr: int 1 becomes
        # "1", not silently dropped or corrupted. A future
        # contributor 'fixing' this to raise on non-str keys would
        # fail this test, surfacing the design choice for explicit
        # review rather than silently changing behavior.
        assert result == {"1": "one", "2": "two", "3": "three"}

    def test_non_str_mapping_keys_with_collision_loses_data(self) -> None:
        # Defense: surface the failure mode of `str()` coercion. Two
        # distinct keys whose `str()` reprs collide produce a
        # collapsed output — verify the pathological case via a
        # custom __str__ that returns the same string for distinct
        # keys. MappingProxyType again routes through default().
        class _Stub:
            def __init__(self, val: int) -> None:
                self._val = val

            def __str__(self) -> str:
                # Both stubs stringify identically — collision.
                return "collide"

            def __hash__(self) -> int:
                return self._val  # distinct hashes → distinct dict entries

            def __eq__(self, other: object) -> bool:
                return isinstance(other, _Stub) and self._val == other._val

        a = _Stub(1)
        b = _Stub(2)
        m = MappingProxyType({a: "first", b: "second"})
        result = json.loads(json.dumps(m, cls=WhatifJSONEncoder))
        # The dict-comprehension `{str(k): v for k, v in obj.items()}`
        # collapses on duplicate string keys; one value wins (which
        # one is iteration-order-dependent). Pin only that the
        # collapse occurred (one entry, not two), NOT the specific
        # winner — that would couple to dict iteration order.
        assert len(result) == 1
        assert "collide" in result
        assert result["collide"] in ("first", "second")

    def test_frozenset_encodes_as_sorted_list(self) -> None:
        fs = frozenset({"c", "a", "b"})
        result = json.loads(json.dumps(fs, cls=WhatifJSONEncoder))
        # Determinism: sorted output regardless of frozenset iteration order.
        assert result == ["a", "b", "c"]

    def test_set_encodes_as_sorted_list(self) -> None:
        s: set[str] = {"c", "a", "b"}
        result = json.loads(json.dumps(s, cls=WhatifJSONEncoder))
        assert result == ["a", "b", "c"]

    def test_tuple_encodes_as_list_via_stdlib(self) -> None:
        # JSON has no native tuple; stdlib already converts. Pin the
        # behavior here so a future override that changed tuple
        # handling fails this test.
        t = ("x", "y", "z")
        result = json.loads(json.dumps(t, cls=WhatifJSONEncoder))
        assert result == ["x", "y", "z"]

    def test_unknown_type_raises_type_error(self) -> None:
        # Cardinal #1: unknown types are failures-as-data, not silent.
        # An object with no encode path raises TypeError from stdlib's
        # default() fallback — surfaces to the caller, not silently
        # converts to "<object at 0x...>".
        class _Opaque:
            pass

        with pytest.raises(TypeError, match="not JSON serializable"):
            json.dumps(_Opaque(), cls=WhatifJSONEncoder)


# ---------------------------------------------------------------------------
# encode_report_v01 end-to-end
# ---------------------------------------------------------------------------


class TestEncodeReportV01:
    def _report_bytes(self) -> bytes:
        report = project_to_report_v01(
            ship(),
            failures=[],
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        return encode_report_v01(report)

    def test_returns_ascii_bytes(self) -> None:
        out = self._report_bytes()
        assert isinstance(out, bytes)
        assert all(b < 128 for b in out)

    def test_canonical_form_no_pretty_printing(self) -> None:
        # Pin the canonical-form contract structurally: re-serialize
        # the parsed output with the same canonical kwargs and assert
        # byte equality. This catches any pretty-printing artifact
        # (extra newlines, indentation, comma-space, colon-space)
        # WITHOUT producing false positives on string-literal content
        # that happens to contain a colon-space (e.g., a future
        # methodology note like "judge: claude-sonnet-4-6"). A
        # bytes-substring search for ": " would fail spuriously on
        # such content; structural re-serialization compares the
        # CANONICAL form to itself.
        #
        # Note: the re-serialization uses stdlib `json.dumps` directly
        # (NOT `encode_report_v01`) — intentional. The point is to
        # verify our encoder's output matches stdlib's canonical form
        # for a parsed-and-resialized dict. Routing back through
        # encode_report_v01 would test the encoder against itself
        # (tautological); routing through stdlib pins that the encoder
        # produced bytes a stdlib-only consumer would also produce.
        out = self._report_bytes()
        parsed = json.loads(out)
        canonical_reserialize = json.dumps(
            parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
        assert out == canonical_reserialize

    def test_round_trips_to_dict(self) -> None:
        out = self._report_bytes()
        parsed = json.loads(out)
        assert parsed["schema_version"] == "0.1"
        assert parsed["verdict_state"] == "ship"
        assert isinstance(parsed["cohort_results"], list)
        assert isinstance(parsed["failures"], list)

    def test_byte_identical_for_identical_input(self) -> None:
        # Determinism: same ReportV01 produces same bytes. The fixture
        # invariant this test relies on:
        #   - `runtime()` fixture stamps fixed timestamps
        #     ("2026-05-06T10:00:00Z" / "2026-05-06T10:01:00Z") not
        #     `datetime.now()`.
        #   - `ship()` constructs a real Ship via evaluate_floor; the
        #     FloorPassedProof's `floor_version` is sticky ("v1").
        # If a future fixture change introduces wall-clock state, this
        # test will flake — the fix is to pin the fixture, not relax
        # the assertion.
        a = self._report_bytes()
        b = self._report_bytes()
        assert a == b

    # Note: key-sort and pretty-print absence are both covered by
    # `test_canonical_form_no_pretty_printing` above (re-serializes
    # parsed output with sort_keys=True and asserts byte equality).

    def test_includes_methodology_block(self) -> None:
        # Cardinal #10: methodology is a required field; the wire
        # form must carry it.
        parsed = json.loads(self._report_bytes())
        assert "methodology" in parsed
        assert parsed["methodology"]["unit_of_analysis"] == "paired_trace_delta"
        assert parsed["methodology"]["per_trace_inference"] == "descriptive_only"

    def test_rejects_non_report_input_at_runtime(self) -> None:
        # Cardinal #6 defense-in-depth: mypy strict catches wrong-type
        # calls at type-check time, but the runtime guard exists for
        # callers that bypass type-checking (dynamic CLI paths, REPL
        # usage, tests passing garbage). Pin the guard's behavior.
        with pytest.raises(TypeError, match="expects a ReportV01"):
            encode_report_v01("not a report")  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="expects a ReportV01"):
            # Even another frozen dataclass is rejected — the guard
            # checks for ReportV01 specifically, not "any dataclass".
            encode_report_v01(cohort())  # type: ignore[arg-type]
