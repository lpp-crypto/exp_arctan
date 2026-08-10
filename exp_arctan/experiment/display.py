"""
experiment.py

Provides `Experiment`, a context manager for research/benchmark scripts that:
  - temporarily redirects `print()` through a `logging.Logger`
  - renders console output via Rich (colorized levels, aligned timestamps)
  - collapses repeated dates/times so the timestamp column only shows what
    changed since the previous line (date reappears only when it changes;
    time is blanked entirely when identical to the previous line)
  - optionally archives plain-text output to a log file
  - allows one-off timestamp overrides (e.g. showing elapsed runtime
    instead of a wall-clock time for a single line)

Design notes
------------
`RichHandler.log_time_format` accepts a callable `datetime -> rich.text.Text`,
called once per emitted record with only the timestamp (no access to the
LogRecord itself). `StickyDateTime` uses that call to compare against the
previous date/time it rendered and decide how much of the timestamp to
actually draw. Because it holds state, each `Experiment.__enter__` call
must construct a *fresh* instance -- sharing one across separate `with`
blocks would leak state between unrelated experiments.

The one-shot override (`StickyDateTime.override_next`) exists because Rich
gives us no other hook to inject arbitrary content into the timestamp slot
for a single line (e.g. "+ 12.34s" instead of a clock time). It is consumed
(cleared) as soon as it's read, so it never leaks into subsequent lines.
"""

from __future__ import annotations

import builtins
import logging
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text


ONGOING_EXPERIMENT = None


class StickyDateTime:
    """
    Callable time formatter for RichHandler.log_time_format.

    Behavior per emitted line, compared to the previous line:
      - date changed            -> "[MM/DD/YY HH:MM:SS]"   (full)
      - date same, time changed -> "[          HH:MM:SS]"  (date blanked)
      - date and time unchanged -> "                    "  (fully blank)

    All three branches render to the same character width so the console
    table's timestamp column stays aligned. Pass `omit_repeated_times=False`
    to RichHandler so its own (coarser, all-or-nothing) collapsing logic
    doesn't fight with this one.
    """

    def __init__(self, date_fmt: str = "%m/%d/%y", time_fmt: str = "%H:%M:%S"):
        self.date_fmt = date_fmt
        self.time_fmt = time_fmt
        self._last_date: Optional[str] = None
        self._last_time: Optional[str] = None
        self._override: Optional[str] = None

        # Width of a fully-rendered timestamp, e.g. "[08/07/26 11:39:21]".
        # Computed once from a throwaway strftime so it stays correct even
        # if date_fmt/time_fmt are customized.
        import datetime as _dt
        probe = _dt.datetime(2000, 1, 1)
        self._full_width = len(
            f"[{probe.strftime(self.date_fmt)} {probe.strftime(self.time_fmt)}]"
        )

    def override_next(self, text: str) -> None:
        """
        Replace the timestamp field for the *next* rendered line only.
        `text` is padded/truncated to match the normal timestamp width so
        columns stay aligned; wrap it in brackets yourself if you want them.
        """
        self._override = text

    def __call__(self, dt) -> Text:
        if self._override is not None:
            text, self._override = self._override, None  # consume: one-shot
            return Text(f"{text:<{self._full_width}}"[: self._full_width])

        date_str = dt.strftime(self.date_fmt)
        time_str = dt.strftime(self.time_fmt)

        if date_str == self._last_date and time_str == self._last_time:
            return Text(" " * self._full_width)

        if date_str == self._last_date:
            self._last_time = time_str
            rendered = f"[{' ' * len(date_str)} {time_str}]"
            return Text(f"{rendered:<{self._full_width}}"[: self._full_width])

        self._last_date = date_str
        self._last_time = time_str
        rendered = f"[{date_str} {time_str}]"
        return Text(f"{rendered:<{self._full_width}}"[: self._full_width])


class Experiment:
    """
    Context manager that routes `print()` through a Rich-backed logger for
    the duration of the `with` block, then restores the original `print`.

    Examples
    --------
    with Experiment("sieve benchmark"):
        print("computing primes...")
        print("done, found", 1229, "primes")

    with Experiment("quiet pass", level=logging.CRITICAL):
        print("this never appears")

    with Experiment("archived run", logfile="run.log") as exp:
        print("shown in color on console, plain text in run.log")
        exp.stamp("+ 12.34s", "checkpoint reached")   # one-off timestamp override

    Nesting: each instance saves whatever `print` currently is (not assumed
    to be the "real" builtin) and restores exactly that on exit, so nested
    `Experiment` blocks compose correctly (LIFO restore).
    """

    def __init__(
        self,
        title: str,
        level: int = logging.INFO,
        logfile: Optional[str] = None,
        date_fmt: str = "%m/%d/%y",
        time_fmt: str = "%H:%M:%S",
    ):
        self.title = title
        self.level = level
        self.logfile = Path(logfile) if logfile else None
        self.date_fmt = date_fmt
        self.time_fmt = time_fmt

        self._saved_print = None
        self._logger: Optional[logging.Logger] = None
        self._handlers = []
        self._time_formatter: Optional[StickyDateTime] = None
        self.console: Optional[Console] = None


    def section(self, depth: int, title: str) -> None:
        self._logger.info("#" * depth + " " + title)
        

    def __enter__(self) -> "Experiment":
        self._logger = logging.getLogger(f"experiment.{id(self)}.{self.title}")
        self._logger.handlers.clear()
        self._logger.setLevel(self.level)
        self._logger.propagate = False

        self._time_formatter = StickyDateTime(self.date_fmt, self.time_fmt)
        self.console = Console()

        console_handler = RichHandler(
            console=self.console,
            show_time=True,
            show_level=True,
            show_path=False,
            rich_tracebacks=True,
            markup=True,
            log_time_format=self._time_formatter,
            omit_repeated_times=False,  # our formatter owns this logic instead
        )
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(console_handler)
        self._handlers.append(console_handler)

        if self.logfile:
            plain_formatter = logging.Formatter(
                "%(asctime)s | %(message)s", datefmt="%H:%M:%S"
            )
            file_handler = logging.FileHandler(self.logfile)
            file_handler.setFormatter(plain_formatter)
            self._logger.addHandler(file_handler)
            self._handlers.append(file_handler)

        self._saved_print = builtins.print
        builtins.print = lambda *a, **k: self._logger.info(
            " ".join(str(x) for x in a)
        )

        # Markup like [bold]...[/bold] only renders in the RichHandler
        # (console); a plain FileHandler would log it as literal text.
        # Keeping this plain avoids that asymmetry between console and file.
        self._logger.info(f"=== {self.title} : starting ===")

        global ONGOING_EXPERIMENT
        ONGOING_EXPERIMENT = self
        return self

    
    def stamp(self, timestamp_text: str, *args) -> None:
        """
        Log a message with an arbitrary string in place of the timestamp
        for that one line only (e.g. elapsed runtime instead of a clock
        time). Subsequent lines revert to normal timestamp behavior.
        """
        self._time_formatter.override_next(timestamp_text)
        self._logger.info(" ".join(str(a) for a in args))

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._logger.info(f"=== {self.title} : finished ===")

        builtins.print = self._saved_print

        for handler in self._handlers:
            handler.close()
            self._logger.removeHandler(handler)

        return False  # never suppress exceptions

    
def section(title: str) -> None:
    ONGOING_EXPERIMENT.section(2, title)
