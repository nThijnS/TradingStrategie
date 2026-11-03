"""De centrale trade-simulatie (backtesting/engine.py): instap, volgorde stop/doel, tijdsluiting, kosten."""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtesting import engine  # noqa: E402
from backtesting.engine import Costs, Exits  # noqa: E402
from backtesting.ict import outcome, trade  # noqa: E402
from strategies.ict_tjr import target_price  # noqa: E402


def bars(rows, start="2026-03-02 09:30", freq="5min", tz="America/New_York"):
    idx = pd.date_range(start, periods=len(rows), freq=freq, tz=tz)
    return engine.Bars(pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx))


class Entry(unittest.TestCase):
    def test_limit_fills_on_touch(self):
        B = bars([(105, 106, 104, 105), (104, 104.5, 99.5, 101), (101, 103, 100, 102)])
        tr = engine.simulate(B, 1, 100, 95, 110, 0, "LIMIT")
        self.assertEqual(tr.entry_i, 1)
        self.assertEqual(tr.entry, 100)

    def test_limit_not_filled_returns_none(self):
        B = bars([(105, 106, 104, 105), (105, 106, 103, 104)])
        self.assertIsNone(engine.simulate(B, 1, 100, 95, 110, 0, "LIMIT"))
        self.assertIsNone(engine.simulate(bars([(100, 101, 99, 100)] * 3), 1, 100, 99, 105, 0, "LIMIT", fill_until_i=-1))

    def test_market_enters_at_open(self):
        B = bars([(100, 101, 99, 100), (102, 103, 101, 102)])
        tr = engine.simulate(B, 1, 102, 97, 107, 1, "MARKET")
        self.assertEqual((tr.entry_i, tr.entry), (1, 102))

    def test_non_positive_risk(self):
        B = bars([(100, 101, 99, 100)])
        self.assertIsNone(engine.simulate(B, 1, 100, 100, 105, 0, "MARKET"))
        self.assertIsNone(engine.simulate(B, -1, 100, 99, 95, 0, "MARKET"))


class Order(unittest.TestCase):
    def test_stop_first_when_both_in_one_bar(self):
        B = bars([(100, 100, 100, 100), (100, 111, 94, 100)])
        tr = engine.simulate(B, 1, 100, 95, 110, 0, "MARKET")
        self.assertEqual((tr.reason, tr.gross_r), ("stop", -1.0))

    def test_tp_in_fill_bar_not_counted_by_default(self):
        B = bars([(101, 106, 99, 104), (104, 104.5, 103, 104)])   # vult op 100 en raakt 105 in dezelfde candle
        self.assertEqual(engine.simulate(B, 1, 100, 95, 105, 0, "LIMIT").reason, "open")
        tr = engine.simulate(B, 1, 100, 95, 105, 0, "LIMIT", Exits(tp_on_fill_bar=True))
        self.assertEqual((tr.reason, tr.gross_r), ("tp", 1.0))

    def test_stop_in_fill_bar_counts(self):
        B = bars([(101, 101, 94, 95)])
        self.assertEqual(engine.simulate(B, 1, 100, 95, 105, 0, "LIMIT").reason, "stop")

    def test_gap_through_stop_exits_at_open(self):
        B = bars([(100, 101, 99.5, 100), (93, 94, 92, 93)])
        tr = engine.simulate(B, 1, 100, 95, 110, 0, "MARKET")
        self.assertEqual((tr.reason, tr.exit), ("stop", 93))
        self.assertAlmostEqual(tr.gross_r, -1.4)

    def test_short_mirror(self):
        B = bars([(100, 100.5, 99, 100), (100, 100.2, 89, 90)])
        tr = engine.simulate(B, -1, 100, 105, 90, 0, "MARKET")
        self.assertEqual((tr.reason, tr.gross_r), ("tp", 2.0))

    def test_breakeven(self):
        B = bars([(100, 106, 99.5, 105), (105, 105, 99, 100)])
        tr = engine.simulate(B, 1, 100, 95, 115, 0, "MARKET", Exits(be_at=1.0))
        self.assertEqual((tr.reason, tr.gross_r), ("stop", 0.0))

    def test_exit_signal_on_next_open(self):
        B = bars([(100, 101, 99, 100), (100, 101, 99, 100), (102, 103, 101, 102)])
        ex = [False, True, False]
        tr = engine.simulate(B, 1, 100, 90, None, 0, "MARKET", exit_long=ex)
        self.assertEqual((tr.reason, tr.exit, tr.exit_i), ("signal", 102, 2))


