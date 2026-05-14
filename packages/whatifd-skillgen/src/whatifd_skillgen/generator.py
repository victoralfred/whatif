"""Generate adapter code from a ``SkillManifest``.

``generate_skill(manifest, body_md)`` returns a ``GeneratedSkill`` dataclass:

- ``skill_code``: complete ``__init__.py`` content (valid Python).
- ``config_patch_hint``: instructions for wiring config into whatifd's
  ``src/whatifd/config.py``.
- ``factory_patch_hint``: instructions for wiring the dispatch branch into
  ``src/whatifd/adapters/factory.py``.

Generation is deterministic: same manifest → same output. No LLM calls, no
randomness, no timestamps.

## Generated code shapes

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
async def <name>_runner(case: RunnerCase) -> RunnerResult: ...
```

All stubs raise ``NotImplementedError`` with an actionable message. Cardinal
#5 (Sensitive[T]) reminders are inlined so implementors cannot miss them.
The ``adapter_metadata()`` stub reads the distribution version from
``importlib.metadata`` — never a hardcoded string.
"""

from __future__ import annotations

from dataclasses import dataclass

from whatifd_skillgen.errors import SkillGenerationError
from whatifd_skillgen.schema import ParameterSpec, SkillManifest


@dataclass(frozen=True, slots=True)
class GeneratedSkill:
    """Output of ``generate_skill``."""

    skill_code: str
    config_patch_hint: str
    factory_patch_hint: str


