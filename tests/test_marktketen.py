"""De keten per markt: mapping, instrumentverificatie, handelsuren, sizing per marktsoort en foutafhandeling.
Alles met een nep-broker en testwaarden: er gaat niets naar Capital.com, en de instrumentgegevens hieronder zijn
GEEN echte brokergegevens."""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import broker  # noqa: E402
from core import market_hours  # noqa: E402
from core.data import check_ohlc, clean  # noqa: E402
from core.markets import ICT_MARKETS, LAB_MARKETS  # noqa: E402
from execution import instruments  # noqa: E402
from risk import rules as risico  # noqa: E402
from risico import Instrument  # noqa: E402
from test_broker import DEMO_ENV, NOW, Base, FakeCapital, cfg, report  # noqa: E402

NY = ZoneInfo("America/New_York")
SOORTEN = {"crypto", "forex", "index", "grondstof", "aandeel"}
# Testinstrumenten per marktsoort: (markt, soort, bronkoers, valuta, minimum, stap, decimalen, stopafstand)
TEST_INSTRUMENTS = [
    ("BTC", "crypto", 60000.0, "USD", 0.001, 0.001, 1, 900.0),
    ("EURUSD", "forex", 1.10, "USD", 100.0, 1.0, 5, 0.002),
    ("USDJPY", "forex", 150.0, "JPY", 100.0, 1.0, 3, 0.30),
    ("NQ", "index", 20000.0, "USD", 0.1, 0.1, 1, 40.0),
    ("DAX", "index", 19000.0, "EUR", 0.1, 0.1, 1, 30.0),
    ("OLIE", "grondstof", 70.0, "USD", 1.0, 1.0, 2, 0.8),
    ("AAPL", "aandeel", 200.0, "USD", 1.0, 1.0, 2, 2.0),
]
FX = {("USD", "EUR"): 1 / 1.1, ("JPY", "EUR"): 1 / 165.0}


class MultiCapital(FakeCapital):
    """Nep-broker met per epic een eigen (test)instrument en koers."""

    def __init__(self, specs, **kw):
        super().__init__(**kw)
        self.specs = specs

    def instrument(self, markt, epic):
        sp = self.specs[epic]
        return Instrument(markt=markt, epic=epic, ccy=sp["ccy"], lot_size=sp.get("lot", 1), scaling=1, min_size=sp["min"],
                          max_size=None, step=sp["step"], decimals=sp["dec"], min_stop=0.0, max_stop=None, status="TRADEABLE",
                          quote_time=None, bid=sp["bid"], ask=sp["ask"])

    def market(self, epic):
        sp = self.specs.get(epic, dict(ccy="USD", bid=1.1, ask=1.1))
        return dict(instrument=dict(currency=sp["ccy"]), snapshot=dict(bid=sp["bid"], offer=sp["ask"]))

    def fx(self, src, dst):
        return 1.0 if src == dst else FX.get((src, dst))

    def place_market(self, epic, side, size, stop, tp):
        self.quote = dict(bid=self.specs[epic]["bid"], ask=self.specs[epic]["ask"])
        return super().place_market(epic, side, size, stop, tp)


def lab_row(markt, soort, price, stopd, status="actief", t=None, kant="LONG"):
    t = t or (NOW - timedelta(minutes=5)).isoformat()
    side = 1 if kant == "LONG" else -1
    return dict(naam=markt, soort=soort, open=True, status="live", koers=price,
                keuze=dict(status=status, strategie="momentum" if status == "actief" else None, titel="Momentum"),
                signalen=[dict(t=t, kant=kant, entry=price, stop=price - side * stopd, tp=price + side * 2 * stopd, status="nieuw")])


def spec(price, ccy, mn, step, dec, spread_frac=0.0001):
    half = price * spread_frac / 2
    return dict(ccy=ccy, min=mn, step=step, dec=dec, bid=round(price - half, dec), ask=round(price + half, dec))


