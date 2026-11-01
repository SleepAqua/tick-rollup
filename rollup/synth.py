"""Synthetic tick generator. Seeded and reproducible.

The walk is a simple random step on the last price, one tick every few hundred
milliseconds inside the configured windows, with a small share of deliberately
late and out-of-session rows so the late-tick paths get exercised on real runs.

``days`` is the number of trading days to walk; generation stops early once
``rows`` lines have been produced, so the file holds ``min(rows, generated)``
ticks.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

from .sessions import DEFAULT_SESSIONS, SessionSpec

SIZES = (100, 200, 300, 500, 1000, 1500)


def generate_lines(
    rows: int = 200_000,
    seed: int = 7,
    days: int = 3,
    start_date: date = date(2026, 3, 2),
    sessions: str = DEFAULT_SESSIONS,
    late_frac: float = 0.005,
    out_of_session_frac: float = 0.002,
    start_price: float = 100.0,
) -> Iterator[str]:
    """Yield CSV lines (header first) for a synthetic tick file."""
    if rows < 1:
        raise ValueError("rows must be at least 1")
    if days < 1:
        raise ValueError("days must be at least 1")
    spec = SessionSpec.parse(sessions, "1m")
    rng = random.Random(seed)

    yield "timestamp,price,size,side\n"
    price = start_price
    emitted = 0

    for day_index in range(days):
        if emitted >= rows:
            break
        day = start_date + timedelta(days=day_index)
        midnight = datetime.combine(day, datetime.min.time())
        for window in spec.windows:
            second = float(window.start_sec)
            while second <= window.end_sec and emitted < rows:
                ts = midnight + timedelta(seconds=second)
                step = rng.gauss(0.0, 0.02)
                price = max(1.0, round(price + step, 2))
                size = rng.choice(SIZES)
                side = "B" if step >= 0 else "S"

                if rng.random() < out_of_session_frac:
                    # A print during lunch or before the open: no bar should take it.
                    gap = window.start_sec - 1800 + rng.randint(0, 600)
                    yield _line(midnight + timedelta(seconds=gap), price, size, side)
                    emitted += 1

                when = ts
                if rng.random() < late_frac:
                    candidate = ts - timedelta(seconds=rng.randint(5, 600))
                    if spec.bucket(candidate) is not None and candidate.date() == ts.date():
                        when = candidate
                yield _line(when, price, size, side)
                emitted += 1

                if rng.random() < 0.0004:
                    second += 60  # land on a minute boundary now and then
                else:
                    second += rng.randint(15, 305) / 1000.0


def _line(ts: datetime, price: float, size: int, side: str) -> str:
    millis = ts.microsecond // 1000
    return f"{ts:%Y-%m-%dT%H:%M:%S}.{millis:03d},{price:.2f},{size},{side}\n"


def write_ticks(path: str | Path, rows: int = 200_000, **kwargs) -> dict:
    """Write a synthetic tick file and return a small summary of it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    first = last = None
    count = 0
    with open(path, "w", encoding="utf-8", newline="") as handle:
        for line in generate_lines(rows=rows, **kwargs):
            handle.write(line)
            if line.startswith("timestamp"):
                continue
            count += 1
            if first is None:
                first = line[:23]
            last = line[:23]
    return {
        "path": str(path),
        "rows": count,
        "bytes": path.stat().st_size,
        "first_ts": first,
        "last_ts": last,
    }
