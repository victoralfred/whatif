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
uv run pytest packages/whatifd-langfuse/tests/test_recorded_smoke.py \\
    --record-mode=once
```

The cassette lands under `packages/whatifd-langfuse/tests/cassettes/`
and gets committed. Sensitive request headers (`Authorization`,
`x-langfuse-public-key`) are filtered by the `vcr_config` fixture
below — DO NOT commit a cassette without verifying the YAML is
clean of secrets.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

_MODULE_NAME = Path(__file__).stem
# pytest-recording lays cassettes out as
# `cassettes/<module-stem>/<test-name>.yaml`. Track the per-module
# subdirectory here so the skip-presence check looks in the right
# place; otherwise every CI run skips even when the cassette exists.
_CASSETTES_DIR = Path(__file__).resolve().parent / "cassettes" / _MODULE_NAME

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


_PUBLIC_KEY_RE = re.compile(r"pk-lf-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_SECRET_KEY_RE = re.compile(r"sk-lf-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


_scrub_state_local = threading.local()


def _scrub_local() -> threading.local:
    """Per-thread scrub state carrier.

    Globally unique trace placeholder ids across responses (not
    per-page) — a future bug where the adapter emits duplicate
    trace_id across pages would otherwise be invisible because the
    scrubber would overwrite both pages with redacted-trace-000…002.

    `threading.local` (instead of a class attribute or module-level
    list) so pytest-xdist or any other parallel test runner that
    spawns recording threads doesn't race the counter. Single-
    threaded test runs see identical behavior; concurrent recording
    workers each get their own counter rooted at 0.
    """
    if not hasattr(_scrub_state_local, "next_trace_idx"):
        _scrub_state_local.next_trace_idx = 0
    return _scrub_state_local


class _ScrubState:
    """Public-facing API over `_scrub_state_local`. Methods delegate
    to the thread-local carrier; the surface stays the same so the
    autouse reset fixture and the scrubber both call
    `_ScrubState.reset()` / `_ScrubState.take_trace_idx()` without
    caring about the thread-local plumbing."""

    @classmethod
    def reset(cls) -> None:
        _scrub_local().next_trace_idx = 0

    @classmethod
    def take_trace_idx(cls) -> int:
        local = _scrub_local()
        idx: int = local.next_trace_idx
        local.next_trace_idx = idx + 1
        return idx


def _scrub_response_body(response: dict[str, object]) -> dict[str, object]:
    """vcrpy `before_record_response` hook: scrub the response body
    of EVERYTHING that could leak from the recorder's project.

    The committed cassette MUST NOT carry user content from the
    recording project (cardinal #5 spirit: even if the project is
    a "test project," its prompts/responses/metadata are
    `Sensitive`). The strategy here is structural: parse the JSON
    body, walk the trace shape, and replace user-content fields
    with deterministic placeholders. The replayed test still
    exercises the protocol contract (Sensitive[str] wrapping over
    a real Trace shape) without committing the original content.

    What gets scrubbed:
    - Top-level `data[*].input` / `data[*].output` → REDACTED placeholders
    - Top-level `data[*].metadata` → `{}` (project-specific tooling state)
    - Top-level `data[*].name` → `"redacted-trace-name"` (may carry
      project-specific endpoint paths)
    - Top-level `data[*].projectId` → `"redacted-project-id"`
    - Top-level `data[*].userId` / `sessionId` / `tags` → null/empty
    - Top-level `data[*].observations` / `scores` / `htmlPath` →
      empty/redacted (carry references to project state)
    - `data[*].id` is REPLACED with `redacted-trace-NN` so the
      cassette test still asserts `RawTrace.trace_id` is non-empty
      without committing the project's actual trace ids.
    - Langfuse credential patterns anywhere in the body
      (defence-in-depth fallback for echoed keys).
    """
    import json as _json  # local: keeps the canonical-import lint clean

    # Strip Content-Length from response headers — the body-scrub
    # below shrinks the body, so any preserved Content-Length would
    # mismatch the actual cassette bytes. vcrpy 8.x ignores it on
    # replay, but a future strict-mode vcrpy could raise. The
    # `filter_headers` config above runs before this hook fires
    # and the response-side scrub didn't take in vcrpy 8.x; doing
    # it here is the reliable point.
    headers = response.get("headers", {})
    if isinstance(headers, dict):
        for key in list(headers.keys()):
            if key.lower() == "content-length":
                headers.pop(key, None)

    body = response.get("body", {})
    if not isinstance(body, dict):
        return response
    raw = body.get("string")
    if not isinstance(raw, (str, bytes)):
        return response
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw

    try:
        parsed = _json.loads(text)
    except _json.JSONDecodeError:
        # Non-JSON response — fall back to regex-only credential
        # scrub. Surface a warning during recording so a future
        # Langfuse endpoint that switches off JSON (HTML error page,
        # protobuf, gRPC response) is visible: regex-only scrubbing
        # only catches credential PATTERNS, not structural fields.
        # If this warning fires during a recording session, the
        # cassette MUST be hand-reviewed before commit.
        import warnings

        warnings.warn(
            "Non-JSON response in cassette recording; falling back to "
            "regex-only credential scrub. The structural-field scrubber "
            "(input/output/metadata/projectId redaction) does NOT run on "
            "this response. Hand-review the cassette for user content "
            "before commit.",
            RuntimeWarning,
            stacklevel=2,
        )
        cleaned = _PUBLIC_KEY_RE.sub("pk-lf-FILTERED", text)
        cleaned = _SECRET_KEY_RE.sub("sk-lf-FILTERED", cleaned)
        body["string"] = cleaned.encode("utf-8") if isinstance(raw, bytes) else cleaned
        return response

    if isinstance(parsed, dict) and isinstance(parsed.get("data"), list):
        for trace in parsed["data"]:
            if not isinstance(trace, dict):
                continue
            trace["id"] = f"redacted-trace-{_ScrubState.take_trace_idx():03d}"
            trace["projectId"] = "redacted-project-id"
            trace["name"] = "redacted-trace-name"
            trace["input"] = "[REDACTED USER CONTENT]"
            trace["output"] = "[REDACTED USER CONTENT]"
            trace["metadata"] = {}
            trace["userId"] = None
            trace["sessionId"] = None
            trace["tags"] = []
            trace["observations"] = []
            trace["scores"] = []
            trace["htmlPath"] = "/redacted"
            trace["release"] = None
            trace["version"] = None
            trace["externalId"] = None

    # Test scaffold: this `json.dumps` lives in test code, not a
    # runtime path. The project's banned-import lint
    # (tests/unit/whatifd/serialization/test_banned_imports.py)
    # walks `src/whatifd/` only — `tests/` and `packages/*/tests/`
    # are out of scope by design. If the lint is ever extended to
    # cover `packages/`, this call needs an explicit allowlist
    # entry; the marker-comment below is the search anchor for
    # that future audit.
    cleaned_text = _json.dumps(parsed, sort_keys=True)  # whatifd-json-dumps: test-scaffold-allowed
    # Belt-and-suspenders: regex-scrub credential patterns from the
    # serialized JSON in case a future Langfuse field grows a new
    # echo path.
    cleaned_text = _PUBLIC_KEY_RE.sub("pk-lf-FILTERED", cleaned_text)
    cleaned_text = _SECRET_KEY_RE.sub("sk-lf-FILTERED", cleaned_text)
    body["string"] = cleaned_text.encode("utf-8") if isinstance(raw, bytes) else cleaned_text
    return response


@pytest.fixture(autouse=True)
def _reset_scrub_state() -> Iterator[None]:
    """Reset the per-recording-session counter before every test.

    Defends against cross-test ordering surprises: if two recording
    tests run in one process, the counter would otherwise carry
    over and the second cassette's trace ids would start at the
    first cassette's continuation. autouse + reset-before-each-test
    keeps each cassette numbered from 0 regardless of test order.
    """
    _ScrubState.reset()
    yield


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
            # Stripped because the body-scrub hook
            # (`_scrub_response_body`) shrinks the response after
            # vcrpy captures the original Content-Length. vcrpy 8.x
            # ignores the header on replay, but a future strict-mode
            # vcrpy 9+ would raise on the mismatch. Filtering out
            # makes the cassette future-proof.
            ("content-length", None),
        ],
        "filter_query_parameters": [
            ("publicKey", "FILTERED"),
        ],
        "before_record_response": _scrub_response_body,
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

    # The `pk-replay` / `sk-replay` placeholders aren't real
    # credentials — they're the no-op values used in REPLAY mode
    # (cassette playback) where vcrpy intercepts every HTTP call
    # before the SDK ever transmits the auth header. The
    # `_ensure_skip_when_cannot_run` gate above already rejects
    # the case "no cassette + no creds + record-mode=none", so
    # this code path is reached only when a cassette exists OR
    # real credentials are present. Hardcoded placeholders are
    # deliberately implausible-looking so a contributor reading
    # them doesn't mistake them for a leaked secret.
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
    from whatifd.types.sensitive import Sensitive

    from whatifd_langfuse import LangfuseTraceSource

    source = LangfuseTraceSource(
        api=langfuse_api,
        cohort_classifier=lambda _t: "failure",
        page_limit=5,
        max_traces=5,
    )
    emitted = list(source.iter_traces())
    # Load-bearing lower bound: the committed cassette covers a
    # project with at least 5 traces; `max_traces=5` caps emission
    # at exactly 5. A regression that returns zero traces (e.g., the
    # adapter accidentally swallows the response.data list) would
    # otherwise pass the per-trace shape loop vacuously. Pin the
    # count so the smoke gate actually exercises the projection.
    assert len(emitted) == 5, f"smoke expected 5 traces; got {len(emitted)}"
    for raw in emitted:
        assert isinstance(raw.trace_id, str) and raw.trace_id
        assert isinstance(raw.cohort, str) and raw.cohort
        assert isinstance(raw.user_message, Sensitive)
        assert isinstance(raw.original_response, Sensitive)