class Mapping(unittest.TestCase):
    def test_all_15_markets_have_one_epic_and_known_kind(self):
        names = [m["naam"] for m in LAB_MARKETS]
        self.assertEqual(len(names), 15)
        self.assertEqual(set(names), set(broker.EPICS))
        self.assertEqual(len(set(broker.EPICS.values())), 15)          # geen twee markten op hetzelfde instrument
        self.assertTrue({m["name"] for m in ICT_MARKETS} <= set(broker.EPICS))
        self.assertTrue(all(m["soort"] in SOORTEN for m in LAB_MARKETS))
        self.assertTrue(all(risico.group_of(n) for n in names))       # elke markt valt in een correlatiegroep

    def test_runner_name_still_works(self):
        from execution import markets, runner
        self.assertIs(runner.EPICS, markets.EPICS)


class Verification(unittest.TestCase):
    def test_no_report_blocks(self):
        self.assertIn("ontbreekt", instruments.verified("GOUD", "GOLD", None))

    def test_report_must_confirm_epic_and_usability(self):
        ok = report()
        self.assertIsNone(instruments.verified("GOUD", "GOLD", ok))
        self.assertIn("epic", instruments.verified("GOUD", "XAUUSD", ok))
        bad = report(GOUD=dict(epic="GOLD", fout="HTTP 404: error.not-found.epic"))
        self.assertIn("fout", instruments.verified("GOUD", "GOLD", bad))
        lot = report(NQ=dict(epic="US100", naam="US Tech 100", bruikbaar_voor_broker_py=False, problemen=["lotSize 10"]))
        self.assertIn("lotSize 10", instruments.verified("NQ", "US100", lot))
        missing = report()
        del missing["huidig"]["SOL"]
        self.assertIn("staat niet", instruments.verified("SOL", "SOLUSD", missing))
        self.assertIn("demo", instruments.verified("GOUD", "GOLD", dict(ok, omgeving="live")))

    def test_malformed_report_refused_without_crash(self):
        for bad in ([1, 2], dict(omgeving=None, huidig={}), dict(omgeving="demo", huidig=[]),
                    dict(omgeving="demo", huidig=dict(GOUD="GOLD"))):
            self.assertIsNotNone(instruments.verified("GOUD", "GOLD", bad))
            self.assertTrue(all(instruments.status_per_market(bad).values()))
        self.assertIn("type", instruments.verified("GOUD", "GOLD", report(GOUD=dict(epic="GOLD", naam="Gold", type="SHARES",
                                                                                     bruikbaar_voor_broker_py=True))))

    def test_report_problems_include_missing_fields(self):
        class B:
            def market(self, epic):
                return dict(instrument=dict(name="Gold", currency=None, lotSize=1), dealingRules={}, snapshot=dict(bid=1.0, offer=1.1))

            def call(self, *a):
                return dict(prices=[])
        d = instruments.details(B(), "GOLD")
        self.assertFalse(d["bruikbaar_voor_broker_py"])
        self.assertTrue({"minimale ordergrootte ontbreekt", "stapgrootte ontbreekt", "valuta ontbreekt"} <= set(d["problemen"]))


