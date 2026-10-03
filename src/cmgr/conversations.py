"""Summarize the conversations of a project, newest first."""

import dataclasses
import datetime
import pathlib
import sys

import humanize
import rich.console
import rich.text

from cmgr import common
from cmgr import console as console_lib


# Maximum number of prompts printed for each conversation.
MAX_PROMPTS = 6


@dataclasses.dataclass
class Summary:
  """Summary of a single conversation.

  Attributes:
    conversation: The conversation being summarized.
    size: Size of the conversation file in bytes.
    start: Time of the first timestamped record.
    modified: Time the conversation file was last written to.
    prompts: Text of each prompt typed by the user, in order.
    title: Auto-generated title, if any.
    custom_title: Title set by the user, if any.
    assistant_turns: Number of assistant records in the main conversation.
    tool_calls: Number of tool calls made by the assistant.
  """

  conversation: common.Conversation
  size: int
  start: datetime.datetime
  modified: datetime.datetime
  prompts: list[str]
  title: str | None = None
  custom_title: str | None = None
  assistant_turns: int = 0
  tool_calls: int = 0


def parse_time(value: object) -> datetime.datetime | None:
  """Parse a conversation timestamp into local time.

  Args:
    value: An ISO 8601 timestamp, as found on a conversation record.

  Returns:
    The timestamp in the local timezone, or None if it cannot be parsed.
  """
  if not isinstance(value, str):
    return None
  try:
    return datetime.datetime.fromisoformat(
      value.replace("Z", "+00:00")
    ).astimezone()
  except ValueError:
    return None


def summarize(conversation: common.Conversation) -> Summary:
  """Summarize a conversation.

  Args:
    conversation: Conversation to summarize.

  Returns:
    A summary of the conversation. If no record has a timestamp the start
    time falls back to the file's modification time.
  """
  modified = conversation.modified()
  start: datetime.datetime | None = None
  summary = Summary(
    conversation=conversation,
    size=conversation.path.stat().st_size,
    start=modified,
    modified=modified,
    prompts=[],
  )
  for record in conversation.records():
    kind = record.get("type")
    if kind == "ai-title":
      summary.title = record.get("aiTitle")
    elif kind == "custom-title":
      summary.custom_title = record.get("customTitle")
    start = start or parse_time(record.get("timestamp"))
    if kind == "user":
      text = common.prompt_text(record)
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
  if start:
    summary.start = start
  return summary


def show(
  console: rich.console.Console,
  summary: Summary,
  index: int,
  total: int,
) -> None:
  """Print the summary of a conversation.

  Args:
    console: Console to print to.
    summary: Summary to print.
    index: Position of the conversation among those being shown, from 1.
    total: Number of conversations being shown.
  """
  title = summary.custom_title or summary.title or "(untitled)"
  size = humanize.naturalsize(summary.size, gnu=True)
  prompts = summary.prompts

  def show_field(key: str, *value: str | tuple[str, str]) -> None:
    separator = " " if value else ""
    console.print(
      rich.text.Text.assemble((f"{key}:", "key"), separator, *value)
    )

  def show_prompt(text: str) -> None:
    # Collapse the prompt onto one line, cut to the width of the terminal.
    console.print(
      f" - {' '.join(text.split())}",
      soft_wrap=False,
      no_wrap=True,
      overflow="ellipsis",
    )

  console.print(
    rich.text.Text.assemble(
      (title, "header"), " ", (f"[{index}/{total}]", "dim")
    )
  )
  show_field("id", summary.conversation.id)
  show_field(
    "time",
    f"{humanize.naturaltime(summary.modified)} ",
    (f"(started {humanize.naturaltime(summary.start)})", "dim"),
  )
  details = (
    f"({summary.assistant_turns} assistant messages,"
    f" {summary.tool_calls} tool calls, {size})"
  )
  show_field("activity", f"{len(prompts)} prompts ", (details, "dim"))
  if prompts:
    show_field("prompts")
    # When there are too many prompts show the first few and the last one.
    shown = (
      prompts if len(prompts) <= MAX_PROMPTS else prompts[: MAX_PROMPTS - 1]
    )
    for text in shown:
      show_prompt(text)
    if len(shown) < len(prompts):
      skipped = len(prompts) - len(shown) - 1
      if skipped:
        console.print(f"   … {skipped} more …")
      show_prompt(prompts[-1])


def run(path: pathlib.Path) -> None:
  """Print a summary of each conversation of a project.

  Args:
    path: Working directory of the project.
  """
  project = common.Project(path.resolve())
  summaries = sorted(
    (summarize(c) for c in project.conversations() if not c.is_empty()),
    key=lambda s: s.modified,
    reverse=True,
  )
  if not summaries:
    sys.exit(f"No Claude Code conversations found for {project.path}")

  console = console_lib.make_console()
  for index, summary in enumerate(summaries, 1):
    show(console, summary, index, len(summaries))
    console.print()
