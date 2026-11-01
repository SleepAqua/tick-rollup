"""Nothing may be merged across the lunch break or across a session edge."""

import unittest

import _util
from rollup.sessions import SessionSpec


class MiddayGapTests(unittest.TestCase):
    spec = SessionSpec.parse()

    def test_morning_and_afternoon_stay_separate(self):
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T11:29:00", 100.0, 10),
                ("2026-03-02T11:29:59", 101.0, 10),
                ("2026-03-02T13:00:00", 105.0, 20),
            ],
        )
        self.assertEqual(len(bars), 2)
        morning, afternoon = bars
        self.assertEqual(morning.session, "09:30-11:30")
        self.assertEqual(afternoon.session, "13:00-15:00")
        self.assertEqual(morning.volume, 20)
        self.assertEqual(afternoon.open, 105.0)
        self.assertEqual(afternoon.volume, 20)
        self.assertEqual(afternoon.start.strftime("%H:%M"), "13:00")

    def test_lunch_tick_is_dropped_not_attached(self):
        engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T11:29:00", 100.0, 10),
                ("2026-03-02T12:15:00", 500.0, 10_000),
                ("2026-03-02T13:00:00", 105.0, 20),
            ],
        )
        self.assertEqual(engine.stats.dropped_out_of_session, 1)
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].volume, 10)
        self.assertEqual(bars[0].high, 100.0)
        self.assertEqual(bars[1].high, 105.0)
        self.assertEqual(bars[1].volume, 20)

    def test_afternoon_bar_numbers_restart(self):
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T11:29:30", 100.0, 1),
                ("2026-03-02T13:00:30", 100.0, 1),
                ("2026-03-02T13:01:30", 100.0, 1),
            ],
        )
        self.assertEqual(
            [b.start.strftime("%H:%M") for b in bars], ["11:29", "13:00", "13:01"]
        )

    def test_multi_day_file_does_not_join_days(self):
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T14:59:00", 100.0, 10),
                ("2026-03-03T09:30:00", 200.0, 10),
            ],
        )
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].start.day, 2)
        self.assertEqual(bars[1].start.day, 3)
        self.assertEqual(bars[1].open, 200.0)


if __name__ == "__main__":
    unittest.main()
