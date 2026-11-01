"""Which bar a tick lands in, one interval at a time."""

import unittest

import _util
from rollup.sessions import SessionSpec


class OneMinuteTests(unittest.TestCase):
    spec = SessionSpec.parse()

    def test_tick_before_minute_end_stays_in_bar(self):
        engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:30:00", 100.0, 10),
                ("2026-03-02T09:30:59.999", 100.5, 10),
            ],
        )
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].start.isoformat(), "2026-03-02T09:30:00")
        self.assertEqual(bars[0].trades, 2)
        self.assertEqual(bars[0].close, 100.5)

    def test_tick_at_minute_end_opens_next_bar(self):
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:30:59", 100.0, 10),
                ("2026-03-02T09:31:00", 101.0, 20),
            ],
        )
        self.assertEqual([b.start.strftime("%H:%M") for b in bars], ["09:30", "09:31"])
        self.assertEqual(bars[0].volume, 10)
        self.assertEqual(bars[1].open, 101.0)

    def test_bar_closes_when_watermark_passes_it(self):
        engine = _util.RollupEngine(self.spec, "strict")
        self.assertEqual(engine.feed(_util.ts("2026-03-02T09:30:10"), 100.0, 10), [])
        closed = engine.feed(_util.ts("2026-03-02T09:31:10"), 100.0, 10)
        self.assertEqual([b.start.strftime("%H:%M") for b in closed], ["09:30"])
        self.assertEqual(len(engine.close()), 1)

    def test_exact_session_close_joins_last_bar(self):
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T11:29:58", 100.0, 10),
                ("2026-03-02T11:30:00", 100.0, 5),
            ],
        )
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].start.strftime("%H:%M"), "11:29")
        self.assertEqual(bars[0].volume, 15)

    def test_empty_minutes_are_skipped_not_filled(self):
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:30:10", 100.0, 10),
                ("2026-03-02T09:33:10", 100.0, 10),
            ],
        )
        self.assertEqual([b.start.strftime("%H:%M") for b in bars], ["09:30", "09:33"])


class FiveMinuteTests(unittest.TestCase):
    spec = SessionSpec.parse(interval="5m")

    def test_last_tick_of_block_and_first_of_next(self):
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:30:00", 100.0, 1),
                ("2026-03-02T09:34:59.999", 101.0, 2),
                ("2026-03-02T09:35:00", 102.0, 3),
            ],
        )
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].start.strftime("%H:%M"), "09:30")
        self.assertEqual((bars[0].open, bars[0].close, bars[0].volume), (100.0, 101.0, 3))
        self.assertEqual(bars[1].start.strftime("%H:%M"), "09:35")
        self.assertEqual(bars[1].volume, 3)

    def test_block_count_per_session(self):
        _engine, bars = _util.run(
            self.spec,
            [("2026-03-02T09:30:00", 100.0, 1), ("2026-03-02T11:29:59", 100.0, 1)],
        )
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].start.strftime("%H:%M"), "09:30")
        self.assertEqual(bars[1].start.strftime("%H:%M"), "11:25")


class FifteenMinuteTests(unittest.TestCase):
    spec = SessionSpec.parse(interval="15m")

    def test_fifteen_minute_edges(self):
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:44:59", 100.0, 1),
                ("2026-03-02T09:45:00", 101.0, 1),
                ("2026-03-02T11:29:59", 102.0, 1),
            ],
        )
        self.assertEqual(
            [b.start.strftime("%H:%M") for b in bars], ["09:30", "09:45", "11:15"]
        )


if __name__ == "__main__":
    unittest.main()
