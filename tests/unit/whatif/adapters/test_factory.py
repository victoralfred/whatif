"""Phase 10 CLI wiring foundation — adapter factory tests."""

from __future__ import annotations

import pytest

from whatif.adapters.factory import (
    AdapterFactoryError,
    build_scorer,
    build_trace_source,
)
from whatif.adapters.protocols import Scorer, TraceSource
from whatif.adapters.stub import StubScorer, StubTraceSource
from whatif.config import ScorerConfig, SourceConfig


def test_build_trace_source_stub_returns_stub_source() -> None:
    src = build_trace_source(SourceConfig(adapter="stub"))
    assert isinstance(src, StubTraceSource)
    # Empty-specs default — callers needing fixture data construct
    # `StubTraceSource(specs=...)` directly. Pinned so a future
    # refactor that adds a default fixture doesn't change the
    # documented zero-traces shape.
    assert list(src.iter_traces()) == []


def test_build_trace_source_satisfies_protocol() -> None:
    src = build_trace_source(SourceConfig(adapter="stub"))
    assert isinstance(src, TraceSource)


def test_build_trace_source_unknown_adapter_raises() -> None:
    with pytest.raises(AdapterFactoryError, match="Unknown trace-source adapter"):
        build_trace_source(SourceConfig(adapter="not_a_real_adapter"))


