"""whatifd-skillgen CLI.

Entry point: ``whatifd-skillgen``

Subcommands
-----------
generate <skill_dir>
    Read ``<skill_dir>/skill.md``, generate ``<skill_dir>/__init__.py``,
    and print config.py + factory.py patch instructions to stdout.

    ``skill_dir`` should be the adapter package's source directory — e.g.
    ``packages/whatifd-myadapter/src/whatifd_myadapter/``. The generated
    ``__init__.py`` lands in that directory, not inside whatifd's own source
    tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    name="whatifd-skillgen",
    help="Scaffold whatifd adapter stubs from a declarative skill.md manifest.",
    no_args_is_help=True,
)

_EXIT_OK = 0
_EXIT_ERR = 2


@app.command("generate")
def generate(
    skill_dir: Annotated[
        Path,
        typer.Argument(
            help=(
                "Directory containing skill.md. The generated __init__.py is "
                "written to the same directory. Use the adapter package's source "
                "directory (e.g. packages/whatifd-myadapter/src/whatifd_myadapter/), "
                "not a path inside whatifd's own source tree."
            ),
        ),
    ],
    overwrite: Annotated[
        bool,
        typer.Option(
            "--overwrite",
            help=(
                "Allow overwriting an existing __init__.py. Without this flag "
                "the command refuses to clobber existing implementation work."
            ),
        ),
    ] = False,
) -> None:
    """Scaffold an adapter stub from skill.md.

    Reads ``<skill_dir>/skill.md``, generates protocol-compliant adapter
    boilerplate, writes ``<skill_dir>/__init__.py``, and prints actionable
    patch instructions for config.py and factory.py.

    Exit 0 on success. Exit 2 on manifest error, generation error, or
    filesystem error.
    """
    from whatifd_skillgen.errors import SkillGenerationError, SkillManifestError
    from whatifd_skillgen.scaffold import scaffold_skill

    if not skill_dir.is_dir():
        typer.echo(
            f"whatifd-skillgen: directory not found: {skill_dir}. "
            "Create it and add a skill.md file, then re-run.",
            err=True,
        )
        raise typer.Exit(code=_EXIT_ERR)

    try:
        result = scaffold_skill(skill_dir, overwrite=overwrite)
    except SkillManifestError as exc:
        typer.echo(f"whatifd-skillgen: manifest error:\n{exc}", err=True)
        raise typer.Exit(code=_EXIT_ERR) from exc
    except SkillGenerationError as exc:
        typer.echo(f"whatifd-skillgen: generation error:\n{exc}", err=True)
        raise typer.Exit(code=_EXIT_ERR) from exc

    typer.echo(f"whatifd-skillgen: wrote {result.path_written}")
    typer.echo("")
    typer.echo(result.config_patch_hint)
    typer.echo(result.factory_patch_hint)
    raise typer.Exit(code=_EXIT_OK)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
