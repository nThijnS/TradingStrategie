"""Strategie-selectie per markt (learning/selector.py + learning/lab.choose/write_learned)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from learning import lab, selector  # noqa: E402
from storage import paths  # noqa: E402

NOW = pd.Timestamp("2026-11-03 18:00", tz="America/New_York")
CUT = pd.Timestamp("2026-05-07", tz="UTC")


def trades(mean_train, mean_val, n_train=120, n_val=80, sd=1.0, seed=1, start="2025-06-01"):
    """Trades met vaste gemiddelden in train en validatie (ruis met vaste seed)."""
    rs = np.random.RandomState(seed)
    out = []
    t0 = pd.Timestamp(start, tz="UTC")
    for i in range(n_train):
        out.append(dict(t=t0 + pd.Timedelta(days=i * 330 / n_train), R=mean_train + sd * rs.standard_normal()))
    for i in range(n_val):
        out.append(dict(t=CUT + pd.Timedelta(days=1 + i * 175 / n_val), R=mean_val + sd * rs.standard_normal()))
    for x in out:
        x["R15"] = x["R"] - 0.01
    return out


def family(sid, by_variant, trials=10, keep=None):
    return selector.evaluate_family("TEST", sid, by_variant, CUT, trials, keep)


class Gate(unittest.TestCase):
    def test_too_little_data_never_active(self):
        f = family("trend", {"a": trades(0.5, 0.5, n_train=20, n_val=15)})
        self.assertFalse(f["poort"]["geslaagd"])
        self.assertTrue(any(r.startswith("P1") for r in f["poort"]["redenen"]))

    def test_strong_consistent_edge_passes(self):
        f = family("trend", {"a": trades(0.6, 0.6, sd=0.8)})
        self.assertTrue(f["poort"]["geslaagd"], f["poort"]["redenen"])

    def test_overfit_train_only_fails(self):
        f = family("trend", {"a": trades(0.6, -0.3)})
        self.assertFalse(f["poort"]["geslaagd"])
        self.assertTrue(any(r.startswith("P2") for r in f["poort"]["redenen"]))

    def test_more_trials_is_stricter(self):
        by = {"a": trades(0.25, 0.25, seed=3)}
        few, many = family("trend", by, trials=2), family("trend", by, trials=5000)
        self.assertGreater(few["poort"]["dsr"], many["poort"]["dsr"])

    def test_variant_chosen_on_train_only(self):
        # variant b is beter in de validatie, maar slechter in train: de selector mag b niet kiezen
        by = {"a": trades(0.4, 0.1, seed=4), "b": trades(0.1, 0.9, seed=5)}
        self.assertEqual(family("trend", by)["variant"], "a")

    def test_bootstrap_reproducible(self):
        by = {"a": trades(0.3, 0.3, seed=6)}
        self.assertEqual(family("trend", by)["poort"], family("trend", by)["poort"])


class Decide(unittest.TestCase):
    def decide(self, fams, prev=None, by=None):
        return selector.decide("TEST", fams, prev, NOW.to_pydatetime(), lambda sid, k: (by or {}).get((sid, k), []))

    def test_active_when_passing(self):
        d = self.decide([family("trend", {"a": trades(0.6, 0.6, sd=0.8)}), family("ict", {"v": trades(0.2, -0.4)}, )])
        self.assertEqual((d["status"], d["strategie"]), ("actief", "trend"))

    def test_research_when_promising_but_unproven(self):
        d = self.decide([family("momentum", {"a": trades(0.15, 0.2, n_val=25, sd=0.3, seed=8)}), family("trend", {"a": trades(-0.2, -0.1)})])
        self.assertEqual((d["status"], d["strategie"]), ("onderzoek", None))
        self.assertEqual(d["onderzoek"]["strategie"], "momentum")

    def test_pause_when_nothing(self):
        d = self.decide([family("trend", {"a": trades(-0.2, -0.1)}), family("ict", {"v": trades(0.3, -0.5)})])
        self.assertEqual((d["status"], d["strategie"], d["onderzoek"]), ("pauze", None, None))

    def test_forward_results_switch_off_and_block(self):
        good = trades(0.6, 0.6, sd=0.8)
        prev = dict(status="actief", strategie="trend", variant_key="a", sinds="2026-09-01", titel="Trend")
        fwd = [dict(t=pd.Timestamp("2026-09-02", tz="UTC") + pd.Timedelta(days=i), R=-0.3) for i in range(25)]
        d = self.decide([family("trend", {"a": good}, keep="a")], prev, by={("trend", "a"): fwd})
        self.assertNotEqual(d["status"], "actief")
        self.assertIn("trend", d["geblokkeerd"])
        # en de volgende dag mag trend niet terugkomen, ook al haalt hij de poort
        d2 = self.decide([family("trend", {"a": good})], dict(d, titel="x"))
        self.assertNotEqual(d2["strategie"], "trend")

    def test_switch_margin_keeps_current(self):
        a, b = family("trend", {"a": trades(0.6, 0.6, sd=0.8, seed=9)}), family("momentum", {"a": trades(0.6, 0.62, sd=0.8, seed=10)})
        prev = dict(status="actief", strategie="trend", variant_key="a", sinds="2026-10-01", titel="Trend")
        d = self.decide([a, b], prev)
        if b["poort"]["ondergrens"] < a["poort"]["ondergrens"] + selector.MARGIN:
            self.assertEqual(d["strategie"], "trend")
            self.assertEqual(d["sinds"], "2026-10-01")


class OneStrategyPerMarket(unittest.TestCase):
    """learned.json: ICT staat alleen aan waar de selector ICT als actieve strategie koos."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.p = mock.patch.multiple(paths, LEARNED=self.d / "learned.json", LEREN_HISTORY=self.d / "h.json")
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def res(self, name, status, sid, vkey):
        ict = dict(id="ict", variant=dict(variant="basis · TP 1.0 · NY AM · bias geen"),
                   poort=dict(validatie=dict(n=40, gem=0.1, win=0.5, totaal=4.0), ondergrens=0.02))
        return dict(naam=name, strategieen=[ict], keuze=dict(status=status, strategie=sid, variant_key=vkey, sinds="2026-11-03",
                                                                reden_vandaag="test"))

    def test_ict_only_on_when_selected(self):
        app = lab.write_learned([
            self.res("NQ", "actief", "ict", "strenger · TP 1.5 · NY AM · bias 1H mee"),
            self.res("EURUSD", "actief", "trend", '{"tp": 2.0}'),
            self.res("GOUD", "onderzoek", None, None)], now=NOW.to_pydatetime())["markten"]
        self.assertTrue(app["NQ"]["actief"])
        self.assertEqual(app["NQ"]["cfg"], dict(disp_pct=0.7, disp_atr=1.5, tp_mode="R", tp_r=1.5))
        self.assertEqual(app["NQ"]["need_bias_b"], True)
        self.assertFalse(app["EURUSD"]["actief"])        # trend gekozen: ICT mag niet ook nog melden/handelen
        self.assertFalse(app["GOUD"]["actief"])
        self.assertEqual(app["EURUSD"]["selectie"]["strategie"], "trend")
        self.assertEqual(json.loads((self.d / "h.json").read_text())[-1]["keuze"]["NQ"]["actief"], True)

    def test_app_reads_it(self):
        lab.write_learned([self.res("NQ", "pauze", None, None)], now=NOW.to_pydatetime())
        from core import config
        config.apply_settings(self.d / "geen-config.json", self.d / "learned.json")
        nq = config.CFG["markets"][0]
        self.assertFalse(nq["actief"])
        config.apply_settings(self.d / "geen-config.json", self.d / "geen.json")


