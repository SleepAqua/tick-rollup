"""The generator has to be reproducible, otherwise the benchmark means nothing."""

import filecmp
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import _util
from rollup.synth import write_ticks


class SynthTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_same_seed_same_bytes(self):
        first = write_ticks(self.dir / "a.csv", rows=2000, seed=11, days=1)
        second = write_ticks(self.dir / "b.csv", rows=2000, seed=11, days=1)
        self.assertTrue(filecmp.cmp(first["path"], second["path"], shallow=False))
        self.assertEqual(first["rows"], second["rows"])

    def test_different_seed_different_bytes(self):
        write_ticks(self.dir / "a.csv", rows=2000, seed=11, days=1)
        write_ticks(self.dir / "b.csv", rows=2000, seed=12, days=1)
        self.assertFalse(
            filecmp.cmp(self.dir / "a.csv", self.dir / "b.csv", shallow=False)
        )

    def test_row_count_is_respected(self):
        summary = write_ticks(self.dir / "small.csv", rows=1234, seed=3, days=2)
        self.assertEqual(summary["rows"], 1234)

    def test_generated_file_rolls_up(self):
        path = self.dir / "small.csv"
        write_ticks(path, rows=5000, seed=5, days=1)
        code = subprocess.run(
            [sys.executable, "-m", "rollup", "bar", "--input", str(path),
             "--out", str(self.dir / "bars.csv"), "--quiet"],
            cwd=_util.ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(code.returncode, 0, code.stderr)
        rows = (self.dir / "bars.csv").read_text().splitlines()
        self.assertGreater(len(rows), 10)

    def test_tool_script_writes_the_file(self):
        target = self.dir / "ticks.csv"
        result = subprocess.run(
            [sys.executable, str(_util.ROOT / "tools" / "make_ticks.py"),
             "--out", str(target), "--rows", "500", "--seed", "2", "--days", "1"],
            cwd=_util.ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(target.read_text().splitlines()), 501)


if __name__ == "__main__":
    unittest.main()
