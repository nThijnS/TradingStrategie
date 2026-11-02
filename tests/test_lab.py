"""Strategielab en onderzoek: instap na het signaal, stop eerst bij twijfel, financiering en de statistiek."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import onderzoek  # noqa: E402
import strategielab as lab  # noqa: E402


def frame(rows, start="2026-11-02 10:00"):
    idx = pd.date_range(start, periods=len(rows), freq="1h", tz="UTC")
    X = pd.DataFrame(rows, columns=["o", "h", "l", "c"], index=idx)
    X["mid"], X["trend"], X["vol"] = X["c"], "Zijwaarts", "Normale volatiliteit"
    return X


class Simulate(unittest.TestCase):
    def test_entry_on_next_open_and_stop_first(self):
        X = frame([(100, 101, 99, 100), (102, 103, 101, 102), (102, 110, 95, 100), (100, 100, 100, 100)])
        up = pd.Series([True, False, False, False], index=X.index)
        dn = pd.Series(False, index=X.index)
        t = lab.simulate(X, up, dn, pd.Series(5.0, index=X.index), ("R", 1.0), 0.0)
        self.assertEqual(t[0]["entry"], 102)          # open van de candle NA het signaal
        self.assertEqual(t[0]["bruto"], -1.0)         # stop (97) en doel (107) in dezelfde candle: stop eerst

    def test_financing_charged_over_rollover(self):
        X = frame([(100, 100, 100, 100)] + [(100, 100.5, 99.5, 100)] * 12, start="2026-11-02 15:00")
        up = pd.Series([True] + [False] * 12, index=X.index)
        dn = pd.Series(False, index=X.index)
        no = lab.simulate(X, up, dn, pd.Series(5.0, index=X.index), ("R", 3.0), 0.0)[0]["R"]
        yes = lab.simulate(X, up, dn, pd.Series(5.0, index=X.index), ("R", 3.0), 0.0, fin=0.065)[0]["R"]
        self.assertAlmostEqual(no - yes, 0.065 / 365 * 100 / 5)

    def test_nights(self):
        T = pd.Timestamp
        self.assertEqual(lab.nights(T("2026-11-02 10:00", tz="UTC"), T("2026-11-02 21:00", tz="UTC")), 0)
        self.assertEqual(lab.nights(T("2026-11-02 20:00", tz="UTC"), T("2026-11-03 01:00", tz="UTC")), 1)


class Stats(unittest.TestCase):
    def test_dsr_penalises_many_trials(self):
        rng = np.random.default_rng(1)
        R = rng.normal(0.1, 1.0, 300)
        self.assertGreater(onderzoek.deflated_sharpe(R, 2), onderzoek.deflated_sharpe(R, 500))

    def test_pbo_detects_pure_noise(self):
        rng = np.random.default_rng(2)
        p = onderzoek.pbo_cscv(rng.normal(0, 1, (40, 50)), S=8)
        self.assertTrue(0.3 < p < 0.7)                 # ruis: de beste in-sample is out-of-sample willekeurig

    def test_pbo_low_for_real_edge(self):
        rng = np.random.default_rng(3)
        M = rng.normal(0, 1, (40, 20))
        M[:, 0] += 1.5
        self.assertLess(onderzoek.pbo_cscv(M, S=8), 0.1)

    def test_bootstrap_interval_contains_mean(self):
        rng = np.random.default_rng(4)
        t0 = pd.Timestamp("2025-01-01", tz="UTC")
        trades = [dict(t=t0 + pd.Timedelta(days=int(i)), R=float(r)) for i, r in enumerate(rng.normal(0.2, 1, 300))]
        lo, _, hi = onderzoek.block_bootstrap(trades)
        self.assertLess(lo, np.mean([x["R"] for x in trades]))
        self.assertGreater(hi, np.mean([x["R"] for x in trades]))


if __name__ == "__main__":
    unittest.main()
