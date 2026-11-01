"""Streaming tick CSV reader.

The reader walks the file one line at a time and yields parsed ticks, so the
process never holds the file in memory.  Column order does not matter: the
header names are matched case-insensitively.  ``timestamp``, ``price`` and
``size`` are required; ``side`` is optional and defaults to an empty string.
"""

from __future__ import annotations

import csv
import io
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, TextIO

REQUIRED = ("timestamp", "price", "size")


class TickFormatError(ValueError):
    """Raised when a tick line cannot be parsed. Carries the line number."""

    def __init__(self, message: str, lineno: int, line: str = "") -> None:
        self.lineno = lineno
        self.line = line
        super().__init__(f"line {lineno}: {message}")


def parse_timestamp(raw: str) -> datetime:
    text = raw.strip()
    if not text:
        raise ValueError("empty timestamp")
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"timestamp {raw!r} is not ISO 8601") from None


def _header_map(names: Iterable[str], lineno: int) -> dict[str, int]:
    index: dict[str, int] = {}
    for position, name in enumerate(names):
        cleaned = (name or "").strip().lower().lstrip("\ufeff")
        if cleaned:
            index.setdefault(cleaned, position)
    missing = [name for name in REQUIRED if name not in index]
    if missing:
        raise TickFormatError(
            "header is missing column(s): " + ", ".join(missing), lineno
        )
    return index


def iter_ticks(handle: TextIO) -> Iterator[tuple[int, datetime, float, float, str]]:
    """Yield (line_number, timestamp, price, size, side) from an open text file."""
    reader = csv.reader(handle)
    header: dict[str, int] | None = None
    for row in reader:
        if not row or all(not cell.strip() for cell in row):
            continue
        if header is None:
            header = _header_map(row, reader.line_num)
            continue
        lineno = reader.line_num
        try:
            ts = parse_timestamp(row[header["timestamp"]])
        except (IndexError, ValueError) as exc:
            raise TickFormatError(str(exc), lineno, ",".join(row)) from None
        try:
            price = float(row[header["price"]])
            size = float(row[header["size"]])
        except (IndexError, ValueError):
            raise TickFormatError(
                "price or size is not a number", lineno, ",".join(row)
            ) from None
        if price != price or size != size:  # NaN check without importing math
            raise TickFormatError("price or size is NaN", lineno, ",".join(row))
        side = ""
        if "side" in header:
            try:
                side = row[header["side"]].strip()
            except IndexError:
                side = ""
        yield lineno, ts, price, size, side
    if header is None:
        raise TickFormatError("file has no header row", 0)


def read_path(path: str | Path) -> Iterator[tuple[int, datetime, float, float, str]]:
    """Open ``path`` (or stdin for '-') and stream ticks from it."""
    if str(path) == "-":
        stream = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8-sig", newline="")
        try:
            yield from iter_ticks(stream)
        finally:
            stream.detach()
        return
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        yield from iter_ticks(handle)
