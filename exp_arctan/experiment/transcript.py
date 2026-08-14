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

from rich.console import Console, Theme
from rich.logging import RichHandler
from rich.text import Text
from rich.table import Table
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from .utils import pretty_counters, StickyDateTime, Chronograph



# !SECTION! Customize the appearance of the transcripts


# !SUBSECTION! Custom levels

GOOD_LEVEL = logging.ERROR-1
logging.addLevelName(GOOD_LEVEL, "GOOD")
END_LEVEL = logging.INFO-1
logging.addLevelName(END_LEVEL, "END")


# !SUBSECTION! Custom Rich-based terminal log handler

class CustomRichHandler(RichHandler):
    LEVEL_OVERRIDES = {
        logging.DEBUG: ("DEBG", "grey58"),
        logging.INFO-1: ("END", "blue"),
        logging.INFO: ("", None),
        logging.ERROR: ("FAIL", "bold red"),
        logging.WARNING: ("WARN", "orange"),
        logging.CRITICAL: ("CRIT", "bold red on white"),
    }
    LEVEL_WIDTH = 4

    def get_level_text(self, record: logging.LogRecord) -> Text:
        """

        The names of the levels is hard coded in the logic of RichHandler, so using custom level names would a priori break their highlighting (i.e., FAIL being in red). Rewriting this method bypasses this problem.
        
        """
        if record.levelno in self.LEVEL_OVERRIDES:
            text, style = self.LEVEL_OVERRIDES[record.levelno]
        else:
            style = f"logging.level.{record.levelname.lower()}"
            text = record.levelname
        return Text(text.ljust(self.LEVEL_WIDTH)[: self.LEVEL_WIDTH], style=style)

    
# !SUBSECTION! Custom file log handler



class MarkupStrippingFormatter(logging.Formatter):
    """
    Formatter that strips Rich markup tags (e.g. "[bold]...[/bold]",
    "[green]OK[/green]") from a message before applying the standard
    logging format string.
 
    Use this for handlers that write plain text (like a FileHandler) --
    Rich markup is meant to be interpreted by a Console/RichHandler, and
    without one, tags like "[green]OK[/green]" would otherwise show up
    verbatim (brackets and all) in a plain-text log file.
    """
 
    def format(self, record: logging.LogRecord) -> str:
        original_msg = record.getMessage()
        try:
            stripped = Text.from_markup(original_msg).plain.strip()
        except Exception:
            # If markup parsing fails for any reason, fall back to the
            # raw message rather than losing the log line entirely.
            stripped = original_msg
        record.msg = stripped
        record.args = None
        return super().format(record)




    
# !SECTION!  The actual Transcript class

VERBOSE_TABLE = {
    "debug"  : logging.DEBUG,
    "normal" : END_LEVEL,
    "errors" : logging.ERROR,
    "silent" : logging.CRITICAL + 1,
}