class LabChoose(unittest.TestCase):
    """choose() op een complete markt: schrijft status, poort per strategie en versies."""

    def test_choose_end_to_end(self):
        by = {"trend": {json.dumps(dict(tp=2.0)): trades(0.6, 0.6, sd=0.8)},
              "momentum": {json.dumps(dict(er=0.3)): trades(-0.1, -0.2)}}
        for v in by.values():
            for t in v.values():
                for x in t:
                    x.update(kant="LONG", entry=100.0, stop=99.0, tp=102.0)
        res = dict(naam="TEST", strategieen=[dict(id=k, titel=lab.STRATS[k]["titel"], nieuw={}) for k in by])
        versions = {}
        entry, why, rejected = lab.choose(res, dict(by=by, cut=CUT, trials=4), versions, now=NOW.to_pydatetime())
        self.assertEqual((entry["status"], entry["strategie"]), ("actief", "trend"))
        self.assertEqual(res["keuze"]["titel"], "Trend volgen")
        self.assertIn("poort", res["strategieen"][0])
        self.assertEqual(len(versions["TEST"]), 1)
        lab.choose(res, dict(by=by, cut=CUT, trials=4), versions, now=NOW.to_pydatetime())
        self.assertEqual(len(versions["TEST"]), 1)          # zelfde keuze: geen nieuwe versie


if __name__ == "__main__":
    unittest.main()
