"""List the projects that have conversations, newest first."""

import dataclasses
import datetime
import json
import pathlib
import sys

import humanize
import rich.console
import rich.text

from cmgr import conversations


# Style used for the age of a project, which is ANSI color 7.
AGE_STYLE = "bright_black"

# File in which Claude Code records the projects it has been run in.
CONFIG_FILE = pathlib.Path.home() / ".claude.json"


@dataclasses.dataclass
class Project:
  """A project known to Claude Code.

  Attributes:
    directory: Directory holding the project's transcripts.
    path: Working directory of the project, or None if it cannot be determined.
    conversations: Number of transcripts in the project.
    modified: Time the project was last active, or None if it has no
      transcripts.
  """

  directory: pathlib.Path
  path: pathlib.Path | None
  conversations: int
  modified: datetime.datetime | None


def working_dir(
  directory: pathlib.Path, transcripts: list[pathlib.Path]
) -> pathlib.Path | None:
  """Recover the working directory of a project from its transcripts.

  The name of a transcript directory is a lossy encoding of the working
  directory, so the path is read from the transcript records instead.

  Args:
    directory: Directory holding the project's transcripts.
    transcripts: Transcripts of the project, in the order they are searched.

  Returns:
    The working directory, or None if no record names one. A conversation can
    move into subdirectories, so a path which maps back to the transcript
    directory is preferred over the first one found.
  """
  fallback: pathlib.Path | None = None
  for transcript in transcripts:
    seen: set[str] = set()
    with transcript.open() as f:
      for line in f:
        try:
          cwd = json.loads(line).get("cwd")
        except (json.JSONDecodeError, AttributeError):
          continue
        if not isinstance(cwd, str) or cwd in seen:
          continue
        seen.add(cwd)
        if conversations.project_dir(cwd) == directory:
          return pathlib.Path(cwd)
        fallback = fallback or pathlib.Path(cwd)
  return fallback


def registered() -> dict[pathlib.Path, pathlib.Path]:
  """Find the projects recorded in the Claude Code config file.

  Returns:
    A mapping from the transcript directory of each project to its working
    directory, which is empty if the config file cannot be read.
  """
  try:
    config = json.loads(CONFIG_FILE.read_text())
  except (OSError, json.JSONDecodeError):
    return {}
  if not isinstance(config, dict) or not isinstance(
    config.get("projects"), dict
  ):
    return {}
  return {
    conversations.project_dir(path): pathlib.Path(path)
    for path in config["projects"]
  }


def load(directory: pathlib.Path, path: pathlib.Path | None = None) -> Project:
  """Describe the project stored in a transcript directory.

  Args:
    directory: Directory holding the project's transcripts, which may not
      exist.
    path: Working directory to use if the transcripts do not name one.

  Returns:
    A description of the project.
  """
  transcripts = sorted(
    directory.glob("*.jsonl"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
  )
  modified = None
  if transcripts:
    modified = datetime.datetime.fromtimestamp(
      transcripts[0].stat().st_mtime
    ).astimezone()
  return Project(
    directory=directory,
    path=working_dir(directory, transcripts) or path,
    conversations=len(transcripts),
    modified=modified,
  )


def run() -> None:
  """Print a line for each project."""
  root = conversations.CLAUDE_DIR / "projects"
  known = registered()
  directories = set(known)
  if root.is_dir():
    directories.update(d for d in root.iterdir() if d.is_dir())
  if not directories:
    sys.exit(f"No Claude Code projects found ({root}, {CONFIG_FILE})")

  # Projects that have never been used sort last, by name.
  projects = sorted(
    (load(d, known.get(d)) for d in sorted(directories)),
    key=lambda p: p.modified.timestamp() if p.modified else float("-inf"),
    reverse=True,
  )

  console = rich.console.Console(highlight=False, soft_wrap=True)
  for project in projects:
    age = "never"
    if project.modified:
      age = humanize.naturaltime(project.modified)
    console.print(
      rich.text.Text.assemble(
        f"{project.path or project.directory.name} ",
        (f"({age})", AGE_STYLE),
      )
    )
