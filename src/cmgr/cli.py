"""Command line interface for cmgr."""

import pathlib
from typing import Annotated

import typer

from cmgr import clean as clean_lib
from cmgr import conversations as conversations_lib
from cmgr import projects as projects_lib


app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
  """Tool for managing local Claude Code projects and conversations."""


@app.command()
def conversations(
  project: Annotated[pathlib.Path, typer.Argument()] = pathlib.Path(),
) -> None:
  """List and summarize the conversations of a given project."""
  conversations_lib.run(project)


@app.command()
def projects() -> None:
  """List projects."""
  projects_lib.run()


@app.command()
def clean(
  yes: Annotated[
    bool,
    typer.Option("--yes", "-y", help="Delete without asking."),
  ] = False,
  dry_run: Annotated[
    bool,
    typer.Option("--dry-run", "-n", help="Only list what would be deleted."),
  ] = False,
) -> None:
  """Delete state that no longer refers to anything."""
  clean_lib.run(yes=yes, dry_run=dry_run)