class Transcript:
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
        description: str="",
        logfile: Optional[str] = None,
        date_fmt: str = "%m/%d/%y",
        time_fmt: str = "%H:%M:%S",
        verbose = END_LEVEL
    ):
        self.title = title
        self.description = description
        self.logfile = Path(logfile) if logfile else None
        self.date_fmt = date_fmt
        self.time_fmt = time_fmt

        self._saved_print = None
        self._logger: Optional[logging.Logger] = None
        self._handlers = []
        self._time_formatter: Optional[StickyDateTime] = None
        self.console: Optional[Console] = None
        try:
            self.level = int(verbose)
        except:
            self.level = VERBOSE_TABLE[verbose]
        
        self._sections_counters = [0]
        self._timers = [ Chronograph('"' + self.title + '"' ) ]
        self._times_table = Table()
        self._times_table.add_column("Sec.", justify="left")
        self._times_table.add_column("Title", justify="left")
        self._times_table.add_column("Time", justify="right")
        self._times_table.add_column("Time (s)", justify="right")
        

    def start(self):
        self._logger = logging.getLogger(f"experiment.{id(self)}.{self.title}")
        self._logger.handlers.clear()
        self._logger.setLevel(self.level)
        self._logger.propagate = False

        self._time_formatter = StickyDateTime(self.date_fmt, self.time_fmt)
        self.console = Console(theme=Theme({
            "logging.level.good": "green"
        }))

        console_handler = CustomRichHandler(
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
            plain_formatter = MarkupStrippingFormatter(
                "%(asctime)s | %(message)s", datefmt="%H:%M:%S"
            )
            file_handler = logging.FileHandler(self.logfile)
            file_handler.setFormatter(plain_formatter)
            file_handler.setLevel(1)
            self._logger.addHandler(file_handler)
            self._handlers.append(file_handler)

        self._saved_print = builtins.print
        builtins.print = lambda *a, **k: self._logger.info(
            " ".join(str(x) for x in a)
        )

        # Markup like [bold]...[/bold] only renders in the RichHandler
        # (console); a plain FileHandler would log it as literal text.
        # Keeping this plain avoids that asymmetry between console and file.
        self._logger.info(f"=== {self.title}  ===\n\n")
        self._logger.info(self.description + "\n")
        


    
    def stamp(self, timestamp_text: str, *args) -> None:
        """
        Log a message with an arbitrary string in place of the timestamp
        for that one line only (e.g. elapsed runtime instead of a clock
        time). Subsequent lines revert to normal timestamp behavior.
        """
        self._time_formatter.override_next(timestamp_text)
        self._logger.info(" ".join(str(a) for a in args))
        
        
    def finish(self) -> None:
        self.finalize_sections(0)

        # if self.level < logging.INFO:
        #     self.console.print(self._times_table)

        builtins.print = self._saved_print

        for handler in self._handlers:
            handler.close()
            self._logger.removeHandler(handler)

            
    def progress_bar(self, iterated_over, title: str):
        if self.level > logging.INFO:
            for x in iterated_over:
                yield x
        else:
            columns = (
                TextColumn(" "*25 + "[progress.description]{task.description}"),
                BarColumn(bar_width=22),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
            )
            # the `console` optional arg is needed for the display to play nicely with logs
            with Progress(*columns, console=self.console) as progress:
                if hasattr(iterated_over, "__len__"):
                    task = progress.add_task(title, total=len(iterated_over))
                else:
                    task = progress.add_task(title, total=None)
                for x in iterated_over:
                    progress.update(task, advance=1)
                    yield x
                    

    def finalize_sections(self, target_depth: int) -> int:
        # !TODO! the times table doesn't work
        total_depth = len(self._sections_counters)
        to_print = ""
        while len(self._timers) > target_depth:
            chrono = self._timers.pop()
            # self._times_table.add_row(
            #     pretty_counters(self._sections_counters[0:total_depth-i]),
            #     chrono.title,
            #     chrono.elapsed_time_str(),
            #     str(chrono.elapsed_seconds()),
            # )
            to_print += str(chrono) + " ; "
        if len(to_print) > 0:
            self._logger.log(END_LEVEL, to_print[:-2])
            
        
    def section(self, title: str) -> None:
        if self._sections_counters != [0]:
            self.finalize_sections(1)
        self._sections_counters = [self._sections_counters[0] + 1]
        h1_format = "[b][blue]{}[/blue][/b]"
        indices = pretty_counters(self._sections_counters)
        full_title = f"\n\n{indices}  {title}"
        self._logger.info(h1_format.format(full_title))
        self._logger.info(h1_format.format("=" * len (full_title)) + "\n")
        self._timers.append(Chronograph("SEC " + indices))

        
    def subsection(self, title: str) -> None:
        self.finalize_sections(2)
        if len(self._sections_counters) < 2:
            self._sections_counters.append(0)
        self._sections_counters = [
            self._sections_counters[0],
            self._sections_counters[1] + 1
        ]
        h2_format = "[b]{}[/b]"
        indices = pretty_counters(self._sections_counters)
        full_title = f"\n{indices}  {title}"
        self._logger.info(h2_format.format(full_title))
        self._logger.info(h2_format.format("-" * len (full_title)))
        self._timers.append(Chronograph("SEC " + indices))

        
    def subsubsection(self, title: str) -> None:
        self.finalize_sections(3)
        if len(self._sections_counters) < 2:
            self._sections_counters.append(0)
        self._sections_counters = [
            self._sections_counters[0],
            self._sections_counters[1] + 1
        ]
        self._sections_counters = self._sections_counters[:2] + [self._sections_counters[2] + 1]
        indices = pretty_counters(self._sections_counters)
        full_title = f"{indices}  {title}"
        self._logger.info(full_title)
        self._timers.append(Chronograph("SEC " + indices))

        
    def debug(self, reason: str) -> None:
        self._logger.debug(reason)

    def warning(self, reason: str) -> None:
        self._logger.warning(reason)
        
    def fail(self, reason: str) -> None:
        self._logger.error(reason)
        
    def good(self, reason: str) -> None:
        self._logger.log(GOOD_LEVEL, reason)


