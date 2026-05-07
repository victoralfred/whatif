"""`whatif.config` — typed configuration with hint generation.

Phase 8.1 of the v0.1 implementation plan. Top-level `WhatifConfig`
plus per-section sub-models. Pydantic v2 strict (`extra="forbid"`)
so unknown fields fail validation rather than silently absorb. A
hint generator translates Pydantic's stack-trace-flavored errors
into a multi-line message named-fields-and-suggestions.

## Sections

  - `source` — adapter ref (e.g., `"langfuse"`).
  - `target` — runner ref (e.g., `"python:my_agent.replay:run"`).
  - `selection` — per-cohort selection limits.
  - `change` — the proposed change (`system_prompt`, `model`, etc.
    — same shape as `whatif.contract.ReplayConfig`).
  - `scorer` — scorer adapter + cache settings.
  - `decision` — verdict policy thresholds (mirrors v0.1's
    internal `DecisionPolicy` fields).
  - `reporting` — output profile + forensic acknowledgment block.
  - `timeouts` — replay / score wall-clock budgets.

## Two-affirmation rule (cardinal #7)

The `reporting.profile = "forensic"` capability is structurally
dangerous (full unredacted user content in the artifact). Cardinal
#7 requires affirmation across TWO independent surfaces before the
forensic capability activates:

  1. The config carries `reporting.profile: forensic` AND
     `reporting.forensic_acknowledgment` block populated.
  2. The CLI invocation includes `--profile forensic`.

`assert_two_affirmation(cfg, *, cli_profile)` enforces this. Single-
affirmation attempts (config-only, CLI-only, or
`forensic_acknowledgment` block missing) raise
`ForensicAffirmationError` with a message naming exactly which
surface is missing.

## Hint generation

`format_validation_errors(ValidationError)` produces a friendly
multi-line summary: per-error path + Pydantic message + a
suggestion drawn from the `_HINTS` table for the most common
misconfigurations. Falls back to "no hint registered" for codes
not in the table — operators see the raw Pydantic message either
way.

## Cardinal alignment

- **#7 two-affirmation:** load-bearing for forensic-profile
  enablement. Tests pin that single-surface attempts fail.
- **#5 sensitive data wrapped:** the forensic profile's structural
  danger is exactly that it bypasses redaction. The two-affirmation
  rule is the structural defense; without both surfaces, `redact()`
  applies the default profile.
- **#1 failures-as-data:** validation errors are typed
  (`ValidationError`); hint generation is presentational. The
  config-load function returns `WhatifConfig` or raises
  `ValidationError` — no silent defaults for missing required
  fields.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# ---------------------------------------------------------------------------
# Forensic-profile enforcement (cardinal #7)
# ---------------------------------------------------------------------------


class ForensicAffirmationError(ValueError):
    """Raised when forensic-profile enablement fails the two-
    affirmation rule. Cardinal #7.

    The error message names exactly which surface is missing
    (config block vs CLI flag) so the operator can fix the right
    one. Both surfaces are required because either alone is
    insufficient — accidental enablement on either side would
    surface unredacted content otherwise.
    """


# ---------------------------------------------------------------------------
# Per-section sub-models
# ---------------------------------------------------------------------------

# Strict Pydantic v2 config: forbid unknown fields so a typo
# surfaces as a validation error, NOT as a silently-ignored value.
_STRICT = ConfigDict(extra="forbid", strict=True)


class SourceConfig(BaseModel):
    """Trace source adapter reference + per-source options."""

    model_config = _STRICT

    adapter: str = Field(
        ...,
        description="Adapter name; e.g., 'langfuse'. Resolved at load time.",
    )
    # Adapter-specific options omitted from v0.1 per YAGNI:
    # `langfuse` (the only v0.1 adapter) takes no config-level
    # options. Phase 4 adapter integration will revisit if a future
    # adapter needs them; the typed shape (dedicated `<Adapter>Options`
    # model, NOT `dict[str, Any]`) lands then per cardinal #6.


class TargetConfig(BaseModel):
    """Runner target reference. v0.1 supports `python:` runners."""

    model_config = _STRICT

    runner: str = Field(
        ...,
        description=(
            "Runner reference; v0.1 supports `python:module.path:attr`. "
            "Async runners are detected at import time."
        ),
    )


class CohortSelectionConfig(BaseModel):
    model_config = _STRICT

    limit: int = Field(..., ge=1)
    filter: str | None = None


class SelectionConfig(BaseModel):
    """Per-cohort selection limits."""

    model_config = _STRICT

    failure_cohort: CohortSelectionConfig
    baseline_cohort: CohortSelectionConfig


class ChangeConfig(BaseModel):
    """The proposed change. Mirrors `whatif.contract.ReplayConfig`
    keys; v0.1 supports `system_prompt` only."""

    model_config = _STRICT

    system_prompt: str | None = None
    model: str | None = None


class ScorerConfig(BaseModel):
    model_config = _STRICT

    adapter: str
    cache_mode: Literal["auto", "on", "off", "read_only", "refresh"] = "auto"


class DecisionConfig(BaseModel):
    """Mirrors `whatif.types.policy.DecisionPolicy` fields. The
    runtime constructs a `DecisionPolicy` from these values.
    """

    model_config = _STRICT

    require_baseline: bool = True
    max_baseline_regression_ratio: float = Field(0.10, ge=0.0, le=1.0)
    min_failure_improvement_ratio: float = Field(0.50, ge=0.0, le=1.0)
    max_ci_width: float | None = Field(None, ge=0.0)
    practical_delta_epsilon: float = Field(0.05, ge=0.0)


class ForensicAcknowledgment(BaseModel):
    """The config-side affirmation for forensic profile enablement.

    Populating this block is one of the two surfaces required by
    cardinal #7. The CLI flag is the other. The fields exist to
    make accidental enablement IMPOSSIBLE — a deployment that
    typos `forensic_ackn0wledgment` (zero) hits Pydantic's
    `extra="forbid"` and fails immediately.
    """

    model_config = _STRICT

    accepted_by: str = Field(..., min_length=1)
    accepted_at: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class ReportingConfig(BaseModel):
    model_config = _STRICT

    profile: Literal["default", "review", "minimal", "forensic"] = "default"
    forensic_acknowledgment: ForensicAcknowledgment | None = None

    @model_validator(mode="after")
    def _forensic_requires_acknowledgment_block(self) -> ReportingConfig:
        """Config-level half of the two-affirmation rule. The CLI
        half is enforced by `assert_two_affirmation` at startup —
        this validator only catches the case where `profile:
        forensic` is set without the acknowledgment block."""
        if self.profile == "forensic" and self.forensic_acknowledgment is None:
            raise ValueError(
                "reporting.profile='forensic' requires a populated "
                "reporting.forensic_acknowledgment block (cardinal #7 "
                "two-affirmation rule). Add accepted_by, accepted_at, "
                "and reason; then re-run with `--profile forensic`."
            )
        return self


class TimeoutsConfig(BaseModel):
    model_config = _STRICT

    replay_seconds: float = Field(60.0, gt=0.0)
    score_seconds: float = Field(30.0, gt=0.0)


# ---------------------------------------------------------------------------
# Top-level config
# ---------------------------------------------------------------------------


class WhatifConfig(BaseModel):
    """Top-level whatif configuration.

    Loaded from `whatif.config.yaml` (or alternative path) at CLI
    startup. Pydantic v2 strict mode rejects unknown fields at any
    nesting level — typos fail loud rather than silently absorb.
    """

    model_config = _STRICT

    source: SourceConfig
    target: TargetConfig
    selection: SelectionConfig
    change: ChangeConfig
    scorer: ScorerConfig
    # decision / reporting / timeouts sections are REQUIRED at the
    # top-level config. Each sub-model's fields carry their own
    # defaults, so an empty `decision: {}` block in YAML is enough
    # to opt in to the v0.1 defaults — but the section must be
    # present, not silently inferred. This avoids the
    # `model_construct` / `model_validate({})` factory complexity
    # while keeping mypy strict happy without the Pydantic plugin.
    decision: DecisionConfig
    reporting: ReportingConfig
    timeouts: TimeoutsConfig


# ---------------------------------------------------------------------------
# Two-affirmation enforcement
# ---------------------------------------------------------------------------


def assert_two_affirmation(cfg: WhatifConfig, *, cli_profile: str | None) -> None:
    """Enforce the cardinal-#7 two-affirmation rule for forensic.

    Both surfaces must agree:
      - config: `reporting.profile == "forensic"` AND
        `reporting.forensic_acknowledgment` block populated
      - CLI: `--profile forensic` (passed as `cli_profile="forensic"`)

    The config-side post-init validator already catches "profile
    forensic but no acknowledgment block". This function's job is
    to enforce the cross-surface match: forensic on one side
    without forensic on the other is the dangerous-misconfiguration
    case.

    ## CLI startup ordering

    Call this at CLI startup IMMEDIATELY after `WhatifConfig` loads
    and BEFORE any forensic-path code runs. Config construction
    alone enforces only the config-side half of cardinal #7; the
    cross-surface check below is what catches `--profile forensic`
    without the matching config block (or vice versa). Phase 8.2
    CLI must call this before resolving the redaction profile.
    """
    config_says_forensic = cfg.reporting.profile == "forensic"
    cli_says_forensic = cli_profile == "forensic"

    if config_says_forensic and not cli_says_forensic:
        raise ForensicAffirmationError(
            "Forensic profile enabled in config (reporting.profile='forensic') "
            "but the CLI invocation did not include `--profile forensic`. "
            "Cardinal #7 requires affirmation across BOTH surfaces. "
            "Either add `--profile forensic` to the command line or "
            "remove the forensic profile from config."
        )
    if cli_says_forensic and not config_says_forensic:
        raise ForensicAffirmationError(
            "CLI invoked with `--profile forensic` but config does not "
            "set reporting.profile='forensic' with a populated "
            "forensic_acknowledgment block. Cardinal #7 requires "
            "affirmation across BOTH surfaces. The CLI flag alone is "
            "insufficient."
        )


# ---------------------------------------------------------------------------
# Hint generation
# ---------------------------------------------------------------------------

# Map (loc-tail, error-type) → human-readable hint. The loc-tail is
# the last element of the Pydantic error's `loc` tuple; the error-
# type is Pydantic's `type` field. This is intentionally a small
# table — the goal is to cover the top-N common misconfigurations,
# not be exhaustive (operators see the raw Pydantic message either
# way).
# Map (full-loc-path, error-type) -> human-readable hint. The path
# is the dotted location string (matching `loc` joined with '.')
# so identically-named fields in different sections (e.g.,
# `source.adapter` vs `scorer.adapter`) get distinct hints.
#
# The model_validator path for forensic_acknowledgment is
# intentionally NOT in this table: Pydantic emits those errors
# with `loc=()` (empty tuple), so there's no field path to key on.
# The validator's raised message already includes the actionable
# text, so the bare Pydantic message surfaces correctly without a
# hint.
_HINTS: dict[tuple[str, str], str] = {
    ("source.adapter", "missing"): ("set `source.adapter` to your tracer name (e.g., 'langfuse')."),
    ("target.runner", "missing"): ("set `target.runner` to a `python:module.path:attr` string."),
    ("selection.failure_cohort.limit", "greater_than_equal"): (
        "selection.failure_cohort.limit must be >= 1; use a positive integer."
    ),
    ("selection.baseline_cohort.limit", "greater_than_equal"): (
        "selection.baseline_cohort.limit must be >= 1; use a positive integer."
    ),
    ("decision.max_baseline_regression_ratio", "less_than_equal"): (
        "decision.max_baseline_regression_ratio must be a fraction in [0, 1]."
    ),
    ("decision.min_failure_improvement_ratio", "less_than_equal"): (
        "decision.min_failure_improvement_ratio must be a fraction in [0, 1]."
    ),
    ("decision.practical_delta_epsilon", "greater_than_equal"): (
        "decision.practical_delta_epsilon must be >= 0."
    ),
    ("timeouts.replay_seconds", "greater_than"): ("timeouts.replay_seconds must be > 0."),
    ("timeouts.score_seconds", "greater_than"): ("timeouts.score_seconds must be > 0."),
}


def format_validation_errors(exc: ValidationError) -> str:
    """Format a Pydantic `ValidationError` as a multi-line operator-
    facing message with hints where available.

    Each error in `exc.errors()` becomes a block:

      <dotted.field.path>: <pydantic-message>
        Hint: <suggestion> (when registered in _HINTS)

    Errors are emitted in `exc.errors()` order — Pydantic surfaces
    them depth-first by location, which produces a readable
    walkthrough of the misconfiguration without sorting.
    """
    lines: list[str] = ["whatif config validation failed:", ""]
    for err in exc.errors():
        path = ".".join(str(part) for part in err["loc"]) or "(root)"
        msg = err["msg"]
        lines.append(f"  {path}: {msg}")
        hint = _HINTS.get((path, err["type"]))
        if hint is not None:
            lines.append(f"    Hint: {hint}")
        lines.append("")
    # Trim the trailing blank line so the output ends cleanly.
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


__all__ = [
    "ChangeConfig",
    "CohortSelectionConfig",
    "DecisionConfig",
    "ForensicAcknowledgment",
    "ForensicAffirmationError",
    "ReportingConfig",
    "ScorerConfig",
    "SelectionConfig",
    "SourceConfig",
    "TargetConfig",
    "TimeoutsConfig",
    "WhatifConfig",
    "assert_two_affirmation",
    "format_validation_errors",
]
