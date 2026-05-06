"""Tests for `whatif.replay.result` — Phase 6.1 typed replay-stage
result.

Pin properties:

1. `ReplaySuccess` constructs with `(trace_id, cohort, output)`.
2. `ReplayFailure` constructs with a registered replay-stage code.
3. `ReplayFailure` rejects unknown codes (cardinal #1: closed-set).
4. `ReplayFailure` rejects codes from other stages (the replay
   pipeline emits only replay-stage codes).
5. Both types are frozen (mutation raises) and slotted (no
   arbitrary attribute assignment).
6. `ReplayResult` is a typing union with both variants.
"""

from __future__ import annotations

from typing import get_args

import pytest

from whatif.contract import ReplayOutput
from whatif.replay import ReplayFailure, ReplayResult, ReplaySuccess


def _output() -> ReplayOutput:
    return ReplayOutput(text="hello")


# ---------------------------------------------------------------------------
# ReplaySuccess
# ---------------------------------------------------------------------------


class TestReplaySuccess:
    def test_construct(self) -> None:
        s = ReplaySuccess(trace_id="t-1", cohort="failure", output=_output())
        assert s.trace_id == "t-1"
        assert s.cohort == "failure"
        assert s.output.text == "hello"

    def test_frozen(self) -> None:
        # frozen=True + slots=True: assignment raises
        # FrozenInstanceError (subclass of AttributeError on 3.11+).
        s = ReplaySuccess(trace_id="t-1", cohort="failure", output=_output())
        with pytest.raises(AttributeError):
            s.trace_id = "t-2"  # type: ignore[misc]

    def test_no_dict_no_arbitrary_attribute(self) -> None:
        # slots=True positive assertion: no __dict__, novel attribute
        # set fails. Matches the project convention in
        # tests/unit/whatif/types/test_failure.py — accept any of the
        # three error types because the dataclass __setattr__ /
        # slots interaction varies across Python versions.
        s = ReplaySuccess(trace_id="t-1", cohort="failure", output=_output())
        assert not hasattr(s, "__dict__")
        with pytest.raises((AttributeError, TypeError)):
            s.smuggled = "extra"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ReplayFailure — registry validation (cardinal #1)
# ---------------------------------------------------------------------------


class TestReplayFailureRegistry:
    def test_construct_with_replay_code(self) -> None:
        f = ReplayFailure(
            trace_id="t-1",
            cohort="failure",
            code="tool_cache_miss",
            message="missing get_weather output",
            details={"tool_name": "get_weather"},
        )
        assert f.code == "tool_cache_miss"
        assert f.details["tool_name"] == "get_weather"

    def test_runner_timeout_accepted(self) -> None:
        f = ReplayFailure(
            trace_id="t-1",
            cohort="failure",
            code="runner_timeout",
            message="exceeded 30s",
            details={"timeout_seconds": 30},
        )
        assert f.code == "runner_timeout"

    def test_runner_exception_accepted(self) -> None:
        f = ReplayFailure(
            trace_id="t-1",
            cohort="failure",
            code="runner_exception",
            message="ValueError",
            details={"exception_type": "ValueError", "message": "oops"},
        )
        assert f.code == "runner_exception"

    def test_unknown_code_rejected(self) -> None:
        with pytest.raises(ValueError, match="not in FAILURE_CODE_REGISTRY"):
            ReplayFailure(
                trace_id="t-1",
                cohort="failure",
                code="totally_made_up",
                message="x",
            )

    def test_non_replay_stage_code_rejected(self) -> None:
        # `scorer_unavailable` is registered with stage="score". The
        # replay pipeline must not emit it — that's the scorer's job.
        # Decoupled from the literal stage string: the test asserts
        # the rejection message names the actual registered stage,
        # so a future stage rename in the registry remains caught
        # for the right reason. (A bare `match="stage='score'"`
        # would silently pass if `scorer_unavailable`'s stage were
        # changed to e.g. "decision" — wrong-reason green test.)
        from whatif.decision.failure_codes import FAILURE_CODE_REGISTRY

        registered_stage = FAILURE_CODE_REGISTRY["scorer_unavailable"].stage
        assert registered_stage != "replay"  # premise of this test
        with pytest.raises(ValueError, match=f"stage={registered_stage!r}"):
            ReplayFailure(
                trace_id="t-1",
                cohort="failure",
                code="scorer_unavailable",
                message="x",
                details={"provider": "anthropic", "reason": "x"},
            )

    def test_decision_stage_code_rejected(self) -> None:
        # Same defense for decision-stage codes; same decoupling
        # rationale as the score-stage test above.
        from whatif.decision.failure_codes import FAILURE_CODE_REGISTRY

        registered_stage = FAILURE_CODE_REGISTRY["ci_uncomputable_for_required_cohort"].stage
        assert registered_stage != "replay"
        with pytest.raises(ValueError, match=f"stage={registered_stage!r}"):
            ReplayFailure(
                trace_id="t-1",
                cohort="failure",
                code="ci_uncomputable_for_required_cohort",
                message="x",
                details={"cohort": "failure", "reason": "x"},
            )


# ---------------------------------------------------------------------------
# ReplayFailure — frozen / slotted
# ---------------------------------------------------------------------------


class TestReplayFailureShape:
    def test_frozen(self) -> None:
        f = ReplayFailure(
            trace_id="t-1",
            cohort="failure",
            code="tool_cache_miss",
            message="x",
            details={"tool_name": "x"},
        )
        with pytest.raises(AttributeError):
            f.code = "runner_timeout"  # type: ignore[misc]

    def test_no_dict_no_arbitrary_attribute(self) -> None:
        f = ReplayFailure(
            trace_id="t-1",
            cohort="failure",
            code="tool_cache_miss",
            message="x",
            details={"tool_name": "x"},
        )
        assert not hasattr(f, "__dict__")
        with pytest.raises((AttributeError, TypeError)):
            f.smuggled = "extra"  # type: ignore[attr-defined]

    def test_details_defaults_to_empty(self) -> None:
        # Required-details validation lives at projection time
        # (`make_failure_record`), so the constructor accepts an
        # empty details map. Some codes (e.g., a future code with
        # zero required keys) won't need any.
        f = ReplayFailure(
            trace_id="t-1",
            cohort="failure",
            code="tool_cache_miss",
            message="x",
        )
        assert f.details == {}


# ---------------------------------------------------------------------------
# ReplayResult union
# ---------------------------------------------------------------------------


class TestReplayResultUnion:
    def test_union_includes_both_variants(self) -> None:
        # Pin the union shape so a future refactor that drops a
        # variant (or adds a third) surfaces here for explicit
        # review.
        variants = set(get_args(ReplayResult))
        assert variants == {ReplaySuccess, ReplayFailure}
