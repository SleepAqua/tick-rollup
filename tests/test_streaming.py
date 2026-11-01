"""The engine must not grow with the file."""

import unittest

import _util
from rollup.sessions import SessionSpec


def stamp(day: int, minute: int) -> str:
    """Minute 0..239 of a trading day, mapped into the two sessions."""
    start = 9 * 3600 + 30 * 60 if minute < 120 else 13 * 3600
    seconds = start + (minute % 120) * 60 + 5
    return f"2026-03-{day:02d}T{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}:05"


class MemoryTests(unittest.TestCase):
    spec = SessionSpec.parse()

    def test_open_bars_never_exceed_one_session(self):
        engine = _util.RollupEngine(self.spec, "repair")
        peak = 0
        for day in (2, 3, 4):
            for minute in range(240):
                for _ in range(5):
                    engine.feed(_util.ts(stamp(day, minute)), 100.0, 10)
                peak = max(peak, len(engine._open))
        self.assertLessEqual(peak, 120)
        self.assertEqual(engine.stats.bars, 3 * 240 - len(engine._open))

    def test_strict_mode_holds_almost_nothing(self):
        engine = _util.RollupEngine(self.spec, "strict")
        for minute in range(240):
            for _ in range(5):
                engine.feed(_util.ts(stamp(2, minute)), 100.0, 10)
        self.assertLessEqual(len(engine._open), 1)

    def test_every_tick_is_accounted_for(self):
        ticks = [
            ("2026-03-02T08:59:00", 100.0, 10),   # before the open
            ("2026-03-02T09:30:10", 100.0, 10),
            ("2026-03-02T12:00:00", 100.0, 10),   # lunch
            ("2026-03-02T09:31:10", 101.0, 10),
            ("2026-03-02T09:30:20", 102.0, 10),   # late
            ("2026-03-02T13:00:10", 103.0, 10),
        ]
        for mode in ("strict", "repair"):
            engine, _bars = _util.run(self.spec, ticks, mode=mode)
            stats = engine.stats
            self.assertEqual(
                stats.ticks_read,
                stats.ticks_used + stats.dropped_out_of_session + stats.dropped_late,
                msg=mode,
            )

    def test_bar_count_matches_session_arithmetic(self):
        engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:30:00", 100.0, 1),
                ("2026-03-02T15:00:00", 100.0, 1),
            ],
        )
        self.assertEqual(len(bars), 2)
        self.assertEqual(engine.stats.bars, 2)
        self.assertEqual(bars[0].key[1:], (0, 0))
        self.assertEqual(bars[1].key[1:], (1, 119))


if __name__ == "__main__":
    unittest.main()
