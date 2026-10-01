"""Summarize the Claude Code conversations of a project, newest first."""

import json
import re
import shutil
import sys
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


CLAUDE_DIR = Path.home() / ".claude"

# Line width used when the width of the terminal cannot be determined.
DEFAULT_WIDTH = 100

# Maximum number of prompts printed for each conversation.
MAX_PROMPTS = 6

# A single decoded line of a transcript file.
Record = dict[str, Any]


@dataclass
class Summary:
  """Summary of a single conversation transcript.

  Attributes:
    id: Session id, which is also the stem of the transcript's filename.
    path: Location of the transcript file.
    size: Size of the transcript file in bytes.
    start: Time of the first timestamped record.
    end: Time of the last timestamped record.
    prompts: Text of each prompt typed by the user, in order.
    title: Auto-generated title, if any.
    custom_title: Title set by the user, if any.
    assistant_turns: Number of assistant records in the main conversation.
    tool_calls: Number of tool calls made by the assistant.
    branch: Git branch the conversation last ran on, if any.
    version: Claude Code version the conversation last ran with, if any.
  """

  id: str
  path: Path
  size: int
  start: datetime
  end: datetime
  prompts: list[str]
  title: str | None = None
  custom_title: str | None = None
  assistant_turns: int = 0
  tool_calls: int = 0
  branch: str | None = None
  version: str | None = None


def project_dir(path: str | Path) -> Path:
  """Map a working directory to its transcript directory under ~/.claude.

  Args:
    path: Working directory of the project.

  Returns:
    The directory holding the project's transcripts, which may not exist.
  """
  encoded = re.sub(r"[^a-zA-Z0-9]", "-", str(Path(path).resolve()))
  return CLAUDE_DIR / "projects" / encoded


def parse_time(value: object) -> datetime | None:
  """Parse a transcript timestamp into local time.

  Args:
    value: An ISO 8601 timestamp, as found on a transcript record.

  Returns:
    The timestamp in the local timezone, or None if it cannot be parsed.
  """
  if not isinstance(value, str):
    return None
  try:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
  except ValueError:
    return None


def prompt_text(record: Record) -> str | None:
  """Extract the text the user typed from a user record.

  Args:
    record: A transcript record of type "user".

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


def summarize(path: Path) -> Summary:
  """Summarize a conversation transcript.

  Args:
    path: Location of the transcript, a JSONL file with one record per line.

  Returns:
    A summary of the conversation. If no record has a timestamp the start and
    end times fall back to the file's modification time.
  """
  modified = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
  start: datetime | None = None
  end: datetime | None = None
  summary = Summary(
    id=path.stem,
    path=path,
    size=path.stat().st_size,
    start=modified,
    end=modified,
    prompts=[],
  )
  with path.open() as f:
    for line in f:
      try:
        record: Record = json.loads(line)
      except json.JSONDecodeError:
        continue
      kind = record.get("type")
      if kind == "ai-title":
        summary.title = record.get("aiTitle")
      elif kind == "custom-title":
        summary.custom_title = record.get("customTitle")
      when = parse_time(record.get("timestamp"))
      if when:
        start = start or when
        end = when
      if kind == "user":
        summary.branch = record.get("gitBranch") or summary.branch
        summary.version = record.get("version") or summary.version
        text = prompt_text(record)
        if text:
          summary.prompts.append(text)
      elif kind == "assistant" and not record.get("isSidechain"):
        summary.assistant_turns += 1
        content = record.get("message", {}).get("content")
        if isinstance(content, list):
          summary.tool_calls += sum(
            1
            for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use"
          )
  if start and end:
    summary.start = start
    summary.end = end
  return summary


def shorten(text: str, width: int) -> str:
  """Collapse text onto a single line of limited width.

  Args:
    text: Text to shorten, which may span multiple lines.
    width: Maximum length of the result.

  Returns:
    The text with whitespace collapsed, truncated with an ellipsis if needed.
  """
  return textwrap.shorten(" ".join(text.split()), width=width, placeholder="…")


def human_size(size: float) -> str:
  """Format a size in bytes using binary unit suffixes.

  Args:
    size: Size in bytes.

  Returns:
    The size as a short string, e.g. "512B" or "1.9M".
  """
  if size < 1024:
    return f"{size:.0f}B"
  for unit in ("K", "M"):
    size /= 1024
    if size < 1024:
      return f"{size:.1f}{unit}"
  return f"{size / 1024:.1f}G"


def show(summary: Summary, index: int, total: int, width: int) -> None:
  """Print the summary of a conversation.

  Args:
    summary: Summary to print.
    index: Position of the conversation among those being shown, from 1.
    total: Number of conversations being shown.
    width: Line width used when truncating prompts.
  """
  fmt = "%Y-%m-%d %H:%M"
  title = summary.custom_title or summary.title or "(untitled)"
  minutes = int((summary.end - summary.start).total_seconds() // 60)
  prompts = summary.prompts

  print(f"[{index}/{total}] {title}")
  print(f"  id        {summary.id}")
  print(
    f"  when      {summary.start.strftime(fmt)} → {summary.end.strftime(fmt)}"
    f"  ({minutes // 60}h{minutes % 60:02d}m)"
  )
  print(
    f"  activity  {len(prompts)} prompts,"
    f" {summary.assistant_turns} assistant messages,"
    f" {summary.tool_calls} tool calls, {human_size(summary.size)}"
  )
  details = [
    d for d in (summary.branch, summary.version and f"v{summary.version}") if d
  ]
  if details:
    print(f"  context   {', '.join(details)}")
  if prompts:
    print("  prompts")
    # When there are too many prompts show the first few and the last one.
    shown = (
      prompts if len(prompts) <= MAX_PROMPTS else prompts[: MAX_PROMPTS - 1]
    )
    for text in shown:
      print(f"    - {shorten(text, width - 6)}")
    if len(shown) < len(prompts):
      skipped = len(prompts) - len(shown) - 1
      if skipped:
        print(f"      … {skipped} more …")
      print(f"    - {shorten(prompts[-1], width - 6)}")


def run(project: str | Path = ".") -> None:
  """Print a summary of each conversation of a project.

  Args:
    project: Working directory of the project.
  """
  directory = project_dir(project)
  if not directory.is_dir():
    sys.exit(
      "No Claude Code conversations found for"
      f" {Path(project).resolve()} ({directory})"
    )

  summaries = sorted(
    (summarize(p) for p in directory.glob("*.jsonl")),
    key=lambda s: s.end,
    reverse=True,
  )
  if not summaries:
    sys.exit(f"No conversations in {directory}")

  width = shutil.get_terminal_size(fallback=(DEFAULT_WIDTH, 24)).columns
  for index, summary in enumerate(summaries, 1):
    show(summary, index, len(summaries), width)
    print()
