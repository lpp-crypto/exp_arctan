import datetime
from math import floor
from rich.text import Text


# !SECTION! Format section indices

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


# !SECTION! The Chronograph class 

class Chronograph:
    def __init__(self, title):
        self.title = title
        self.start_time = datetime.datetime.now()

    def __str__(self):
        return "{} lasted {}".format(
            self.title,
            self.elapsed_time_str(),
        )

    def elapsed_seconds(self):
        return floor((datetime.datetime.now() - self.start_time).total_seconds())

    
    def elapsed_time_str(self):
        tot_secs = self.elapsed_seconds()
        days = floor(tot_secs / 86400)
        hours = floor((tot_secs % 86400) / 3600)
        minutes = floor((tot_secs % 3600) / 60)
        seconds = tot_secs % 60
        return "{:d}d {:02d}:{:02d}:{:02d}".format(
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



# !SECTION! The StickyDateTime class

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
