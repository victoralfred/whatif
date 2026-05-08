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
from whatif.adapters import TraceSource

from whatif_langfuse import LangfuseTraceSource

# Test scaffolds below are intentionally NOT `frozen=True` / `slots=True`
# nor `Protocol`-typed. The project's style for production code
# (cardinal #6 typed boundaries; frozen + slots dataclasses) doesn't
# apply to test fakes — these classes exist to be mutated in-fixture
# (`_FakeTraceClient.requested_pages` is appended to during the
# protocol-call shape check) and rebound across test methods. If a
# future contributor mechanically applies the production style to
# this file, the conformance harness's auditing surface breaks.


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
    """Single-page Langfuse `trace.list` fake.

    Behavior:
    - Page 1 (or unspecified): returns every fixture trace.
    - Page ≥ 2: returns empty data (the standard exhaust signal).
    - Tracks requested pages so the fixture can detect adapter bugs
      that re-fetch page 1 — a future conformance test asserting
      "no duplicate traces across pages" would catch that bug
      because both calls return identical data; this fake records
      the call sequence to make the bug auditable.

    What this fake does NOT simulate:
    - True multi-page pagination with distinct content per page.
      That contract is exercised in
      `TestLangfuseSpecificBehaviors::test_pagination_streams_across_pages`
      via a dedicated `_PaginatingClient`.
    """

    def __init__(self, traces: list[_FakeTrace]) -> None:
        self._traces = traces
        self.requested_pages: list[int | None] = []

    def list(
        self,
        *,
        page: int | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> _FakeTracesResponse:
        # Reject negative/zero pages structurally — the Langfuse
        # API is 1-indexed, and an adapter that emits page=0 is
        # broken. `if/raise` instead of `assert` so the guard
        # survives `python -O` (asserts strip under optimized
        # builds).
        #
        # The `page is not None` short-circuit looks dead given
        # `LangfuseTraceSource.iter_traces` ALWAYS passes
        # `page=<int starting at 1>` — but the `_TraceClientLike`
        # Protocol declares `page: int | None = None`, so a
        # future direct caller (test, alternative iterator) is
        # protocol-allowed to pass None. Without the None
        # short-circuit, `None < 1` raises TypeError and the
        # guard's intent (catch the page-0 bug) gets buried under
        # an unrelated error type. Keep the short-circuit.
        if page is not None and page < 1:
            raise ValueError(f"page must be ≥1; got {page}")
        self.requested_pages.append(page)
        # Single-page mock: return everything on page 1, empty on 2+.
        # The harness's `test_iter_traces_is_generator_or_iterator`
        # only consumes the iterator's first batch and asserts
        # iterator-ness; the harness's emit-content tests collect
        # the full stream but with a small fixture (3 traces in a
        # page-limit-10 source), the page-1 return is also the
        # exhaust signal. This is intentional but minimal — the
        # multi-page → short-page termination contract is exercised
        # explicitly in `TestLangfuseSpecificBehaviors::
        # test_pagination_streams_across_pages` below using a
        # dedicated `_PaginatingClient`. If this fixture grows new
        # multi-page assertions, replace `_FakeTraceClient` with the
        # paginating variant rather than expanding this one.
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
        # `canonical_json_bytes` uses tight separators (`,` and `:`).
        assert unwrapped == '{"a":1,"b":2}'

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

    def test_fake_trace_client_records_requested_pages(self) -> None:
        # Make `_FakeTraceClient.requested_pages` load-bearing —
        # not just diagnostic state. With a fixture of 3 traces and
        # `page_limit=10`, `iter_traces` should call list(page=1)
        # exactly once and stop on the short-page exhaust signal
        # (3 < 10). A future regression that re-fetches page 1, or
        # eagerly probes page 2 even after a short response, fails
        # this assertion immediately.
        api = _FakeAPI([_trace(0), _trace(1), _trace(2)])
        src = LangfuseTraceSource(
            api=api,
            cohort_classifier=lambda _t: "failure",
            page_limit=10,
        )
        list(src.iter_traces())
        assert api.trace.requested_pages == [1]

    def test_fake_trace_client_rejects_page_zero_and_negative(self) -> None:
        # Pin the page-validation branch on the test scaffold itself.
        # The fake mirrors the Langfuse 1-indexed contract; without
        # this test, a future refactor of `_FakeTraceClient.list`
        # could silently drop the guard and the harness would still
        # pass on the dominant page=1 path. Make the contract load-
        # bearing with explicit page=0 and page=-1 cases.
        client = _FakeTraceClient([])
        with pytest.raises(ValueError, match=r"page must be ≥1; got 0"):
            client.list(page=0)
        with pytest.raises(ValueError, match=r"page must be ≥1; got -1"):
            client.list(page=-1)
        # `page=None` and `page=1` are valid — no raise.
        client.list(page=None)
        client.list(page=1)

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
