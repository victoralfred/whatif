"""Tests for `whatifd.serialization.graph_walk` — Phase 5.4 cardinal #5
layer (b): pre-serialization graph walk.

Pin properties:

1. Clean `ReportV01` passes silently.
2. `Sensitive[T]` raises `UnredactedSensitiveError` when reachable via:
   dataclass field, mapping value, mapping KEY, list element, tuple
   element, set element, deeply nested combinations.
3. Error message includes the path breadcrumb to the offending value.
4. Error message includes the classification.
5. Cycle protection: a self-referential container does not infinite-loop.
6. Primitives at the root are no-ops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType

import pytest

from whatifd.report.projection import project_to_report_v01
from whatifd.serialization import assert_no_unredacted_sensitive
from whatifd.types.sensitive import Sensitive, UnredactedSensitiveError

from ..report._fixtures import (
    cache_summary,
    methodology,
    runtime,
    ship,
)

# ---------------------------------------------------------------------------
# Clean graph passes silently
# ---------------------------------------------------------------------------


class TestCleanGraphPasses:
    def test_clean_report_passes(self) -> None:
        report = project_to_report_v01(
            ship(),
            failures=[],
            cache_summary=cache_summary(),
            methodology=methodology(),
            runtime=runtime(),
        )
        # Returns None, no raise.
        assert assert_no_unredacted_sensitive(report) is None

    def test_primitives_at_root_are_noop(self) -> None:
        # No raise, no recursion needed.
        for primitive in ("hello", 42, 3.14, True, False, None, b"bytes"):
            assert assert_no_unredacted_sensitive(primitive) is None

    def test_empty_containers_pass(self) -> None:
        assert assert_no_unredacted_sensitive([]) is None
        assert assert_no_unredacted_sensitive(()) is None
        assert assert_no_unredacted_sensitive({}) is None
        assert assert_no_unredacted_sensitive(set()) is None
        assert assert_no_unredacted_sensitive(frozenset()) is None


# ---------------------------------------------------------------------------
# Sensitive detection across container shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Holder:
    """Local frozen dataclass for graph-walk reachability tests. Not a
    wire-shape type — exists only to exercise the dataclass branch
    independent of `ReportV01`."""

    name: str
    payload: object = None
    children: list[object] = field(default_factory=list)


class TestSensitiveDetection:
    def test_top_level_sensitive_raises(self) -> None:
        s = Sensitive("secret", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError, match="user_secret"):
            assert_no_unredacted_sensitive(s)

    def test_sensitive_in_dataclass_field_raises(self) -> None:
        s = Sensitive("secret", classification="judge_rationale")
        h = _Holder(name="root", payload=s)
        with pytest.raises(UnredactedSensitiveError, match="judge_rationale"):
            assert_no_unredacted_sensitive(h)

    def test_sensitive_in_list_raises(self) -> None:
        s = Sensitive("x", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError):
            assert_no_unredacted_sensitive([1, 2, s, 3])

    def test_sensitive_in_tuple_raises(self) -> None:
        s = Sensitive("x", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError):
            assert_no_unredacted_sensitive(("a", s))

    def test_sensitive_in_dict_value_raises(self) -> None:
        s = Sensitive("x", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError):
            assert_no_unredacted_sensitive({"creds": s})

    def test_sensitive_in_dict_key_raises(self) -> None:
        # A Sensitive in a key is just as bad as in a value.
        s = Sensitive("x", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError):
            assert_no_unredacted_sensitive({s: "value"})

    def test_sensitive_in_mapping_proxy_raises(self) -> None:
        s = Sensitive("x", classification="user_secret")
        m = MappingProxyType({"creds": s})
        with pytest.raises(UnredactedSensitiveError):
            assert_no_unredacted_sensitive(m)

    def test_sensitive_in_set_raises(self) -> None:
        s = Sensitive("x", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError):
            assert_no_unredacted_sensitive({s, "other"})

    def test_sensitive_in_frozenset_raises(self) -> None:
        s = Sensitive("x", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError):
            assert_no_unredacted_sensitive(frozenset({s}))

    def test_deeply_nested_sensitive_raises(self) -> None:
        # dataclass → list → dict → tuple → Sensitive
        s = Sensitive("x", classification="user_secret")
        h = _Holder(
            name="root",
            children=[{"k": ("a", "b", s)}],
        )
        with pytest.raises(UnredactedSensitiveError):
            assert_no_unredacted_sensitive(h)


# ---------------------------------------------------------------------------
# Diagnostic path breadcrumb
# ---------------------------------------------------------------------------


class TestPathBreadcrumb:
    def test_path_includes_field_name(self) -> None:
        s = Sensitive("x", classification="user_secret")
        h = _Holder(name="root", payload=s)
        with pytest.raises(UnredactedSensitiveError, match=r"\.payload"):
            assert_no_unredacted_sensitive(h)

    def test_path_includes_list_index(self) -> None:
        s = Sensitive("x", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError, match=r"\[2\]"):
            assert_no_unredacted_sensitive([0, 1, s])

    def test_path_includes_mapping_key(self) -> None:
        s = Sensitive("x", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError, match=r"creds"):
            assert_no_unredacted_sensitive({"creds": s})

    def test_path_starts_at_root_by_default(self) -> None:
        s = Sensitive("x", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError, match=r"<root>"):
            assert_no_unredacted_sensitive(s)

    def test_custom_path_overrides_root(self) -> None:
        s = Sensitive("x", classification="user_secret")
        with pytest.raises(UnredactedSensitiveError, match=r"report\.foo"):
            assert_no_unredacted_sensitive(s, path="report.foo")


# ---------------------------------------------------------------------------
# Cycle protection
# ---------------------------------------------------------------------------


class TestCycleProtection:
    def test_self_referential_list_terminates(self) -> None:
        # A clean cycle must not infinite-loop. The wire shape is
        # acyclic by design, but the walk is robust.
        a: list[object] = [1, 2]
        a.append(a)
        # No raise, terminates.
        assert assert_no_unredacted_sensitive(a) is None

    def test_self_referential_dict_terminates(self) -> None:
        d: dict[str, object] = {"k": 1}
        d["self"] = d
        assert assert_no_unredacted_sensitive(d) is None

    def test_cycle_with_sensitive_still_raises(self) -> None:
        # Cycle protection must not mask a Sensitive on a reachable path.
        s = Sensitive("x", classification="user_secret")
        a: list[object] = [s]
        a.append(a)
        with pytest.raises(UnredactedSensitiveError):
            assert_no_unredacted_sensitive(a)
