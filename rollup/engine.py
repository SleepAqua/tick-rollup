"""Roll-up engine: ticks in, OHLCV bars out.

Two late-tick modes:

``strict``
    A tick whose (window, bucket) key is lower than the highest key already
    seen belongs to a bar that is already closed.  It is dropped and counted
    in ``dropped_late``.  Bars are emitted as soon as the watermark moves past
    them, so memory is constant.

``repair``
    The same tick reopens the bar, is folded in, and marks that bar
    ``revised``.  Bars of a session are held until the session ends (the first
    tick of the next session, or end of file), then emitted in time order.
    Memory is bounded by the bars in one session, which for the default
    sessions is 120 bars at 1m, 24 at 5m and 8 at 15m, regardless of how many
    ticks the file holds.  A tick older than the session already flushed cannot
    be repaired and is counted in ``dropped_late``.

Nothing is ever merged across a session boundary: the key carries the window
index, and each window starts its own bucket sequence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .bars import Bar
from .sessions import SessionSpec


class LateMode:
    STRICT = "strict"
    REPAIR = "repair"
    CHOICES = (STRICT, REPAIR)


def time_key(ts: datetime) -> float:
    """Ordering key for a timestamp: day ordinal in seconds plus second of day.

    Avoids ``datetime.timestamp()``, which depends on the host timezone for
    naive datetimes.
    """
    return (
        ts.date().toordinal() * 86400.0
        + ts.hour * 3600.0
        + ts.minute * 60.0
        + ts.second
        + ts.microsecond / 1_000_000.0
    )


@dataclass
class Stats:
    ticks_read: int = 0
    ticks_used: int = 0
    dropped_out_of_session: int = 0
    dropped_late: int = 0
    repaired: int = 0
    bars: int = 0
    bars_revised: int = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    def as_dict(self, extra: dict | None = None) -> dict:
        data = {
            "ticks_read": self.ticks_read,
            "ticks_used": self.ticks_used,
            "dropped_out_of_session": self.dropped_out_of_session,
            "dropped_late": self.dropped_late,
            "repaired": self.repaired,
            "bars": self.bars,
            "bars_revised": self.bars_revised,
            "first_ts": self.first_ts.isoformat() if self.first_ts else None,
            "last_ts": self.last_ts.isoformat() if self.last_ts else None,
        }
        if extra:
            data.update(extra)
        return data

    def summary(self) -> str:
        return (
            f"ticks_read={self.ticks_read} ticks_used={self.ticks_used} "
            f"bars={self.bars} dropped_out_of_session={self.dropped_out_of_session} "
            f"dropped_late={self.dropped_late} repaired={self.repaired} "
            f"bars_revised={self.bars_revised}"
        )


@dataclass
class RollupEngine:
    spec: SessionSpec
    late_mode: str = LateMode.STRICT
    stats: Stats = field(default_factory=Stats)
    _open: dict[tuple[int, int, int], Bar] = field(default_factory=dict)
    max_key: tuple[int, int, int] | None = None
    _session: tuple[int, int] | None = None
    # Debug aid only: when a list is passed, every tick that reaches a bar is
    # appended as (key, timestamp, price, size). Off by default so the normal
    # path allocates nothing.
    trace: list | None = None

    def __post_init__(self) -> None:
        if self.late_mode not in LateMode.CHOICES:
            raise ValueError(f"late mode must be one of {LateMode.CHOICES}")

    # -- feeding -----------------------------------------------------------
    def feed(
        self, ts: datetime, price: float, size: float, side: str = ""
    ) -> list[Bar]:
        """Fold one tick in. Returns the bars that closed because of it."""
        stats = self.stats
        stats.ticks_read += 1
        if stats.first_ts is None or ts < stats.first_ts:
            stats.first_ts = ts
        if stats.last_ts is None or ts > stats.last_ts:
            stats.last_ts = ts

        key = self.spec.bucket(ts)
        if key is None:
            stats.dropped_out_of_session += 1
            return []

        if self.max_key is not None and key < self.max_key:
            return self._late(ts, key, price, size)

        closed: list[Bar] = []
        if self.max_key is None:
            self.max_key = key
        elif key > self.max_key:
            closed.extend(self._advance(key))
            self.max_key = key
        self._session = key[:2]
        bar = self._open.get(key)
        if bar is None:
            bar = self._new_bar(ts, key, price)
        bar.apply(time_key(ts), price, size)
        stats.ticks_used += 1
        if self.trace is not None:
            self.trace.append((key, ts, price, size))
        return closed

    def _late(
        self, ts: datetime, key: tuple[int, int, int], price: float, size: float
    ) -> list[Bar]:
        """Handle a tick that belongs before the highest key seen."""
        stats = self.stats
        bar = self._open.get(key)
        if self.late_mode == LateMode.STRICT:
            stats.dropped_late += 1
            return []
        if bar is None:
            if key[:2] != self._session:
                # That session (or day) is already flushed, so there is no bar
                # left to repair.
                stats.dropped_late += 1
                return []
            # The bucket had no trades when it passed, so there is no closed
            # bar to revise. Create it now; it is new, not revised.
            bar = self._new_bar(ts, key, price)
        else:
            bar.revised = True
            stats.repaired += 1
        bar.apply(time_key(ts), price, size)
        stats.ticks_used += 1
        if self.trace is not None:
            self.trace.append((key, ts, price, size))
        return []

    def _new_bar(self, ts: datetime, key: tuple[int, int, int], price: float) -> Bar:
        start, end = self.spec.bar_bounds(ts, key)
        bar = Bar(
            session=self.spec.session_label(key),
            key=key,
            start=start,
            end=end,
            open=price,
            high=price,
            low=price,
            close=price,
        )
        self._open[key] = bar
        return bar

    def _advance(self, key: tuple[int, int, int]) -> list[Bar]:
        """Emit bars made final by a new highest key."""
        if self.late_mode == LateMode.STRICT:
            ready = sorted(k for k in self._open if k < key)
        else:
            # Only whole sessions become final early; the current session is
            # kept open so a late tick can still repair it.
            ready = sorted(k for k in self._open if k[:2] < key[:2])
        out = [self._open.pop(k) for k in ready]
        for bar in out:
            self._count(bar)
        return out

    def _count(self, bar: Bar) -> None:
        self.stats.bars += 1
        if bar.revised:
            self.stats.bars_revised += 1

    def close(self) -> list[Bar]:
        """Flush everything still open. Call once after the last tick."""
        out = [self._open[k] for k in sorted(self._open)]
        self._open.clear()
        for bar in out:
            self._count(bar)
        return out
