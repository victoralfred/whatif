"""Generate adapter code fomr a ``SkillManifest``.

``generate_skill(manifest, body_md)`` returns a ``GeneratedSkill`` dataclass
containing:
- ``skill_code``: the full ``__init__.py`` content (valid Python).
- ``config_patch_hint``: actionable instructions for adding config fields to
  ``src/whatifd/config.py`` (printed, not applied automatically).
- ``factory_patch_hint``: actionable instructions for adding factory registration
  to ``src/whatifd/adapters/factory.py`` (printed, not applied automatically).

Generation is deterministic: same manifest -> same output. No LLM calls.

## Generated code shape

### kind=scorer

```python
@dataclass(frozen=True, slots=True)
class <Name>Scorer:
    <parameters as dataclass fields>

    def score(self, case: ScoreCase) -> JudgeResult: ...
    def cache_key_components(self, case: ScoreCase) -> CacheKeyComponents: ...
    def adapter_metadata(self) -> AdapterMetadata: ...

if TYPE_CHECKING:
    _protocol_witness: Scorer = <Name>Scorer.__new__(<Name>Scorer)
```

### kind=tracer

```python
@dataclass(frozen=True, slots=True)
class <Name>TraceSource:
    <parameters as dataclass fields>

    def iter_traces(self) -> Iterator[RawTrace]: ...
    def cluster_key_support(self) -> ClusterKeySupport: ...
    def adapter_metadata(self) -> AdapterMetadata: ...

if TYPE_CHECKING:
    _protocol_witness: TraceSource = <Name>TraceSource.__new__(<Name>TraceSource)
```

### kind=runner

```python
async def <name>_runner(case: RunnerCase) -> RunnerResult:
    ...
```

All stubs raise ``NotImplementedError`` with an actionable message pointing at
the implementation notes in ``skill.md``. Cardinal #5 warnings are included as
inline comment so implementors cannot miss them.
"""

from __future__ import annotations

from dataclasses import dataclass

from whatifd.skills.errors import SkillGenerationError
from whatifd.skills.schema import ParameterSpec, SkillManifest


@dataclass(frozen=True, slots=True)
class GeneratedSkill:
    """Output of ``generate_skill``."""

    skill_code: str
    config_patch_hint: str
    factory_patch_hint: str


def generate_skill(manifest: SkillManifest, body_md: str) -> GeneratedSkill:
    """Produce adapter code and patch hints from a validated manifest.

    :param manifest: Validated ``SkillManifest`` from the loader.

    :param body_md: Raw mardown body from ``skill.md`` (used as implementation
                    context in the generated docstring).

    :return:  ``GeneratedSkill`` with rendered code and patch instructions.

    :raises: SkillGenerationError: If the manifest kind is unrecognized or template
             rendering fails for any reason.
    """
    try:
        if manifest.kind == "score":
            code = _render_scorer(manifest, body_md)
        elif manifest.kind == "tracer":
            code = _render_tracer(manifest, body_md)
        elif manifest.kind == "runner":
            code = _render_runner(manifest, body_md)
        else:
            raise SkillGenerationError(
                f"Unrecognized skill kind: {manifest.kind!r}"
                "Supported: 'scorer', 'tracer', 'runner'."
            )
    except SkillGenerationError:
        raise
    except Exception as exc:
        raise SkillGenerationError(
            f"Template rendering failed for skill: {manifest.name!r}:"
            f"{type(exc).__name__}: {exc}"
        ) from exc

    config_hint = _render_config_hint(manifest)
    factory_hint = _render_factory_hint(manifest)

    return GeneratedSkill(
        skill_code=code,
        config_patch_hint=config_hint,
        factory_patch_hint=factory_hint,
    )


#-----------------------------------------------------------------------
# Internal helpers
#-----------------------------------------------------------------------


def _title(name: str) -> str:
    """'my_skill' -> 'My Skill'"""
    return "".join(part.capitalize() for part in name.split("_"))

