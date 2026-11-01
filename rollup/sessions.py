"""Trading session windows and bar bucketing.

A session is a set of explicit half-open-ish windows given in local wall-clock
time.  Membership is inclusive at both ends, so a tick stamped exactly at the
close (11:30:00.000) still belongs to the session.  Bars are bucketed inside a
window with ``floor((t - window_start) / interval)``; the final bucket of a
window is clipped to the window end, so a window whose length is not a multiple
of the interval produces one short trailing bar instead of a bar that spills
into the next window.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

DEFAULT_SESSIONS = "09:30-11:30,13:00-15:00"

INTERVALS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
}


class SessionError(ValueError):
    """Raised when a session or interval specification cannot be understood."""


def _parse_clock(text: str, what: str) -> int:
    """Parse 'HH:MM' or 'HH:MM:SS' into seconds from midnight."""
    raw = text.strip()
    if not raw:
        raise SessionError(f"empty time in {what!r}")
    parts = raw.split(":")
    if len(parts) not in (2, 3):
        raise SessionError(f"bad time {raw!r} in {what!r}, expected HH:MM or HH:MM:SS")
    try:
        values = [int(p) for p in parts]
    except ValueError:
        raise SessionError(f"bad time {raw!r} in {what!r}, not numeric") from None
    hour, minute = values[0], values[1]
    second = values[2] if len(values) == 3 else 0
    if not (0 <= hour <= 24):
        raise SessionError(f"hour out of range in {raw!r}")
    if not (0 <= minute < 60) or not (0 <= second < 60):
        raise SessionError(f"minute or second out of range in {raw!r}")
    total = hour * 3600 + minute * 60 + second
    if total > 86400:
        raise SessionError(f"time {raw!r} is past end of day")
    return total


def clock_text(seconds: int) -> str:
    """Render seconds from midnight as HH:MM (or HH:MM:SS when needed)."""
    hour, rest = divmod(int(seconds), 3600)
    minute, sec = divmod(rest, 60)
    if sec:
        return f"{hour:02d}:{minute:02d}:{sec:02d}"
    return f"{hour:02d}:{minute:02d}"


@dataclass(frozen=True)
class Window:
    """One trading window, in seconds from midnight."""

    start_sec: int
    end_sec: int

    @property
    def duration(self) -> int:
        return self.end_sec - self.start_sec

    @property
    def label(self) -> str:
        return f"{clock_text(self.start_sec)}-{clock_text(self.end_sec)}"

    def contains(self, sec: float) -> bool:
        return self.start_sec <= sec <= self.end_sec


@dataclass(frozen=True)
class SessionSpec:
    """A set of windows plus the bar interval that applies inside each."""

    windows: tuple[Window, ...]
    interval_sec: int
    interval_label: str = "1m"

    @classmethod
    def parse(
        cls,
        sessions: str = DEFAULT_SESSIONS,
        interval: str = "1m",
    ) -> "SessionSpec":
        if interval not in INTERVALS:
            known = ", ".join(sorted(INTERVALS))
            raise SessionError(f"unknown interval {interval!r}, choose one of: {known}")
        interval_sec = INTERVALS[interval]

        raw_windows = [w for w in sessions.split(",") if w.strip()]
        if not raw_windows:
            raise SessionError("no session windows given")

        windows: list[Window] = []
        for spec in raw_windows:
            text = spec.strip()
            if "-" not in text:
                raise SessionError(
                    f"bad window {text!r}, expected START-END such as 09:30-11:30"
                )
            start_text, _, end_text = text.partition("-")
            start = _parse_clock(start_text, text)
            end = _parse_clock(end_text, text)
            if end <= start:
                raise SessionError(f"window {text!r} ends before it starts")
            windows.append(Window(start, end))

        ordered = sorted(windows, key=lambda w: w.start_sec)
        for prev, nxt in zip(ordered, ordered[1:]):
            if nxt.start_sec <= prev.end_sec:
                raise SessionError(
                    f"windows {prev.label} and {nxt.label} overlap or touch"
                )

        return cls(tuple(ordered), interval_sec, interval)

    def bucket(self, ts: datetime) -> tuple[int, int, int] | None:
        """Return (day, window_index, bucket_index), or None if the market is shut.

        The day is part of the key so that a file spanning several days is
        ordered correctly and a tick from Tuesday can never be mistaken for a
        late tick from Monday.  A timestamp at exactly the window end lands in
        the last bucket, not in the next window, so the closing print is not
        lost.
        """
        sec = (
            ts.hour * 3600
            + ts.minute * 60
            + ts.second
            + ts.microsecond / 1_000_000
        )
        for index, window in enumerate(self.windows):
            if not window.contains(sec):
                continue
            offset = sec - window.start_sec
            k = int(offset // self.interval_sec)
            buckets = max(1, (window.duration + self.interval_sec - 1) // self.interval_sec)
            if k >= buckets:
                k = buckets - 1
            return (ts.date().toordinal(), index, k)
        return None

    def bar_bounds(
        self, ts: datetime, key: tuple[int, int, int]
    ) -> tuple[datetime, datetime]:
        """Wall-clock start and end of the bar identified by ``key``."""
        window = self.windows[key[1]]
        start_sec = window.start_sec + key[2] * self.interval_sec
        end_sec = min(start_sec + self.interval_sec, window.end_sec)
        return (
            datetime.combine(ts.date(), datetime.min.time()).replace(
                hour=start_sec // 3600,
                minute=(start_sec % 3600) // 60,
                second=start_sec % 60,
                tzinfo=ts.tzinfo,
            ),
            datetime.combine(ts.date(), datetime.min.time()).replace(
                hour=end_sec // 3600,
                minute=(end_sec % 3600) // 60,
                second=end_sec % 60,
                tzinfo=ts.tzinfo,
            ),
        )

    def session_label(self, key: tuple[int, int, int]) -> str:
        return self.windows[key[1]].label

    def buckets_per_window(self) -> tuple[int, ...]:
        return tuple(
            max(1, (w.duration + self.interval_sec - 1) // self.interval_sec)
            for w in self.windows
        )