class Time(unittest.TestCase):
    def test_max_hours_closes_on_last_bar_inside(self):
        B = bars([(100, 101, 99, 100)] * 80)                     # 5m-candles vanaf 09:30
        tr = engine.simulate(B, 1, 100, 90, 120, 0, "MARKET", Exits(max_hours=5))
        self.assertEqual(tr.reason, "time")
        self.assertEqual(tr.exit_time, pd.Timestamp("2026-03-02 14:25", tz="America/New_York"))   # eindigt 14:30

    def test_close_at_same_day(self):
        B = bars([(100, 101, 99, 100)] * 100)
        tr = engine.simulate(B, 1, 100, 90, 120, 0, "MARKET", Exits(close_at="16:00"))
        self.assertEqual(tr.exit_time, pd.Timestamp("2026-03-02 15:55", tz="America/New_York"))

    def test_max_bars_counts_entry_bar(self):
        B = bars([(100, 101, 99, 100)] * 20, freq="1h", tz="UTC")
        self.assertEqual(engine.simulate(B, 1, 100, 90, 120, 1, "MARKET", Exits(max_bars=12)).bars, 12)

    def test_gap_closes_on_previous_close(self):
        idx = pd.DatetimeIndex(["2026-03-06 20:00", "2026-03-06 21:00", "2026-03-09 01:00"], tz="UTC")
        B = engine.Bars(pd.DataFrame([(100, 101, 99, 100), (100, 101, 99, 100.5), (90, 91, 89, 90)],
                                     columns=["Open", "High", "Low", "Close"], index=idx))
        tr = engine.simulate(B, 1, 100, 95, 110, 0, "MARKET", Exits(gap_hours=6))
        self.assertEqual((tr.reason, tr.exit), ("gap", 100.5))

    def test_open_at_end_of_data(self):
        B = bars([(100, 101, 99, 100)] * 3)
        self.assertEqual(engine.simulate(B, 1, 100, 90, 120, 0, "MARKET").reason, "open")


class CostModel(unittest.TestCase):
    def test_price_frac_slippage(self):
        B = bars([(100, 100, 100, 100), (100, 111, 99.5, 110)])
        tr = engine.simulate(B, 1, 100, 95, 110, 0, "MARKET", costs=Costs(price=1.0, frac=0.001, slippage_r=0.02))
        self.assertAlmostEqual(tr.gross_r, 2.0)
        self.assertAlmostEqual(tr.cost_r, (1.0 + 0.1) / 5)
        self.assertAlmostEqual(tr.net_r, 2.0 - 0.22 - 0.02)

    def test_financing_per_rollover(self):
        B = bars([(100, 100.5, 99.5, 100)] * 30, start="2026-03-02 18:00", freq="1h", tz="UTC")
        tr = engine.simulate(B, 1, 100, 95, 120, 0, "MARKET", Exits(max_bars=10), Costs(financing=0.065))
        self.assertEqual(tr.nights, 1)
        self.assertAlmostEqual(tr.fin_r, 0.065 / 365 * 100 / 5)

    def test_rollovers(self):
        T = pd.Timestamp
        self.assertEqual(engine.rollovers(T("2026-11-02 10:00", tz="UTC"), T("2026-11-02 21:00", tz="UTC")), 0)
        self.assertEqual(engine.rollovers(T("2026-11-02 20:00", tz="UTC"), T("2026-11-04 01:00", tz="UTC")), 2)


class ICTAdapter(unittest.TestCase):
    S = dict(side="LONG", entry=100.0, stop=95.0, tp=105.0, rr=1.0, dol=None,
             entry_hit=pd.Timestamp("2026-03-02 09:35", tz="America/New_York"), time=pd.Timestamp("2026-03-02 09:30", tz="America/New_York"))

    def test_dol_falls_back_to_app_tp_r(self):
        self.assertEqual(target_price(self.S, "DOL", 1.0), 105.0)          # zoals de app (cfg tp_r), niet 2R
        self.assertEqual(target_price(dict(self.S, dol=112.0), "DOL", 1.0), 112.0)
        self.assertEqual(target_price(self.S, "1.5"), 107.5)

    def test_outcome_mapping_and_costs(self):
        B = bars([(101, 101, 100.5, 101), (101, 101, 99.8, 100), (100, 106, 100, 105.5)])
        self.assertEqual(outcome(B, self.S), ("TP", 1.0))
        self.assertEqual(outcome(B, dict(self.S, entry_hit=None)), ("geen entry", 0.0))
        tr = trade(B, self.S, "2.0", costs=Costs(price=1.0))
        self.assertEqual(tr.reason, "open")
        self.assertAlmostEqual(trade(B, self.S, costs=Costs(price=1.0)).net_r, 1.0 - 0.2)


if __name__ == "__main__":
    unittest.main()
