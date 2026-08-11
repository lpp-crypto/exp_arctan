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
import datetime

from math import floor
from pathlib import Path
from typing import Optional

from rich.console import Console
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



def to_roman(n: int) -> str:
    if not 0 <= n < 4000:
        raise ValueError("Roman numerals only support 1-3999")
    elif n == 0:
        return "0"
    values = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    result = []
    for value, symbol in values:
        count, n = divmod(n, value)
        result.append(symbol * count)
    return "".join(result)


def pretty_counters(counters):
    result = to_roman(counters[0])
    if len(counters) > 1:
        result += "-" + str(counters[1])
    if len(counters) > 2:
        result += "." + to_roman(counters[2]).lower()
    return result + ")"


# !SECTION! Trick to bypass some `logging` behaviors

# !SUBSECTION! To not display the time on every line if it hasn't changed 

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


# !SUBSECTION! To remove the display of "INFO" 


class CustomRichHandler(RichHandler):
    LEVEL_OVERRIDES = {
        logging.INFO-1: "END",
        logging.INFO: "",
        logging.ERROR: "FAIL",
        logging.WARNING: "WARN",
        logging.CRITICAL: "CRIT",
    }
    LEVEL_WIDTH = 4

    def get_level_text(self, record: logging.LogRecord) -> Text:
        """

        The names of the levels is hard coded in the logic of RichHandler, so using custom level names would a priori break their highlighting (i.e., FAIL being in red). Rewriting this method bypasses this problem.
        
        """
        # 
        style = f"logging.level.{record.levelname.lower()}"
        if record.levelno in self.LEVEL_OVERRIDES:
            text = self.LEVEL_OVERRIDES[record.levelno]
        else:
            text = record.levelname
        return Text(text.ljust(self.LEVEL_WIDTH)[: self.LEVEL_WIDTH], style=style)

    

# !SUBSECTION! To simplify tracking durations: the Chonograph



class Chronograph:
    def __init__(self, title):
        self.title = title
        self.start_time = datetime.datetime.now()

    def __str__(self):
        return "\"{}\" lasted {}s".format(
            self.title,
            self.elapsed_seconds(),
        )

    def elapsed_seconds(self):
        return floor((datetime.datetime.now() - self.start_time).total_seconds())

    
    def elapsed_time_str(self):
        tot_secs = self.elapsed_seconds()
        days = floor(tot_secs / 86400)
        hours = floor((tot_secs % 86400) / 3600)
        minutes = floor((tot_secs % 3600) / 60)
        seconds = tot_secs % 60
        return "{:d}d {:02d}h {:02d}m {:2d}s".format(
            days,
            hours,
            minutes,
            seconds
        )

    def __rich_str__(self):
        return "[blue]{}[/blue] lasted [bold]{}[/bold]s [gray]({})[/gray]".format(
            self.title,
            self.elapsed_seconds(),
            self.elapsed_time_str(),
        )



    
# !SECTION!  The actual Transcript class
    
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
        logfile: Optional[str] = None,
        date_fmt: str = "%m/%d/%y",
        time_fmt: str = "%H:%M:%S",
        verbose: str = "normal"
    ):
        self.title = title
        self.logfile = Path(logfile) if logfile else None
        self.date_fmt = date_fmt
        self.time_fmt = time_fmt

        self._saved_print = None
        self._logger: Optional[logging.Logger] = None
        self._handlers = []
        self._time_formatter: Optional[StickyDateTime] = None
        self.console: Optional[Console] = None
        verbose_table = {
            "debug"  : logging.DEBUG,
            "normal" : logging.INFO,
            "errors" : logging.ERROR,
            "silent" : logging.CRITICAL + 1,
        }
        self.level = verbose_table[verbose]
        
        self._sections_counters = [0]
        self._timers = []
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
        self.console = Console()

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
        


    
    def stamp(self, timestamp_text: str, *args) -> None:
        """
        Log a message with an arbitrary string in place of the timestamp
        for that one line only (e.g. elapsed runtime instead of a clock
        time). Subsequent lines revert to normal timestamp behavior.
        """
        self._time_formatter.override_next(timestamp_text)
        self._logger.info(" ".join(str(a) for a in args))
        
        
    def finish(self) -> None:
        self._logger.info(f"[DONE]")
        self.finalize_sections(0)

        # !TODO! the times table doesn't work
        self.console.print(self._times_table)

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
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
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
        total_depth = len(self._sections_counters)
        for i in range(target_depth, total_depth):
            chrono = self._timers.pop()
            self._times_table.add_row(
                pretty_counters(self._sections_counters[0:total_depth-i]),
                chrono.title,
                chrono.elapsed_time_str(),
                str(chrono.elapsed_seconds()),
            )
            
        
    def section(self, title: str) -> None:
        self.finalize_sections(1)
        self._timers.append(Chronograph(title))
        self._sections_counters = [self._sections_counters[0] + 1]
        h1_format = "[b][blue]{}[/blue][b]"
        full_title = "\n\nSEC {}  {}".format(
            pretty_counters(self._sections_counters),
            title,
        )
        self._logger.info(h1_format.format(full_title))
        self._logger.info(h1_format.format("=" * len (full_title)) + "\n")

        
    def subsection(self, title: str) -> None:
        self.finalize_sections(2)
        self._timers.append(Chronograph(title))
        if len(self._sections_counters) < 2:
            self._sections_counters.append(0)
        self._sections_counters = [
            self._sections_counters[0],
            self._sections_counters[1] + 1
        ]
        h2_format = "[b]{}[b]"
        full_title = "\nSEC {}  {}".format(
            pretty_counters(self._sections_counters),
            title,
        )
        self._logger.info(h2_format.format(full_title))
        self._logger.info(h2_format.format("-" * len (full_title)))

        
    def subsubsection(self, title: str) -> None:
        # finishing the previous section (and subsections)
        self.finalize_sections(3)
        self._timers.append(Chronograph(title))
        if len(self._sections_counters) < 2:
            self._sections_counters.append(0)
        self._sections_counters = [
            self._sections_counters[0],
            self._sections_counters[1] + 1
        ]
        # handling the new section
        
        self._sections_counters = self._sections_counters[:depth] + [counter + 1]
        full_title = "SEC {}  {}".format(
            pretty_counters(self._sections_counters),
            title,
        )
        self._logger.info(full_title)

        
    def debug(self, reason: str) -> None:
        self._logger.debug(reason)

    def warning(self, reason: str) -> None:
        self._logger.warning(reason)
        
    def fail(self, reason: str) -> None:
        self._logger.error(reason)


