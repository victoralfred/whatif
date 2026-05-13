---
name: capabilities
description: Scaffold a new whatifd skill - write skill.md, run the generator, apply printed patches, run tests. Use when asked to add a new adapter, scorer, tracer, or runner to whatifd.
---

# whatifd Skill Scaffolding

## When to use this skill

Use this skill whenever the user asks to:
- Add a new scorer, trace source, or runner adapter to whatifd
- Create a new whatifd skill (any kind)
- Extend whatifd with a new external-system integration (e.g. OpenAI, Anthropic, Phoenix)
- Generate boilerplate for a protocol-compliant adapter


Do NOT use this skill for:
- Changes to the verdict pipeline (use the `whatifd-design` skill)
- Config or schema changes that don't involve a new adapter
- Debugging or reviewing existing adapters

---

## How a skill is created (the three-step process)

### Step 1 - Write `src/whatifd/skills/<name>/skill.md`

Create the directory and write a `skill.md` with YAML frontmatter.
The frontmatter is the machine-readable declaration; the markdown body is
human-readable implementation context embedded in the generated docstring.

See the full frontmatter schema below and the copy-paste template at
`.claude/skills/capabilities/templates/skill-template.md`.


### Step 2 - Run the generator

```bash
whatifd skill generate <name>
```

This reads `src/whatifd/skills/<name>/skill.md`, generates
`src/whatifd/skills/<name>/__init__.py`, and prints two blocks of patch
instructions to stdout:
- **config.py patch** - a new `<Name>Config` Pydantic model and where to wire it
- **factory.py patch** - the dispatch branch to add to `build_scorer` / `build_trace_source`

The generator does NOT modify `config.py` or `factory.py` automatically (v0.1 policy).
The operator applies those patches manually after reviewing the output.

Options:
- `--overwrite` - allow overwriting an existing `__init__.py`
-  `--skills-root <path>` - use a different root (default: `src/whatifd/skills`)


### Step 3 - Apply patches and run tests

1. Copy the `config.py` patch block printed by the generator into
   `src/whatifd/config.py` (add the new Pydantic model + union field update).
2. Copy the `factory.py` patch block into `src/whatifd/adapters/factory.py`
   (add the dispatch branch inisde `builder_scorer` or `build_trace_source`).
3. Implement the `TODO` sections in the generated `__init__.py`.
4. Run the test suite:
   ```bash
   whatifd skill generate example # smoke-test the generator itself
   pytest tests/ -x -q
   mypy src/whatifd/skill/<name>
   ```
   

---


## The `skill.md` frontmatter schema


All fields use `extra="forbid"` - unknown keys raise `SkillManifestError`.

```yaml
---
name: <slug>               # Required. Valid Python identifier (e.g. anthropic_scorer).
description: "<text>"      # Required. One-line description used in the generated docstring.
version: "0.1"             # Optional. Semver-like string (default "0.1").
kind: scorer               # Required. One of: scorer | tracer | runner

env_vars:                  # Optional. Environment variables the adapter reads.
  - name: MY_API_KEY       # UPPER_SNAKE_CASE only.
    required: true         # Default true.
    description: "..."

parameters:                # Optional. Constructor fields for the generated class.
  - name: model_id         # Valid Python identifier.
    type: str              # str | int | float | bool only.
    required: true         # Default true.
    description: "..."
  - name: timeout
    type: float
    required: false
    default: "30.0"
    description: "...."
---


## Markdown body

Everything after the closing `---` becomes the  "Implementation notes"
section in the generated docstring. Write prose here describing:
- What the adapter does
- How it connects to the external system
- Any non-obvious implementation constraints
- Cardinal rule reminders specific to this adapter
```


### Field rules

| Field | Constraint |
|---|---|
| `name` | Python identifier; no keywords; used as module name and class prefix |
| `kind` | Exactly one of `scorer`, `tracer`, `runner` |
| `env_var[].name` | `UPPER_SNAKE_CASE` - letters, digits, underscores; must start with uppercase |
| `parameters[].type` | `str`, `int`, `float`, or `bool` only - complex types use `str` + documented format |
| `parameters[].default` | Required when `required: false`; must be a valid Python literal string |
| `version` | Semver-like: `"0.1"`, `"1.0"`, `"1.0.0"` |

---

## What the generator produces


### `kind: scorer`

A Class `<Name>Scorer` that satisfies the `Scorer` protocol:
- `score(case: ScoreCase) -> JudegeResult`
- `cache_key_componentns(case: ScoreCase) -> CacheKeyComponents`
- `adapter_metadata() -> AdapterMetadata`
- `TYPE_CHECKING` witness: `_protocol_witness: Scorer = <Name>Scorer.__new__(...)`


