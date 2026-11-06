"""Onderzoek vijf-v1: signalen zonder vooruitkijken."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research import vijf  # noqa: E402


class Herbalancering(unittest.TestCase):
    def test_voorbeeld_uit_paper_en_reset(self):
        t = pd.date_range("2026-01-01", periods=3, freq="B")
        es, zn = pd.Series([100.0, 110.0, 110.0], t), pd.Series([100.0, 100.0, 100.0], t)
        s = vijf.drempelsignaal(es, zn)
        self.assertAlmostEqual(s.iloc[0], 0.0226, places=3)    # 10% stijging: 60% -> 62,26%
        self.assertAlmostEqual(s.iloc[1], 0.0, places=9)       # boven 2 punt: terug op 60%

    def test_onder_drempel_geen_reset(self):
        t = pd.date_range("2026-01-01", periods=3, freq="B")
        s = vijf.drempelsignaal(pd.Series([100.0, 105.0, 105.0], t), pd.Series([100.0] * 3, t))
        self.assertAlmostEqual(s.iloc[0], s.iloc[1], places=9)


class Cot(unittest.TestCase):
    def cot(self):
        t = pd.date_range("2024-01-02", periods=60, freq="7D")
        return pd.DataFrame({"CFTC Contract Market Code": "X", "As of Date in Form YYYY-MM-DD": t.strftime("%Y-%m-%d"),
                             "Noncommercial Positions-Long (All)": 30.0, "Noncommercial Positions-Short (All)": 10.0})

    def test_waarde_lag_en_teken(self):
        s = vijf.spec_druk(self.cot(), "X")
        self.assertAlmostEqual(s.iloc[0], 0.5)
        self.assertEqual(s.index[0], pd.Timestamp("2024-01-02") + pd.Timedelta(weeks=51, days=3))
        self.assertAlmostEqual(vijf.spec_druk(self.cot(), "X", -1).iloc[0], -0.5)


class GeenVooruitkijken(unittest.TestCase):
    def test_grote_dag_hangt_niet_af_van_later(self):
        r = pd.Series(np.random.RandomState(1).standard_normal(200))
        a = vijf.grote_dag(r)
        b = vijf.grote_dag(r.iloc[:150])
        self.assertTrue(a.iloc[:150].equals(b))

    def test_funding_hangt_niet_af_van_later(self):
        t = pd.date_range("2024-01-01", periods=3 * 800, freq="8h", tz="UTC")
        f = pd.DataFrame(dict(f=np.random.RandomState(2).standard_normal(len(t))), index=t)
        a, b = vijf.funding_aan(f), vijf.funding_aan(f.iloc[:2400])
        c = b.index[:-2]
        self.assertTrue(a.reindex(c).equals(b.reindex(c)))


class Kosten(unittest.TestCase):
    def test_rij_spread_grens_en_rente(self):
        class T:
            entry_time = pd.Timestamp("2026-01-05 10:00", tz="America/New_York")
            exit_time = pd.Timestamp("2026-01-06 10:00", tz="America/New_York")
            risk, entry, gross_r, side = 10.0, 1000.0, 1.0, 1
        x = vijf.rij(T, 1.0, dict(longRate=-0.1, shortRate=0.1))
        self.assertAlmostEqual(x["R"], 1.0 - 0.15 - 0.1)
        self.assertIsNone(vijf.rij(T, 3.0, None))
        T.side = -1
        self.assertAlmostEqual(vijf.rij(T, 1.0, dict(longRate=-0.1, shortRate=0.1))["R"], 0.85)   # ontvangen rente telt niet


if __name__ == "__main__":
    unittest.main()
