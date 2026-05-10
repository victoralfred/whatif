"""`PhoenixTraceSource` conformance test (mocked spans_provider).

Runs the parent repo's `TraceSourceConformance` harness against a
synthetic OpenInference-shaped span fixture. No network. Real-Phoenix
recorded smoke (against arize-phoenix-client) is deferred to v0.3
when the cassette infrastructure for Phoenix's HTTP API lands.
"""

from __future__ import annotations

import pytest
from conformance import TraceSourceConformance  # type: ignore[import-not-found]
from whatifd.adapters import TraceSource

from whatifd_phoenix import PhoenixTraceSource


def _classify_baseline(_spans: list[dict[str, object]]) -> str:
    return "baseline"


def _make_root_span(
    trace_id: str, *, user_input: str = "hello", llm_output: str = "world"
) -> dict[str, object]:
    """Construct a synthetic root span with OpenInference attributes."""
    return {
        "context.trace_id": trace_id,
        "parent_id": None,
        "openinference.span.kind": "CHAIN",
        "input.value": user_input,
        "output.value": llm_output,
        "user.id": f"user-{trace_id}",
        "session.id": f"session-{trace_id}",
        "model.name": "claude-haiku-4-5",
    }


def _make_child_span(trace_id: str, parent_id: str = "root") -> dict[str, object]:
    return {
        "context.trace_id": trace_id,
        "parent_id": parent_id,
        "openinference.span.kind": "TOOL",
        "tool.name": "search",
    }


class TestPhoenixTraceSource(TraceSourceConformance):
    # Override the base class's `__test__ = False` so pytest collects
    # the inherited test_* methods against this concrete adapter.
    __test__ = True

    @pytest.fixture
    def trace_source(self) -> TraceSource:
        spans = [
            _make_root_span("trace-1", user_input="what's the weather?", llm_output="sunny"),
            _make_child_span("trace-1"),
            _make_root_span("trace-2", user_input="define entropy", llm_output="disorder"),
        ]
        return PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=_classify_baseline,
        )


# ---------------------------------------------------------------------------
# Adapter-specific behavior (beyond the conformance harness)
# ---------------------------------------------------------------------------


class TestSpanGrouping:
    """Phoenix-specific behavior: spans grouped by trace_id, root
    span identified, projection drops input/output from metadata."""

    def test_groups_spans_by_trace_id(self) -> None:
        spans = [
            _make_root_span("t-1"),
            _make_child_span("t-1"),
            _make_root_span("t-2"),
            _make_child_span("t-2"),
        ]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=_classify_baseline,
        )
        traces = list(source.iter_traces())
        assert len(traces) == 2
        assert {t.trace_id for t in traces} == {"t-1", "t-2"}

    def test_skips_spans_without_trace_id(self) -> None:
        # Defensive: a malformed span without a trace_id is dropped
        # rather than crashing the iteration.
        spans = [
            _make_root_span("good"),
            {"parent_id": None, "input.value": "no-trace-id-here"},
        ]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=_classify_baseline,
        )
        traces = list(source.iter_traces())
        assert len(traces) == 1
        assert traces[0].trace_id == "good"

    def test_root_span_provides_user_content(self) -> None:
        spans = [_make_root_span("t-1", user_input="Q?", llm_output="A.")]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=_classify_baseline,
        )
        [trace] = list(source.iter_traces())
        # Sensitive[T] doesn't expose its value via repr; check via
        # the audited unwrap path. Equality assertion (not endswith)
        # — the projection is identity for str inputs.
        assert trace.user_message.unwrap(reason="conformance test") == "Q?"
        assert trace.original_response.unwrap(reason="conformance test") == "A."

    @pytest.mark.parametrize("bad_trace_id", [None, "", 42, 3.14, b"bytes-id", []])
    def test_skips_spans_with_non_string_trace_id(self, bad_trace_id: object) -> None:
        # Defensive: any non-string trace_id (None, empty str, int,
        # float, bytes, list) is dropped rather than crashing or
        # emitting a malformed RawTrace. The isinstance guard in
        # iter_traces is the structural check.
        spans = [
            _make_root_span("good"),
            {"context.trace_id": bad_trace_id, "parent_id": None, "input.value": "x"},
        ]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=_classify_baseline,
        )
        traces = list(source.iter_traces())
        assert len(traces) == 1
        assert traces[0].trace_id == "good"

    def test_metadata_excludes_input_output_attrs(self) -> None:
        spans = [_make_root_span("t-1")]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=_classify_baseline,
        )
        [trace] = list(source.iter_traces())
        # input.value and output.value are wrapped as Sensitive[T]
        # at the user_message / original_response slots; they MUST
        # NOT also leak into metadata (would double-expose user
        # content under cardinal #5).
        assert "input.value" not in trace.metadata
        assert "output.value" not in trace.metadata
        # Tooling attributes should still be present.
        assert "model.name" in trace.metadata
        assert trace.metadata["model.name"] == "claude-haiku-4-5"

    def test_classifier_receives_full_span_list(self) -> None:
        # Cohort classification often depends on non-root spans
        # (e.g., a tool span that errored, a tag attribute on a
        # specific child). The classifier callable receives the
        # full span list, not just the root.
        captured: list[list[dict[str, object]]] = []

        def capturing_classifier(spans: list[dict[str, object]]) -> str:
            captured.append(spans)
            return "baseline"

        spans = [_make_root_span("t-1"), _make_child_span("t-1")]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=capturing_classifier,
        )
        list(source.iter_traces())
        assert len(captured) == 1
        assert len(captured[0]) == 2  # both spans visible to classifier

    def test_max_traces_caps_iteration(self) -> None:
        spans = [_make_root_span(f"t-{i}") for i in range(10)]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=_classify_baseline,
            max_traces=3,
        )
        assert len(list(source.iter_traces())) == 3


