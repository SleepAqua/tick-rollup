"""Reading ticks: header handling, column order, error reporting."""

import io
import tempfile
import unittest
from pathlib import Path

import _util
from rollup.reader import TickFormatError, iter_ticks, parse_timestamp, read_path


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def ticks(self, text):
        return list(iter_ticks(io.StringIO(text)))

    def test_standard_header(self):
        rows = self.ticks(
            "timestamp,price,size,side\n"
            "2026-03-02T09:30:00,100.10,200,B\n"
        )
        self.assertEqual(len(rows), 1)
        lineno, stamp, price, size, side = rows[0]
        self.assertEqual(lineno, 2)
        self.assertEqual(stamp.hour, 9)
        self.assertEqual(price, 100.10)
        self.assertEqual(size, 200.0)
        self.assertEqual(side, "B")

    def test_column_order_does_not_matter(self):
        rows = self.ticks(
            "size,side,price,timestamp,extra\n"
            "100,S,99.5,2026-03-02T09:30:00,ignored\n"
        )
        self.assertEqual(rows[0][2], 99.5)
        self.assertEqual(rows[0][3], 100.0)

    def test_side_is_optional(self):
        rows = self.ticks("timestamp,price,size\n2026-03-02T09:30:00,1.5,2\n")
        self.assertEqual(rows[0][4], "")

    def test_blank_lines_are_skipped(self):
        rows = self.ticks(
            "timestamp,price,size,side\n"
            "\n"
            "2026-03-02T09:30:00,1.5,2,B\n"
            "\n"
        )
        self.assertEqual(len(rows), 1)

    def test_missing_column_is_named_in_the_error(self):
        with self.assertRaises(TickFormatError) as caught:
            self.ticks("timestamp,price\n2026-03-02T09:30:00,1.0\n")
        self.assertIn("size", str(caught.exception))

    def test_bad_price_reports_the_line_number(self):
        with self.assertRaises(TickFormatError) as caught:
            self.ticks(
                "timestamp,price,size,side\n"
                "2026-03-02T09:30:00,1.0,2,B\n"
                "2026-03-02T09:31:00,oops,2,B\n"
            )
        self.assertEqual(caught.exception.lineno, 3)
        self.assertIn("line 3", str(caught.exception))

    def test_bad_timestamp(self):
        with self.assertRaises(TickFormatError):
            self.ticks("timestamp,price,size,side\n02/03/2026 09:30,1.0,2,B\n")

    def test_zulu_suffix_is_accepted(self):
        stamp = parse_timestamp("2026-03-02T09:30:00Z")
        self.assertIsNotNone(stamp.tzinfo)
        self.assertEqual(stamp.hour, 9)

    def test_empty_file_is_an_error(self):
        with self.assertRaises(TickFormatError):
            self.ticks("")

    def test_header_only_file_yields_no_ticks(self):
        self.assertEqual(self.ticks("timestamp,price,size,side\n"), [])

    def test_read_path_streams_a_file(self):
        path = _util.write_ticks(
            self.dir / "ticks.csv",
            [("2026-03-02T09:30:00", 1.0, 2, "B"), ("2026-03-02T09:31:00", 1.0, 2, "B")],
        )
        self.assertEqual(len(list(read_path(path))), 2)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            list(read_path(self.dir / "nope.csv"))


if __name__ == "__main__":
    unittest.main()
