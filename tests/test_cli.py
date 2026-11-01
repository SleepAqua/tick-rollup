"""End to end runs of the three commands, against the shipped fixture."""

import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import _util
from rollup.cli import main

FIXTURE = _util.ROOT / "examples" / "demo_ticks.csv"


class BarCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_bar(self, *extra):
        out = self.dir / "bars.csv"
        argv = ["bar", "--input", str(FIXTURE), "--out", str(out), "--quiet", *extra]
        code = main(argv)
        self.assertEqual(code, 0)
        with open(out, newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_strict_bars(self):
        rows = self.run_bar()
        self.assertEqual(len(rows), 9)
        first = rows[0]
        self.assertEqual(first["bar_start"], "2026-03-02T09:30:00")
        self.assertEqual(first["session"], "09:30-11:30")
        self.assertEqual(float(first["open"]), 100.10)
        self.assertEqual(float(first["high"]), 100.20)
        self.assertEqual(float(first["low"]), 100.05)
        self.assertEqual(float(first["close"]), 100.05)
        self.assertEqual(float(first["volume"]), 600.0)
        self.assertEqual(float(first["turnover"]), 60085.0)
        self.assertEqual(first["trades"], "3")
        self.assertEqual(first["vwap"], "100.141667")
        self.assertEqual(first["revised"], "no")

    def test_repair_bars(self):
        rows = self.run_bar("--late", "repair")
        second = rows[1]
        self.assertEqual(second["bar_start"], "2026-03-02T09:31:00")
        self.assertEqual(float(second["volume"]), 550.0)
        self.assertEqual(float(second["low"]), 100.15)
        self.assertEqual(second["revised"], "yes")
        self.assertEqual(sum(1 for r in rows if r["revised"] == "yes"), 1)

    def test_five_minute_bars(self):
        rows = self.run_bar("--interval", "5m")
        self.assertEqual(
            [r["bar_start"][11:] for r in rows],
            ["09:30:00", "09:35:00", "13:00:00", "13:05:00"],
        )

    def test_stats_json(self):
        stats_path = self.dir / "stats.json"
        self.run_bar("--stats-json", str(stats_path))
        data = json.loads(stats_path.read_text())
        self.assertEqual(data["ticks_read"], 16)
        self.assertEqual(data["bars"], 9)
        self.assertEqual(data["dropped_late"], 2)
        self.assertEqual(data["late_mode"], "strict")

    def test_stdout_is_csv_when_output_is_a_dash(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer), redirect_stderr(io.StringIO()):
            code = main(["bar", "--input", str(FIXTURE), "--out", "-"])
        self.assertEqual(code, 0)
        rows = list(csv.reader(io.StringIO(buffer.getvalue())))
        self.assertEqual(rows[0][0], "session")
        self.assertEqual(len(rows), 10)

    def test_stdin_input(self):
        result = subprocess.run(
            [sys.executable, "-m", "rollup", "bar", "--input", "-", "--quiet"],
            input=FIXTURE.read_text(),
            cwd=_util.ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 10)


class BenchAndDemoTests(unittest.TestCase):
    def test_benchmark_reports_measured_numbers(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["benchmark", "--rows", "3000", "--days", "1"])
        self.assertEqual(code, 0)
        text = buffer.getvalue()
        self.assertIn("ticks_per_second", text)
        self.assertIn("wall_seconds", text)
        self.assertIn("rows             3000", text)
        rate = [line for line in text.splitlines() if line.startswith("ticks_per_second")][0]
        self.assertGreater(float(rate.split()[-1]), 0)

    def test_demo_shows_both_modes(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["demo"])
        self.assertEqual(code, 0)
        text = buffer.getvalue()
        self.assertIn("== strict ==", text)
        self.assertIn("== repair ==", text)
        self.assertIn("100.141667", text)
        self.assertIn("revised bars:", text)

    def test_demo_single_mode(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(["demo", "--late", "repair", "--interval", "5m"])
        self.assertEqual(code, 0)
        text = buffer.getvalue()
        self.assertIn("== repair ==", text)
        self.assertNotIn("== strict ==", text)
        self.assertIn("13:05:00", text)


if __name__ == "__main__":
    unittest.main()
