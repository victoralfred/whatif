# whatifd-skillgen (third-party adapter scaffolding)

`whatifd-skillgen` is a standalone developer tool for adapter authors. It generates protocol-compliant whatifd adapter stubs (`TraceSource`, `Scorer`, or runner) from a short declarative `skill.md` manifest.

**This is not part of whatifd core.** It is a DX tool that reduces the time to write the structural shell of a new adapter. Install it on demand when starting a new integration; it is not a runtime dependency and carries no verdict-pipeline surface.

---

## When to use it

Use `whatifd-skillgen` when you are authoring a new `whatifd-<name>` adapter package and want to avoid handwriting the structural boilerplate: the `TYPE_CHECKING` protocol witness, the `importlib.metadata.version()` call, the `Sensitive[T]` reminders, and the `NotImplementedError` stubs with actionable messages.

Do not use it as a substitute for understanding the adapter contract. Read [`docs/runner-contract.md`](../runner-contract.md) and study an existing adapter (`packages/whatifd-phoenix/` is the most recent) before generating.

---

## Install

```bash
pip install whatifd-skillgen
# or
uv pip install whatifd-skillgen
```

Requires Python 3.11+. No runtime dependency on whatifd.

---

## How to add a new adapter (full walkthrough)

This is the canonical seven-step process for adding a `whatifd-<name>` adapter to the workspace. `whatifd-skillgen` automates step 3; the rest require decisions only you can make.

### Step 1 — Create the workspace member directory

```
packages/whatifd-<name>/
├── pyproject.toml
├── README.md
└── src/
    └── whatifd_<name>/
        └── skill.md        ← write this in step 2
```

Distribution name: `whatifd-<name>` (hyphenated). Package slug: `whatifd_<name>` (underscored). Version: start at the current workspace version (currently `0.2.0`).

Copy `packages/whatifd-phoenix/pyproject.toml` as the template. Substitute the new name throughout. If the adapter has a live-API dependency, add a `[live]` optional-extras group following the phoenix pattern.

### Step 2 — Write `skill.md` inside the package source directory

Create `packages/whatifd-<name>/src/whatifd_<name>/skill.md`:

```yaml
---
name: <name>
description: "<one-line description>"
version: "0.1"
kind: scorer          # or: tracer | runner

env_vars:
  - name: MY_API_KEY
    required: true
    description: "API key for the external service."

parameters:
  - name: model_id
    type: str
    required: true
    description: "Model identifier."
  - name: timeout
    type: float
    required: false
    default: "30.0"
    description: "Request timeout in seconds."
---

## What this adapter does

<Describe what the adapter does and how it connects to the external system.>

## Implementation notes

<Non-obvious constraints, cardinal rule reminders specific to this adapter.>
```

