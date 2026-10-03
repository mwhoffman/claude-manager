"""List the projects known to Claude Code, most recently used first."""

import sys

import humanize
import rich.text

from cmgr import common
from cmgr import console as console_lib


def run() -> None:
  """Print a line for each project."""
  projects = common.projects()
  if not projects:
    sys.exit("No Claude Code projects found.")

  modified = {p: p.modified() for p in projects}

  def recency(project: common.Project) -> float:
    when = modified[project]
    return when.timestamp() if when else float("-inf")

  # Projects that have never been used sort last, by path.
  projects.sort(key=recency, reverse=True)

  console = console_lib.make_console()
  for project in projects:
    when = modified[project]
    age = humanize.naturaltime(when) if when else "never"
    if not project.exists():
      age += ", missing"
    console.print(
      rich.text.Text.assemble(f"{project.path} ", (f"({age})", "dim"))
    )