def _render_fields(parameters: list[ParameterSpec]) -> str:
    """Render dataclass field declarations from parameter specs."""
    if not parameters:
        return ""
    lines = []
    for p in parameters:
        type_hint = p.type
        if p.required:
            lines.append(f"    {p.name}: {type_hint}")
        else:
            lines.append(f"    {p.name}: {type_hint} = {p.default}")
    return "\n".join(lines)


def _render_env_block(manifest: SkillManifest) -> str:
    """Render the env-var docblock section."""
    if not manifest.env_vars:
        return ""
    lines = ["\n## Required environment variables\n"]
    for ev in manifest.env_vars:
        req = "required" if ev.required else "optional"
        lines.append(f"   {ev.name}  ({req}): {ev.description}")
    return "\n".join(lines)


def _render_param_notes(manifest: SkillManifest) -> str:
    """Render parameter documentation lines."""
    if not manifest.parameters:
        return ""
    lines = ["\n## Constructor parameters\n"]
    for p in manifest.parameters:
        req = "required" if p.required else f"optional, default={p.default}"
        lines.append(f"   {p.name} ({p.type}, {req}): {p.description}")
    return "\n".join(lines)


def _render_body_block(body_md: str) -> str:
    """Indent the skill.md body into the docstring"""
    if not body_md.strip():
        return ""
    indented = "\n".join("    " + line if line else "" for line in body_md.splitlines())
    return f"\n## Implementation notes from skill.md\n\n{indented}"


def _render_scorer(manifest: SkillManifest, body_md: str) -> str:
    """Render the scoring function docstring."""
    class_name = f"{_title(manifest.name)}Scorer"
    fields = _render_fields(manifest.parameters)
    fields_block = f"\n{fields}\n" if fields else ""
    env_block = _render_env_block(manifest)
    param_notes = _render_param_notes(manifest)
    body_block = _render_body_block(body_md)

    return f'''\
"""{manifest.name} skill - generated by `whatifd skill generate {manifest.name}`.

{manifest.description}
{env_block}{param_notes}{body_block}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator

from whatifd.adapters.protocols import (
  AdapterMetadata,
  CacheKeyComponents,
  JudgeResult,
  RawTrace,
  ScoreCase,
) 

# Cardinal #5: any user-content entering the adapter boundary MUST be wrapped in
# Sensitive[T] before being stored or returned. Use:
#   from whatifd.types.sensitive import Sensitive
#   Sensitive(value=..., classification="user_content")
# Unwrapping requires .unwrap(reason="...") which audit-logs the access.


if TYPE_CHECKING:
    from whatifd.adapters.protocols import Scorer
    

@dataclass(frozen=True, slots=True)
class {class_name}:
    """{manifest.description}"""
{fields_block}
    def score(self, case: ScoreCase) -> JudgeResult:
        # TODO: implement scoring logic.
        # Cardinal #5 wrap any user content (rationale text, etc.) in Sensitive[T].
        # Example:
        #   from whatifd.types.sensitive import Sensitive
        #   rationale = Sensitive(value="...", classification="user_content")
        raise NotImplementedError(
              "{manifest.name} scorer: implement score() before production use. "
              "See src/whatifd/skills/{manifest.name}/skill.md for implementation notes."
              )
    
    def cache_key_components(self, case: ScoreCase) -> CacheKeyComponents:
        # TODO: return a CacheKeyComponents with deterministic fields.
        # Include model_id, prompt_hash, rubric_hash - anything that
        # distinguishes one scoring call from another.
        raise NotImplementedError(
              "{manifest.name} scorer: implement cache_key_components(). "
              "Return a CacheKeyComponents(model_id=..., prompt_hash=..., rubric_hash=...)."
              )
              
    def adapter_metadata(self) -> AdapterMetadata:
        # TODO: replace package_version with importlib.metadata.version("<your-package>")
        # once the adapter is in its own package.
        return AdapterMetadata(
            adapter_id="{manifest.name}",
            package_version="{manifest.version}",
            )
            
    # Satisfy TraceSource (unused here but kept for completeness when copy-pasting).
    def iter_traces(self) -> Iterator[RawTrace]:
        raise NotImplementedError("{manifest.name}: iter_traces() not applicable for scorers.")
        
if TYPE_CHECKING:
    # TYPE_CHECKING witness: this line fails at mypy-time if {class_name}
    # no longer satisfies the Scorer protocol, catching signature drift
    # before it reaches CI.
    _protocol_witness: Scorer = {class_name}.__new__({class_name})        
'''

