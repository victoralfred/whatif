"""Phase 10.2 — runner-target loader tests.

The loader's contract is "any importable Python module + attribute,"
so the tests register an in-memory module in `sys.modules` and point
`load_runner` at it. This avoids fragile filesystem layout coupling
(the `tests/` directory isn't a package under `--import-mode=importlib`,
so `python:tests.unit...` won't resolve) and exercises exactly the
real production path: `importlib.import_module(name)` looks the name
up in `sys.modules`, no actual disk read happens for our fixture.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Generator

import pytest

from whatifd.contract import ReplayConfig, ReplayOutput, ToolCache, TraceInput
from whatifd.runner_loader import LoadedRunner, RunnerLoadError, load_runner

_FIXTURE_MODULE_NAME = "_whatif_runner_loader_test_fixture"


def _sync_runner(
    trace_input: TraceInput,
    config: ReplayConfig,
    tool_cache: ToolCache,
) -> ReplayOutput:
    _ = (trace_input, config, tool_cache)
    return ReplayOutput(text="sync-fixture", tool_spans=[], metadata={})


async def _async_runner(
    trace_input: TraceInput,
    config: ReplayConfig,
    tool_cache: ToolCache,
) -> ReplayOutput:
    _ = (trace_input, config, tool_cache)
    return ReplayOutput(text="async-fixture", tool_spans=[], metadata={})


_NOT_A_CALLABLE = 42


@pytest.fixture(autouse=True)
def _register_fixture_module() -> Generator[types.ModuleType, None, None]:
    """Inject an in-memory module exposing the runner fixtures, then
    drop it from sys.modules at teardown so each test starts clean.

    The yield type is `types.ModuleType` (not `object`) so consumers
    that bind the fixture as a parameter get accurate typing. Note:
    the per-attribute `# type: ignore[attr-defined]` comments on the
    inner assignments stay regardless — `ModuleType` doesn't
    statically declare arbitrary attributes, so dynamic
    `module.<name> = ...` is always `attr-defined` to mypy.
    """
    module = types.ModuleType(_FIXTURE_MODULE_NAME)
    module.sync_runner = _sync_runner  # type: ignore[attr-defined]
    module.async_runner = _async_runner  # type: ignore[attr-defined]
    module.NOT_A_CALLABLE = _NOT_A_CALLABLE  # type: ignore[attr-defined]
    sys.modules[_FIXTURE_MODULE_NAME] = module
    yield module
    sys.modules.pop(_FIXTURE_MODULE_NAME, None)


def test_load_sync_runner() -> None:
    loaded = load_runner(f"python:{_FIXTURE_MODULE_NAME}:sync_runner")
    assert isinstance(loaded, LoadedRunner)
    assert loaded.kind == "sync"
    assert loaded.reference == f"python:{_FIXTURE_MODULE_NAME}:sync_runner"
    assert callable(loaded.callable_)


def test_load_async_runner() -> None:
    loaded = load_runner(f"python:{_FIXTURE_MODULE_NAME}:async_runner")
    assert loaded.kind == "async"


def test_unsupported_scheme_raises() -> None:
    with pytest.raises(RunnerLoadError, match="unsupported scheme"):
        load_runner("file:/path/to/runner.py:run")


def test_empty_string_raises() -> None:
    with pytest.raises(RunnerLoadError, match="non-empty"):
        load_runner("")


def test_missing_module_path_raises() -> None:
    with pytest.raises(RunnerLoadError, match="missing the module path"):
        load_runner("python::run")


def test_missing_attr_raises() -> None:
    with pytest.raises(RunnerLoadError, match="missing the attribute name"):
        load_runner(f"python:{_FIXTURE_MODULE_NAME}:")


def test_too_many_separators_raises() -> None:
    with pytest.raises(RunnerLoadError, match="malformed"):
        load_runner(f"python:{_FIXTURE_MODULE_NAME}:run:extra")


def test_module_not_importable_raises() -> None:
    with pytest.raises(RunnerLoadError) as excinfo:
        load_runner("python:nonexistent.module.path:run")
    msg = str(excinfo.value)
    assert "could not be imported" in msg
    assert "nonexistent.module.path" in msg
    # Cardinal #1 / diagnostic-tooling contract: the original
    # ImportError MUST be preserved as `__cause__` so downstream
    # tools that walk exception chains (sentry, structured loggers)
    # can attribute the failure correctly. The `raise ... from exc`
    # idiom in runner_loader.py:117 is what sets this; pin the
    # contract so a future refactor that drops `from exc` (e.g.,
    # converts to a plain `raise RunnerLoadError(...)`) fails first.
    assert isinstance(excinfo.value.__cause__, ImportError)


def test_attribute_missing_raises() -> None:
    with pytest.raises(RunnerLoadError, match="has no attribute"):
        load_runner(f"python:{_FIXTURE_MODULE_NAME}:does_not_exist")


def test_non_callable_attribute_raises() -> None:
    """A loaded attribute that isn't callable (or doesn't satisfy
    Runner/AsyncRunner) MUST surface as RunnerLoadError, not
    AttributeError or TypeError. Cardinal #1: setup failure is
    structured data."""
    with pytest.raises(RunnerLoadError, match="is not callable"):
        load_runner(f"python:{_FIXTURE_MODULE_NAME}:NOT_A_CALLABLE")


class _AsyncCallableInstance:
    """Class-instance runner whose `__call__` is `async def`. Covers
    the `getattr(candidate, '__call__', None)` probe inside the
    classifier — `inspect.iscoroutinefunction` returns False on the
    instance itself but True on the bound `__call__` method, so the
    instance must classify as `async`."""

    async def __call__(
        self,
        trace_input: TraceInput,
        config: ReplayConfig,
        tool_cache: ToolCache,
    ) -> ReplayOutput:
        _ = (trace_input, config, tool_cache)
        return ReplayOutput(text="async-instance", tool_spans=[], metadata={})


def test_class_instance_with_async_call_classified_as_async(
    _register_fixture_module: types.ModuleType,
) -> None:
    """Reviewer-feedback coverage: a callable instance whose
    `__call__` is `async def` must classify as async via the
    `getattr(__call__, None)` probe. The instance itself is not a
    coroutine function; only its bound `__call__` is. Without the
    probe, this would route to the sync kernel and the returned
    coroutine would be treated as a `ReplayOutput`."""
    _register_fixture_module.async_instance = _AsyncCallableInstance()  # type: ignore[attr-defined]
    loaded = load_runner(f"python:{_FIXTURE_MODULE_NAME}:async_instance")
    assert loaded.kind == "async"


def test_async_classified_before_sync() -> None:
    """An `async def` function returns a coroutine; if the loader
    classified async-def as `sync`, the sync replay kernel would
    treat the returned coroutine as a `ReplayOutput` (it isn't),
    surfacing as a confusing downstream type error.

    Pin the AsyncRunner-first ordering so a refactor that drops
    AsyncRunner from the isinstance chain (or reorders to sync
    first) fails here, not deep in the kernel."""
    loaded = load_runner(f"python:{_FIXTURE_MODULE_NAME}:async_runner")
    assert loaded.kind == "async", (
        f"async def runner classified as {loaded.kind}; "
        "AsyncRunner check must come before Runner check."
    )
