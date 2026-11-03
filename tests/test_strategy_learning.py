"""Strategieherkenning zonder look-ahead, de strategie-interface en de leerlogica (keuze, remmen, validatie)."""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import fixtures  # noqa: E402
from backtesting import engine  # noqa: E402
from core.config import CFG  # noqa: E402
from core.sessions import NY  # noqa: E402
from learning import ict as leren  # noqa: E402
from research import validation  # noqa: E402
from strategies import lab  # noqa: E402
from strategies.ict_tjr import ICTStrategy, analyse  # noqa: E402

CORE = ("time", "side", "entry", "stop", "tp", "score", "grade", "sweep", "bias_a", "bias_b", "checks")


class NoLookAhead(unittest.TestCase):
    """Een setup die op tijd T bekend is, mag niet veranderen als er data NA T bij komt."""

    @classmethod
    def setUpClass(cls):
        m1, o1 = fixtures.minute_bars()
        cls.m5, cls.o5 = fixtures.to5(m1), fixtures.to5(o1)

    def test_ict_setups_do_not_depend_on_future_bars(self):
        cfg = dict(CFG, disp_pct=0.6, disp_atr=1.2)
        full = analyse(self.m5, self.o5, cfg)[0]
        for cut in ("2026-03-20 11:00", "2026-04-02 10:15"):
            T = pd.Timestamp(cut, tz=NY)
            part = analyse(self.m5[self.m5.index < T], self.o5[self.o5.index < T], cfg)[0]
            a = [{k: s[k] for k in CORE} for s in full if s["time"] < T - pd.Timedelta(minutes=5)]
            b = [{k: s[k] for k in CORE} for s in part if s["time"] < T - pd.Timedelta(minutes=5)]
            self.assertGreater(len(a), 3)
            self.assertEqual(a, b, cut)

    def test_lab_signals_do_not_depend_on_future_bars(self):
        h = fixtures.hourly_bars()
        X, Xp = lab.indicators(h), lab.indicators(h.iloc[:2500])
        for sid, info in lab.STRATS.items():
            for v in info.get("varianten", []):
                up, dn, sd, _ = lab.signals(sid, X, v)
                up2, dn2, sd2, _ = lab.signals(sid, Xp, v)
                n = len(Xp)
                self.assertTrue(up.iloc[:n].fillna(False).equals(up2.fillna(False)), sid)
                self.assertTrue(dn.iloc[:n].fillna(False).equals(dn2.fillna(False)), sid)

    def test_lab_entry_after_signal(self):
        X = lab.indicators(fixtures.hourly_bars())
        up, dn, sd, tg = lab.signals("breakout", X, dict(n=24))
        for t in lab.simulate(X, up, dn, sd, tg, 0.0):
            self.assertEqual(t["entry"], X["o"].iloc[t["i"] + 1])     # open van de candle NA het signaal


class Interface(unittest.TestCase):
    def test_ict_strategy_signals_through_engine(self):
        m1, o1 = fixtures.minute_bars()
        m5, o5 = fixtures.to5(m1), fixtures.to5(o1)
        sigs = ICTStrategy(dict(disp_pct=0.6, disp_atr=1.2)).signals(m5, o5, target="1.0")
        self.assertTrue(sigs)
        B = engine.Bars(m5)
        trades = [engine.simulate_signal(B, s, engine.Exits(max_hours=5)) for s in sigs if s.fill_from is not None]
        for s, t in zip([s for s in sigs if s.fill_from is not None], trades):
            self.assertEqual(s.order, "LIMIT")
            self.assertGreaterEqual(t.entry_time, s.fill_from)
            self.assertIn(t.reason, ("stop", "tp", "time", "open"))


def rows(market="NQ", n=40, r=0.3, disp="basis", target="1.0", start="2026-01-05", sess="NY AM"):
    t0 = datetime.fromisoformat(start).replace(tzinfo=NY)
    return {f"{market}|{disp}|{target}|{i}": dict(markt=market, disp=disp, target=target, sess=sess, bias_mee=True,
                                                    t=(t0 + timedelta(days=i)).isoformat(), R=r if i % 3 else -0.5 * r, bron="test")
            for i in range(n)}


class Learning(unittest.TestCase):
    NOW = datetime(2026, 3, 1, 12, tzinfo=NY)

    def choose(self, mem, prev=None):
        import unittest.mock as mk
        with mk.patch.object(leren, "datetime", wraps=datetime) as d:
            d.now.return_value = self.NOW
            return leren.choose(mem, prev or {})

    def test_needs_min_trades(self):
        out, rep = self.choose(rows(n=leren.MIN_TRADES - 5))
        self.assertNotIn("NQ", out)
        self.assertIn("nog geen variant", rep["NQ"]["waarom"])

    def test_first_choice_and_pause_when_negative(self):
        out, _ = self.choose(rows(n=40, r=0.4))
        self.assertTrue(out["NQ"]["actief"])
        out, rep = self.choose(rows(n=40, r=-0.4))
        self.assertFalse(out["NQ"]["actief"])
        self.assertIn("pauze", rep["NQ"]["waarom"])

    def test_switch_margin(self):
        mem = {**rows(n=40, r=0.40), **rows(n=40, r=0.41, target="1.5")}
        cur = dict(disp="basis", target="1.0", sessies="NY AM", bias="geen")
        out, rep = self.choose(mem, {"NQ": dict(variant=cur, sinds="2026-01-01")})
        self.assertEqual(out["NQ"]["variant"], cur)                  # te klein verschil: blijven
        self.assertIn("minder dan", rep["NQ"]["waarom"])

    def test_learned_json_roundtrip(self):
        out, _ = self.choose(rows(n=40, r=0.4, target="DOL"))
        app = leren.to_app(out)["markten"]["NQ"]
        self.assertEqual(app["cfg"]["tp_mode"], "DOL")
        self.assertNotIn("tp_r", app["cfg"])                         # DOL valt in de app terug op tp_r = 1R
        self.assertEqual(leren._parse(app["variant"]), out["NQ"]["variant"])

    def test_validation_is_chronological_and_reporting_only(self):
        mem = rows(n=50, r=0.4)                                        # 5 jan t/m 23 feb
        v = dict(disp="basis", target="1.0", sessies="NY AM", bias="geen")
        val = leren.validate(list(mem.values()), v, self.NOW, days=30)
        self.assertEqual((val["train"]["n"], val["nieuw"]["n"]), (26, 24))   # grens 30 januari 12:00
        out, rep = self.choose(mem)
        self.assertIn("validatie", rep["NQ"])

    def test_split_by_date(self):
        a, b = validation.split_by_date([dict(t="2026-02-01"), dict(t="2026-01-01"), dict(t="2026-03-01")], "2026-02-01")
        self.assertEqual(([x["t"] for x in a], [x["t"] for x in b]), (["2026-01-01"], ["2026-02-01", "2026-03-01"]))


if __name__ == "__main__":
    unittest.main()