class MarketHours(unittest.TestCase):
    def ny(self, *a):
        return datetime(*a, tzinfo=NY)

    def test_close_times(self):
        self.assertEqual(market_hours.session_end("aandeel", "AAPL", self.ny(2026, 11, 2, 15, 30)), self.ny(2026, 11, 2, 16, 0))
        self.assertIsNone(market_hours.session_end("aandeel", "AAPL", self.ny(2026, 11, 2, 16, 30)))
        self.assertIsNone(market_hours.session_end("crypto", "BTC", self.ny(2026, 11, 7, 12, 0)))
        self.assertEqual(market_hours.session_end("forex", "EURUSD", self.ny(2026, 11, 2, 10, 0)), self.ny(2026, 11, 6, 17, 0))
        self.assertEqual(market_hours.session_end("grondstof", "GOUD", self.ny(2026, 11, 8, 19, 0)), self.ny(2026, 11, 13, 17, 0))

    def test_dax_follows_frankfurt_also_when_dst_differs(self):
        # 26 oktober 2026: Europa al wintertijd, de VS nog zomertijd (verschil 5 uur in plaats van 6)
        t = datetime(2026, 10, 26, 16, 45, tzinfo=ZoneInfo("Europe/Berlin"))
        self.assertTrue(market_hours.is_open("index", "DAX", t))      # oude regel (tot 11:30 NY = 16:30 Frankfurt): dicht
        self.assertEqual(market_hours.session_end("index", "DAX", t), datetime(2026, 10, 26, 17, 30, tzinfo=ZoneInfo("Europe/Berlin")))

    def test_dashboard_uses_same_rules(self):
        from dashboard import status
        for soort, naam in (("aandeel", "AAPL"), ("index", "DAX"), ("forex", "EURUSD"), ("crypto", "BTC")):
            for h in range(0, 24):
                t = self.ny(2026, 11, 2, h, 15)
                self.assertEqual(status.is_open(soort, naam, t), market_hours.is_open(soort, naam, t))

    def test_close_by(self):
        aapl = dict(markt="AAPL", strategie="momentum", marktsoort="aandeel")
        until, why = broker.close_by(aapl, self.ny(2026, 11, 2, 15, 30), 12)
        self.assertEqual(until, self.ny(2026, 11, 2, 15, 55))
        self.assertIsNone(broker.close_by(aapl, self.ny(2026, 11, 2, 15, 57), 12)[0])
        btc = dict(markt="BTC", strategie="momentum", marktsoort="crypto")
        t = self.ny(2026, 11, 7, 12, 0)
        self.assertEqual(broker.close_by(btc, t, 12)[0], t + timedelta(hours=12))
        fx = dict(markt="EURUSD", strategie="trend", marktsoort="forex")
        self.assertEqual(broker.close_by(fx, self.ny(2026, 11, 6, 10, 0), 12)[0], self.ny(2026, 11, 6, 16, 55))
        ict = dict(markt="NQ", strategie="ict", marktsoort=None)
        self.assertEqual(broker.close_by(ict, self.ny(2026, 11, 2, 10, 0), 12)[0], self.ny(2026, 11, 2, 16, 0))
        self.assertIsNone(broker.close_by(ict, self.ny(2026, 11, 2, 16, 10), 12)[0])


class SizingPerKind(unittest.TestCase):
    """Positiegrootte per marktsoort: afgerond op de stap, risico binnen het budget, valuta omgerekend."""

    def test_each_kind(self):
        lim = risico.Limits(risico_pct=0.5)
        for markt, soort, price, ccy, mn, step, dec, stopd in TEST_INSTRUMENTS:
            sp = spec(price, ccy, mn, step, dec)
            inst = Instrument(markt=markt, epic=broker.EPICS[markt], ccy=ccy, lot_size=1, scaling=1, min_size=mn, max_size=None,
                              step=step, decimals=dec, min_stop=0.0, max_stop=None, bid=sp["bid"], ask=sp["ask"], status="TRADEABLE")
            sig = dict(kant="LONG", entry=price, stop=price - stopd, tp=price + 2 * stopd, soort="MARKET")
            p, why = risico.plan_levels(sig, inst, lim)
            self.assertIsNone(why, markt)
            fx = FX.get((ccy, "EUR"), 1.0)
            equity = 100000.0
            why = risico.size_plan(p, inst, lim, equity, fx)
            self.assertIsNone(why, markt)
            self.assertAlmostEqual(p.size / step, round(p.size / step), places=6, msg=markt)
            self.assertLessEqual(p.risico_acc, equity * 0.005 + 1e-6, markt)
            self.assertGreater(p.risico_acc, equity * 0.005 * 0.8, markt)    # niet onnodig klein
            self.assertEqual(p.stop, round(p.stop, dec))
            self.assertAlmostEqual(abs(p.entry - p.stop), stopd, delta=10 ** -dec, msg=markt)

    def test_too_small_account_is_refused_not_rounded_up(self):
        lim = risico.Limits(risico_pct=0.5)
        inst = Instrument(markt="BTC", epic="BTCUSD", ccy="USD", lot_size=1, scaling=1, min_size=0.01, max_size=None, step=0.01,
                          decimals=1, min_stop=0.0, max_stop=None, bid=59997.0, ask=60003.0, status="TRADEABLE")
        p, _ = risico.plan_levels(dict(kant="LONG", entry=60000.0, stop=59100.0, tp=61800.0, soort="MARKET"), inst, lim)
        self.assertIn("te klein", risico.size_plan(p, inst, lim, 1000.0, 1 / 1.1))

    def test_unknown_currency_conversion_refused(self):
        lim = risico.Limits()
        inst = Instrument(markt="USDJPY", epic="USDJPY", ccy="JPY", lot_size=1, scaling=1, min_size=100, max_size=None, step=1,
                          decimals=3, min_stop=0.0, max_stop=None, bid=149.99, ask=150.01, status="TRADEABLE")
        p, _ = risico.plan_levels(dict(kant="LONG", entry=150.0, stop=149.7, tp=150.6, soort="MARKET"), inst, lim)
        self.assertIn("wisselkoers", risico.size_plan(p, inst, lim, 10000.0, None))


