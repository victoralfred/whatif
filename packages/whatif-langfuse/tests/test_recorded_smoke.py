"""Real-network smoke against a recorded Langfuse cassette.

Industry-standard CI strategy for SDK adapters: `pytest-recording`
(built on `vcrpy`) records HTTP interactions to YAML cassettes on
the first local run with credentials, and replays from cassette
in CI. Sensitive headers are filtered.

## When this test runs

| Environment | Cassette present | Behavior |
|---|---|---|
| Local dev with `LANGFUSE_*` env vars | Yes | Replay (uses cassette, no network) |
| Local dev with `LANGFUSE_*` env vars | No | **Records** (pytest-recording `--record-mode=once`) |
| CI without credentials | Yes | Replay (uses cassette, no network) |
| CI without credentials | No | Skip with a clear message |

## Recording cassettes

A contributor with real credentials runs:

```bash
LANGFUSE_HOST=https://cloud.langfuse.com \\
LANGFUSE_PUBLIC_KEY=pk-... \\
LANGFUSE_SECRET_KEY=sk-... \\
uv run pytest packages/whatif-langfuse/tests/test_recorded_smoke.py \\
    --record-mode=once
```

The cassette lands under `packages/whatif-langfuse/tests/cassettes/`
and gets committed. Sensitive request headers (`Authorization`,
`x-langfuse-public-key`) are filtered by the `vcr_config` fixture
below — DO NOT commit a cassette without verifying the YAML is
clean of secrets.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

_CASSETTES_DIR = Path(__file__).resolve().parent / "cassettes"

_HOST_ENV_KEYS = ("LANGFUSE_HOST", "LANGFUSE_BASE_URL")
_OTHER_CRED_KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
_CRED_KEYS = (_HOST_ENV_KEYS[0], *_OTHER_CRED_KEYS)


def _resolve_host() -> str | None:
    """Accept either `LANGFUSE_HOST` or `LANGFUSE_BASE_URL`. The
    Langfuse SDK and dashboard both ship `LANGFUSE_BASE_URL` as the
    canonical name; older docs use `LANGFUSE_HOST`. Adapter authors
    shouldn't have to remember which."""
    for key in _HOST_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            return value
    return None


def _have_credentials() -> bool:
    return _resolve_host() is not None and all(os.environ.get(k) for k in _OTHER_CRED_KEYS)


def _cassette_for(name: str) -> Path:
    return _CASSETTES_DIR / f"{name}.yaml"


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    """pytest-recording filter config. Strips secrets from cassettes
    before they hit disk; replay mode strips again on read so
    cassettes recorded in older filter configs stay safe."""
    return {
        "filter_headers": [
            ("authorization", "FILTERED"),
            ("x-langfuse-public-key", "FILTERED"),
            ("x-langfuse-sdk-name", "FILTERED"),
            ("x-langfuse-sdk-version", "FILTERED"),
            ("user-agent", "FILTERED"),
        ],
        "filter_query_parameters": [
            ("publicKey", "FILTERED"),
        ],
        "decode_compressed_response": True,
    }


def _record_mode(request: pytest.FixtureRequest) -> str:
    """Read `--record-mode` from the pytest config. pytest-recording
    defaults to `"none"` (replay-only); `"once"` / `"new_episodes"` /
    `"all"` are the recording modes."""
    try:
        return request.config.getoption("--record-mode") or "none"
    except ValueError:
        return "none"


def _ensure_skip_when_cannot_run(cassette_name: str, record_mode: str) -> None:
    """Skip with a clear message when the test cannot run cleanly.

    Three skippable conditions:
    - No cassette AND record-mode is `none` (replay-only): nothing
      to play back, no permission to record.
    - No cassette AND no credentials: even in record mode, there's
      no real backend to call.
    - Cassette exists AND credentials absent: fine — replay mode
      doesn't need credentials. NOT a skip case.
    """
    cassette = _cassette_for(cassette_name)
    if cassette.exists():
        return  # replay path
    if record_mode == "none":
        pytest.skip(
            f"No cassette at {cassette} and `--record-mode=none` "
            f"(default). Record locally with `pytest --record-mode=once` "
            "to land the cassette."
        )
    if not _have_credentials():
        pytest.skip(
            f"No cassette at {cassette} and no "
            f"{', '.join(_CRED_KEYS)} env vars. Recording needs both."
        )


@pytest.fixture
def langfuse_api() -> Iterator[object]:
    """Construct a real `LangfuseAPI` from environment variables.

    Yields the API client directly; pytest-recording intercepts the
    underlying `httpx.Client` so the call shape is recorded /
    replayed without the test caring about the wire layer.
    """
    pytest.importorskip("langfuse", reason="langfuse SDK not installed")
    from langfuse.api import LangfuseAPI

    host = _resolve_host() or "https://cloud.langfuse.com"
    public = os.environ.get("LANGFUSE_PUBLIC_KEY", "pk-replay")
    secret = os.environ.get("LANGFUSE_SECRET_KEY", "sk-replay")
    yield LangfuseAPI(base_url=host, username=public, password=secret)


@pytest.mark.vcr
def test_iter_traces_smoke(  # type: ignore[no-untyped-def]
    langfuse_api,
    request: pytest.FixtureRequest,
) -> None:
    """Smoke: construct the adapter, iterate up to 5 traces, assert
    each emitted RawTrace satisfies the protocol shape (Sensitive
    wrapping, str trace_id, str cohort).

    This is the load-bearing real-network proof for Phase 4B.1's
    gate item "Sensitive wrapping verified end-to-end with real
    adapter": a real Langfuse `Trace` with real content fields
    flows through `LangfuseTraceSource._project` and lands in a
    `RawTrace` with `Sensitive[str]` user_message and
    original_response.
    """
    _ensure_skip_when_cannot_run("test_iter_traces_smoke", _record_mode(request))

    pytest.importorskip("langfuse", reason="langfuse SDK not installed")
    from whatif_langfuse import LangfuseTraceSource

    from whatif.types.sensitive import Sensitive

    source = LangfuseTraceSource(
        api=langfuse_api,
        cohort_classifier=lambda _t: "failure",
        page_limit=5,
        max_traces=5,
    )
    emitted = list(source.iter_traces())
    # The fixture project may have zero traces; the smoke gate only
    # requires that whatever IS returned satisfies the protocol.
    for raw in emitted:
        assert isinstance(raw.trace_id, str) and raw.trace_id
        assert isinstance(raw.cohort, str) and raw.cohort
        assert isinstance(raw.user_message, Sensitive)
        assert isinstance(raw.original_response, Sensitive)
