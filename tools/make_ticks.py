#!/usr/bin/env python3
"""Write a seeded synthetic tick CSV.

    python tools/make_ticks.py --out ticks.csv --rows 200000 --seed 7

Same seed and same arguments produce the same bytes. The generator lives in
rollup/synth.py so the benchmark command can call it without shelling out.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rollup.sessions import DEFAULT_SESSIONS  # noqa: E402
from rollup.synth import write_ticks  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", "-o", default="ticks.csv", help="output path")
    parser.add_argument("--rows", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--days", type=int, default=3)
    parser.add_argument("--sessions", default=DEFAULT_SESSIONS)
    parser.add_argument("--late-frac", type=float, default=0.005,
                        help="share of ticks written out of order")
    parser.add_argument("--out-of-session-frac", type=float, default=0.002,
                        help="share of ticks written outside the windows")
    args = parser.parse_args(argv)

    summary = write_ticks(
        args.out,
        rows=args.rows,
        seed=args.seed,
        days=args.days,
        sessions=args.sessions,
        late_frac=args.late_frac,
        out_of_session_frac=args.out_of_session_frac,
    )
    print(f"wrote {summary['rows']} ticks to {summary['path']}")
    print(f"bytes {summary['bytes']}  first {summary['first_ts']}  last {summary['last_ts']}")
    print(f"seed {args.seed}  days {args.days}  sessions {args.sessions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
