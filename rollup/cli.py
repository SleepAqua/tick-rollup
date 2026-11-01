"""Command line entry point: bar, benchmark, demo."""

from __future__ import annotations

import argparse
import csv
import json
import resource
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import TextIO

from .bars import COLUMNS, Bar
from .engine import LateMode, RollupEngine, Stats
from .reader import TickFormatError, read_path
from .sessions import DEFAULT_SESSIONS, INTERVALS, SessionError, SessionSpec
from .synth import write_ticks

PROG = "rollup"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE = PACKAGE_ROOT / "examples" / "demo_ticks.csv"


# -- shared helpers --------------------------------------------------------
def _spec(args: argparse.Namespace) -> SessionSpec:
    return SessionSpec.parse(args.sessions, args.interval)


def roll_file(
    path: str | Path,
    spec: SessionSpec,
    late_mode: str,
    sink=None,
    trace: list | None = None,
) -> Stats:
    """Roll one file up, calling ``sink(bar)`` for every bar that closes."""
    engine = RollupEngine(spec, late_mode)
    engine.trace = trace
    for _lineno, ts, price, size, side in read_path(path):
        for bar in engine.feed(ts, price, size, side):
            if sink is not None:
                sink(bar)
    for bar in engine.close():
        if sink is not None:
            sink(bar)
    return engine.stats


def _print_stats(stats: Stats, stream: TextIO, prefix: str = "") -> None:
    print(f"{prefix}{stats.summary()}", file=stream)


def _table(bars: list[Bar]) -> str:
    head = (
        f"{'bar_start':<19} {'open':>10} {'high':>10} {'low':>10} {'close':>10} "
        f"{'volume':>10} {'turnover':>13} {'trades':>6} {'vwap':>12}  revised"
    )
    lines = [head, "-" * len(head)]
    for bar in bars:
        lines.append(
            f"{bar.start.isoformat(timespec='seconds'):<19} "
            f"{bar.open:>10.4f} {bar.high:>10.4f} {bar.low:>10.4f} {bar.close:>10.4f} "
            f"{bar.volume:>10.1f} {bar.turnover:>13.2f} {bar.trades:>6d} "
            f"{(bar.vwap if bar.vwap is not None else float('nan')):>12.6f}  "
            f"{'yes' if bar.revised else 'no'}"
        )
    return "\n".join(lines)


def _group_trace(trace: list) -> dict[tuple[int, int], list[tuple]]:
    """Group the ticks a run actually kept, by bar key. Demo only."""
    grouped: dict[tuple[int, int], list[tuple]] = {}
    for key, ts, price, size in trace:
        grouped.setdefault(key, []).append((ts, price, size))
    return grouped


def _arithmetic(bars: list[Bar], grouped: dict[tuple[int, int], list[tuple]], limit: int = 2) -> str:
    lines: list[str] = []
    for bar in bars[:limit]:
        ticks = grouped.get(bar.key)
        if not ticks:
            continue
        sizes = [size for _ts, _price, size in ticks]
        terms = [f"{price:.2f}*{size:g}" for _ts, price, size in ticks]
        volume = sum(sizes)
        turnover = sum(price * size for _ts, price, size in ticks)
        lines.append(
            f"{bar.start.strftime('%H:%M')} volume   = "
            + " + ".join(f"{s:g}" for s in sizes)
            + f" = {volume:g}"
        )
        lines.append(
            f"{bar.start.strftime('%H:%M')} turnover = "
            + " + ".join(terms)
            + f" = {turnover:.2f}"
        )
        vwap = turnover / volume if volume else float("nan")
        lines.append(
            f"{bar.start.strftime('%H:%M')} vwap     = {turnover:.2f} / {volume:g}"
            f" = {vwap:.6f}"
        )
        lines.append(
            f"{bar.start.strftime('%H:%M')} ohlc     = open {bar.open:.2f} high "
            f"{bar.high:.2f} low {bar.low:.2f} close {bar.close:.2f}"
        )
    return "\n".join(lines)


