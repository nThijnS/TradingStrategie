"""Kandidaat-generator (learning/generator.py): alleen train, kosten, budget, geen versoepeling van de poort."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import fixtures  # noqa: E402
from learning import generator, lab, selector  # noqa: E402

CUT = pd.Timestamp("2026-05-07", tz="UTC")
BASE = [dict(tp=2.0), dict(tp=3.0)]


def trades(m_train, m_val, cost15=0.0, n_train=120, n_val=60, seed=0):
    rs = np.random.RandomState(seed)
    t0 = pd.Timestamp("2025-06-01", tz="UTC")
    out = [dict(t=t0 + pd.Timedelta(days=i * 330 / n_train), R=m_train + 0.5 * rs.standard_normal()) for i in range(n_train)]
    out += [dict(t=CUT + pd.Timedelta(days=1 + i * 170 / n_val), R=m_val + 0.5 * rs.standard_normal()) for i in range(n_val)]
    for x in out:
        x["R15"] = x["R"] - cost15
    return out


def run(reg, sim, day="2026-11-03", by=None):
    by = by if by is not None else {json.dumps(v): trades(0.1, 0.1, seed=i) for i, v in enumerate(BASE)}
    return generator.generate(reg, "TEST", "trend", BASE, by, CUT, day, sim), by


class Proposals(unittest.TestCase):
    def test_neighbors_one_step_inside_grid(self):
        for sid, space in generator.SPACE.items():
            base = {k: v[len(v) // 2] for k, v in space.items()}
            for n, rule in generator.neighbors(sid, base):
                diff = [k for k in space if n[k] != base[k]]
                self.assertEqual(len(diff), 1, rule)
                g = space[diff[0]]
                self.assertEqual(abs(g.index(n[diff[0]]) - g.index(base[diff[0]])), 1)

    def test_base_variants_unchanged_by_defaults(self):
        # een basisvariant met de standaardwaarden is dezelfde strategie (zelfde signalen en stop)
        X = lab.indicators(fixtures.hourly_bars(2000))
        a = lab.signals("momentum", X, dict(er=0.3))
        b = lab.signals("momentum", X, generator.full("momentum", dict(er=0.3)))
        self.assertTrue(a[0].equals(b[0]) and a[2].equals(b[2]) and a[3] == b[3])


class TrainOnly(unittest.TestCase):
    def test_validation_data_never_influences_generation(self):
        # zelfde train, totaal andere validatie: exact dezelfde voorstellen, zeef en pool
        def sim_a(v):
            return trades(0.2 if v["tp"] > 2 else -0.1, 5.0, seed=int(v["tp"] * 10 + v["sm"]))

        def sim_b(v):
            return trades(0.2 if v["tp"] > 2 else -0.1, -5.0, seed=int(v["tp"] * 10 + v["sm"]))
        by_a = {json.dumps(v): trades(0.1, 3.0, seed=i) for i, v in enumerate(BASE)}
        by_b = {json.dumps(v): trades(0.1, -3.0, seed=i) for i, v in enumerate(BASE)}
        ra, rb = {}, {}
        ea, _ = run(ra, sim_a, by=by_a)
        eb, _ = run(rb, sim_b, by=by_b)
        self.assertEqual(ea, eb)
        strip = lambda r: {k: {kk: vv for kk, vv in c.items()} for k, c in r["markten"]["TEST"]["families"]["trend"].items()}
        self.assertEqual(strip(ra), strip(rb))

    def test_screen_uses_train_not_validation(self):
        reg = {}
        ev, by = run(reg, lambda v: trades(-0.3, 2.0))      # slecht op train, top in validatie
        self.assertTrue(ev and all(e["uitkomst"] == "afgewezen op train" for e in ev))
        reg = {}
        ev, by = run(reg, lambda v: trades(0.3, -2.0))      # goed op train, slecht in validatie: mag de pool in
        self.assertTrue(ev and all(e["uitkomst"] == "in pool" for e in ev))
        # ... en de poort houdt hem dan tegen
        f = selector.evaluate_family("TEST", "trend", {ev[0]["variant"]: by[ev[0]["variant"]]}, CUT, 20)
        self.assertFalse(f["poort"]["geslaagd"])

    def test_costs_count(self):
        reg = {}
        ev, _ = run(reg, lambda v: trades(0.05, 0.05, cost15=0.25))  # bruto positief, na 1,5x kosten negatief
        self.assertTrue(all(e["uitkomst"] == "afgewezen op train" for e in ev))
        self.assertIn("kosten", ev[0]["reden"])


class Budget(unittest.TestCase):
    def test_budget_no_repeats_and_trials_only_grow(self):
        reg, seen, counts = {}, set(), []
        for d in range(6):
            ev, _ = run(reg, lambda v: trades(-0.1, 0.0), day=f"2026-11-{d + 3:02d}")
            self.assertLessEqual(len(ev), generator.BUDGET)
            for e in ev:
                self.assertNotIn(e["variant"], seen)
                seen.add(e["variant"])
            counts.append(generator.trials(reg, "TEST", 10))
        self.assertEqual(counts, sorted(counts))
        self.assertGreater(counts[-1], counts[0])
        self.assertEqual(len(reg["log"]), len(seen))

    def test_budget_is_per_day_even_when_rerun(self):
        reg = {}
        for _ in range(3):
            run(reg, lambda v: trades(-0.1, 0.0), day="2026-11-03")
        self.assertEqual(reg["markten"]["TEST"]["proeven"], generator.BUDGET)

    def test_more_candidates_make_gate_stricter(self):
        reg = {}
        by = {"a": trades(0.15, 0.15, seed=3)}
        before = selector.evaluate_family("TEST", "trend", by, CUT, generator.trials(reg, "TEST", 10))["poort"]["dsr"]
        for d in range(5):
            run(reg, lambda v: trades(-0.1, 0.0), day=f"2026-12-{d + 1:02d}")
        after = selector.evaluate_family("TEST", "trend", by, CUT, generator.trials(reg, "TEST", 10))["poort"]["dsr"]
        self.assertLess(after, before)

    def test_pool_is_capped_and_protects_current_choice(self):
        reg = {}
        by = {json.dumps(v): trades(0.1, 0.1, seed=i) for i, v in enumerate(BASE)}
        first = None
        for d in range(8):
            ev, by = run(reg, lambda v: trades(0.05 + 0.01 * v["tp"] + 0.001 * v["sm"], 0.0, seed=int(v["sm"] * 7)),
                         day=f"2026-11-{d + 3:02d}", by=by)
            first = first or next((e["variant"] for e in ev if e["uitkomst"] == "in pool"), None)
            generator.generate(reg, "TEST", "trend", BASE, by, CUT, f"2026-11-{d + 3:02d}x", lambda v: trades(0.0, 0.0),
                               protected={first})
        self.assertLessEqual(len(generator.pool(reg, "TEST", "trend")), generator.POOL_MAX)
        self.assertIn(first, generator.pool(reg, "TEST", "trend"))


class GateFrozen(unittest.TestCase):
    """De generator mag de poort niet versoepelen: de drempels liggen vast en worden hier bewaakt."""

    def test_gate_thresholds(self):
        self.assertEqual((selector.VAL_DAYS, selector.MIN_TRAIN, selector.MIN_VAL, selector.COST_X, selector.DSR_MIN,
                          selector.FWD_MIN, selector.COOLDOWN_DAYS, selector.MARGIN), (180, 30, 30, 1.5, 0.95, 20, 60, 0.05))
        self.assertFalse(any(hasattr(generator, n) for n in ("VAL_DAYS", "MIN_VAL", "DSR_MIN", "gate")))


class Integration(unittest.TestCase):
    def test_lab_market_with_generator(self):
        h = fixtures.hourly_bars(6000, start="2025-06-01")
        m = dict(naam="TEST", titel="Test", soort="index", symbool="X", kosten=0.0001)
        reg, versions = {}, {}
        res, ctx = lab.analyse_market(m, h, versions, reg, day="2026-03-01")
        self.assertTrue(res["kandidaten"]["vandaag"])
        self.assertEqual(res["kandidaten"]["proeven"], 10 + reg["markten"]["TEST"]["proeven"])
        for sid, by in ctx["by"].items():
            for k in by:
                self.assertTrue(k in {json.dumps(v) for v in lab.STRATS[sid]["varianten"]} or
                                reg["markten"]["TEST"]["families"][sid][k]["status"] == "in pool")
        entry, why, _ = lab.choose(res, ctx, versions, now=pd.Timestamp("2026-03-01 18:00", tz="America/New_York").to_pydatetime())
        if entry["status"] == "actief":           # alleen als hij de (ongewijzigde) poort haalt
            self.assertTrue(next(s for s in res["strategieen"] if s["id"] == entry["strategie"])["poort"]["geslaagd"])
        n1 = reg["markten"]["TEST"]["proeven"]
        lab.analyse_market(m, h, versions, reg, day="2026-03-02")
        self.assertGreaterEqual(reg["markten"]["TEST"]["proeven"], n1)


if __name__ == "__main__":
    unittest.main()
