"""Late ticks: strict drops them, repair reopens the bar and flags it."""

import unittest

import _util
from rollup.sessions import SessionSpec


class StrictModeTests(unittest.TestCase):
    spec = SessionSpec.parse()
    ticks = [
        ("2026-03-02T09:30:10", 100.0, 10),
        ("2026-03-02T09:31:05", 101.0, 10),
        ("2026-03-02T09:30:20", 999.0, 500),  # late, belongs to a closed bar
    ]

    def test_late_tick_is_dropped_and_counted(self):
        engine, bars = _util.run(self.spec, self.ticks, mode="strict")
        self.assertEqual(engine.stats.dropped_late, 1)
        self.assertEqual(engine.stats.repaired, 0)
        self.assertEqual(engine.stats.ticks_used, 2)
        self.assertEqual(engine.stats.ticks_read, 3)

    def test_dropped_tick_does_not_touch_the_bar(self):
        _engine, bars = _util.run(self.spec, self.ticks, mode="strict")
        first = bars[0]
        self.assertEqual(first.volume, 10)
        self.assertEqual(first.high, 100.0)
        self.assertEqual(first.trades, 1)
        self.assertFalse(first.revised)

    def test_bar_closes_before_the_late_tick_is_seen(self):
        engine = _util.RollupEngine(self.spec, "strict")
        first, second, third = self.ticks
        self.assertEqual(engine.feed(_util.ts(first[0]), first[1], first[2]), [])
        closed = engine.feed(_util.ts(second[0]), second[1], second[2])
        self.assertEqual(len(closed), 1)  # 09:30 bar was already handed out
        self.assertEqual(engine.feed(_util.ts(third[0]), third[1], third[2]), [])


class RepairModeTests(unittest.TestCase):
    spec = SessionSpec.parse()

    def test_late_tick_reopens_bar_and_flags_it(self):
        engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:30:10", 100.0, 100),
                ("2026-03-02T09:30:40", 100.4, 100),
                ("2026-03-02T09:31:05", 101.0, 100),
                ("2026-03-02T09:30:20", 99.5, 50),
            ],
            mode="repair",
        )
        self.assertEqual(engine.stats.dropped_late, 0)
        self.assertEqual(engine.stats.repaired, 1)
        self.assertEqual(engine.stats.bars_revised, 1)
        bar = bars[0]
        self.assertTrue(bar.revised)
        self.assertEqual(bar.volume, 250)
        self.assertEqual(bar.low, 99.5)
        self.assertEqual(bar.trades, 3)

    def test_open_and_close_follow_trade_time_not_arrival(self):
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:30:10", 100.0, 10),
                ("2026-03-02T09:30:40", 100.4, 10),
                ("2026-03-02T09:31:05", 101.0, 10),
                ("2026-03-02T09:30:05", 99.0, 10),   # earlier than the open
                ("2026-03-02T09:30:55", 102.0, 10),  # later than the close
            ],
            mode="repair",
        )
        bar = bars[0]
        self.assertEqual(bar.open, 99.0)
        self.assertEqual(bar.close, 102.0)
        self.assertEqual(bar.high, 102.0)
        self.assertEqual(bar.low, 99.0)
        self.assertEqual(bar.trades, 4)

    def test_repair_keeps_output_in_time_order(self):
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:30:10", 100.0, 1),
                ("2026-03-02T09:32:10", 100.0, 1),
                ("2026-03-02T09:33:10", 100.0, 1),
                ("2026-03-02T09:31:10", 100.0, 1),  # fills the empty 09:31 bucket
            ],
            mode="repair",
        )
        starts = [b.start.strftime("%H:%M") for b in bars]
        self.assertEqual(starts, sorted(starts))
        self.assertEqual(starts, ["09:30", "09:31", "09:32", "09:33"])

    def test_tick_into_previously_empty_bucket_is_not_marked_revised(self):
        engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:32:10", 100.0, 1),
                ("2026-03-02T09:31:10", 100.0, 1),
            ],
            mode="repair",
        )
        self.assertEqual(engine.stats.repaired, 0)
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars[0].start.strftime("%H:%M"), "09:31")
        self.assertFalse(bars[0].revised)

    def test_previous_session_cannot_be_repaired(self):
        engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T11:29:10", 100.0, 10),
                ("2026-03-02T13:00:10", 101.0, 10),
                ("2026-03-02T11:29:50", 102.0, 10),  # morning already flushed
            ],
            mode="repair",
        )
        self.assertEqual(engine.stats.dropped_late, 1)
        self.assertEqual(engine.stats.repaired, 0)
        self.assertEqual(engine.stats.bars_revised, 0)
        self.assertEqual([b.volume for b in bars], [10, 10])

    def test_repair_holds_only_the_current_session(self):
        engine = _util.RollupEngine(self.spec, "repair")
        engine.feed(_util.ts("2026-03-02T09:30:10"), 100.0, 1)
        engine.feed(_util.ts("2026-03-02T09:31:10"), 100.0, 1)
        self.assertEqual(len(engine._open), 2)  # same session, still open
        engine.feed(_util.ts("2026-03-02T13:00:10"), 100.0, 1)
        self.assertEqual(len(engine._open), 1)  # morning flushed


if __name__ == "__main__":
    unittest.main()
