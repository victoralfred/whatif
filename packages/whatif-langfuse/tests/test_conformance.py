"""`LangfuseTraceSource` conformance test (mocked client).

Runs the parent repo's `TraceSourceConformance` harness against a
mocked Langfuse API client. No network. Real-network smoke (against
recorded cassettes from a local credential set) lives in
`test_recorded_smoke.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from conformance import TraceSourceConformance  # type: ignore[import-not-found]
from whatif_langfuse import LangfuseTraceSource

from whatif.adapters import TraceSource


@dataclass
class _FakeTrace:
    id: str
    input: Any
    output: Any
    metadata: Any
    tags: Any
    user_id: Any
    session_id: Any


@dataclass
class _FakeTracesResponse:
    data: list[_FakeTrace]


class _FakeTraceClient:
    def __init__(self, traces: list[_FakeTrace]) -> None:
        self._traces = traces

    def list(
        self,
        *,
        page: int | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> _FakeTracesResponse:
        # Single-page mock: return everything on page 1, empty on 2+.
        # Sufficient for the conformance harness; the streaming-
        # pagination contract is exercised by a dedicated test below.
        if page is None or page == 1:
            return _FakeTracesResponse(data=list(self._traces))
        return _FakeTracesResponse(data=[])


class _FakeAPI:
    def __init__(self, traces: list[_FakeTrace]) -> None:
        self.trace = _FakeTraceClient(traces)


def _trace(idx: int, *, cohort: str = "failure") -> _FakeTrace:
    return _FakeTrace(
        id=f"trace-{idx:03d}",
        input=f"hello {idx}",
        output=f"reply {idx}",
        metadata={"cohort_hint": cohort},
        tags=[cohort],
        user_id=f"user-{idx % 3}",
        session_id=f"session-{idx // 5}",
    )


class TestLangfuseTraceSourceConformance(TraceSourceConformance):
    __test__ = True

    @pytest.fixture
    def trace_source(self) -> TraceSource:
        traces = [
            _trace(0, cohort="failure"),
            _trace(1, cohort="baseline"),
            _trace(2, cohort="failure"),
        ]
        api = _FakeAPI(traces)
        return LangfuseTraceSource(
            api=api,
            cohort_classifier=lambda t: "failure" if "failure" in (t.tags or []) else "baseline",
            page_limit=10,
            sdk_version="4.5.1-test",
        )


class TestLangfuseSpecificBehaviors:
    """Behaviors the generic harness doesn't cover — Langfuse-shape
    projection, pagination, and adapter-metadata sourcing."""

    def test_dict_input_serialized_deterministically(self) -> None:
        # Trace.input is typed Any; a dict input MUST project to the
        # same string across calls (cardinal #4 determinism for the
        # boundary projection). Pin via `sort_keys=True` round-trip.
        api = _FakeAPI(
            [
                _FakeTrace(
                    id="t",
                    input={"b": 2, "a": 1},
                    output={"x": "y"},
                    metadata={},
                    tags=[],
                    user_id=None,
                    session_id=None,
                )
            ]
        )
        src = LangfuseTraceSource(
            api=api,
            cohort_classifier=lambda _t: "failure",
            page_limit=10,
        )
        emitted = list(src.iter_traces())
        assert len(emitted) == 1
        # `Sensitive` redacts repr; unwrap with reason for the test.
        unwrapped = emitted[0].user_message.unwrap(
            reason="conformance: deterministic projection check"
        )
        assert unwrapped == '{"a": 1, "b": 2}'

    def test_pagination_streams_across_pages(self) -> None:
        # Pagination contract: when a page returns exactly
        # `page_limit` rows, fetch the next page; stop on a short
        # page. The mocked client returns 10 traces on page 1 and 3
        # on page 2 — total 13.
        page1 = [_trace(i, cohort="failure") for i in range(10)]
        page2 = [_trace(i + 100, cohort="baseline") for i in range(3)]

        class _PaginatingClient:
            def list(
                self, *, page: int | None = None, limit: int | None = None, **kwargs: Any
            ) -> _FakeTracesResponse:
                if page == 1:
                    return _FakeTracesResponse(data=list(page1))
                if page == 2:
                    return _FakeTracesResponse(data=list(page2))
                return _FakeTracesResponse(data=[])

        class _PaginatingAPI:
            trace = _PaginatingClient()

        src = LangfuseTraceSource(
            api=_PaginatingAPI(),
            cohort_classifier=lambda t: "failure" if "failure" in (t.tags or []) else "baseline",
            page_limit=10,
        )
        emitted = list(src.iter_traces())
        assert len(emitted) == 13

    def test_max_traces_cap(self) -> None:
        # max_traces caps the iteration even when more pages remain.
        api = _FakeAPI([_trace(i) for i in range(20)])
        src = LangfuseTraceSource(
            api=api,
            cohort_classifier=lambda _t: "failure",
            page_limit=20,
            max_traces=5,
        )
        assert len(list(src.iter_traces())) == 5

    def test_adapter_metadata_sourced(self) -> None:
        api = _FakeAPI([])
        src = LangfuseTraceSource(
            api=api,
            cohort_classifier=lambda _t: "failure",
            sdk_version="4.5.1-test",
        )
        meta = src.adapter_metadata()
        assert meta.adapter_id == "langfuse"
        assert meta.package_version  # non-empty
        assert meta.sdk_version == "4.5.1-test"