See the full schema reference in the [whatifd-skillgen README](https://github.com/victoralfred/whatifd-skillgen#skill-md-schema).

### Step 3 — Run the generator

```bash
whatifd-skillgen generate packages/whatifd-<name>/src/whatifd_<name>/
```

This writes `__init__.py` to the directory you specified and prints two blocks of patch instructions to stdout. The output directory is your adapter's source directory — not inside whatifd's own source tree.

Options:
- `--overwrite` — overwrite an existing `__init__.py` (re-running after editing the stub)

### Step 4 — Apply patches and implement the TODOs

**config.py patch.** Add the `<Name>Config` Pydantic model to `src/whatifd/config.py`. The printed hint gives you the starting shape; you must add:
- `@model_validator` cross-field guards for any field that is conditionally required (required only when this adapter is selected). See the existing `ScorerConfig` for the pattern.
- A discriminated union update in `WhatifConfig`: `scorer: Annotated[ScorerConfig | <Name>Config, Field(discriminator="adapter")]`.

**factory.py patch.** Add one `if name == "<name>":` branch in `build_scorer` or `build_trace_source` in `src/whatifd/adapters/factory.py`, BEFORE the final `raise AdapterFactoryError(...)` fallback. Use a lazy import (inside the `if` branch, never at module top-level — the lazy-load contract is enforced by `tests/unit/whatifd/adapters/test_protocols.py`):

```python
if name == "<name>":
    try:
        from whatifd_<name> import <Name>Scorer
    except ImportError as exc:
        raise AdapterFactoryError(
            "scorer.adapter='<name>' requires the 'whatifd-<name>' package. "
            "Install with: pip install whatifd-<name>"
        ) from exc
    return <Name>Scorer(...)
```

**Implement the TODOs** in the generated `__init__.py`:
- `score()` / `iter_traces()` / `<name>_runner()` — the actual integration logic
- `cache_key_components()` (scorer only) — deterministic cache key fields
- Wrap user content in `Sensitive[T]` at the boundary (cardinal #5):
  ```python
  from whatifd.types.sensitive import Sensitive
  rationale = Sensitive(value=raw_text, classification="user_content")
  plain = rationale.unwrap(reason="passing to judge model API")
  ```

### Step 5 — Register the workspace member

Three edits in the root `pyproject.toml`:

```toml
[tool.uv.workspace]
members = [
    "packages/whatifd-langfuse",
    "packages/whatifd-inspect-ai",
    "packages/whatifd-phoenix",
    "packages/whatifd-<name>",    # ← add
]

[tool.uv.sources]
whatifd-<name> = { workspace = true }    # ← add

[dependency-groups]
workspace = [
    "whatifd-langfuse",
    "whatifd-inspect-ai",
    "whatifd-phoenix",
    "whatifd-<name>",    # ← add
]
```

`pytest.ini_options.testpaths` already covers `packages/` so test collection picks up automatically.

### Step 6 — Version parity and release wiring

**`tests/unit/whatifd/test_version_parity.py`** — add two lines:

```python
import whatifd_<name>

# Inside test_all_workspace_packages_share_the_same_version:
"whatifd-<name>": whatifd_<name>.__version__,
```

Also add `whatifd_<name>.__version__ != "0.0.0+unknown"` to `test_no_package_reports_sentinel_when_installed`.

**`RELEASING.md`** — add `whatifd-<name>` to every checklist entry that mentions the four packages (pre-flight versions check, verify PyPI visibility, `pip install` smoke).

**`.github/workflows/release.yml`** — four places:

1. Tag↔version guard `packages` list: add `"packages/whatifd-<name>/pyproject.toml"`
2. Build job: add `uv build --package whatifd-<name> --out-dir dist-whatifd-<name>`
3. Upload-artifact: add an `actions/upload-artifact` step for `dist-whatifd-<name>`
4. New publish job (copy `publish-whatifd-phoenix`; set `environment.name: pypi-whatifd-<name>`)
5. `github-release.needs`: add `publish-whatifd-<name>`

Register a Pending Publisher on PyPI at `https://pypi.org/manage/account/publishing/` before tagging. Environment name must match the `environment.name` in the publish job exactly.

### Step 7 — Docs and release

Add `docs/integrations/<name>.md` modeled on this page. Link it from `docs/integrations/index.md` and the README Documentation section.

The next workspace version bump publishes all packages together via `release.yml`. See `RELEASING.md` for the full runbook.

---

## Running the generated adapter's tests

```bash
uv sync --all-extras --dev --group workspace
uv run pytest packages/whatifd-<name>/tests/ -q
uv run mypy packages/whatifd-<name>/src
```

The conformance harness at `tests/adapters/conformance.py` runs automatically once your class inherits from and implements the correct Protocol.

---

## Cardinal rules that apply to all adapters

| Rule | What it requires |
|---|---|
| **#1 Failure-as-data** | Wrap `ImportError` as `AdapterFactoryError` in the dispatch branch. No raw tracebacks. |
| **#5 Sensitive[T] at the boundary** | `user_message`, `original_response`, `rationale` — all wrapped at the adapter boundary, never raw. |
| **#9 Orchestration, not compute** | No `ProcessPoolExecutor`, `numpy`, or in-adapter parallel replay. The bottleneck is I/O. |

---

## See also

- [`packages/whatifd-phoenix/`](../../packages/whatifd-phoenix/) — freshest reference adapter; copy its `pyproject.toml` structure
- [`packages/whatifd-langfuse/`](../../packages/whatifd-langfuse/) — recorded-smoke cassette pattern (v0.3+ target for new adapters)
- [`docs/runner-contract.md`](../runner-contract.md) — runner protocol reference
- [whatifd-skillgen on PyPI](https://pypi.org/project/whatifd-skillgen/) — the scaffolding tool this page documents