# -- commands --------------------------------------------------------------
def cmd_bar(args: argparse.Namespace) -> int:
    spec = _spec(args)
    out: TextIO
    close_out = False
    if args.out == "-":
        out = sys.stdout
    else:
        out = open(args.out, "w", encoding="utf-8", newline="")
        close_out = True
    writer = csv.writer(out, lineterminator="\n")
    try:
        writer.writerow(COLUMNS)

        def sink(bar: Bar) -> None:
            writer.writerow(bar.row())

        stats = roll_file(args.input, spec, args.late, sink)
    finally:
        if close_out:
            out.close()

    if args.stats_json:
        payload = stats.as_dict(
            {"interval": spec.interval_label, "late_mode": args.late, "input": str(args.input)}
        )
        Path(args.stats_json).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        _print_stats(stats, sys.stderr)
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    spec = _spec(args)
    tempdir: str | None = None
    path: str
    if args.input:
        path = args.input
        generated = None
    else:
        tempdir = tempfile.mkdtemp(prefix="rollup-bench-")
        path = str(Path(tempdir) / "ticks.csv")
        generated = write_ticks(
            path,
            rows=args.rows,
            seed=args.seed,
            days=args.days,
            sessions=args.sessions,
        )

    started = time.perf_counter()
    stats = roll_file(path, spec, args.late)
    wall = time.perf_counter() - started

    size_bytes = Path(path).stat().st_size
    peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rate = stats.ticks_read / wall if wall > 0 else float("inf")

    cleanup = bool(tempdir) and not args.keep
    print(f"file             {path}" + ("  (deleted after run)" if cleanup else ""))
    print(f"rows             {stats.ticks_read}")
    print(f"file_mb          {size_bytes / 1e6:.2f}")
    print(f"interval         {spec.interval_label}")
    print(f"late_mode        {args.late}")
    print(f"sessions         {args.sessions}")
    print(f"wall_seconds     {wall:.6f}")
    print(f"ticks_per_second {rate:.0f}")
    print(f"bars             {stats.bars}")
    print(f"dropped_late     {stats.dropped_late}")
    print(f"repaired         {stats.repaired}")
    print(f"peak_rss_mb      {peak_kb / 1024:.1f}")
    if generated:
        print(f"generated_rows   {generated['rows']}  seed {args.seed}  days {args.days}")
    if cleanup:
        shutil.rmtree(tempdir, ignore_errors=True)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    spec = _spec(args)
    path = Path(args.input) if args.input else DEFAULT_FIXTURE
    if not path.exists():
        print(f"error: fixture not found: {path}", file=sys.stderr)
        return 2
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    tick_lines = [line for line in text.splitlines() if line.strip()][1:]

    try:
        label = str(path.resolve().relative_to(PACKAGE_ROOT))
    except ValueError:
        label = str(path)
    modes = [args.late] if args.late else [LateMode.STRICT, LateMode.REPAIR]

    print(f"fixture  {label}  ({len(tick_lines)} ticks)")
    print(f"interval {spec.interval_label}")
    print(f"sessions {', '.join(w.label for w in spec.windows)}")
    print()

    for mode in modes:
        bars: list[Bar] = []
        trace: list = []
        stats = roll_file(path, spec, mode, bars.append, trace)
        print(f"== {mode} ==")
        _print_stats(stats, sys.stdout)
        print()
        print(_table(bars))
        print()
        if mode == modes[0]:
            print(_arithmetic(bars, _group_trace(trace)))
            print()
        revised = [b for b in bars if b.revised]
        if revised:
            print("revised bars:")
            print(_table(revised))
            print()
    return 0


# -- parser ----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Roll a tick CSV up into OHLCV bars, one session at a time.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser, late_default: str | None = LateMode.STRICT) -> None:
        p.add_argument(
            "--interval",
            default="1m",
            choices=sorted(INTERVALS),
            help="bar size, default 1m",
        )
        p.add_argument(
            "--sessions",
            default=DEFAULT_SESSIONS,
            help=f"comma separated windows, default {DEFAULT_SESSIONS}",
        )
        p.add_argument(
            "--late",
            default=late_default,
            choices=LateMode.CHOICES,
            help="late tick handling, default strict",
        )

    bar = sub.add_parser("bar", help="write bars as CSV")
    common(bar)
    bar.add_argument("--input", "-i", required=True, help="tick CSV, or - for stdin")
    bar.add_argument("--out", "-o", default="-", help="output CSV, default stdout")
    bar.add_argument("--stats-json", default=None, help="also write counters as JSON")
    bar.add_argument("--quiet", action="store_true", help="do not print counters")
    bar.set_defaults(func=cmd_bar)

    bench = sub.add_parser("benchmark", help="measure throughput on a generated file")
    common(bench)
    bench.add_argument(
        "--rows", type=int, default=200_000, help="upper bound on ticks to generate"
    )
    bench.add_argument("--seed", type=int, default=7)
    bench.add_argument(
        "--days", type=int, default=3, help="trading days to walk, which caps the row count"
    )
    bench.add_argument("--input", default=None, help="use this file instead of generating one")
    bench.add_argument("--keep", action="store_true", help="keep the generated file")
    bench.set_defaults(func=cmd_benchmark)

    demo = sub.add_parser("demo", help="run the shipped fixture and show the arithmetic")
    common(demo, late_default=None)
    demo.add_argument("--input", default=None, help="ticks to use instead of the fixture")
    demo.set_defaults(func=cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SessionError as exc:
        print(f"error: session spec: {exc}", file=sys.stderr)
        return 2
    except TickFormatError as exc:
        print(f"error: bad tick data: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0
