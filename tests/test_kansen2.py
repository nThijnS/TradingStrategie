import unittest

import numpy as np
import pandas as pd

from research import kansen2 as K2


def candles(start="2026-01-05 00:00", n=24 * 40, step=0.0):
    t = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    c = 100 + step * np.arange(n)
    return pd.DataFrame(dict(Open=c, High=c + 0.5, Low=c - 0.5, Close=c, spread=0.01), index=t)


class Tijdvak(unittest.TestCase):
    def test_lange_periode_verdient_stijging_zonder_toekomstkennis(self):
        df = candles(step=0.01)
        tr = K2.tijdvak("X", "europa_open", df, None, 2, 6)
        self.assertTrue(tr)
        x = tr[0]
        self.assertEqual(x["t"].tz_convert(K2.TZ).hour, 2)
        self.assertEqual(x["t_uit"].tz_convert(K2.TZ).hour, 6)
        self.assertAlmostEqual(x["bruto"], 0.04 / x["risk"], places=6)
        # Het eerste signaal komt pas na 20 dagen, omdat de ATR alleen eerdere dagen gebruikt.
        self.assertGreaterEqual((x["t"] - df.index[0]).days, 20)

    def test_nacht_slaat_vrijdag_over(self):
        tr = K2.tijdvak("X", "nacht", candles(n=24 * 60), None, 16, 9, volgende_dag=True, geen_vrijdag=True)
        self.assertTrue(tr)
        self.assertFalse(any(x["t"].tz_convert(K2.TZ).weekday() == 4 for x in tr))
        self.assertFalse(any((x["t_uit"] - x["t"]) > pd.Timedelta(hours=18) for x in tr))


class Rondgang(unittest.TestCase):
    def test_stop_geeft_min_een_r_en_gap_is_slechter(self):
        df = candles(n=10)
        df.iloc[2, df.columns.get_loc("Low")] = 98.0
        t = K2.rondgang("X", "f", df, 1, 5, 1, 1.0, None)
        self.assertAlmostEqual(t["bruto"], -1.0)
        df = candles(n=10)
        df.iloc[2, df.columns.get_loc("Open")] = 97.0
        df.iloc[2, df.columns.get_loc("Low")] = 96.5
        t = K2.rondgang("X", "f", df, 1, 5, 1, 1.0, None)
        self.assertAlmostEqual(t["bruto"], -3.0)

    def test_financiering_en_te_hoge_spread(self):
        df = candles(n=40)
        t = K2.rondgang("X", "f", df, 1, 30, 1, 1.0, dict(longRate=-0.05, shortRate=0.01))
        self.assertLess(t["R"], t["bruto"])
        self.assertLessEqual(t["R15"], t["R"])
        df["spread"] = 0.3
        self.assertIsNone(K2.rondgang("X", "f", df, 1, 30, 1, 1.0, None))


class Trend(unittest.TestCase):
    def test_trend_volgt_en_kost_rente(self):
        idx = pd.date_range("2020-01-01", periods=300, freq="1D", tz="UTC")
        c = np.r_[np.full(100, 100.0), 100 + np.arange(200) * 1.0]
        d = pd.DataFrame(dict(Open=c, High=c + 0.5, Low=c - 0.5, Close=c), index=idx)
        d["High"] = d["High"].where(d.index > idx[60], d["High"] + 0.0)
        tr = K2.trend_trades(d.iloc[:-1], 0.05, dict(longRate=-0.02, shortRate=0.0), "X") + K2.trend_trades(pd.concat([d, d.iloc[::-1].set_axis(d.index + pd.Timedelta(days=300))]), 0.05, None, "Y")
        self.assertTrue(any(x["kant"] == 1 for x in tr))
        self.assertTrue(all(x["R15"] <= x["R"] <= x["bruto"] for x in tr))


if __name__ == "__main__":
    unittest.main()