### `kind: tracer`

A clas `<Name>TraceSource` that satisfies the `TraceSource` protocol:
- `iter_traces() -> Iterator[RawTrace]`
- `adapter_metadata() -> AdapterMetadata`
- `cluster_key_support() -> ClusterKeySupport`
- `TYPE_CHECKING` witness

### `kind: runner`

An `async def <name>_runner(case: RunnerCase) -> RunnerResult` function.

All stubs raise `NotImplementedError` with an actionable message pointing at the `skill.md`
implementation notes.


---

## Cardinal rules that apply to skills


### Rule #1 - Failures as data

Every error in skill adapters must surface as a typed exception with an actionable 
message. Use `AdapterFactoryError` for construction failures, never raw `ImportError` or 
`ValueError`.


```python
# Wrong
from my_sdk import Client # ImportError leaks

# Right (in factory.py dispatch branch)
try:
   from my_sdk import Client
except ImportError as exc:
   raise AdapterFactoryError(
       "my_adapter requires my-sdk. Install with: pip install my-sdk"
      ) from exc
```


### Rule #5 - Sensitive data is wrapped, never raw

Any user content (trace messages, model responses, rationale text) that enters a skill adapter 
MUST be wrapped in `Sentitive[T]` before being stored or returned. The generated stub 
includes an inline comment reminder.


```python
from whatifd.types.sensitive import Sensitive

# At the adapter boundary - wrap immediately
user_msg = Sensitive(value=raw_text, classification="user_content")

# When you must unwrap - always supply a reason (audit-logged)
plain = user_msg.unwrap(reason="passing to judge model API")
```


The serializer's graph-walk (`assert_no_unredacted_sensitive`) will catch unwrapped Sensitive values
before serialization - but the adapter boundary is where the wrapping must happen, not at the serializer.


### Rule #9 - Orchestration, not compute

Skill adapters are I/O-bound (API calls, trace fetches). Do NOT introduce:
- `ProcessPoolExecutor` or `ThreadPoolExecutor` for parallelism within a single adapter
- `numpy` for numerical operations on scores
- `asyncio.gather` batching beyond what the external SDK supports natively

If the external API returns multiple results in one call, that's fine.
If you're implementing parallel replay inside the adapter, that's wrong.


---


## Example: adding a new anthropic scorer

### `src/whatifd/skills/anthropic_scorer/skill.md`

```yaml
---
name: anthropic_scorer               
description: "Claude-based scorer using the Anthropic Messages API."      
version: "0.1"            
kind: scorer               

env_vars:                  
  - name: ANTHROPIC_API_KEY      
    required: true         
    description: "Anthropic API key."

parameters:               
  - name: judge_model_id        
    type: str              
    required: true         
    description: "Claude model ID (e.g. claude-opus-4-7)."
  - name: rubric_text
    type: str
    description: "Full rubric text passed to the judge"
    required: true
  - name: timeout
    type: float
    required: false
    default: "30.0"
    description: "Request timeout in seconds."
---

## What this skill does


Calls the Anthropic Messages API to score trace faithfulness against a rubric.
Returns a float score (0.0-1.0) and a rationale string.


## Implementation notes

Use `anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])`.
Parse the score from the model's text response using a structured prompt
that asks for a JSON block with `{"score": <float>, "rationale": "<text>"}`.
Wrap the rationale in `Sensitive(value=rationale, classification="user_content")`
before including it in the `JudgeResult`.
```

### Run the generator

```bash
whatifd skills generate anthropic_scorer
```

Output:
```
whatifd skill generate: wrote src/whatifd/skills/anthropic_scorer/__init__.py

=== config.py patch instructions ===

...

=== factory.py patch instructions ===
...
```

### Apply patches, implement TODOs, run tests

Follow the Step 3 instructions above.


---

## Diagnostic: common errors

|Error | Cause | Fix|
|---|---|---|
| `skill.md not found` | Directory exists but no `skill.md` | Create the file with frontmatter |
| `skill name 'my-skill' must be a valid Python identifier | Hyphens not allowed | Use underscores: `my_skill` |
| `parameter.type 'list' is not supported` | Complex type | Use `str` and document expected format |
| `optional parameters must supply a default value` | `required: false` without `default` | Add `default: "<value>"` |
| `__init__.py already exists` | Re-running without `--overwrite` | Pass `--overwrite` or rename the existing file |
