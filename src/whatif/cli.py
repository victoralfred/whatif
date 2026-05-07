"""`whatif` CLI entry point.

Phase 8.2 of the v0.1 implementation plan. Typer-based command
surface:

  - `whatif fork [--config PATH] [--profile {default|review|minimal|forensic}]`
    — main entrypoint. Loads config, runs two-affirmation,
    threads `TwoAffirmationProof` to the (Phase 4 / Phase 9)
    adapter pipeline. v0.1 8.2 ships the CLI SHELL — argument
    parsing, config load, two-affirmation, exit-code dispatch.
    The actual fork execution is gated on Phase 4 adapter
    integration; missing adapter → exit 2 with a clear setup
    message, NOT a silent fallback.
  - `whatif report-migrate` (Phase 8.5 stub)
  - `whatif cache rebuild|unlock|verify` (Phase 8.3 stubs)
  - `whatif diff <prev.json> <new.json>` (Phase 8.4 stub)

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Ship verdict |
| `1` | Don't Ship verdict |
| `2` | Inconclusive verdict, setup failure, floor violation, OR config error |

Floor violations ALWAYS produce exit 2 regardless of policy
(cardinal #2). Setup failures (missing config, validation
errors, missing forensic affirmation) also produce exit 2
because they prevent producing a verdict at all.

## Two-affirmation invocation point

`assert_two_affirmation` is called IMMEDIATELY after
`load_config` returns and BEFORE any forensic-path code runs.
The returned `TwoAffirmationProof` is threaded to downstream
code that consumes the redaction profile (Phase 8.5+ /
Phase 4 adapter). Cascade-catalog entry "CLI must enforce
two-affirmation before forensic-path code" tracks this.

## Why a thin CLI shell now

The downstream pipeline (replay → score → decision → render)
still has open dependencies on Phase 4 (adapters) and Phase 9
(integration). Shipping the CLI shell now gets the CLI surface,
exit-code semantics, and config-load flow in place; the missing
adapter integration surfaces as a typed exit-2 setup failure,
NOT as a runtime crash that bypasses cardinal #1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from whatif.cache import DEFAULT_CACHE_ROOT
from whatif.cache.recovery import rebuild, unlock, verify
from whatif.config import (
    ConfigFileError,
    ForensicAffirmationError,
    TwoAffirmationProof,
    WhatifConfig,
    assert_two_affirmation,
    format_validation_errors,
    load_config,
)
from whatif.diff import (
    DiffError,
    compute_diff,
    load_report,
    render_diff_markdown,
)

# Default config-file path. Operators override via `--config`.
_DEFAULT_CONFIG_PATH = Path("whatif.config.yaml")

# Default cache root is imported from the package's single source
# of truth (`whatif.cache.DEFAULT_CACHE_ROOT`) so a future change
# in the storage-layer canonical path propagates here automatically.

# Exit codes per the cardinal-#2 / phase-8 contract.
#
# Semantics:
#   0 - command succeeded. For `whatif fork` specifically, 0
#       means a Ship verdict (the alias `EXIT_SHIP` documents
#       that meaning at the call site). For commands that do not
#       produce a verdict (`report-migrate` no-op, future
#       `cache verify` clean-pass), 0 means "command did its
#       job"; use the `EXIT_SUCCESS` alias for clarity.
#   1 - Don't Ship verdict (fork only).
#   2 - Inconclusive verdict / setup failure / floor violation.
#       Floor violations always produce 2 regardless of policy.
EXIT_SUCCESS = 0
EXIT_SHIP = 0  # alias: fork-specific semantic name for exit 0
EXIT_DONT_SHIP = 1
EXIT_INCONCLUSIVE_OR_SETUP_FAILURE = 2

app = typer.Typer(
    name="whatif",
    help=(
        "whatif: trust-first experiment runner for LLM behavior changes. "
        "Fork production traces, replay with a proposed change, score the "
        "diff, emit a defensible Ship / Don't Ship / Inconclusive verdict."
    ),
    no_args_is_help=True,
    add_completion=False,
)


# ---------------------------------------------------------------------------
# `whatif fork` — main entry
# ---------------------------------------------------------------------------


@app.command()
def fork(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to the whatif config file (.yaml/.yml/.json).",
        ),
    ] = _DEFAULT_CONFIG_PATH,
    profile: Annotated[
        str | None,
        typer.Option(
            "--profile",
            "-p",
            help=(
                "Reporting profile override; must match the config's "
                "reporting.profile. `forensic` requires the "
                "forensic_acknowledgment block per cardinal #7."
            ),
        ),
    ] = None,
) -> None:
    """Fork production traces, replay with the proposed change, emit
    a verdict. Exit code 0 = Ship, 1 = Don't Ship, 2 = Inconclusive
    or setup failure.
    """
    try:
        cfg = load_config(config)
    except ConfigFileError as exc:
        typer.echo(f"whatif: config error: {exc}", err=True)
        raise typer.Exit(code=EXIT_INCONCLUSIVE_OR_SETUP_FAILURE) from exc
    except ValidationError as exc:
        typer.echo(format_validation_errors(exc), err=True)
        raise typer.Exit(code=EXIT_INCONCLUSIVE_OR_SETUP_FAILURE) from exc

    # TODO(cardinal #7): the cascade-catalog entry "CLI must enforce
    # two-affirmation before forensic-path code" pins this call as
    # the load-bearing site. The witness-token threading downstream
    # is Phase 4 / Phase 9 work.
    try:
        proof = assert_two_affirmation(cfg, cli_profile=profile)
    except ForensicAffirmationError as exc:
        typer.echo(f"whatif: {exc}", err=True)
        raise typer.Exit(code=EXIT_INCONCLUSIVE_OR_SETUP_FAILURE) from exc

    # Phase 8.2 dispatches into _run_fork_pipeline, which holds
    # the typed-proof contract: callers MUST pass a
    # TwoAffirmationProof. The compiler now rejects any future
    # refactor that bypasses the witness — the threading is
    # structural, not by comment convention.
    exit_code = _run_fork_pipeline(cfg, proof)
    raise typer.Exit(code=exit_code)


def _run_fork_pipeline(cfg: WhatifConfig, proof: TwoAffirmationProof) -> int:
    """Execute the fork pipeline (replay → score → decision →
    render) and return the appropriate exit code.

    The `proof: TwoAffirmationProof` parameter is the load-bearing
    witness — Phase 4 / Phase 9 wiring of the runner / scorer /
    decision / render stages MUST go through this signature. The
    compiler enforces that callers obtain the proof via
    `assert_two_affirmation`; there is no Optional default and no
    Any fallback. Mirrors cardinal #2's `FloorPassedProof` threading.

    v0.1 8.2 ships the dispatcher SHELL — Phase 4 adapter
    integration wires the runner; Phase 9 wires the full pipeline.
    Until that lands, this function returns the setup-failure exit
    code with a clear stderr message naming the missing wiring.
    The Phase-4 contributor extends this body in place; the
    function signature is the stable contract surface.

    ## Stability marker

    This function is module-private (`_`-prefixed) but its
    signature is the load-bearing Phase-4 wiring point. The test
    `TestWitnessThreading::test_run_fork_pipeline_signature_requires_proof`
    pins the signature shape (cfg, proof, return type, no
    defaults) so a Phase-4 contributor cannot rename or relax
    the contract silently — the test fails first. Renaming /
    refactoring is fine; loosening the witness-token requirement
    is not.
    """
    # Runtime guard: an `_ = proof` suppression alone would let a
    # future contributor accidentally delete the parameter (mypy
    # passes; runtime is silent). The explicit raise makes the
    # contract executable — bypassing the witness fails immediately.
    # `if/raise` rather than `assert` because `python -O` strips
    # asserts; cardinal #7 enforcement must hold under all run
    # modes including optimized production deployments.
    if not isinstance(proof, TwoAffirmationProof):
        raise TypeError(
            "_run_fork_pipeline must receive a TwoAffirmationProof "
            "from assert_two_affirmation; bypassing the witness "
            "violates cardinal #7."
        )
    # `cfg` and `proof` are accepted but not yet consumed by the
    # body — Phase 4 wires the runner from cfg.target.runner, the
    # scorer from cfg.scorer.adapter, etc. `proof.forensic_active`
    # gates the redaction profile at the artifact-bundle write
    # boundary.
    _ = cfg
    typer.echo(
        "whatif: fork pipeline requires Phase 4 adapter integration, "
        "which is not yet wired into the v0.1 CLI. Config and "
        "two-affirmation passed; downstream replay/score/decision/"
        "render stages are pending. See cascade-catalog entries "
        '"Replay subpackage boundary" and "Render subpackage '
        'boundary" for the remaining wiring.',
        err=True,
    )
    return EXIT_INCONCLUSIVE_OR_SETUP_FAILURE


# ---------------------------------------------------------------------------
# Subcommand stubs (Phase 8.3 / 8.4 / 8.5)
# ---------------------------------------------------------------------------


cache_app = typer.Typer(help="Cache management subcommands.")
app.add_typer(cache_app, name="cache")


@cache_app.command("rebuild")
def cache_rebuild(
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help=(
                "Required to actually delete entries. Without this flag, "
                "the command is a no-op safety belt against typos."
            ),
        ),
    ] = False,
    cache_root: Annotated[
        Path,
        typer.Option("--cache-root", help="Cache root (default `.whatif/cache`)."),
    ] = DEFAULT_CACHE_ROOT,
) -> None:
    """Wipe `<cache-root>/entries/`. Preserves `meta.json` and the
    lock file so the storage layer's schema-version contract stays
    intact; only cached values are removed.

    Exits 0 on a clean rebuild OR a no-op-because-no-entries-dir.
    Exits 2 when `--force` is missing (safety belt).
    """

    result = rebuild(cache_root, force=force)
    if result.error == "force_required":
        typer.echo(
            "whatif cache rebuild: refusing to delete without --force.",
            err=True,
        )
        raise typer.Exit(code=EXIT_INCONCLUSIVE_OR_SETUP_FAILURE)
    if result.error == "entries_dir_missing":
        typer.echo(
            f"whatif cache rebuild: no entries directory at {cache_root}/entries (already clean).",
        )
        raise typer.Exit(code=EXIT_SUCCESS)
    summary = (
        f"whatif cache rebuild: removed {result.entries_removed} entries "
        f"across {result.bucket_dirs_removed} bucket directories under "
        f"{cache_root}/entries."
    )
    typer.echo(summary)
    # Surface anomaly counts when non-zero so the operator sees
    # the same information the result dataclass carries. A silent
    # zero leaves clean output; a positive count prints the
    # anomaly with its location so the operator can investigate.
    if result.non_bucket_skipped:
        typer.echo(
            f"  note: skipped {result.non_bucket_skipped} non-directory "
            f"path(s) directly under {cache_root}/entries (stray files; "
            "preserved for inspection).",
            err=True,
        )
    if result.non_file_skipped_in_bucket:
        typer.echo(
            f"  note: skipped {result.non_file_skipped_in_bucket} "
            f"non-file path(s) inside bucket directories (unexpected "
            "subdirs; bucket dirs preserved for inspection).",
            err=True,
        )
    raise typer.Exit(code=EXIT_SUCCESS)


@cache_app.command("unlock")
def cache_unlock(
    allow_alive: Annotated[
        bool,
        typer.Option(
            "--allow-alive",
            help=(
                "Override the live-PID safety check. Use only when "
                "you're sure the recorded process is gone."
            ),
        ),
    ] = False,
    cache_root: Annotated[
        Path,
        typer.Option("--cache-root", help="Cache root (default `.whatif/cache`)."),
    ] = DEFAULT_CACHE_ROOT,
) -> None:
    """Remove `<cache-root>/.lock` after a PID-alive safety check.

    Default refuses to clobber a live lock; `--allow-alive`
    overrides. Exits 0 on successful unlock OR no-lock-file.
    Exits 2 when the lock holder is alive and `--allow-alive`
    was not passed.
    """

    result = unlock(cache_root, allow_alive=allow_alive)
    if result.error == "no_lock_file":
        typer.echo(
            f"whatif cache unlock: no lock file at {cache_root}/.lock (already unlocked).",
        )
        raise typer.Exit(code=EXIT_SUCCESS)
    if result.error == "lock_holder_alive":
        typer.echo(
            "whatif cache unlock: lock holder is still alive. Pass --allow-alive to override.",
            err=True,
        )
        raise typer.Exit(code=EXIT_INCONCLUSIVE_OR_SETUP_FAILURE)
    if result.error == "unlink_failed":
        # The closed UnlockErrorCode literal lets us match
        # exhaustively on the sentinel; `unlink_error` carries
        # the OS-level diagnostic separately.
        typer.echo(
            f"whatif cache unlock: unlink failed: {result.unlink_error}",
            err=True,
        )
        raise typer.Exit(code=EXIT_INCONCLUSIVE_OR_SETUP_FAILURE)

    if result.pid_was_alive:
        typer.echo(
            "whatif cache unlock: removed lock file (live-PID override via --allow-alive).",
        )
    else:
        typer.echo("whatif cache unlock: removed stale lock file.")
    raise typer.Exit(code=EXIT_SUCCESS)


@cache_app.command("verify")
def cache_verify(
    cache_root: Annotated[
        Path,
        typer.Option("--cache-root", help="Cache root (default `.whatif/cache`)."),
    ] = DEFAULT_CACHE_ROOT,
) -> None:
    """Verify cache-entry structural integrity.

    Walks `<cache-root>/entries/` and confirms each JSON file
    parses as a valid CacheEntry. Exits 0 if all entries valid OR
    no entries directory exists. Exits 2 if any entry is corrupted
    (operator should run `whatif cache rebuild --force`).

    v0.1 checks structural integrity only; cryptographic
    content-hash verification is deferred to v0.2.
    """
    result = verify(cache_root)
    if result.vacuous:
        typer.echo(
            f"whatif cache verify: no entries directory at {cache_root}/entries (vacuously clean).",
        )
        raise typer.Exit(code=EXIT_SUCCESS)
    # Print the headline (clean OR corrupted) first, then the
    # anomaly counts apply equally to both branches — operators
    # need the full picture in one invocation, not just on the
    # success path.
    if result.corrupted:
        typer.echo(
            f"whatif cache verify: {len(result.corrupted)}/{result.total} "
            "entries are corrupted. Files:",
            err=True,
        )
        for p in result.corrupted:
            typer.echo(f"  {p}", err=True)
        typer.echo(
            "Run `whatif cache rebuild --force` to wipe and start clean.",
            err=True,
        )
    else:
        typer.echo(f"whatif cache verify: {result.valid}/{result.total} entries OK.")
    # Anomaly counts surface on both paths so an operator sees
    # everything in one invocation. The entries that DO parse
    # pass the structural check; these counters describe layout
    # anomalies that exist independently of corruption.
    if result.non_bucket_skipped:
        typer.echo(
            f"  note: skipped {result.non_bucket_skipped} non-directory "
            f"path(s) directly under {cache_root}/entries (stray files).",
            err=True,
        )
    if result.non_file_skipped_in_bucket:
        typer.echo(
            f"  note: skipped {result.non_file_skipped_in_bucket} "
            "non-file path(s) inside bucket directories (unexpected "
            "subdirs).",
            err=True,
        )
    raise typer.Exit(code=EXIT_INCONCLUSIVE_OR_SETUP_FAILURE if result.corrupted else EXIT_SUCCESS)


@app.command()
def diff(
    prev: Annotated[Path, typer.Argument(help="Previous report.json")],
    new: Annotated[Path, typer.Argument(help="New report.json")],
) -> None:
    """Compare two whatif reports and emit a Markdown diff to stdout.

    Exits 0 on a successful render (whether or not anything changed —
    the diff is descriptive, not a verdict). Exits 2 on file-level
    errors (missing file, parse failure, non-mapping JSON) surfaced
    as `DiffError` from `load_report`.
    """
    try:
        prev_data = load_report(prev)
        new_data = load_report(new)
    except DiffError as exc:
        typer.echo(f"whatif diff: {exc}", err=True)
        raise typer.Exit(code=EXIT_INCONCLUSIVE_OR_SETUP_FAILURE) from exc
    report = compute_diff(prev_data, new_data)
    typer.echo(render_diff_markdown(report), nl=False)
    raise typer.Exit(code=EXIT_SUCCESS)


@app.command("report-migrate")
def report_migrate(
    report: Annotated[Path, typer.Argument(help="Report file to migrate")],
) -> None:
    """Migrate a report to the current schema.

    v0.1 has no schema bumps to migrate from, so this is an
    intentional no-op. Exits 0 (success) because there's nothing
    to fix — conflating "intentional no-op" with "setup failure"
    in the exit-code contract would mislead operators wiring this
    into automated pipelines.

    Real migration logic lands in v0.2+ when v0.2 schema diverges
    from v0.1.
    """
    typer.echo(
        f"whatif report-migrate: v0.1 has no migrations to apply ({report}). No-op success.",
    )
    raise typer.Exit(code=EXIT_SUCCESS)  # exit 0: intentional no-op


def main() -> None:
    """Console-script entry point (`pyproject.toml` declares
    `whatif = whatif.cli:main`)."""
    app()


if __name__ == "__main__":
    main()
