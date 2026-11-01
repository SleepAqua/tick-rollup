"""The bar record and its CSV representation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

COLUMNS = (
    "session",
    "bar_start",
    "bar_end",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "trades",
    "vwap",
    "revised",
)


def num(value: float | None, places: int = 6) -> str:
    """Fixed-precision text, or an empty field when there is no value."""
    if value is None:
        return ""
    return f"{value:.{places}f}"


@dataclass
class Bar:
    """One OHLCV bar.

    ``open`` and ``close`` follow trade time, not arrival order: a late trade
    that is older than the first trade of the bar replaces ``open``, and one
    newer than the last replaces ``close``.  ``turnover`` is sum(price * size)
    so that ``vwap == turnover / volume`` exactly.
    """

    session: str
    key: tuple[int, int, int]
    start: datetime
    end: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    turnover: float = 0.0
    trades: int = 0
    revised: bool = False
    first_ts: float = 0.0
    last_ts: float = 0.0

    @property
    def vwap(self) -> float | None:
        if self.volume == 0:
            return None
        return self.turnover / self.volume

    def apply(self, ts_value: float, price: float, size: float) -> None:
        """Fold one trade into the bar. ``ts_value`` is epoch-free ordering key."""
        if self.trades == 0:
            self.open = price
            self.high = price
            self.low = price
            self.close = price
            self.first_ts = ts_value
            self.last_ts = ts_value
        else:
            if ts_value < self.first_ts:
                self.first_ts = ts_value
                self.open = price
            if ts_value > self.last_ts:
                self.last_ts = ts_value
                self.close = price
            if price > self.high:
                self.high = price
            if price < self.low:
                self.low = price
        self.volume += size
        self.turnover += price * size
        self.trades += 1

    def row(self) -> list[str]:
        return [
            self.session,
            self.start.isoformat(timespec="seconds"),
            self.end.isoformat(timespec="seconds"),
            num(self.open),
            num(self.high),
            num(self.low),
            num(self.close),
            num(self.volume),
            num(self.turnover),
            str(self.trades),
            num(self.vwap),
            "yes" if self.revised else "no",
        ]
