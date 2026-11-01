import unittest

import _util  # noqa: F401  (puts the repo root on sys.path)
from rollup.sessions import SessionError, SessionSpec, clock_text


class ParseTests(unittest.TestCase):
    def test_default_sessions(self):
        spec = SessionSpec.parse()
        self.assertEqual([w.label for w in spec.windows], ["09:30-11:30", "13:00-15:00"])
        self.assertEqual(spec.buckets_per_window(), (120, 120))

    def test_bucket_counts_per_interval(self):
        self.assertEqual(SessionSpec.parse(interval="5m").buckets_per_window(), (24, 24))
        self.assertEqual(SessionSpec.parse(interval="15m").buckets_per_window(), (8, 8))

    def test_custom_windows_and_seconds(self):
        spec = SessionSpec.parse("09:30:00-09:33:00", "1m")
        self.assertEqual(spec.buckets_per_window(), (3,))
        self.assertEqual(spec.windows[0].duration, 180)

    def test_unknown_interval(self):
        with self.assertRaises(SessionError):
            SessionSpec.parse(interval="7m")

    def test_window_without_dash(self):
        with self.assertRaises(SessionError):
            SessionSpec.parse("09:30")

    def test_window_ends_before_start(self):
        with self.assertRaises(SessionError):
            SessionSpec.parse("11:30-09:30")

    def test_overlapping_windows(self):
        with self.assertRaises(SessionError):
            SessionSpec.parse("09:30-12:00,11:00-15:00")

    def test_touching_windows_rejected(self):
        with self.assertRaises(SessionError):
            SessionSpec.parse("09:30-11:30,11:30-15:00")

    def test_clock_text(self):
        self.assertEqual(clock_text(9 * 3600 + 30 * 60), "09:30")
        self.assertEqual(clock_text(9 * 3600 + 30 * 60 + 5), "09:30:05")


class BucketTests(unittest.TestCase):
    spec = SessionSpec.parse()

    def bucket(self, text, spec=None):
        full = (spec or self.spec).bucket(_util.ts(text))
        return None if full is None else full[1:]

    def test_day_is_part_of_the_key(self):
        key = self.spec.bucket(_util.ts("2026-03-02T09:30:00"))
        self.assertEqual(key[0], _util.ts("2026-03-02T00:00:00").date().toordinal())

    def test_before_open_is_closed(self):
        self.assertIsNone(self.bucket("2026-03-02T09:29:59.999"))

    def test_exact_open_belongs_to_first_bar(self):
        self.assertEqual(self.bucket("2026-03-02T09:30:00"), (0, 0))

    def test_before_minute_end(self):
        self.assertEqual(self.bucket("2026-03-02T09:30:59.999"), (0, 0))

    def test_exact_minute_end_moves_on(self):
        self.assertEqual(self.bucket("2026-03-02T09:31:00"), (0, 1))

    def test_exact_close_belongs_to_last_bar(self):
        self.assertEqual(self.bucket("2026-03-02T11:30:00"), (0, 119))

    def test_after_close_is_closed(self):
        self.assertIsNone(self.bucket("2026-03-02T11:30:00.001"))

    def test_lunch_is_closed(self):
        self.assertIsNone(self.bucket("2026-03-02T12:00:00"))

    def test_afternoon_open(self):
        self.assertEqual(self.bucket("2026-03-02T13:00:00"), (1, 0))

    def test_afternoon_close(self):
        self.assertEqual(self.bucket("2026-03-02T15:00:00"), (1, 119))
        self.assertIsNone(self.bucket("2026-03-02T15:00:01"))

    def test_five_minute_boundaries(self):
        spec = SessionSpec.parse(interval="5m")
        self.assertEqual(self.bucket("2026-03-02T09:34:59.999", spec), (0, 0))
        self.assertEqual(self.bucket("2026-03-02T09:35:00", spec), (0, 1))
        self.assertEqual(self.bucket("2026-03-02T09:39:59", spec), (0, 1))

    def test_fifteen_minute_boundaries(self):
        spec = SessionSpec.parse(interval="15m")
        self.assertEqual(self.bucket("2026-03-02T09:44:59", spec), (0, 0))
        self.assertEqual(self.bucket("2026-03-02T09:45:00", spec), (0, 1))
        self.assertEqual(self.bucket("2026-03-02T11:29:59", spec), (0, 7))


class BarBoundsTests(unittest.TestCase):
    def test_trailing_bar_is_clipped_to_window_end(self):
        spec = SessionSpec.parse("09:30-09:37", "5m")
        self.assertEqual(spec.buckets_per_window(), (2,))
        day = _util.ts("2026-03-02T09:36:00").date().toordinal()
        start, end = spec.bar_bounds(_util.ts("2026-03-02T09:36:00"), (day, 0, 1))
        self.assertEqual(start.isoformat(), "2026-03-02T09:35:00")
        self.assertEqual(end.isoformat(), "2026-03-02T09:37:00")

    def test_normal_bar_bounds(self):
        spec = SessionSpec.parse()
        day = _util.ts("2026-03-02T09:31:15").date().toordinal()
        start, end = spec.bar_bounds(_util.ts("2026-03-02T09:31:15"), (day, 0, 1))
        self.assertEqual(start.isoformat(), "2026-03-02T09:31:00")
        self.assertEqual(end.isoformat(), "2026-03-02T09:32:00")

    def test_hourly_interval(self):
        spec = SessionSpec.parse(interval="1h")
        self.assertEqual(spec.buckets_per_window(), (2, 2))


if __name__ == "__main__":
    unittest.main()
