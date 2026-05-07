"""Tests for `whatif.adapters.protocols` — Phase 4A.1.

Pin properties:

1. The protocols are `runtime_checkable`: a class implementing the
   shape passes `isinstance`; a class missing any method fails.
2. `RawTrace` and `JudgeResult` are Pydantic v2 strict
   (`extra="forbid"`); a typo raises `ValidationError`.
3. `RawTrace.user_message` and `RawTrace.original_response` are
   `Sensitive[str]` typed; an unwrapped raw string is rejected.
4. `JudgeResult.rationale` is `Sensitive[str]`; same enforcement.
5. `AdapterMetadata` is frozen + slotted; mutation raises and
   arbitrary attributes are rejected.
6. `whatif.adapters` is NOT imported by `import whatif` (lazy-load
   contract per Phase 4A gate).
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from whatif.adapters import (
    AdapterMetadata,
    JudgeResult,
    RawTrace,
    Scorer,
    TraceSource,
)
from whatif.adapters.protocols import CacheKeyComponents
from whatif.contract import ScoreCase
from whatif.types.sensitive import Sensitive
from whatif.types.statistical import ClusterKeySupport


def _wrap(s: str) -> Sensitive[str]:
    return Sensitive(s, classification="user_content")


# ---------------------------------------------------------------------------
# Protocol shape (runtime_checkable)
# ---------------------------------------------------------------------------


class _GoodTraceSource:
    def iter_traces(self) -> Iterator[RawTrace]:
        yield from ()

    def adapter_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(adapter_id="test", package_version="0.0.0")

    def cluster_key_support(self) -> ClusterKeySupport:
        return ClusterKeySupport(supported=False)


class _BadTraceSource:
    # Missing cluster_key_support — should fail isinstance(TraceSource).
    def iter_traces(self) -> Iterator[RawTrace]:
        yield from ()

    def adapter_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(adapter_id="bad", package_version="0.0.0")


class _GoodScorer:
    def score(self, case: ScoreCase) -> JudgeResult:
        raise NotImplementedError

    def cache_key_components(self, case: ScoreCase) -> CacheKeyComponents:
        raise NotImplementedError

    def adapter_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(adapter_id="test-scorer", package_version="0.0.0")


class _BadScorer:
    # Missing cache_key_components.
    def score(self, case: ScoreCase) -> JudgeResult:
        raise NotImplementedError

    def adapter_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(adapter_id="bad-scorer", package_version="0.0.0")


class TestProtocolShape:
    def test_good_trace_source_passes_isinstance(self) -> None:
        assert isinstance(_GoodTraceSource(), TraceSource)

    def test_bad_trace_source_fails_isinstance(self) -> None:
        # `runtime_checkable` checks attribute presence, not signatures.
        # Missing-method rejection is the load-bearing surface.
        assert not isinstance(_BadTraceSource(), TraceSource)

    def test_good_scorer_passes_isinstance(self) -> None:
        assert isinstance(_GoodScorer(), Scorer)

    def test_bad_scorer_fails_isinstance(self) -> None:
        assert not isinstance(_BadScorer(), Scorer)


# ---------------------------------------------------------------------------
# RawTrace — strict, Sensitive-required
# ---------------------------------------------------------------------------


def _raw_trace_kwargs() -> dict[str, object]:
    return {
        "trace_id": "t-1",
        "cohort": "failure",
        "user_message": _wrap("hello"),
        "original_response": _wrap("hi back"),
    }


class TestRawTrace:
    def test_minimal_construction(self) -> None:
        rt = RawTrace(**_raw_trace_kwargs())
        assert rt.trace_id == "t-1"
        assert rt.cohort == "failure"
        assert rt.cluster_key is None
        assert rt.skip_reason is None
        assert rt.tool_spans == []
        assert rt.metadata == {}

    def test_extra_field_rejected(self) -> None:
        kwargs = _raw_trace_kwargs()
        kwargs["mystery"] = "x"
        with pytest.raises(ValidationError):
            RawTrace(**kwargs)

    def test_unwrapped_user_message_rejected(self) -> None:
        kwargs = _raw_trace_kwargs()
        kwargs["user_message"] = "raw string"  # not Sensitive[str]
        with pytest.raises(ValidationError):
            RawTrace(**kwargs)

    def test_unwrapped_original_response_rejected(self) -> None:
        kwargs = _raw_trace_kwargs()
        kwargs["original_response"] = "raw string"
        with pytest.raises(ValidationError):
            RawTrace(**kwargs)


# ---------------------------------------------------------------------------
# JudgeResult — strict, Sensitive rationale, score|None
# ---------------------------------------------------------------------------


def _judge_result_kwargs() -> dict[str, object]:
    return {
        "trace_id": "t-1",
        "score": 0.85,
        "rationale": _wrap("looks good"),
        "judge_model_id": "claude-opus-4-7",
    }


class TestJudgeResult:
    def test_minimal_construction(self) -> None:
        jr = JudgeResult(**_judge_result_kwargs())
        assert jr.score == 0.85
        assert jr.judge_model_snapshot is None  # explicit-None contract

    def test_score_none_signals_structural_failure(self) -> None:
        kwargs = _judge_result_kwargs()
        kwargs["score"] = None
        jr = JudgeResult(**kwargs)
        assert jr.score is None  # cardinal #1 surfaces this as FailureRecord

    def test_unwrapped_rationale_rejected(self) -> None:
        kwargs = _judge_result_kwargs()
        kwargs["rationale"] = "raw rationale"
        with pytest.raises(ValidationError):
            JudgeResult(**kwargs)

    def test_extra_field_rejected(self) -> None:
        kwargs = _judge_result_kwargs()
        kwargs["mystery"] = "x"
        with pytest.raises(ValidationError):
            JudgeResult(**kwargs)


# ---------------------------------------------------------------------------
# AdapterMetadata — frozen + slotted
# ---------------------------------------------------------------------------


class TestAdapterMetadata:
    def test_construction(self) -> None:
        m = AdapterMetadata(adapter_id="x", package_version="1.0.0")
        assert m.adapter_id == "x"
        assert m.sdk_version is None

    def test_frozen(self) -> None:
        m = AdapterMetadata(adapter_id="x", package_version="1.0.0")
        # `dataclasses.FrozenInstanceError` extends `AttributeError`.
        with pytest.raises(AttributeError):
            m.adapter_id = "y"  # type: ignore[misc]

    def test_slots_rejects_arbitrary_attrs(self) -> None:
        # frozen + slots together raise on any setattr — frozen reports
        # via dataclass machinery (TypeError on the super().__setattr__
        # path inside `<string>:18`) when the attribute isn't in slots.
        # Accept either TypeError or AttributeError.
        m = AdapterMetadata(adapter_id="x", package_version="1.0.0")
        with pytest.raises((TypeError, AttributeError)):
            m.mystery = "x"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Lazy-load contract
# ---------------------------------------------------------------------------


class TestLazyLoad:
    def test_import_whatif_does_not_load_adapters(self) -> None:
        # Subprocess so we measure a fresh interpreter, not a session
        # already polluted by other tests' imports. The Phase 4A gate
        # requires that `import whatif` does not trigger
        # `whatif.adapters` (or any concrete adapter module).
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import whatif, sys; "
                "loaded = [m for m in sys.modules if m.startswith('whatif.adapters')]; "
                "print(loaded)",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "[]", (
            f"`import whatif` triggered adapter imports: {result.stdout!r}"
        )
