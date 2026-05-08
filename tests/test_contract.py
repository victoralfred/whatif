"""Smoke tests for the runner contract.

These verify the public API can be imported and the model shapes round-trip.
Real integration tests come with the Langfuse adapter and replay engine.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from whatifd.contract import (
    ReplayConfig,
    ReplayOutput,
    Runner,
    ScoreCase,
    ToolCache,
    TraceInput,
    TraceOutput,
)


def test_trace_input_minimal():
    ti = TraceInput(user_message="hello")
    assert ti.user_message == "hello"
    assert ti.metadata == {}


def test_trace_input_with_metadata():
    ti = TraceInput(user_message="hi", metadata={"trace_id": "abc"})
    assert ti.metadata["trace_id"] == "abc"


def test_replay_config_defaults_are_none():
    cfg = ReplayConfig()
    assert cfg.system_prompt is None
    assert cfg.model is None
    assert cfg.overrides == {}


def test_replay_config_rejects_extra_fields():
    with pytest.raises(ValidationError):
        ReplayConfig(unknown_field="x")  # type: ignore[call-arg]


def test_tool_cache_lookup_hit_and_miss():
    tc = ToolCache(
        cache={ToolCache._key("get_weather", {"city": "Lagos"}): {"temp_c": 32}},
    )
    assert tc.lookup("get_weather", {"city": "Lagos"}) == {"temp_c": 32}
    assert tc.lookup("get_weather", {"city": "Accra"}) is None


def test_tool_cache_default_policy_is_use_original():
    tc = ToolCache()
    assert tc.policy == "use-original"


def test_replay_output_minimal():
    out = ReplayOutput(text="response")
    assert out.text == "response"
    assert out.tool_spans == []


def test_score_case_construction():
    sc = ScoreCase(
        trace_id="t-1",
        cohort="failure",
        input=TraceInput(user_message="hi"),
        original_output=TraceOutput(text="orig"),
        replayed_output=ReplayOutput(text="new"),
    )
    assert sc.cohort == "failure"
    assert sc.original_output.text == "orig"
    assert sc.replayed_output.text == "new"


def test_score_case_rejects_bad_cohort():
    with pytest.raises(ValidationError):
        ScoreCase(
            trace_id="t-1",
            cohort="other",  # type: ignore[arg-type]
            input=TraceInput(user_message="hi"),
            original_output=TraceOutput(text="orig"),
            replayed_output=ReplayOutput(text="new"),
        )


def test_runner_protocol_satisfied_by_simple_function():
    def my_runner(
        trace_input: TraceInput,
        config: ReplayConfig,
        tool_cache: ToolCache,
    ) -> ReplayOutput:
        return ReplayOutput(text=f"replayed: {trace_input.user_message}")

    # Protocol check
    assert isinstance(my_runner, Runner)
    out = my_runner(
        TraceInput(user_message="ping"),
        ReplayConfig(system_prompt="be concise"),
        ToolCache(),
    )
    assert out.text == "replayed: ping"
