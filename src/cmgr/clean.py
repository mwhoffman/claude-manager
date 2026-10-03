"""Delete Claude Code state that no longer refers to anything."""

import json
import pathlib
import shutil

import typer

from cmgr import common
from cmgr import console as console_lib


# Paths grouped by a description of what they are.
Groups = dict[str, list[pathlib.Path]]


def children(directory: pathlib.Path) -> list[pathlib.Path]:
  """List the contents of a directory.

  Args:
    directory: Directory to list, which may not exist.

  Returns:
    The entries of the directory in name order, which is empty if it does not
    exist.
  """
  return sorted(directory.iterdir()) if directory.is_dir() else []


def live_sessions() -> set[str]:
  """Find the sessions that are currently running.

  Returns:
    The session ids of the conversations that Claude Code has recorded as
    running.
  """
  sessions: set[str] = set()
  for path in common.LIVE_DIR.glob("*.json"):
    try:
      session = json.loads(path.read_text()).get("sessionId")
    except (OSError, json.JSONDecodeError, AttributeError):
      continue
    if isinstance(session, str):
      sessions.add(session)
  return sessions


def find() -> Groups:
  """Find state that no longer refers to anything.

  Returns:
    The paths that can be deleted, grouped by kind and omitting kinds for which
    there are none.
  """
  projects = common.projects()
  names = {p.conversations_dir().name for p in projects}
  live = live_sessions()
  conversations = [
    common.Conversation(p)
    for p in sorted(common.PROJECTS_DIR.glob("*/*.jsonl"))
  ]
  empty = [c for c in conversations if c.id not in live and c.is_empty()]
  # Session ids whose state is still in use, which are those of conversations
  # that are running or are being kept.
  sessions = live | {c.id for c in conversations if c not in empty}

  doomed = {
    "Conversations with no prompts or replies": [c.path for c in empty],
    "Empty conversations directories with no project": [
      d for d in common.unmatched_dirs(projects) if not children(d)
    ],
    "Caches for directories that are not projects": [
      d for d in children(common.CACHE_DIR) if d.name not in names
    ],
    "State for conversations that no longer exist": [
      d
      for directory in common.SESSION_DIRS
      for d in children(directory)
      if d.name not in sessions
    ],
  }
  return {kind: paths for kind, paths in doomed.items() if paths}


def run(yes: bool = False, dry_run: bool = False) -> None:
  """Delete state that no longer refers to anything.

  Args:
    yes: Whether to delete without asking for confirmation.
    dry_run: Whether to only print what would be deleted.
  """
  console = console_lib.make_console()
  doomed = find()
  if not doomed:
    console.print("Nothing to clean.")
    return
  for kind, group in doomed.items():
    console.print(kind, style="header")
    for path in group:
      console.print(path)
    console.print()

  paths = [path for group in doomed.values() for path in group]
  if dry_run:
    return
  if not yes:
    typer.confirm(f"Delete these {len(paths)} items?", abort=True)
  for path in paths:
    # A symbolic link is removed without touching what it points to.
    if path.is_dir() and not path.is_symlink():
      shutil.rmtree(path)
    else:
      path.unlink()
  console.print(f"Deleted {len(paths)} items.")
