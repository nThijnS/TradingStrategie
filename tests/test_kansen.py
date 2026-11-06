"""Kansenonderzoek (research/kansen.py): kosten per trade, geen vooruitkijken en de besluitregel bovenop de poort."""
import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from research import kansen as k
from strategies import lab as strat


def bars(c):
    idx = pd.date_range("2026-01-05", periods=len(c), freq="1h", tz="UTC")
    c = np.asarray(c, float)
    return pd.DataFrame(dict(Open=c, High=c + 0.5, Low=c - 0.5, Close=c, spread=0.1), index=idx)


class Kosten(unittest.TestCase):
    def tr(self, side=1):
        return SimpleNamespace(entry_time=pd.Timestamp("2026-01-05 10:00", tz="UTC"), exit_time=pd.Timestamp("2026-01-07 10:00", tz="UTC"), side=side, risk=2.0, entry=100.0)

    def test_spread_and_slippage(self):
        self.assertAlmostEqual(k.kosten_r(self.tr(), 0.4, None)[0], 0.3)

    def test_financing_counts_nights_and_only_paid_rate(self):
        fee = dict(longRate=-0.05, shortRate=0.02)
        self.assertAlmostEqual(k.kosten_r(self.tr(1), 0.4, fee)[1], 2 * 0.05 / 100 * 100 / 2)
        self.assertEqual(k.kosten_r(self.tr(-1), 0.4, fee)[1], 0.0)


class Vooruitkijken(unittest.TestCase):
    def test_signal_ignores_the_future(self):
        rng = np.random.default_rng(1)
        c = 100 + rng.normal(0, 0.3, 1200).cumsum()
        a, b = bars(c), bars(np.concatenate([c[:1000], c[1000:] * 2]))
        for name in ("swing_pullback", "swing_trend", "swing_breakout"):
            v = dict(sm=2.0, tp=3.0, n=20)
            ua, da, _, _ = k.signalen(name, strat.indicators(a), v)
            ub, db, _, _ = k.signalen(name, strat.indicators(b), v)
            self.assertTrue(ua.iloc[:1000].equals(ub.iloc[:1000]), name)
            self.assertTrue(da.iloc[:1000].equals(db.iloc[:1000]), name)

    def test_4h_has_utc_boundaries_and_keeps_extremes(self):
        h = k.naar_4h(bars(list(range(100, 112))))
        self.assertEqual(h.index[0].hour % 4, 0)
        self.assertEqual(h["High"].iloc[0], 103.5)


class Handel(unittest.TestCase):
    def rij(self, c):
        return strat.indicators(c)

    def test_wide_spread_refused(self):
        rng = np.random.default_rng(2)
        df = bars(100 + rng.normal(0, 0.4, 1500).cumsum())
        X = strat.indicators(df)
        ex = k.engine.Exits(max_bars=12, gap_hours=6)
        v = dict(sm=2.0, tp=3.0, n=20)
        ok = k.handel("A", "swing_breakout", "x", X, v, df["spread"], None, ex)
        duur = k.handel("A", "swing_breakout", "x", X, v, df["spread"] * 1000, None, ex)
        self.assertGreater(len(ok), 0)
        self.assertEqual(duur, [])
        self.assertEqual(len({x["id"] for x in ok}), len(ok))
        self.assertTrue(all(x["R"] < x["bruto"] and x["R15"] < x["R"] for x in ok))


class Besluit(unittest.TestCase):
    mid = pd.Timestamp("2026-08-01", tz="UTC")

    def va(self, e1, e2):
        return [dict(t=self.mid - pd.Timedelta(days=1), R15=e1), dict(t=self.mid + pd.Timedelta(days=1), R15=e2)]

    def test_needs_gate_scan_and_both_halves(self):
        self.assertTrue(k.toelaatbaar(dict(geslaagd=True), self.va(0.1, 0.1), self.mid, 0.96))
        self.assertFalse(k.toelaatbaar(dict(geslaagd=False), self.va(0.1, 0.1), self.mid, 0.96))
        self.assertFalse(k.toelaatbaar(dict(geslaagd=True), self.va(0.1, 0.1), self.mid, 0.90))
        self.assertFalse(k.toelaatbaar(dict(geslaagd=True), self.va(-0.1, 0.1), self.mid, 0.96))
        self.assertFalse(k.toelaatbaar(dict(geslaagd=True), self.va(0.1, -0.1), self.mid, 0.96))


if __name__ == "__main__":
    unittest.main()
