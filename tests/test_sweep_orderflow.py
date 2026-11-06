"""Onderzoek sweep-orderflow-v1: detectie zonder vooruitkijken, spiegeling en flowmaten."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtesting import engine  # noqa: E402
from research import sweep_orderflow as so  # noqa: E402


def bars(rows, start="2026-03-03 08:00"):
    idx = pd.date_range(start, periods=len(rows), freq="5min", tz="America/New_York")
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx, dtype=float)


def history():
    """Vorige dag rond 100-110, daarna rustig tot de sessie van 09:30."""
    day = [(105, 110, 100, 105)] * 12
    prev = bars(day, "2026-03-02 09:00")
    calm = [(104, 105, 103, 104)] * 18         # 08:00 - 09:25
    return prev, calm


def scenario(mirror=False):
    prev, calm = history()
    sweep = (104, 111, 103.5, 104.5)           # 09:30: boven PDH 110, sluit terug
    wait = (104.5, 105, 104, 104.5)            # 09:35
    brk = (104.5, 122, 104.4, 121.8)           # 09:40: bullish displacement boven het hoogste punt sinds de sweep
    after = [(121.8, 123, 121, 122)] * 6
    df = pd.concat([prev, bars(calm + [sweep, wait, brk] + after)])
    if mirror:
        df = pd.DataFrame({"Open": 200 - df["Open"], "High": 200 - df["Low"], "Low": 200 - df["High"], "Close": 200 - df["Close"]}, index=df.index)
    return df


class FailedSweep(unittest.TestCase):
    def test_long_after_failed_high_sweep(self):
        df = scenario()
        s = so.failed_sweeps(df, so.CFG_RUN, 0.25)
        self.assertEqual(len(s), 1)
        self.assertEqual(s[0]["side"], 1)
        self.assertEqual(df.index[s[0]["i"]].strftime("%H:%M"), "09:40")
        self.assertAlmostEqual(s[0]["stop"], 103.5 - 1.0)

    def test_mirror_gives_short(self):
        s = so.failed_sweeps(scenario(True), so.CFG_RUN, 0.25)
        self.assertEqual([x["side"] for x in s], [-1])
        self.assertAlmostEqual(s[0]["stop"], 96.5 + 1.0)

    def test_sweep_that_closes_beyond_is_no_failed_sweep(self):
        df = scenario()
        i = df.index.get_loc(pd.Timestamp("2026-03-03 09:30", tz="America/New_York"))
        df.iloc[i, df.columns.get_loc("Close")] = 110.5
        self.assertEqual(so.failed_sweeps(df, so.CFG_RUN, 0.25), [])

    def test_no_lookahead(self):
        df = scenario()
        full = so.failed_sweeps(df, so.CFG_RUN, 0.25)
        cut = so.failed_sweeps(df.iloc[:full[0]["i"] + 1], so.CFG_RUN, 0.25)
        self.assertEqual(cut, full)
        self.assertEqual(so.failed_sweeps(df.iloc[:full[0]["i"]], so.CFG_RUN, 0.25), [])

    def test_market_entry_on_next_open_with_engine(self):
        df = scenario()
        s = so.failed_sweeps(df, so.CFG_RUN, 0.25)
        t = so.market_trades(df, engine.Bars(df, bar=pd.Timedelta(minutes=5)), s, 1.0, engine.Costs())
        # instap 121,8; stop 102,5; doel 141,1 niet geraakt, data op: trade loopt nog en telt dus niet mee
        self.assertEqual(t, [])


class Flow(unittest.TestCase):
    def test_delta_and_relvol(self):
        df = scenario().assign(Volume=100.0, TakerBuy=50.0)
        df.iloc[-1, df.columns.get_loc("TakerBuy")] = 80.0
        df.iloc[-1, df.columns.get_loc("Volume")] = 200.0
        dr, rv = so.flow_columns(df)
        self.assertAlmostEqual(dr[-1], -0.2)
        self.assertAlmostEqual(rv[-1], 2.0)
        self.assertTrue(np.isnan(rv[5]))

    def test_cvd_reversal_needs_flow_against_sweep(self):
        df = scenario().assign(Volume=100.0, TakerBuy=40.0)    # verkopers overheersen: cvd20 < 0
        s = so.cvd_reversals(df, so.CFG_RUN, 0.25)
        self.assertEqual([x["side"] for x in s], [-1])
        self.assertAlmostEqual(s[0]["stop"], 111 + 1.0)
        df = df.assign(TakerBuy=60.0)                          # kopers overheersen: geen divergentie
        self.assertEqual(so.cvd_reversals(df, so.CFG_RUN, 0.25), [])


if __name__ == "__main__":
    unittest.main()
