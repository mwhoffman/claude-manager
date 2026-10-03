"""Model of the projects and conversations Claude Code keeps on disk."""

import dataclasses
import datetime
import json
import pathlib
import re
from collections.abc import Iterator
from typing import Any


# Base directory for claude settings.
CLAUDE_DIR = pathlib.Path.home() / ".claude"

# Directory holding a conversations directory for each project.
PROJECTS_DIR = CLAUDE_DIR / "projects"

# Directories with an entry per conversation, named by its session id.
SESSION_DIRS = (CLAUDE_DIR / "session-env", CLAUDE_DIR / "file-history")

# Directory with a file per running session, named by pid.
LIVE_DIR = CLAUDE_DIR / "sessions"

# Directory in which Claude Code keeps per-project caches, named like the
# conversations directories.
CACHE_DIR = pathlib.Path.home() / ".cache" / "claude-cli-nodejs"

# File in which Claude Code records the projects it has been run in.
CONFIG_FILE = pathlib.Path.home() / ".claude.json"


@dataclasses.dataclass(frozen=True)
class Conversation:
  """A conversation, stored as a JSONL file with one record per line.

  Attributes:
    path: Location of the conversation file.
  """

  path: pathlib.Path

  @property
  def id(self) -> str:
    """Session id of the conversation, which is the stem of its filename."""
    return self.path.stem

  def records(self) -> Iterator[dict[str, Any]]:
    """Read the records of the conversation, skipping lines that are invalid.

    Yields:
      Each record, in order.
    """
    with self.path.open() as f:
      for line in f:
        try:
          record = json.loads(line)
        except json.JSONDecodeError:
          continue
        if isinstance(record, dict):
          yield record

  def modified(self) -> datetime.datetime:
    """Find when the conversation was last written to.

    Returns:
      The modification time of the conversation file, in local time.
    """
    return datetime.datetime.fromtimestamp(
      self.path.stat().st_mtime
    ).astimezone()

  def is_empty(self) -> bool:
    """Check whether the conversation never got started.

    Returns:
      Whether the conversation has neither a prompt typed by the user nor a
      reply from the assistant.
    """
    for record in self.records():
      kind = record.get("type")
      if kind == "user" and prompt_text(record):
        return False
      if kind == "assistant" and not record.get("isSidechain"):
        return False
    return True

  def cwds(self) -> Iterator[str]:
    """Find the working directories the conversation ran in.

    Yields:
      Each distinct working directory, in the order they first appear.
    """
    seen: set[str] = set()
    for record in self.records():
      cwd = record.get("cwd")
      if isinstance(cwd, str) and cwd not in seen:
        seen.add(cwd)
        yield cwd


@dataclasses.dataclass(frozen=True)
class Project:
  """A project known to Claude Code.

  Attributes:
    path: Working directory of the project, which identifies it.
  """

  path: pathlib.Path

  def conversations_dir(self) -> pathlib.Path:
    """Find the directory holding the conversations of the project.

    Returns:
      The directory under ~/.claude/projects named after the working
      directory, with every character other than a letter or digit replaced by
      "-". It may not exist.
    """
    return PROJECTS_DIR / re.sub(r"[^a-zA-Z0-9]", "-", str(self.path.resolve()))

  def conversations(self) -> list[Conversation]:
    """List the conversations of the project.

    Returns:
      Every conversation, including empty ones, most recently modified first.
    """
    return sorted(
      (Conversation(p) for p in self.conversations_dir().glob("*.jsonl")),
      key=lambda c: c.path.stat().st_mtime,
      reverse=True,
    )

  def modified(self) -> datetime.datetime | None:
    """Find when the project was last used.

    Returns:
      The modification time of the newest conversation that is not empty, or
      None if there is no such conversation.
    """
    for conversation in self.conversations():
      if not conversation.is_empty():
        return conversation.modified()
    return None

  def exists(self) -> bool:
    """Check whether the working directory of the project still exists."""
    return self.path.is_dir()


def prompt_text(record: dict[str, Any]) -> str | None:
  """Extract the text the user typed from a user record.

  Args:
    record: A conversation record of type "user".

  Returns:
    The typed prompt, or None if the record is not a prompt typed by the user
    (e.g. a tool result or a message injected by the harness).
  """
  if (
    record.get("isMeta")
    or record.get("isSidechain")
    or "toolUseResult" in record
  ):
    return None
  content = record.get("message", {}).get("content")
  if isinstance(content, list):
    content = "\n".join(
      b.get("text", "")
      for b in content
      if isinstance(b, dict) and b.get("type") == "text"
    )
  if not isinstance(content, str):
    return None
  # Drop harness-injected blocks so only the typed prompt remains.
  content = re.sub(
    r"<(system-reminder|local-command-\w+)>.*?</\1>",
    "",
    content,
    flags=re.DOTALL,
  )
  return content.strip() or None


def registered_projects() -> list[Project]:
  """Find the projects recorded in the Claude Code config file.

  Returns:
    The projects, which is empty if the config file cannot be read.
  """
  try:
    config = json.loads(CONFIG_FILE.read_text())
  except (OSError, json.JSONDecodeError):
    return []
  if not isinstance(config, dict) or not isinstance(
    config.get("projects"), dict
  ):
    return []
  return [Project(pathlib.Path(path)) for path in config["projects"]]


def match(directory: pathlib.Path) -> Project | None:
  """Recover the project a conversations directory belongs to.

  The name of a conversations directory is a lossy encoding of the working
  directory, so the working directory is read from the conversations instead.
  A conversation can move into other directories, so only a working directory
  which maps back to the conversations directory is used.

  Args:
    directory: A directory under ~/.claude/projects.

  Returns:
    The project, or None if no conversation names its working directory.
  """
  for path in sorted(directory.glob("*.jsonl")):
    for cwd in Conversation(path).cwds():
      project = Project(pathlib.Path(cwd))
      if project.conversations_dir() == directory:
        return project
  return None


def projects() -> list[Project]:
  """Find the projects known to Claude Code.

  Returns:
    The projects recorded in the config file or found under ~/.claude/projects,
    ordered by working directory.
  """
  found = set(registered_projects())
  claimed = {p.conversations_dir() for p in found}
  if PROJECTS_DIR.is_dir():
    for directory in PROJECTS_DIR.iterdir():
      if directory.is_dir() and directory not in claimed:
        project = match(directory)
        if project:
          found.add(project)
  return sorted(found, key=lambda p: p.path)


def unmatched_dirs(projects: list[Project]) -> list[pathlib.Path]:
  """Find the conversations directories that belong to no project.

  Args:
    projects: The projects known to Claude Code.

  Returns:
    The directories under ~/.claude/projects that are not the conversations
    directory of any of the projects, in name order.
  """
  if not PROJECTS_DIR.is_dir():
    return []
  claimed = {p.conversations_dir() for p in projects}
  return sorted(
    d for d in PROJECTS_DIR.iterdir() if d.is_dir() and d not in claimed
  )
