"""Phase 9B — Real-adapter smoke (product proof).

End-to-end pipeline runs that exercise both real adapter packages
(`whatifd_langfuse.LangfuseTraceSource` and
`whatifd_inspect_ai.InspectAIScorer`) through `run_pipeline`. Three
scenarios — Ship, Don't Ship, Inconclusive — match the verdict
contract from Phase 9A but with the real adapter projection layers
in the path.

## What "real" means here

- **`LangfuseTraceSource` is the real adapter.** The HTTP transport
  is replaced with a synthetic `_FakeAPI` that produces objects
  matching the Langfuse SDK's `Trace` shape. The adapter's
  `iter_traces` / `_project` / `Sensitive` wrapping / pagination
  logic — the load-bearing surface — runs unchanged. This mirrors
  the conformance harness pattern in
  `packages/whatifd-langfuse/tests/test_conformance.py`; the
  cassette-replay test in `test_recorded_smoke.py` proves the same
  shape against real Langfuse responses, so swapping in the
  synthetic API here doesn't lose coverage.
- **`InspectAIScorer` is the real adapter.** The `score_fn` is a
  deterministic mock that returns an Inspect-AI-`Score`-shaped
  object. This is the documented mocked-only mode for the
  inspect-ai package (see its README "Why no recorded-smoke" — the
  real-network surface is the model provider behind Inspect, not
  Inspect itself).

## Why not the typer CLI

The Phase 8.2 CLI dispatcher (`_run_fork_pipeline`) is still a
stub returning `EXIT_INCONCLUSIVE_OR_SETUP_FAILURE` with a clear
"Phase 4 adapter integration not yet wired" message. CLI wiring
is Phase 10 release work; Phase 9B's gate item is "three smoke
scenarios pass" against the real adapters at the contract surface,
which is `run_pipeline`. The lazy-load assertion (real adapters
not imported by `import whatifd`) is already covered in
`tests/unit/whatifd/adapters/test_protocols.py::
test_core_modules_do_not_load_real_adapter_packages`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

import pytest
from whatifd_inspect_ai import InspectAIScorer
from whatifd_langfuse import LangfuseTraceSource

from whatifd.adapters.protocols import RawTrace
from whatifd.contract import ReplayOutput, ScoreCase, TraceInput, TraceOutput
from whatifd.pipeline import run_pipeline
from whatifd.types.policy import DecisionPolicy, TrustFloor

from ._fixtures import (
    _default_cache_summary,
    _default_methodology,
    _default_runtime,
)

# ---------------------------------------------------------------------------
# Synthetic Langfuse SDK shapes (mirrors
# `packages/whatifd-langfuse/tests/test_conformance.py::_FakeTrace`).
# ---------------------------------------------------------------------------


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
    """Single-page fake. Page 1 returns all traces; page ≥2 empty."""

    def __init__(self, traces: list[_FakeTrace]) -> None:
        self._traces = traces

    def list(
        self,
        *,
        page: int | None = None,
        limit: int | None = None,
        **_kwargs: Any,
    ) -> _FakeTracesResponse:
        if page is not None and page < 1:
            raise ValueError(f"page must be ≥1; got {page}")
        if page is None or page == 1:
            return _FakeTracesResponse(data=list(self._traces))
        return _FakeTracesResponse(data=[])


class _FakeAPI:
    def __init__(self, traces: list[_FakeTrace]) -> None:
        self.trace = _FakeTraceClient(traces)


def _trace(idx: int, *, cohort: str) -> _FakeTrace:
    return _FakeTrace(
        id=f"{cohort}-{idx:02d}",
        input=f"prompt {cohort} {idx}",
        output=f"response {cohort} {idx}",
        metadata={"cohort_hint": cohort},
        tags=[cohort],
        user_id=None,
        session_id=None,
    )


# ---------------------------------------------------------------------------
# Inspect AI Score shape.
# ---------------------------------------------------------------------------


@dataclass
class _FakeScore:
    value: float
    explanation: str
    answer: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    history: list[Any] = field(default_factory=list)


def _build_source(traces: list[_FakeTrace]) -> LangfuseTraceSource:
    return LangfuseTraceSource(
        api=_FakeAPI(traces),
        cohort_classifier=lambda t: "failure" if "failure" in (t.tags or []) else "baseline",
        page_limit=100,
        sdk_version="9b-test",
    )


def _build_scorer(score_fn: Callable[[ScoreCase], _FakeScore]) -> InspectAIScorer:
    return InspectAIScorer(
        score_fn=score_fn,
        judge_provider="anthropic",
        judge_model_id="claude-opus-4-7",
        rubric_id="9b-faithfulness",
        rubric_text="Real-adapter smoke rubric",
        scoring_parameters=MappingProxyType({"temperature": 0.0}),
        sdk_version="9b-test",
    )


def _delta_fn_from(scorer: InspectAIScorer) -> Callable[[RawTrace], float]:
    """Bridge: RawTrace → ScoreCase → InspectAIScorer.score → float.

    Phase 9B exercises the real scorer at the boundary; the pipeline
    consumes a delta so we project `JudgeResult.score` through. A
    None score (cardinal #1 structural failure) raises so the
    pipeline records it as a `scorer_unavailable` `FailureRecord`,
    which is the correct surface for the smoke test (failure-as-data
    propagates through the report)."""

    def _df(rt: RawTrace) -> float:
        case = ScoreCase(
            trace_id=rt.trace_id,
            cohort=rt.cohort,  # type: ignore[arg-type]
            input=TraceInput(
                user_message=rt.user_message.unwrap(reason="9B integration: feed scorer")
            ),
            original_output=TraceOutput(
                text=rt.original_response.unwrap(reason="9B integration: feed scorer")
            ),
            replayed_output=ReplayOutput(text="(replayed)"),
        )
        result = scorer.score(case)
        if result.score is None:
            raise RuntimeError("scorer returned None; cardinal-#1 structural failure")
        return result.score

    return _df


# ---------------------------------------------------------------------------
# Scenarios.
# ---------------------------------------------------------------------------


def test_real_adapters_ship() -> None:
    failures = [_trace(i, cohort="failure") for i in range(20)]
    baselines = [_trace(i, cohort="baseline") for i in range(20)]
    source = _build_source([*failures, *baselines])

    def _score(case: ScoreCase) -> _FakeScore:
        idx = int(case.trace_id.split("-")[1])
        if case.cohort == "failure":
            return _FakeScore(
                value=0.20 if idx < 14 else 0.0,
                explanation=f"failure {idx}",
            )
        return _FakeScore(value=0.01, explanation=f"baseline {idx}")

    scorer = _build_scorer(_score)
    floor = TrustFloor()
    policy = DecisionPolicy()
    report = run_pipeline(
        source,
        delta_fn=_delta_fn_from(scorer),
        floor=floor,
        policy=policy,
        runtime=_default_runtime(floor=floor, policy=policy),
        methodology=_default_methodology(),
        cache_summary=_default_cache_summary(),
    )
    assert report.verdict_state == "ship", report.verdict_state
    assert not report.failures


def test_real_adapters_dont_ship() -> None:
    failures = [_trace(i, cohort="failure") for i in range(20)]
    baselines = [_trace(i, cohort="baseline") for i in range(20)]
    source = _build_source([*failures, *baselines])

    def _score(case: ScoreCase) -> _FakeScore:
        idx = int(case.trace_id.split("-")[1])
        if case.cohort == "failure":
            if idx < 14:
                return _FakeScore(value=0.28, explanation="improved")
            if idx < 17:
                return _FakeScore(value=0.0, explanation="unchanged")
            return _FakeScore(value=-0.10, explanation="regressed")
        # baseline: 1 improved, 13 unchanged, 6 regressed → 30%
        # regression rate exceeds policy.max_baseline_regression_ratio=0.10.
        if idx == 0:
            return _FakeScore(value=0.10, explanation="improved")
        if idx < 14:
            return _FakeScore(value=0.0, explanation="unchanged")
        return _FakeScore(value=-0.18, explanation="regressed")

    scorer = _build_scorer(_score)
    floor = TrustFloor()
    policy = DecisionPolicy()
    report = run_pipeline(
        source,
        delta_fn=_delta_fn_from(scorer),
        floor=floor,
        policy=policy,
        runtime=_default_runtime(floor=floor, policy=policy),
        methodology=_default_methodology(),
        cache_summary=_default_cache_summary(),
    )
    assert report.verdict_state == "dont_ship", report.verdict_state


def test_real_adapters_inconclusive() -> None:
    # Floor failure: baseline cohort has only 3 scored traces (below
    # `floor.min_scored_per_required_cohort=5`), forcing Inconclusive
    # regardless of policy. The InspectAIScorer projects raw values
    # to `JudgeResult.score`; an Inspect-AI-style `value="error"`
    # (non-numeric) projects to `score=None` (cardinal #1), which the
    # `_delta_fn_from` bridge raises into a structured FailureRecord.
    # Combined with the small baseline cohort, that's the floor
    # signal we want.
    failures = [_trace(i, cohort="failure") for i in range(15)]
    baselines = [_trace(i, cohort="baseline") for i in range(8)]
    source = _build_source([*failures, *baselines])

    def _score(case: ScoreCase) -> _FakeScore:
        idx = int(case.trace_id.split("-")[1])
        if case.cohort == "failure":
            if idx < 11:
                return _FakeScore(value=0.34, explanation="improved")
            if idx < 14:
                return _FakeScore(value=0.0, explanation="unchanged")
            return _FakeScore(value=-0.10, explanation="regressed")
        # Baseline: only the first 3 succeed; the remaining 5 emit a
        # non-numeric Inspect-AI Score value, which projects to
        # `score=None` and raises into a `scorer_unavailable`
        # FailureRecord — the same shape a real Inspect AI judge
        # outage would produce.
        if idx < 3:
            return _FakeScore(value=0.04, explanation="unchanged")
        return _FakeScore(value="error", explanation="judge outage")  # type: ignore[arg-type]

    scorer = _build_scorer(_score)
    floor = TrustFloor()
    policy = DecisionPolicy()
    report = run_pipeline(
        source,
        delta_fn=_delta_fn_from(scorer),
        floor=floor,
        policy=policy,
        runtime=_default_runtime(floor=floor, policy=policy),
        methodology=_default_methodology(),
        cache_summary=_default_cache_summary(),
    )
    assert report.verdict_state == "inconclusive", report.verdict_state
    # Cardinal #1: the 5 outage traces surface as structured
    # FailureRecords, NOT exceptions. Pin the count so a regression
    # that swallows the pipeline-side capture is caught.
    scorer_unavailable = [f for f in report.failures if f.code == "scorer_unavailable"]
    assert len(scorer_unavailable) == 5, scorer_unavailable


def test_real_adapter_metadata_surfaces() -> None:
    """Adapter metadata flows through both real packages.

    The conformance harnesses already pin `adapter_metadata()` shape
    per package; this test pins the cross-cutting contract that both
    real adapters report a non-empty `package_version` and a
    non-`None` `adapter_id`. A regression that silently swaps either
    for `"unknown"` would slip past per-package conformance and land
    in audit logs with a useless attribution."""
    source = _build_source([_trace(0, cohort="failure")])
    scorer = _build_scorer(lambda _c: _FakeScore(value=0.5, explanation="ok"))
    src_meta = source.adapter_metadata()
    scorer_meta = scorer.adapter_metadata()
    assert src_meta.adapter_id == "langfuse"
    assert src_meta.package_version
    assert scorer_meta.adapter_id == "inspect_ai"
    assert scorer_meta.package_version


@pytest.mark.parametrize(
    "module_name",
    ["whatifd_langfuse", "whatifd_inspect_ai"],
)
def test_real_adapter_lazy_load(module_name: str) -> None:
    """Phase 4B contract pinned at the integration boundary.

    `import whatifd` MUST NOT pull either real adapter package into
    `sys.modules`. The unit-level test in
    `tests/unit/whatifd/adapters/test_protocols.py` runs this in a
    subprocess; this duplicate is cheaper and runs alongside the
    smoke scenarios so a Phase 9B regression that wires the adapter
    into the core import graph fails here too."""
    import subprocess
    import sys

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import whatifd, whatifd.cli, whatifd.pipeline; "
                f"import sys; "
                f"loaded = [m for m in sys.modules if m == {module_name!r} "
                f"or m.startswith({module_name!r} + '.')]; "
                "print(','.join(sorted(loaded)))"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = proc.stdout.strip()
    assert not loaded, f"{module_name} leaked into core import graph: {loaded}"