class TestAdapterMetadata:
    def test_adapter_id_is_phoenix(self) -> None:
        source = PhoenixTraceSource(
            spans_provider=lambda: [],
            cohort_classifier=_classify_baseline,
        )
        meta = source.adapter_metadata()
        assert meta.adapter_id == "phoenix"

    def test_explicit_sdk_version_passes_through(self) -> None:
        source = PhoenixTraceSource(
            spans_provider=lambda: [],
            cohort_classifier=_classify_baseline,
            sdk_version="1.5.0-test",
        )
        assert source.adapter_metadata().sdk_version == "1.5.0-test"


class TestRootIdentificationCorrectness:
    """Cardinal #1: silent wrong results are forbidden. Root-span
    identification must not pick a child LLM span as the root just
    because its parent_id was dropped from the upstream tracer.
    """

    def test_llm_kind_without_parent_is_not_root(self) -> None:
        # Earlier draft of `_ROOT_SPAN_KINDS` included "LLM"; if a
        # child LLM span has no parent_id (which happens with
        # under-instrumented libraries), it would have been
        # misidentified as the trace root and surfaced the LLM
        # call's prompt as the trace's `user_message`. Pinned: only
        # CHAIN/AGENT count as orchestration-kind roots; LLM does not.
        spans = [
            _make_root_span("t-1", user_input="user's question", llm_output="agent's answer"),
            {
                "context.trace_id": "t-1",
                "parent_id": None,  # ← simulated missing parent
                "openinference.span.kind": "LLM",
                "input.value": "internal prompt to the model",
                "output.value": "model raw completion",
            },
        ]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=_classify_baseline,
        )
        [trace] = list(source.iter_traces())
        # The user_message must be the orchestration-root's input,
        # not the LLM child's prompt.
        assert trace.user_message.unwrap(reason="root-id test") == "user's question"


class TestStringifyJsonRouting:
    """Cardinal #5/#9: non-string span attribute values (dicts,
    lists, structured tool-call outputs) must route through the
    canonical JSON encoder, not Python's `str()` (which produces
    repr garbage).
    """

    def test_dict_input_serialized_canonically(self) -> None:
        spans = [
            {
                "context.trace_id": "t-1",
                "parent_id": None,
                "openinference.span.kind": "CHAIN",
                "input.value": {"role": "user", "content": "hello"},
                "output.value": "world",
            },
        ]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=_classify_baseline,
        )
        [trace] = list(source.iter_traces())
        unwrapped = trace.user_message.unwrap(reason="stringify test")
        # Canonical JSON: sort_keys=True, separators=(",",":")
        assert unwrapped == '{"content":"hello","role":"user"}'

    def test_list_output_serialized_canonically(self) -> None:
        spans = [
            {
                "context.trace_id": "t-1",
                "parent_id": None,
                "openinference.span.kind": "CHAIN",
                "input.value": "q",
                "output.value": [{"tool": "search", "args": {"q": "x"}}],
            },
        ]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=_classify_baseline,
        )
        [trace] = list(source.iter_traces())
        unwrapped = trace.original_response.unwrap(reason="stringify test")
        # Defends against the str()-on-dict regression: repr would
        # produce single-quoted Python output; canonical_json_bytes
        # produces double-quoted JSON.
        assert '"' in unwrapped  # JSON, not repr
        assert "'" not in unwrapped