def _render_tracer(manifest: SkillManifest, body_md: str) -> str:
    class_name = f"{_title(manifest.name)}TraceSource"
    fields = _render_fields(manifest.parameters)
    fields_block = f"\n{fields}\n" if fields else ""
    env_block = _render_env_block(manifest)
    param_notes = _render_param_notes(manifest)
    body_block = _render_body_block(body_md)

    return f'''\
"""{manifest.name} skill - generated by `whatifd skill generate {manifest.name}`.

{manifest.description}
{env_block}{param_notes}{body_block}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator

from whatifd.adapters.protocols import (
  AdapterMetadata,
  ClusterKeySupport,
  RawTrace,
) 

# Cardinal #5: user-content fields in RawTrace MUST be wrapped in
# Sensitive[T]. Use:
#   from whatifd.types.sensitive import Sensitive
#   Sensitive(value=..., classification="user_content")


if TYPE_CHECKING:
    from whatifd.adapters.protocols import TraceSource
    

@dataclass(frozen=True, slots=True)
class {class_name}:
    """{manifest.description}"""
{fields_block}
    def iter_traces(self) -> Iterator[RawTrace]:
        # TODO: yield RawTrace objects fetches from the external system.
        # Cardinal #5 wrap any user_message and original_response in Sensitive[T]:
        # Example:
        #   from whatifd.types.sensitive import Sensitive
        #   yield RawTrace(
        #           trace_id="...",
        #           cohort="failure", # or "baseline"
        #           user_message=Sensitive(value="...", classification="user_content"),
        #           original_response=Sensitive(value="...", classification="user_content"),
        #           )
        raise NotImplementedError(
              "{manifest.name} tracer: implement iter_traces() before production use. "
              "See src/whatifd/skills/{manifest.name}/skill.md for implementation notes."
        ) 
        # mypy requires the return type annotation to be satisfied:
        return # pragma: no cover
        yield RawTrace(
                 trace_id="",
                 cohort="",
                 user_message=None, # type: ignore[arg-type]
                 original_response=None, # type: ignore[arg-type]
           )
    def adapter_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id="{manifest.name}",
            package_version="{manifest.version}",
        )
    
    def cluster_key_support(self) -> ClusterKeySupport:
        # TODO: return ClusterKeySupport.SUPPORTED if traces carry cluster_key.
        return ClusterKeySupport.NOT_SUPPORTED
            
    
if TYPE_CHECKING:
    _protocol_witness: TraceSource = {class_name}.__new__({class_name})    
'''

