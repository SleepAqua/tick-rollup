"""Small helpers shared by the tests. Not a test module."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rollup.sessions import SessionSpec  # noqa: E402


def __getattr__(name):
    """Resolve RollupEngine lazily so reader/session tests do not need it."""
    if name == "RollupEngine":
        from rollup.engine import RollupEngine

        return RollupEngine
    raise AttributeError(name)


def ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def run(spec: SessionSpec, ticks, mode: str = "strict"):
    """Feed (timestamp, price, size) tuples; return (engine, bars)."""
    from rollup.engine import RollupEngine

    engine = RollupEngine(spec, mode)
    bars = []
    for tick in ticks:
        first = tick[0]
        if isinstance(first, str):
            first = ts(first)
        bars.extend(engine.feed(first, *tick[1:]))
    bars.extend(engine.close())
    return engine, bars


def write_ticks(path: Path, rows) -> Path:
    """rows: (timestamp_text, price, size, side)."""
    path.write_text(
        "timestamp,price,size,side\n"
        + "".join(f"{t},{p},{s},{side}\n" for t, p, s, side in rows),
        encoding="utf-8",
    )
    return path