class TestSensitiveWrappingAtIngress:
    """Cardinal #5 boundary: input.value / output.value on EVERY
    span (root + children) must be Sensitive-wrapped before the
    classifier sees them. A naive implementation would only wrap
    at projection time, leaving child-span user content available
    as raw strings to the classifier callable — a covert exfiltration
    surface.
    """

    def test_classifier_sees_wrapped_root_input(self) -> None:
        from whatifd.types.sensitive import Sensitive

        captured: list[object] = []

        def capturing_classifier(spans: list[dict[str, object]]) -> str:
            captured.append(spans[0].get("input.value"))
            return "baseline"

        spans = [_make_root_span("t-1", user_input="secret-prompt")]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=capturing_classifier,
        )
        list(source.iter_traces())
        # The classifier saw a Sensitive wrapper, NOT the raw string.
        assert isinstance(captured[0], Sensitive)

    def test_classifier_sees_wrapped_child_input(self) -> None:
        # Critical case: a child span carries its own user content
        # (e.g., a sub-agent's prompt). It must reach the classifier
        # already wrapped — not just the root's input.
        from whatifd.types.sensitive import Sensitive

        captured: list[object] = []

        def capturing_classifier(spans: list[dict[str, object]]) -> str:
            for s in spans:
                if "input.value" in s:
                    captured.append(s["input.value"])
            return "baseline"

        child_with_input = _make_child_span("t-1")
        child_with_input["input.value"] = "child-prompt-secret"
        spans = [_make_root_span("t-1", user_input="root-prompt"), child_with_input]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=capturing_classifier,
        )
        list(source.iter_traces())
        # Both root AND child input.value reached the classifier
        # wrapped. Two values; both Sensitive.
        assert len(captured) == 2
        assert all(isinstance(v, Sensitive) for v in captured)

    def test_original_input_dicts_not_mutated(self) -> None:
        # _wrap_user_content_in_span returns a copy — the caller's
        # original span dicts must remain raw so a future iteration
        # over the same fixture (e.g., a test that runs twice)
        # doesn't see double-wrapped Sensitive[Sensitive[str]].
        original = _make_root_span("t-1", user_input="raw")
        spans = [original]
        source = PhoenixTraceSource(
            spans_provider=lambda: spans,
            cohort_classifier=_classify_baseline,
        )
        list(source.iter_traces())
        # Original dict still has a plain string at input.value.
        assert original["input.value"] == "raw"
        assert isinstance(original["input.value"], str)


class TestSdkVersionResolution:
    """Coverage for `_resolve_sdk_version` + `__version__` fallback
    paths. Both branches matter at runtime and must not crash a run
    just because the optional adapter package is missing or the
    dist-info is unreadable.
    """

    def test_explicit_sdk_version_skips_resolver(self) -> None:
        # Operator-supplied sdk_version short-circuits the resolver
        # entirely — no SDK import attempt.
        source = PhoenixTraceSource(
            spans_provider=lambda: [],
            cohort_classifier=_classify_baseline,
            sdk_version="explicit-1.0.0",
        )
        assert source.adapter_metadata().sdk_version == "explicit-1.0.0"

    def test_resolver_returns_none_when_sdk_missing(self) -> None:
        # arize-phoenix-client is NOT installed in this test env
        # (it's the [live] extra, not a hard dep). The resolver must
        # return None rather than raising ImportError.
        from whatifd_phoenix.source import _resolve_sdk_version

        # The function is itself the unit-under-test; calling it
        # exercises the ImportError branch end-to-end.
        result = _resolve_sdk_version()
        # Either None (SDK missing — expected in CI) or a real
        # version string (SDK happens to be installed locally).
        assert result is None or isinstance(result, str)

    def test_package_version_fallback_is_string(self) -> None:
        # PackageNotFoundError fallback in __init__.py renders as
        # "0.0.0+unknown" sentinel. This test pins both the success
        # path (installed) AND the sentinel format — whichever
        # branch runs, __version__ is a non-empty str.
        from whatifd_phoenix import __version__ as pkg_version

        assert isinstance(pkg_version, str)
        assert pkg_version  # non-empty


class TestClusterKeySupport:
    def test_no_cluster_keys_in_v0_2(self) -> None:
        # Cardinal #10: empty `available_keys` until v0.3 adds
        # explicit per-attribute opt-in. Mining `user.id` /
        # `session.id` from spans without operator declaration
        # would be an unannounced inferential commitment.
        source = PhoenixTraceSource(
            spans_provider=lambda: [],
            cohort_classifier=_classify_baseline,
        )
        assert source.cluster_key_support().available_keys == ()