def _render_runner(manifest: SkillManifest, body_md: str) -> str:
    env_block = _render_env_block(manifest)
    param_notes = _render_param_notes(manifest)
    body_block = _render_body_block(body_md)

    # Runners are plain async callables, not classes.
    params = ", ".join(
        f"{p.name}: {p.type}" + (f" = {p.default}" if not p.required else "")
        for p in manifest.parameters
    )
    params_str = f", {params}" if params else ""


    return f'''\
"""{manifest.name} skill - generated by `whatifd skill generate {manifest.name}`.

{manifest.description}
{env_block}{param_notes}{body_block}
"""

from __future__ import annotations

from whatifd.contract import RunnerCase, RunnerResult


async def {manifest.name}_runner(case: RunnerCase{params_str}) -> RunnerResult:
    """Run the {manifest.name} experiment against a single trace.
    
    :param case: The runner case containing the trace and proposed change.
    
    :returns: RunnerResult with the new response and any replay metadata.
    
    :raises: NotImplementedError: Until the implementation is complete.
    """
    # TODO: implement the runner logic.
    # The runner receives the proposed change (case.change) and a trace
    # (case.trace). It replays the trace with the change applied and 
    # returns the new response.
    # 
    # Cardinal #5: the runner must NOT unwrap Sensitive fields from the trace
    # without .unwrap(reason="...") - the audit log records the access.
    # Never pass raw Sensitive objects to external APIs.
    raise NotImplementedError(
                "{manifest.name} runner: implement {manifest.name}_runner() before use. "
                "See src/whatifd/skills/{manifest.name}/skill.md for implementation notes."
        )
'''


def _render_config_hint(manifest: SkillManifest) -> str:
    """Produce a human-readable config.py patch instruction."""
    class_name = f"{_title(manifest.name)}Config"
    fields = []
    for p in manifest.parameters:
        type_hint = p.type
        if not p.required:
            fields.append(f"    {p.name}: {type_hint} = {p.default}")
        else:
            fields.append(f"    {p.name}: {type_hint}")

    fields_str = "\n".join(fields) if fields else "   pass # no parameters"

    adapter_literal = f'Literal["stub", "{manifest.name}"]'

    return f"""\
=== config.py patch instructions ===

1. Add this Pydantic model near the other  *Config classes:

    class {class_name}(BaseModel):
        model_config = _STRICT
        adapter: {adapter_literal}
{fields_str}

2. In WhatIfConfig, update the relevant field type. For example, if this is
    a scorer, change:
       scorer: ScorerConfig
    to include your new adapter:
       scorer: ScorerConfig | {class_name}
       
    Or add it as a union discriminated on `adapter`
        scorer: Annotated[ScorerConfig | {class_name}, Field(discriminator="adapter")]

3. Add env-var hints to the _HINTS dict for user-facing error messages:
{chr(10).join(f'    ("scorer.{p.name}", "missing"): "Set scorer.{p.name} in your config."' for p in manifest.parameters)}
"""

def _render_factory_hint(manifest: SkillManifest) -> str:
    """Produce a human-readable factory.py patch instruction."""
    kind_fn = {
        "scorer": "build_scorer",
        "tracer": "build_trace_source",
        "runner": "load_runner",
    }.get(manifest.kind, "build_scorer")

    class_suffix = {"scorer": "Scorer", "tracer": "TraceSource", "runner": "Runner"}.get(
        manifest.kind, "Scorer"
    )
    class_name = f"{_title(manifest.name)}{class_suffix}"
    module_path = f"whatifd.skills.{manifest.name}"

    constructor_args = "\n".join(
        f"        {p.name}=cfg.{p.name}," for p in manifest.parameters
    )
    constructor_block = f"\n{constructor_args}" if constructor_args else ""

    return f"""\
=== factory.py patch instructions ===

In ``{kind_fn}(cfg)`` in ``src/whatifd/adapters/factory.py``, add a branch:

    if cfg.adapter == "{manifest.name}":
        # Lazy import - never import at module top-level (lazy-load contract).
        try:
            from {module_path} import {class_name}
            return {class_name}({constructor_block})
        except ImportError as exc:
            raise AdapterFactoryError(
                "{manifest.name} adapter requires the skill package. "
                "Ensure src/whatifd/skills/{manifest.name}/__init__.py exists."
            ) from exc
        return {class_name}({constructor_block}
        )
        
Place this branch BEFORE the final ``raise AdapterFactoryError(...)`` fallback.

If the skill requires environment variables, read them before the import:
{chr(10).join(f'     {ev.name} = os.environ.get("{ev.name}")' for ev in manifest.env_vars)}
"""


__all__ = ["GeneratedSkill", "generate_skill"]