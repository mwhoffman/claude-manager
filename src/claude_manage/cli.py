"""Command line interface for claude-manage."""

from pathlib import Path
from typing import Annotated

import typer

from claude_manage import conversations


app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
  """Tools for managing local Claude Code data."""


@app.command(name="conversations")
def conversations_command(
  project: Annotated[
    Path,
    typer.Argument(metavar="DIR", help="Project directory."),
  ] = Path(),
) -> None:
  """Summarize the conversations of a project, newest first."""
  conversations.run(project)
