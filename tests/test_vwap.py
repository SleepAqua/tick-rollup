"""VWAP against numbers worked out on paper."""

import unittest

import _util
from rollup.sessions import SessionSpec


class VwapTests(unittest.TestCase):
    spec = SessionSpec.parse()

    def test_hand_computed_vwap(self):
        # 100.00*200 = 20000, 100.10*50 = 5005, 99.90*200 = 19980
        # turnover 44985, volume 450, vwap 99.9666...
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:30:01", 100.00, 200),
                ("2026-03-02T09:30:31", 100.10, 50),
                ("2026-03-02T09:30:59", 99.90, 200),
            ],
        )
        bar = bars[0]
        self.assertEqual(bar.volume, 450)
        self.assertAlmostEqual(bar.turnover, 44985.0, places=9)
        self.assertAlmostEqual(bar.vwap, 44985.0 / 450, places=12)
        self.assertEqual(f"{bar.vwap:.6f}", "99.966667")
        self.assertEqual((bar.open, bar.high, bar.low, bar.close), (100.0, 100.1, 99.9, 99.9))

    def test_vwap_is_turnover_over_volume_by_construction(self):
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:30:01", 10.0, 3),
                ("2026-03-02T09:30:02", 20.0, 1),
                ("2026-03-02T09:30:03", 30.0, 7),
            ],
        )
        bar = bars[0]
        self.assertAlmostEqual(bar.vwap, bar.turnover / bar.volume, places=12)
        self.assertAlmostEqual(bar.vwap, (30 + 20 + 210) / 11, places=12)

    def test_zero_volume_bar_has_no_vwap(self):
        _engine, bars = _util.run(self.spec, [("2026-03-02T09:30:01", 100.0, 0)])
        bar = bars[0]
        self.assertEqual(bar.volume, 0)
        self.assertIsNone(bar.vwap)
        self.assertEqual(bar.trades, 1)
        self.assertEqual(bar.row()[10], "")  # empty field, not a number

    def test_vwap_of_a_single_trade_is_that_price(self):
        _engine, bars = _util.run(self.spec, [("2026-03-02T09:30:01", 42.25, 7)])
        self.assertAlmostEqual(bars[0].vwap, 42.25, places=12)

    def test_vwap_ignores_other_bars(self):
        _engine, bars = _util.run(
            self.spec,
            [
                ("2026-03-02T09:30:01", 100.0, 100),
                ("2026-03-02T09:31:01", 200.0, 100),
            ],
        )
        self.assertAlmostEqual(bars[0].vwap, 100.0, places=12)
        self.assertAlmostEqual(bars[1].vwap, 200.0, places=12)


if __name__ == "__main__":
    unittest.main()
