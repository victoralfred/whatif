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
from whatif.cache.keying.v1 import CacheKeyComponents
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
        return ClusterKeySupport(available_keys=())


class _BadTraceSource:
    """Missing `cluster_key_support` — should fail
    `isinstance(TraceSource)`.

    Note on the limits of this check: `runtime_checkable` Protocol
    isinstance() only verifies attribute *presence*, not argument
    counts, parameter names, or return types. A class that defines
    `cluster_key_support()` as `def cluster_key_support(self,
    extra_arg): ...` would pass isinstance here but break at the
    actual call site. The Phase 4A.2 conformance harness is the
    stronger gate — it invokes each method with realistic inputs and
    asserts return-shape conformance, catching signature drift this
    test cannot."""

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

    def test_score_field_is_required(self) -> None:
        # Cardinal #1: "missing score" and "explicit-None scoring
        # failure" must be distinguishable. `Field(...)` makes the
        # field required — omitting it raises ValidationError, while
        # passing None is the documented structural-failure signal.
        kwargs = _judge_result_kwargs()
        del kwargs["score"]
        with pytest.raises(ValidationError):
            JudgeResult(**kwargs)

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
        # On CPython 3.14, frozen + slots dataclass setattr of a
        # non-slot attribute raises TypeError from the dataclass-
        # generated __setattr__ (it calls super().__setattr__ with a
        # super(cls, self) object whose type doesn't match, surfacing
        # as `super(type, obj): obj is not an instance...`). Older
        # CPython versions surfaced AttributeError from the slots
        # layer first. Accept the union to stay portable, and pin
        # the current shape with a sub-assertion so a future Python
        # change that produces a *different* exception class (e.g.,
        # a new SlotsViolationError) fails loudly here rather than
        # silently passing through `pytest.raises(Exception)`.
        m = AdapterMetadata(adapter_id="x", package_version="1.0.0")
        with pytest.raises((TypeError, AttributeError)) as excinfo:
            m.mystery = "x"  # type: ignore[attr-defined]
        assert excinfo.type in (TypeError, AttributeError)


# ---------------------------------------------------------------------------
# Lazy-load contract
# ---------------------------------------------------------------------------


class TestReExports:
    def test_cluster_key_support_is_canonical_object(self) -> None:
        # The re-export from `whatif.adapters` MUST be the same object
        # as the canonical home in `whatif.types.statistical`. Catches
        # an accidental shadowing (e.g., a future contributor defining
        # a local `ClusterKeySupport` in adapters/__init__.py) that
        # would silently fork the type.
        from whatif.adapters import ClusterKeySupport as Reexported
        from whatif.types.statistical import ClusterKeySupport as Canonical

        assert Reexported is Canonical


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
            check=False,
        )
        assert result.returncode == 0, (
            f"subprocess failed (exit {result.returncode}); stderr:\n{result.stderr}"
        )
        # Whatif-namespace stderr filter: a regression that exits 0
        # but emits a whatif-related deprecation warning passes the
        # exit-code check; this catches it. Transitive third-party
        # warnings (e.g., from pydantic, anyio) are out of scope.
        whatif_stderr = "\n".join(
            line for line in result.stderr.splitlines() if "whatif" in line.lower()
        )
        assert whatif_stderr == "", f"unexpected whatif-related stderr:\n{whatif_stderr}"
        assert result.stdout.strip() == "[]", (
            f"`import whatif` triggered adapter imports: {result.stdout!r}"
        )

    def test_core_modules_do_not_load_adapters(self) -> None:
        # Strengthens the lazy-load contract: not just `import whatif`,
        # but every load-bearing core module. If any of these grows an
        # adapter import (e.g., a future refactor moves a helper out
        # of an adapter and a core module reaches back), this test
        # fails before the lazy-load boundary is silently weakened.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import whatif.cli, whatif.diff, whatif.config, whatif.contract, "
                "whatif.cache, whatif.render, sys; "
                "loaded = sorted(m for m in sys.modules "
                "if m.startswith('whatif.adapters')); "
                "print(loaded)",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"subprocess failed (exit {result.returncode}); stderr:\n{result.stderr}"
        )
        # Whatif-namespace stderr filter: a regression that exits 0
        # but emits a whatif-related deprecation warning passes the
        # exit-code check; this catches it. Transitive third-party
        # warnings (e.g., from pydantic, anyio) are out of scope.
        whatif_stderr = "\n".join(
            line for line in result.stderr.splitlines() if "whatif" in line.lower()
        )
        assert whatif_stderr == "", f"unexpected whatif-related stderr:\n{whatif_stderr}"
        assert result.stdout.strip() == "[]", (
            f"core modules triggered adapter imports: {result.stdout!r}"
        )
