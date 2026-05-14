# whatifd-skillgen

Adapter scaffolding tool for [whatifd](https://github.com/victoralfred/whatifd). Generates protocol-compliant adapter stubs from a declarative `skill.md` manifest — so you spend time on the integration logic, not the boilerplate.

## What this is for

Writing a whatifd adapter (`TraceSource`, `Scorer`, or runner) from scratch means getting several structural details right before you write a single line of real logic: the `TYPE_CHECKING` protocol witness, the `importlib.metadata.version()` call in `adapter_metadata()`, the `Sensitive[T]` wrapping reminder, the `NotImplementedError` stubs with actionable messages. These are the same in every adapter. `whatifd-skillgen` generates them from a short YAML declaration so you only write them once.

**This tool does not belong in whatifd core.** It is a developer-experience tool for adapter authors, not verdict infrastructure. Install it as a standalone dev tool on demand; it is not a runtime dependency of whatifd.

## Install

```bash
pip install whatifd-skillgen
# or
uv pip install whatifd-skillgen
```

Requires Python 3.11+. No dependency on `whatifd` itself — the generated code imports from `whatifd`, but this tool only needs `pydantic`, `pyyaml`, and `typer`.

## Quickstart

**Step 1.** Create your adapter package directory (this is where the generated file lands):

```bash
mkdir -p packages/whatifd-myadapter/src/whatifd_myadapter
```

**Step 2.** Write `skill.md` inside that directory:

```bash
cat > packages/whatifd-myadapter/src/whatifd_myadapter/skill.md <<'EOF'
---
name: myadapter
description: "MyAdapter scorer using the Example API."
version: "0.1"
kind: scorer

env_vars:
  - name: EXAMPLE_API_KEY
    required: true
    description: "API key for the Example scoring service."

parameters:
  - name: model_id
    type: str
    required: true
    description: "Model identifier to use for scoring."
  - name: timeout
    type: float
    required: false
    default: "30.0"
    description: "Request timeout in seconds."
---

## What this adapter does

Calls the Example API to score traces against a rubric. Returns a float
score (0.0–1.0) and a rationale string.

## Implementation notes

Use `example_sdk.Client(api_key=os.environ['EXAMPLE_API_KEY'])`.
Parse the score from the response and wrap rationale in
Sensitive(value=rationale, classification="user_content") before returning.
EOF
```

**Step 3.** Run the generator:

```bash
whatifd-skillgen generate packages/whatifd-myadapter/src/whatifd_myadapter/
```

Output:

```
whatifd-skillgen: wrote packages/whatifd-myadapter/src/whatifd_myadapter/__init__.py

=== config.py patch instructions ===
...

=== factory.py patch instructions ===
...
```

The generator writes `__init__.py` to the directory you pointed at — your adapter package's source directory, not inside whatifd's source tree. The patch instructions printed to stdout tell you exactly which lines to add to whatifd's `config.py` and `factory.py` to wire your adapter into the registry.

## CLI reference

```
whatifd-skillgen generate <skill_dir> [--overwrite]
```

| Argument | Description |
|---|---|
| `skill_dir` | Directory containing `skill.md`. The generated `__init__.py` is written here. |
| `--overwrite` | Allow overwriting an existing `__init__.py`. Without this flag the command refuses to clobber existing implementation work. |

Exit codes: `0` on success, `2` on any error (manifest parse failure, generation error, filesystem error).

## What the generator produces

### `kind: scorer`

```python
@dataclass(frozen=True, slots=True)
class MyadapterScorer:
    model_id: str
    timeout: float = 30.0

    def score(self, case: ScoreCase) -> JudgeResult: ...          # TODO
    def cache_key_components(self, case: ScoreCase) -> CacheKeyComponents: ...  # TODO
    def adapter_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id="myadapter",
            package_version=_dist_version("whatifd-myadapter"),  # importlib.metadata
        )

if TYPE_CHECKING:
    _protocol_witness: Scorer = MyadapterScorer.__new__(MyadapterScorer)
```

### `kind: tracer`

A `MyadapterTraceSource` class satisfying `whatifd.adapters.protocols.TraceSource`:
`iter_traces()`, `cluster_key_support()`, `adapter_metadata()`, plus a `TYPE_CHECKING` witness.

### `kind: runner`

An `async def myadapter_runner(case: RunnerCase) -> RunnerResult` function.

All stubs raise `NotImplementedError` with an actionable message. Cardinal #5 (`Sensitive[T]`) reminders are inlined as comments.

## What you still need to do after generating

The generator writes the structural shell. You still need to:

1. **Implement the TODOs** — `score()`, `iter_traces()`, or the runner body. This is the part that knows your external API.
2. **Apply the config.py patch** — add the `<Name>Config` Pydantic model and union field update in `src/whatifd/config.py`. Include `@model_validator` cross-field guards if any fields are conditionally required.
3. **Apply the factory.py patch** — add the lazy-import dispatch branch in `src/whatifd/adapters/factory.py`. Use a lazy import (inside the `if` branch), never at module top-level.
4. **Register the workspace member** — add your package to `[tool.uv.workspace]`, `[tool.uv.sources]`, and `[dependency-groups]` in the root `pyproject.toml`.
5. **Update version parity** — add your package to `tests/unit/whatifd/test_version_parity.py` and `RELEASING.md`.
6. **Wire into release.yml** — add your package's build, upload-artifact, publish job, and the tag↔version guard's package list to `.github/workflows/release.yml`.

The full seven-step walkthrough is in [`docs/integrations/skillgen.md`](https://github.com/victoralfred/whatifd/blob/main/docs/integrations/skillgen.md) in the whatifd repo.

## skill.md schema

All fields use `extra="forbid"` — unknown keys raise a `SkillManifestError` at parse time with an actionable message.

```yaml
---
name: <slug>          # Required. Valid Python identifier (e.g. my_scorer). Used as module + class prefix.
description: "..."    # Required. One-line description used in the generated docstring.
version: "0.1"        # Optional. Semver-like string (default "0.1").
kind: scorer          # Required. One of: scorer | tracer | runner

env_vars:
  - name: MY_API_KEY  # UPPER_SNAKE_CASE only.
    required: true
    description: "..."

parameters:
  - name: model_id    # Valid Python identifier.
    type: str         # str | int | float | bool only.
    required: true
    description: "..."
  - name: timeout
    type: float
    required: false
    default: "30.0"   # Required when required=false.
    description: "..."
---

## Markdown body

Becomes the "Implementation notes" section in the generated docstring.
```

## Common errors

| Error | Cause | Fix |
|---|---|---|
| `skill.md not found` | Directory exists but no `skill.md` | Create the file with frontmatter |
| `skill name 'my-adapter' must be a valid Python identifier` | Hyphens in name | Use underscores: `my_adapter` |
| `parameter.type 'list' is not supported` | Complex type | Use `str` and document the expected format |
| `optional parameters must supply a default value` | `required: false` without `default` | Add `default: "<value>"` |
| `__init__.py already exists` | Re-running without `--overwrite` | Pass `--overwrite` or inspect the existing file first |

## Running the tests

```bash
pip install "whatifd-skillgen[dev]"
pytest tests/ -q
```

Three test modules:
- `test_schema.py` — `extra="forbid"` rejection, all field validation rules
- `test_loader.py` — parse paths, all error shapes (no raw exceptions escape)
- `test_generator.py` — determinism (same manifest → identical output), protocol correctness, error boundary

## License

Apache-2.0.