class Chain(Base):
    """Volledige ronde met de nep-broker: status.json -> signalen -> verificatie -> order."""

    def setUp(self):
        super().setUp()
        self.specs = {broker.EPICS[m]: spec(price, ccy, mn, step, dec) for m, _, price, ccy, mn, step, dec, _ in TEST_INSTRUMENTS}

    def stat(self, rows):
        return dict(gemaakt=(NOW - timedelta(minutes=1)).isoformat(), markten=[], alle_markten=rows)

    def rows(self):
        return [lab_row(m, soort, price, stopd) for m, soort, price, _, _, _, _, stopd in TEST_INSTRUMENTS]

    def fake(self):
        return MultiCapital(self.specs, nav=100000.0)

    def big_limits(self):
        return cfg(limieten=dict(max_open=10, max_per_groep=3, max_open_risico_pct=4.0, dagverlies_pct=5.0))

    def test_every_kind_gets_a_protected_order_when_verified(self):
        fake = self.fake()
        self.go(fake, c=self.big_limits(), stat=self.stat(self.rows()))
        placed = {c[1] for c in fake.orders_sent()}
        self.assertEqual(placed, {broker.EPICS[m] for m, *_ in TEST_INSTRUMENTS})
        for rec in self.st["orders"].values():
            self.assertEqual(rec["status"], "geplaatst", rec)
            self.assertIsNotNone(rec["stop"])
            self.assertIsNotNone(rec["tp"])
        aapl = next(r for r in self.st["orders"].values() if r["markt"] == "AAPL")
        self.assertEqual(datetime.fromisoformat(aapl["sluit_voor"]), datetime(2026, 11, 2, 15, 55, tzinfo=NY))

    def test_unverified_market_refused_others_go_on(self):
        (broker.INSTRUMENTS_FILE).write_text(json.dumps(report(NQ=dict(epic="US100", fout="HTTP 404"))))
        fake = self.fake()
        self.go(fake, c=self.big_limits(), stat=self.stat(self.rows()))
        placed = {c[1] for c in fake.orders_sent()}
        self.assertNotIn("US100", placed)
        self.assertIn("EURUSD", placed)
        nq = next(r for r in self.st["orders"].values() if r["markt"] == "NQ")
        self.assertEqual(nq["status"], "overgeslagen")
        self.assertIn("niet geverifieerd", nq["reden"])

    def test_no_report_no_orders_at_all(self):
        broker.INSTRUMENTS_FILE.unlink()
        fake = self.fake()
        out = self.go(fake, c=self.big_limits(), stat=self.stat(self.rows()))
        self.assertEqual(fake.orders_sent(), [])
        self.assertTrue(all("ontbreekt" in v for v in out["instrumenten"].values()))

    def test_research_status_never_orders(self):
        fake = self.fake()
        rows = [lab_row("EURUSD", "forex", 1.10, 0.002, status="onderzoek"), lab_row("AAPL", "aandeel", 200.0, 2.0, status="pauze")]
        self.go(fake, c=self.big_limits(), stat=self.stat(rows))
        self.assertEqual(fake.orders_sent(), [])

    def test_wrong_instrument_price_refused(self):
        self.specs["US100"] = spec(2000.0, "USD", 0.1, 0.1, 1)          # tiende van de bronkoers: andere eenheid
        fake = self.fake()
        self.go(fake, c=self.big_limits(), stat=self.stat([lab_row("NQ", "index", 20000.0, 40.0)]))
        self.assertEqual(fake.orders_sent(), [])
        self.assertIn("wijkt", next(iter(self.st["orders"].values()))["reden"])

    def test_error_in_one_market_does_not_stop_others(self):
        class Broken(MultiCapital):
            def instrument(self, markt, epic):
                if markt == "BTC":
                    raise ZeroDivisionError("kapot")
                return super().instrument(markt, epic)
        fake = Broken(self.specs, nav=100000.0)
        rows = self.rows()
        rows.insert(0, dict(naam="SOL", soort="crypto", open=True, status="live", koers=150.0, keuze=dict(status="actief", strategie="trend"),
                            signalen=[dict(t="geen tijd", kant="LONG", entry=1, stop=0.5, tp=2, status="nieuw")]))
        self.go(fake, c=self.big_limits(), stat=self.stat(rows))
        placed = {c[1] for c in fake.orders_sent()}
        self.assertNotIn("BTCUSD", placed)
        self.assertIn("EURUSD", placed)
        self.assertEqual(next(r for r in self.st["orders"].values() if r["markt"] == "BTC")["status"], "fout")
        self.assertTrue(any(x["markt"] == "SOL" and x["actie"] == "fout" for x in self.st["log"]))

    def test_crash_after_journal_is_unknown_and_never_resent(self):
        class Crash(MultiCapital):
            def place_market(self, *a):
                raise KeyError("onverwacht antwoord")
        fake = Crash(self.specs, nav=100000.0)
        stat = self.stat([lab_row("EURUSD", "forex", 1.10, 0.002)])
        self.go(fake, c=self.big_limits(), stat=stat)
        rec = next(iter(self.st["orders"].values()))
        self.assertEqual(rec["status"], "onbekend")
        fake2 = self.fake()
        self.go(fake2, c=self.big_limits(), stat=stat, st=self.st)
        self.assertEqual(fake2.orders_sent(), [])

    def test_order_left_in_sending_state_is_reconciled(self):
        stat = self.stat([lab_row("EURUSD", "forex", 1.10, 0.002)])
        key = f"LAB|EURUSD|{stat['alle_markten'][0]['signalen'][0]['t']}|LONG"
        st = dict(orders={key: dict(markt="EURUSD", status="verzenden", epic="EURUSD", side=1, size=2000.0,
                                    t=(NOW - timedelta(minutes=4)).isoformat())})
        fake = self.fake()
        fake.pos.append(dict(deal_id="X1", epic="EURUSD", side=1, size=2000.0, level=1.1, stop=1.098, tp=1.104,
                             created=NOW - timedelta(minutes=3), upl=0.0, bid=1.1, ask=1.1))
        self.go(fake, c=self.big_limits(), stat=stat, st=st)
        self.assertEqual(fake.orders_sent(), [])
        self.assertEqual(st["orders"][key]["status"], "geplaatst")
        self.assertEqual(st["orders"][key]["deal_id"], "X1")


