"""Empty input, one tick, everything filtered out, bad arguments."""

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

import _util
from rollup.cli import main
from rollup.sessions import SessionSpec


class EdgeCaseTests(unittest.TestCase):
    spec = SessionSpec.parse()

    def test_empty_file_gives_no_bars(self):
        engine, bars = _util.run(self.spec, [])
        self.assertEqual(bars, [])
        self.assertEqual(engine.stats.ticks_read, 0)
        self.assertEqual(engine.stats.bars, 0)
        self.assertIsNone(engine.stats.first_ts)

    def test_single_tick(self):
        engine, bars = _util.run(self.spec, [("2026-03-02T09:30:00", 50.25, 300)])
        self.assertEqual(len(bars), 1)
        bar = bars[0]
        self.assertEqual((bar.open, bar.high, bar.low, bar.close), (50.25, 50.25, 50.25, 50.25))
        self.assertEqual(bar.volume, 300)
        self.assertAlmostEqual(bar.vwap, 50.25, places=12)
        self.assertEqual(bar.trades, 1)
        self.assertEqual(engine.stats.ticks_used, 1)

    def test_only_out_of_session_ticks(self):
        engine, bars = _util.run(
            self.spec,
            [("2026-03-02T08:00:00", 1.0, 1), ("2026-03-02T12:30:00", 1.0, 1)],
        )
        self.assertEqual(bars, [])
        self.assertEqual(engine.stats.dropped_out_of_session, 2)
        self.assertEqual(engine.stats.ticks_used, 0)

    def test_zero_size_ticks_still_count_as_trades(self):
        _engine, bars = _util.run(
            self.spec,
            [("2026-03-02T09:30:00", 10.0, 0), ("2026-03-02T09:30:30", 11.0, 0)],
        )
        bar = bars[0]
        self.assertEqual(bar.trades, 2)
        self.assertEqual(bar.volume, 0)
        self.assertIsNone(bar.vwap)
        self.assertEqual((bar.open, bar.close), (10.0, 11.0))


class CliErrorTests(unittest.TestCase):
    def test_bad_session_spec_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ticks.csv"
            _util.write_ticks(path, [("2026-03-02T09:30:00", 1.0, 1, "B")])
            with redirect_stderr(io.StringIO()):
                code = main(["bar", "--input", str(path), "--sessions", "09:30"])
        self.assertEqual(code, 2)

    def test_bad_row_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ticks.csv"
            path.write_text("timestamp,price,size\n2026-03-02T09:30:00,abc,1\n")
            out = Path(tmp) / "bars.csv"
            with redirect_stderr(io.StringIO()):
                code = main(["bar", "--input", str(path), "--out", str(out), "--quiet"])
        self.assertEqual(code, 2)

    def test_help_runs(self):
        result = subprocess.run(
            [sys.executable, "-m", "rollup", "--help"],
            cwd=_util.ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("bar", result.stdout)
        self.assertIn("benchmark", result.stdout)
        self.assertIn("demo", result.stdout)


if __name__ == "__main__":
    unittest.main()
