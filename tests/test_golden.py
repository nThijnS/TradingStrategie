"""Regressie tegen de OUDE code (tests/golden/oude_code.json, vastgelegd vóór de refactor op vaste synthetische data).

Moet exact gelijk blijven: de ICT-detectie (setups, entries, weigeringen), de lab-simulatie, de onderzoek-simulatie,
walk-forward, Donchian/TSMOM en de leren-score. De ICT-uitkomsten (stop/TP) zijn bewust veranderd door de centrale
engine; die verschillen staan in docs/refactor/3_engine_vergelijking.md en worden in test_engine.py getest.
"""
import json
import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import fixtures  # noqa: E402
import onderzoek  # noqa: E402
from core.config import CFG  # noqa: E402
from learning import ict as leren  # noqa: E402
from research import validation  # noqa: E402
from strategies import lab  # noqa: E402
from strategies.ict_tjr import analyse  # noqa: E402

G = json.loads((ROOT / "tests" / "golden" / "oude_code.json").read_text())
SETUP_KEYS = ["time", "side", "grade", "score", "good", "entry", "stop", "tp", "rr", "dol", "sweep", "sweep_t", "mss_t",
              "bias_a", "bias_b", "checks", "entry_hit", "missed"]
VARIANTS = {"standaard": {}, "basis_alle": dict(disp_pct=0.6, disp_atr=1.2, max_per_day=6),
            "dol_bias": dict(tp_mode="DOL", need_bias_b=True), "nc_smt": dict(no_close=True, need_smt=True, entry_mode="Rand")}


def j(x):
    if isinstance(x, pd.Timestamp):
        return x.isoformat()
    if isinstance(x, dict):
        return {k: j(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [j(v) for v in x]
    if hasattr(x, "item"):
        x = x.item()
    if isinstance(x, float) and x != x:
        return None
    return x


class Same(unittest.TestCase):
    def assertSameish(self, a, b, path=""):
        if isinstance(b, float) or isinstance(a, float):
            self.assertAlmostEqual(float(a), float(b), places=9, msg=path)
        elif isinstance(b, dict):
            self.assertEqual(sorted(a), sorted(b), path)
            for k in b:
                self.assertSameish(a[k], b[k], f"{path}.{k}")
        elif isinstance(b, list):
            self.assertEqual(len(a), len(b), path)
            for i, (x, y) in enumerate(zip(a, b)):
                self.assertSameish(x, y, f"{path}[{i}]")
        else:
            self.assertEqual(a, b, path)


class ICTDetection(Same):
    @classmethod
    def setUpClass(cls):
        m1, o1 = fixtures.minute_bars()
        cls.m5, cls.o5 = fixtures.to5(m1), fixtures.to5(o1)

    def test_setups_entries_refusals_identical(self):
        for name, over in VARIANTS.items():
            refs = []
            setups, entries = analyse(self.m5, self.o5, dict(CFG, **over), refs)
            g = G["ict"][name]
            self.assertGreater(len(g["setups"]) + len(g["refusals"]), 0)
            self.assertSameish([j({k: s.get(k) for k in SETUP_KEYS}) for s in setups], g["setups"], name)
            self.assertEqual([e["time"].isoformat() for e in entries], g["entries"], name)
            self.assertSameish([j({k: f[k] for k in ("time", "side", "reason", "sweep", "sweep_t", "bias_a", "bias_b")})
                                for f in refs], g["refusals"], name)


class LabSimulation(Same):
    def test_lab_and_onderzoek_identical(self):
        X = lab.indicators(fixtures.hourly_bars())
        for key, g in G["lab"].items():
            sid, v = key.split("|")
            up, dn, sd, tg = lab.signals(sid, X, json.loads(v))
            self.assertSameish(j(lab.simulate(X, up, dn, sd, tg, 0.0008, 0.065)), g["lab"], key)
            self.assertSameish(j(onderzoek.simulate(X, up, dn, sd, tg, 0.0008, 0.065, lab.MAX_BARS)), g["onderzoek"], key)

    def test_walk_forward_identical(self):
        X = lab.indicators(fixtures.hourly_bars())
        by = {k: lab.simulate(X, *lab.signals("trend", X, json.loads(k.split("|")[1])), 0.0008, 0.065)
              for k in G["lab"] if k.startswith("trend")}
        oos, picks = validation.walk_forward(by, X.index[0], X.index[-1])
        self.assertSameish(j(oos), G["walk_forward"]["oos"])
        self.assertEqual(picks, G["walk_forward"]["picks"])

    def test_donchian_tsmom_identical(self):
        h = fixtures.hourly_bars()
        d = h.resample("1D").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
        Xd = onderzoek.daily_X(d)
        m = dict(kosten=0.0001, soort="index")
        self.assertSameish(j(onderzoek.donchian(Xd, m, 20, 10)), G["classic"]["donchian"])
        self.assertSameish(j(onderzoek.tsmom(Xd, m, (5, 21, 63))), G["classic"]["tsmom"])


class LearningScore(Same):
    def test_score_identical(self):
        now = pd.Timestamp("2026-05-01 12:00", tz="America/New_York").to_pydatetime()
        rows = list(G["leren_mem"].values())
        for v in leren.variants():
            self.assertSameish(leren.score(rows, v, now), G["leren_score"][leren.vid(v)], leren.vid(v))


if __name__ == "__main__":
    unittest.main()
