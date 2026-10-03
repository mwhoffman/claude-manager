"""Console used by every command to print its output."""

import rich.console
import rich.theme


# Styles that output refers to by name.
THEME = rich.theme.Theme(
  {
    # Heading above a group of lines, which is ANSI color 11.
    "header": "bold underline bright_yellow",
    # Name of a field, before its value, which is ANSI color 11.
    "key": "bright_yellow",
    # Secondary detail, such as how long ago something happened, which is ANSI
    # color 8.
    "dim": "bright_black",
  }
)


def make_console() -> rich.console.Console:
  """Create a console for printing plain lines of output.

  Returns:
    A console using the theme, which prints text as given, without
    interpreting markup or emoji codes, highlighting or wrapping it.
  """
  return rich.console.Console(
    theme=THEME, markup=False, emoji=False, highlight=False, soft_wrap=True
  )