def generate_skill(manifest: SkillManifest, body_md: str) -> GeneratedSkill:
    """Produce adapter code and patch hints from a validated manifest.

    :param manifest: Validated ``SkillManifest`` from the loader.
    :param body_md: Raw markdown body from ``skill.md`` (implementation context).
    :returns: ``GeneratedSkill`` with rendered code and patch instructions.
    :raises SkillGenerationError: If template rendering fails for any reason.
    """
    try:
        if manifest.kind == "scorer":
            code = _render_scorer(manifest, body_md)
        elif manifest.kind == "tracer":
            code = _render_tracer(manifest, body_md)
        elif manifest.kind == "runner":
            code = _render_runner(manifest, body_md)
        else:
            raise SkillGenerationError(
                f"Unrecognized skill kind: {manifest.kind!r}. "
                "Supported: 'scorer', 'tracer', 'runner'."
            )
    except SkillGenerationError:
        raise
    except Exception as exc:
        raise SkillGenerationError(
            f"Template rendering failed for skill {manifest.name!r}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    return GeneratedSkill(
        skill_code=code,
        config_patch_hint=_render_config_hint(manifest),
        factory_patch_hint=_render_factory_hint(manifest),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _title(name: str) -> str:
    """'my_adapter' -> 'MyAdapter'"""
    return "".join(part.capitalize() for part in name.split("_"))


def _dist_name(name: str) -> str:
    """'my_adapter' -> 'whatifd-my-adapter' (PyPI distribution name)"""
    return "whatifd-" + name.replace("_", "-")


def _render_fields(parameters: list[ParameterSpec]) -> str:
    if not parameters:
        return ""
    lines = []
    for p in parameters:
        if p.required:
            lines.append(f"    {p.name}: {p.type}")
        else:
            lines.append(f"    {p.name}: {p.type} = {p.default}")
    return "\n".join(lines)


def _render_env_block(manifest: SkillManifest) -> str:
    if not manifest.env_vars:
        return ""
    lines = ["\n## Required environment variables\n"]
    for ev in manifest.env_vars:
        req = "required" if ev.required else "optional"
        lines.append(f"   {ev.name}  ({req}): {ev.description}")
    return "\n".join(lines)


def _render_param_notes(manifest: SkillManifest) -> str:
    if not manifest.parameters:
        return ""
    lines = ["\n## Constructor parameters\n"]
    for p in manifest.parameters:
        req = "required" if p.required else f"optional, default={p.default}"
        lines.append(f"   {p.name} ({p.type}, {req}): {p.description}")
    return "\n".join(lines)


def _render_body_block(body_md: str) -> str:
    if not body_md.strip():
        return ""
    indented = "\n".join("    " + line if line else "" for line in body_md.splitlines())
    return f"\n## Implementation notes from skill.md\n\n{indented}"


def _render_scorer(manifest: SkillManifest, body_md: str) -> str:
    class_name = f"{_title(manifest.name)}Scorer"
    fields = _render_fields(manifest.parameters)
    fields_block = f"\n{fields}\n" if fields else ""
    env_block = _render_env_block(manifest)
    param_notes = _render_param_notes(manifest)
    body_block = _render_body_block(body_md)
    dist = _dist_name(manifest.name)

    return f'''\
"""{manifest.name} adapter - generated by `whatifd-skillgen generate`.

{manifest.description}
{env_block}{param_notes}{body_block}
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import version as _dist_version
from typing import TYPE_CHECKING

from whatifd.adapters.protocols import (
    AdapterMetadata,
    CacheKeyComponents,
    JudgeResult,
    ScoreCase,
)

# Cardinal #5: any user-content entering the adapter boundary MUST be wrapped in
# Sensitive[T] before being stored or returned:
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
        # Cardinal #5: wrap any user-content (rationale text, etc.) in Sensitive[T].
        #   from whatifd.types.sensitive import Sensitive
        #   rationale = Sensitive(value="...", classification="user_content")
        raise NotImplementedError(
            "{manifest.name}: implement score() before production use. "
            "See skill.md for implementation notes."
        )

    def cache_key_components(self, case: ScoreCase) -> CacheKeyComponents:
        # TODO: return deterministic CacheKeyComponents.
        # Include model_id, prompt_hash, rubric_hash — anything that
        # distinguishes one scoring call from another.
        raise NotImplementedError(
            "{manifest.name}: implement cache_key_components(). "
            "Return CacheKeyComponents(model_id=..., prompt_hash=..., rubric_hash=...)."
        )

    def adapter_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id="{manifest.name}",
            package_version=_dist_version("{dist}"),
        )


if TYPE_CHECKING:
    # Fails at mypy-time if {class_name} drifts from the Scorer protocol.
    _protocol_witness: Scorer = {class_name}.__new__({class_name})
'''


def _render_tracer(manifest: SkillManifest, body_md: str) -> str:
    class_name = f"{_title(manifest.name)}TraceSource"
    fields = _render_fields(manifest.parameters)
    fields_block = f"\n{fields}\n" if fields else ""
    env_block = _render_env_block(manifest)
    param_notes = _render_param_notes(manifest)
    body_block = _render_body_block(body_md)
    dist = _dist_name(manifest.name)

    return f'''\
"""{manifest.name} adapter - generated by `whatifd-skillgen generate`.

{manifest.description}
{env_block}{param_notes}{body_block}
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import version as _dist_version
from typing import TYPE_CHECKING, Iterator

from whatifd.adapters.protocols import (
    AdapterMetadata,
    ClusterKeySupport,
    RawTrace,
)

# Cardinal #5: user-content fields in RawTrace (user_message, original_response)
# MUST be wrapped in Sensitive[T] at the adapter boundary:
#   from whatifd.types.sensitive import Sensitive
#   Sensitive(value=..., classification="user_content")

if TYPE_CHECKING:
    from whatifd.adapters.protocols import TraceSource


@dataclass(frozen=True, slots=True)
class {class_name}:
    """{manifest.description}"""
{fields_block}
    def iter_traces(self) -> Iterator[RawTrace]:
        # TODO: yield RawTrace objects fetched from the external system.
        # Cardinal #5: wrap user_message and original_response in Sensitive[T]:
        #   from whatifd.types.sensitive import Sensitive
        #   yield RawTrace(
        #       trace_id="...",
        #       cohort="failure",  # or "baseline"
        #       user_message=Sensitive(value="...", classification="user_content"),
        #       original_response=Sensitive(value="...", classification="user_content"),
        #   )
        raise NotImplementedError(
            "{manifest.name}: implement iter_traces() before production use. "
            "See skill.md for implementation notes."
        )
        yield  # pragma: no cover  # satisfies Iterator return type for mypy

    def cluster_key_support(self) -> ClusterKeySupport:
        # TODO: return ClusterKeySupport.SUPPORTED if traces carry cluster_key.
        return ClusterKeySupport.NOT_SUPPORTED

    def adapter_metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id="{manifest.name}",
            package_version=_dist_version("{dist}"),
        )


if TYPE_CHECKING:
    # Fails at mypy-time if {class_name} drifts from the TraceSource protocol.
    _protocol_witness: TraceSource = {class_name}.__new__({class_name})
'''


def _render_runner(manifest: SkillManifest, body_md: str) -> str:
    env_block = _render_env_block(manifest)
    param_notes = _render_param_notes(manifest)
    body_block = _render_body_block(body_md)

    extra_params = ", ".join(
        f"{p.name}: {p.type}" + (f" = {p.default}" if not p.required else "")
        for p in manifest.parameters
    )
    params_str = f", {extra_params}" if extra_params else ""

    return f'''\
"""{manifest.name} runner - generated by `whatifd-skillgen generate`.

{manifest.description}
{env_block}{param_notes}{body_block}
"""

from __future__ import annotations

from whatifd.contract import RunnerCase, RunnerResult


async def {manifest.name}_runner(case: RunnerCase{params_str}) -> RunnerResult:
    """Run the {manifest.name} experiment against a single trace.

    :param case: The runner case containing the trace and proposed change.
    :returns: RunnerResult with the new response and any replay metadata.
    :raises NotImplementedError: Until the implementation is complete.
    """
    # TODO: implement the runner logic.
    # The runner receives a proposed change (case.change) and a trace (case.trace).
    # It replays the trace with the change applied and returns the new response.
    #
    # Cardinal #5: NEVER unwrap Sensitive fields without .unwrap(reason="...").
    # The audit log records every unwrap; passing raw Sensitive objects to
    # external APIs raises at serialization time.
    raise NotImplementedError(
        "{manifest.name}: implement {manifest.name}_runner() before use. "
        "See skill.md for implementation notes."
    )
'''


def _render_config_hint(manifest: SkillManifest) -> str:
    """Produce config.py patch instructions matching whatifd's actual config shape."""
    class_name = f"{_title(manifest.name)}Config"
    dist = _dist_name(manifest.name)
    pkg_name = f"whatifd_{manifest.name}"

    fields = []
    for p in manifest.parameters:
        if p.required:
            fields.append(f"    {p.name}: {p.type}")
        else:
            fields.append(f"    {p.name}: {p.type} = {p.default}")
    fields_str = "\n".join(fields) if fields else "    pass  # no parameters"

    # Cross-field validator example — only relevant when adapter has parameters
    # that are conditionally required.
    validator_example = ""
    if manifest.parameters:
        required_names = [p.name for p in manifest.parameters if p.required]
        if required_names:
            check = required_names[0]
            validator_example = f"""
    @model_validator(mode="after")
    def _required_when_adapter_selected(self) -> "{class_name}":
        if self.adapter == "{manifest.name}" and self.{check} is None:
            raise ValueError(
                "scorer.{check} is required when scorer.adapter='{manifest.name}'."
            )
        return self
"""

    return f"""\
=== config.py patch instructions ===

whatifd's config.py uses tightly-bound Pydantic models with cross-field
@model_validator guards. The flat field-list below is the starting shape;
add @model_validator cross-field guards for any field that is conditionally
required (e.g. required only when this adapter is selected).

1. Add this Pydantic model near the other *Config classes in
   src/whatifd/config.py. Import `model_validator` from pydantic if not
   already imported.

    class {class_name}(BaseModel):
        model_config = ConfigDict(extra="forbid")
        adapter: Literal["{manifest.name}"]
{fields_str}{validator_example}

2. In WhatifConfig, update the relevant union field. For example, for a scorer:

    scorer: Annotated[
        ScorerConfig | {class_name},
        Field(discriminator="adapter"),
    ]

   Use a discriminated union on the `adapter` field. This keeps Pydantic's
   error messages actionable (it names the failing branch, not all branches).

3. Register the new distribution as an optional dependency in pyproject.toml:

    [project.optional-dependencies]
    {manifest.name.replace("_", "-")} = ["{dist}"]

   This keeps the adapter package out of the hard-dependency set; users
   install it only when they select adapter='{manifest.name}'.

4. Add env-var hints to the _HINTS dict for user-facing validation messages
   (see the existing LANGFUSE_HOST / LANGFUSE_PUBLIC_KEY entries as the model):
{chr(10).join(f'    ("scorer.{p.name}", "missing"): "Set scorer.{p.name} in your config."' for p in manifest.parameters) or "    # no parameters to hint"}

Reference: packages/whatifd-phoenix/pyproject.toml and src/whatifd/config.py
for the canonical shape of an adapter config.
Import path for the new adapter class: from {pkg_name} import {_title(manifest.name)}{'Scorer' if manifest.kind == 'scorer' else 'TraceSource' if manifest.kind == 'tracer' else 'Runner'}
"""


def _render_factory_hint(manifest: SkillManifest) -> str:
    """Produce factory.py patch instructions matching whatifd's actual dispatch shape."""
    kind_map = {
        "scorer": ("build_scorer", "ScorerConfig", "Scorer"),
        "tracer": ("build_trace_source", "SourceConfig", "TraceSource"),
        "runner": ("load_runner", "RunnerConfig", "Runner"),
    }
    fn_name, cfg_type, suffix = kind_map.get(manifest.kind, ("build_scorer", "ScorerConfig", "Scorer"))
    class_name = f"{_title(manifest.name)}{suffix}"
    pkg_name = f"whatifd_{manifest.name}"
    dist = _dist_name(manifest.name)

    constructor_args = "\n".join(
        f"            {p.name}=cfg.{p.name}," for p in manifest.parameters
    )
    constructor_block = f"\n{constructor_args}\n        " if constructor_args else ""

    env_reads = "\n".join(
        f"        {ev.name} = os.environ.get(\"{ev.name}\")" for ev in manifest.env_vars
    )
    env_block = f"\n        # Read env vars before constructing the adapter.\n{env_reads}\n" if env_reads else ""

    return f"""\
=== factory.py patch instructions ===

whatifd's factory.py is a small explicit registry (not a generic dispatch table).
Add one ``if name == ...`` branch per adapter — see the existing langfuse and
inspect_ai branches as the canonical model.

In ``{fn_name}(cfg: {cfg_type})`` in ``src/whatifd/adapters/factory.py``,
add this branch BEFORE the final ``raise AdapterFactoryError(...)`` fallback:

    if name == "{manifest.name}":{env_block}
        try:
            from {pkg_name} import {class_name}
        except ImportError as exc:
            raise AdapterFactoryError(
                "{manifest.kind}.adapter='{manifest.name}' requires the "
                "'{dist}' package. "
                "Install with: pip install {dist}"
            ) from exc
        return {class_name}({constructor_block})

Important notes:
- Use a lazy import (inside the ``if`` branch) — never import at module
  top-level. The lazy-load contract is enforced by
  tests/unit/whatifd/adapters/test_protocols.py::
  test_core_modules_do_not_load_real_adapter_packages.
- Wrap the ImportError as AdapterFactoryError with an actionable install
  hint (cardinal #1: every expected failure is structured, not a raw traceback).
- If the adapter requires env vars, read them here and raise AdapterFactoryError
  (not KeyError) when they are missing — see _build_langfuse_source() for
  the pattern.

Reference: src/whatifd/adapters/factory.py, the inspect_ai branch starting
at line ~129, is the most complete example (lazy import + cross-validator
belt-and-suspenders checks).
"""


__all__ = ["GeneratedSkill", "generate_skill"]
