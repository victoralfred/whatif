"""Pin that `examples/minimal-agent/replay.py` satisfies the
`Runner` contract.

The example is a copy-paste starting point for users; if it stops
satisfying the protocol (signature drift, return type wrong), users
inherit the breakage. This test fails first.

The example dir uses a hyphenated name (`examples/minimal-agent/`)
to match the convention in `phases.md`, which makes it
non-importable as a package. The test loads the file directly via
`importlib.util.spec_from_file_location`, mirroring how the Phase 10
CLI runner-target loader will resolve `python:<module>:<attr>` for
files that aren't on `sys.path`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from whatifd.contract import ReplayConfig, ReplayOutput, Runner, ToolCache, TraceInput

_REPLAY_PATH = Path(__file__).resolve().parents[2] / "examples" / "minimal-agent" / "replay.py"


@pytest.fixture(scope="module")
def replay_run():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("_minimal_agent_replay", _REPLAY_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run


def test_runner_satisfies_protocol(replay_run) -> None:  # type: ignore[no-untyped-def]
    assert isinstance(replay_run, Runner)


def test_run_returns_replay_output(replay_run) -> None:  # type: ignore[no-untyped-def]
    out = replay_run(
        TraceInput(user_message="hello"),
        ReplayConfig(system_prompt="You are concise."),
        ToolCache(),
    )
    assert isinstance(out, ReplayOutput)
    assert out.text
    assert out.metadata["runner"] == "examples.minimal-agent"