def test_build_trace_source_langfuse_without_credentials_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Strip any developer-environment Langfuse env vars so the test
    # is deterministic regardless of the runner's shell.
    for key in (
        "LANGFUSE_HOST",
        "LANGFUSE_BASE_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(AdapterFactoryError) as excinfo:
        build_trace_source(SourceConfig(adapter="langfuse"))
    msg = str(excinfo.value)
    assert "LANGFUSE_HOST" in msg
    assert "LANGFUSE_PUBLIC_KEY" in msg
    assert "LANGFUSE_SECRET_KEY" in msg
    # Actionable: the message names the credentialless escape hatch
    # so an operator hitting this can keep moving.
    assert "stub" in msg.lower()


@pytest.mark.parametrize(
    ("present", "missing_label"),
    [
        # `host` present, both keys missing → message names both keys.
        ({"LANGFUSE_HOST": "https://example"}, ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")),
        # `host` + public_key present, secret_key missing.
        (
            {"LANGFUSE_HOST": "https://example", "LANGFUSE_PUBLIC_KEY": "pk"},
            ("LANGFUSE_SECRET_KEY",),
        ),
        # `host` + secret_key present, public_key missing.
        (
            {"LANGFUSE_HOST": "https://example", "LANGFUSE_SECRET_KEY": "sk"},
            ("LANGFUSE_PUBLIC_KEY",),
        ),
        # Both keys present, host missing — message names host
        # AND its `LANGFUSE_BASE_URL` alias so an operator who set
        # the wrong env name sees both options.
        (
            {"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"},
            ("LANGFUSE_HOST", "LANGFUSE_BASE_URL"),
        ),
    ],
)
def test_build_trace_source_langfuse_partial_credentials_raises(
    monkeypatch: pytest.MonkeyPatch,
    present: dict[str, str],
    missing_label: tuple[str, ...],
) -> None:
    """Partial-missing credential combinations each produce a
    distinct, actionable error message segment.

    A future refactor that collapses the credential-check branches
    into a single generic `"missing credentials"` string would lose
    the per-var attribution an operator needs to fix the issue
    quickly. Pin each case so the message stays specific.
    """
    for key in (
        "LANGFUSE_HOST",
        "LANGFUSE_BASE_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    for k, v in present.items():
        monkeypatch.setenv(k, v)

    with pytest.raises(AdapterFactoryError) as excinfo:
        build_trace_source(SourceConfig(adapter="langfuse"))
    msg = str(excinfo.value)
    for label in missing_label:
        assert label in msg, f"expected {label!r} in error message; got: {msg}"


def test_build_trace_source_langfuse_import_failure_wraps_to_factory_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`_build_langfuse_source`'s `except ImportError` branch converts a
    missing-package failure into an actionable `AdapterFactoryError`,
    NOT a leaked `ImportError` (which would surface as a stack trace
    rather than a typed setup failure).

    Simulate the missing-package case by injecting an `__import__`
    hook that raises `ImportError` for the Langfuse SDK after credentials
    are present. The credential check runs first; without these env vars
    set, the function returns before the import would fire and this test
    couldn't reach the wrapping branch.
    """
    monkeypatch.setenv("LANGFUSE_HOST", "https://example")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    import builtins
    import sys

    real_import = builtins.__import__

    def _raise_for_langfuse(name: str, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        if name == "langfuse" or name.startswith("langfuse.") or name == "whatif_langfuse":
            raise ImportError(f"simulated: {name} not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _raise_for_langfuse)
    # Drop already-cached modules so the patched __import__ runs.
    for cached in ("langfuse", "whatif_langfuse"):
        monkeypatch.delitem(sys.modules, cached, raising=False)

    with pytest.raises(AdapterFactoryError) as excinfo:
        build_trace_source(SourceConfig(adapter="langfuse"))
    msg = str(excinfo.value)
    assert "langfuse adapter import failed" in msg
    # Actionable: the message names the install command an operator
    # can run to fix the missing package.
    assert "pip install whatif-langfuse" in msg


def test_build_trace_source_langfuse_sdk_construction_failure_wraps_to_factory_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cardinal #1: a `Langfuse(host=..., ...)` constructor exception
    (malformed URL, auth handshake error, etc.) MUST surface as
    `AdapterFactoryError` — NOT a leaked SDK exception.

    Without the boundary catch around the constructor call, a typo
    in `LANGFUSE_HOST` would propagate as a raw `ValueError` past
    the CLI's `AdapterFactoryError` handler and surface as a stack
    trace instead of an actionable setup-failure exit.
    """
    monkeypatch.setenv("LANGFUSE_HOST", "https://example")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    # Inject a fake `langfuse.Langfuse` whose constructor raises.
    # Stable across SDK versions (no real Langfuse import).
    import sys
    import types

    fake_langfuse = types.ModuleType("langfuse")

    class _Boom:
        def __init__(self, **_kwargs: object) -> None:
            raise ValueError("simulated SDK-side host validation failure")

    fake_langfuse.Langfuse = _Boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse)

    with pytest.raises(AdapterFactoryError) as excinfo:
        build_trace_source(SourceConfig(adapter="langfuse"))
    msg = str(excinfo.value)
    assert "langfuse adapter construction failed" in msg
    assert "ValueError" in msg
    # Actionable: the message points at the likely culprits.
    assert "LANGFUSE_HOST" in msg


def test_build_trace_source_langfuse_empty_string_host_treated_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`os.environ.get(k)` returns the literal empty string for an
    explicitly-empty env var; the credential check uses `if not host`,
    so empty-string is correctly treated as absent (not as a valid
    host that would surface deeper as a connection error). Pin this
    behavior so a refactor that switches to `is None` (which would
    accept "" as valid) fails first."""
    monkeypatch.setenv("LANGFUSE_HOST", "")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")

    with pytest.raises(AdapterFactoryError) as excinfo:
        build_trace_source(SourceConfig(adapter="langfuse"))
    assert "LANGFUSE_HOST" in str(excinfo.value)


def test_factory_re_exports_from_adapters_package() -> None:
    """`AdapterFactoryError`, `build_trace_source`, `build_scorer` are
    importable from `whatif.adapters` directly so callers don't need
    to know the implementation module path."""
    from whatif import adapters

    assert hasattr(adapters, "AdapterFactoryError")
    assert hasattr(adapters, "build_trace_source")
    assert hasattr(adapters, "build_scorer")


def test_build_scorer_stub_returns_stub_scorer() -> None:
    scorer = build_scorer(ScorerConfig(adapter="stub"))
    assert isinstance(scorer, StubScorer)


def test_build_scorer_stub_default_score_fn_returns_constant_0_5() -> None:
    """The stub scorer's default `score_fn` returns the constant
    `0.5` (not 0.0, not None). Pin this so:

    1. The CHANGELOG / docs / factory comment claim of "constant
       0.5" stays empirically truthful.
    2. A future change to `_default_score_fn` that flips the
       constant to e.g. 0.0 (which would silently re-shape the
       'real run accidentally uses stub' failure mode from
       'misleading Ship' to 'misleading Don't-Ship') fails first.
    """
    from whatif.contract import ReplayOutput, ScoreCase, TraceInput, TraceOutput

    scorer = build_scorer(ScorerConfig(adapter="stub"))
    case = ScoreCase(
        trace_id="t-1",
        cohort="failure",
        input=TraceInput(user_message="x"),
        original_output=TraceOutput(text="orig"),
        replayed_output=ReplayOutput(text="replay"),
    )
    result = scorer.score(case)
    assert result.score == 0.5


def test_build_scorer_satisfies_protocol() -> None:
    scorer = build_scorer(ScorerConfig(adapter="stub"))
    assert isinstance(scorer, Scorer)


def test_build_scorer_inspect_ai_raises_actionable() -> None:
    # v0.1 doesn't load score_fn from config (it's user code, not
    # config data). The factory surfaces this with an actionable
    # error pointing at the programmatic path. Pinned because a
    # future contributor might silently default `score_fn` to a
    # zero-stub here, which would produce uniformly zero deltas
    # under an `inspect_ai` config — a misleading Ship verdict.
    with pytest.raises(AdapterFactoryError) as excinfo:
        build_scorer(ScorerConfig(adapter="inspect_ai"))
    msg = str(excinfo.value)
    assert "score_fn" in msg
    assert "run_pipeline" in msg


def test_build_scorer_unknown_adapter_raises() -> None:
    with pytest.raises(AdapterFactoryError, match="Unknown scorer adapter"):
        build_scorer(ScorerConfig(adapter="not_a_real_scorer"))


def test_factory_does_not_import_real_adapter_packages() -> None:
    """Lazy-load contract: `import whatif.adapters.factory` MUST NOT
    pull `whatif_langfuse` or `whatif_inspect_ai` into sys.modules.
    Real-adapter imports happen inside the dispatch functions and
    only fire when the caller asks for that adapter.

    This pins the cardinal-enforced lazy-load contract specifically
    at the wiring boundary — a future contributor moving the real-
    adapter import to module top-level would break the broader
    test_core_modules_do_not_load_real_adapter_packages, but this
    test fails first with a focused message.
    """
    import subprocess
    import sys

    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import whatif.adapters.factory; "
                "import sys; "
                "leaked = [m for m in sys.modules "
                "if m == 'whatif_langfuse' or m.startswith('whatif_langfuse.') "
                "or m == 'whatif_inspect_ai' or m.startswith('whatif_inspect_ai.')]; "
                "print(','.join(sorted(leaked)))"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    leaked = proc.stdout.strip()
    assert not leaked, f"factory module leaked real adapters into import graph: {leaked}"