class DashboardSignals(unittest.TestCase):
    def test_only_active_strategy_gives_signals(self):
        import fixtures
        from dashboard import status
        h = fixtures.hourly_bars(2000)
        m = dict(naam="TEST", kosten=0.0001, soort="index")
        now = h.index[-1] + pd.Timedelta(hours=2)
        for st in ("onderzoek", "pauze", None):
            self.assertEqual(status.lab_signals(m, h, dict(status=st, strategie="breakout", variant=dict(n=24)), True, now), [])
        active = status.lab_signals(m, h, dict(status="actief", strategie="breakout", variant=dict(n=24)), True, now)
        self.assertTrue(active)
        self.assertTrue(all(x["stop"] != x["entry"] and x["tp"] != x["entry"] for x in active))


class DataValidation(unittest.TestCase):
    def test_clean_counts_and_removes_bad_bars(self):
        idx = pd.date_range("2026-11-02 14:00", periods=6, freq="1h")
        df = pd.DataFrame(dict(Open=[1, 1, 1, 1, 1, 1.0], High=[2, 2, 0.5, 2, 2, 2.0], Low=[0.5] * 6, Close=[1.5] * 6), index=idx)
        df.iloc[3] = float("nan")
        df = pd.concat([df, df.iloc[[1]]])
        out, q = clean(df)
        self.assertEqual((q["ongeldig"], q["dubbel"], q["candles"]), (1, 1, 4))
        self.assertEqual(check_ohlc(out), [])
        self.assertEqual(str(out.index.tz), "UTC")


if __name__ == "__main__":
    unittest.main()
