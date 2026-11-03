"""Orderuitvoering met een nep-broker: modus, accountcontrole, noodstop, dubbele orders, time-outs en brokerfouten.
Er gaat niets naar Capital.com."""
import json
import socket
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import broker  # noqa: E402
import broker_capital as bc  # noqa: E402
from risico import Instrument  # noqa: E402

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)
DEMO_ENV = dict(CAPITAL_API_KEY="k", CAPITAL_IDENTIFIER="me@example.com", CAPITAL_PASSWORD="geheim-wachtwoord")
LIVE_ENV = dict(CAPITAL_MODUS="live", CAPITAL_LIVE_BEVESTIGING=broker.LIVE_PHRASE, CAPITAL_LIVE_API_KEY="lk",
                CAPITAL_LIVE_IDENTIFIER="me@example.com", CAPITAL_LIVE_PASSWORD="lpw", CAPITAL_LIVE_ACCOUNT_ID="LIVE123456")


def report(**markets):
    """Een instrumentrapport zoals execution/instruments.main() het schrijft (testwaarden, geen echte brokerdata)."""
    from execution.instruments import SOORT
    from execution.markets import INSTRUMENT_TYPES
    huidig = {m: dict(epic=e, naam=f"test {m}", type=INSTRUMENT_TYPES[SOORT[m]], bruikbaar_voor_broker_py=True, problemen=[])
              for m, e in broker.EPICS.items()}
    huidig.update(markets)
    return dict(gemaakt=NOW.isoformat(), omgeving="demo (alleen lezen)", huidig=huidig, kandidaten={})


def cfg(**kw):
    c = broker.settings(Path("/nonexistent"))
    c.update(kw)
    return c


def live_cfg(**live):
    c = cfg(broker=dict(modus="live"))
    c["live"] = dict(dict(limieten_gevalideerd=True, strategieen=["GOUD:momentum"]), **live)
    return c


def status(kant="LONG", age_min=5):
    t = (NOW - timedelta(minutes=age_min)).isoformat()
    return dict(gemaakt=(NOW - timedelta(minutes=1)).isoformat(), markten=[],
                alle_markten=[dict(naam="GOUD", soort="grondstof", open=True, status="live", koers=2400.0,
                                   keuze=dict(status="actief", strategie="momentum", titel="Momentum"),
                                   signalen=[dict(t=t, kant=kant, entry=2400.0, stop=2390.0, tp=2420.0, status="nieuw")])])


class FakeCapital:
    """Gedraagt zich als broker_capital.Capital, maar alles in het geheugen."""

    def __init__(self, account_id="DEMO1", ccy="EUR", nav=10000.0, session_account=None):
        self.sessie = dict(currentAccountId=session_account or account_id, hasActiveDemoAccounts=True, hasActiveLiveAccounts=True)
        self.active = session_account or account_id
        self.acc = dict(id=account_id, ccy=ccy, saldo=nav, open_pl=0.0, nav=nav)
        self.pos, self.wo, self.calls = [], [], []
        self.laatste_ok = NOW
        self.place_error = None
        self.drop_stop = False
        self.quote = dict(bid=2400.0, ask=2400.4)

    def select_account(self, acc):
        self.calls.append(("select", acc))
        if acc == self.acc["id"]:
            self.active = acc
        return self.active

    def current_account_id(self):
        return self.active

    def account(self, acc):
        return dict(self.acc, id=acc)

    def market(self, epic):
        return dict(instrument=dict(currency="USD"), snapshot=dict(bid=1.1, offer=1.1))

    def instrument(self, markt, epic):
        return Instrument(markt=markt, epic=epic, ccy="USD", lot_size=1, scaling=1, min_size=0.01, max_size=None, step=0.01,
                          decimals=2, min_stop=0.5, max_stop=None, status="TRADEABLE", quote_time=None, **self.quote)

    def fx(self, src, dst):
        return 1.0 if src == dst else (1 / 1.1 if (src, dst) == ("USD", "EUR") else None)

    def positions(self):
        return [dict(p) for p in self.pos]

    def working_orders(self):
        return [dict(w) for w in self.wo]

    def place_market(self, epic, side, size, stop, tp):
        self.calls.append(("market", epic, side, size, stop, tp))
        if self.place_error:
            raise self.place_error
        d = f"D{len(self.calls)}"
        self.pos.append(dict(deal_id=d, epic=epic, side=side, size=size, level=self.quote["ask"], stop=None if self.drop_stop else stop,
                             tp=tp, created=NOW, upl=0.0, bid=self.quote["bid"], ask=self.quote["ask"]))
        return dict(accepted=True, deal_id=d, ref="o_1")

    def place_limit(self, epic, side, size, level, stop, tp, good_till):
        self.calls.append(("limit", epic, side, size, level))
        d = f"W{len(self.calls)}"
        # zoals de API-documentatie wachtende orders toont: alleen afstanden, geen absolute niveaus
        self.wo.append(dict(deal_id=d, epic=epic, side=side, size=size, level=level, stop=None, tp=None,
                            stop_dist=abs(level - stop), tp_dist=abs(tp - level), created=NOW, good_till=None))
        return dict(accepted=True, deal_id=d, ref="o_2")

    def close(self, deal_id):
        self.calls.append(("close", deal_id))
        self.pos = [p for p in self.pos if p["deal_id"] != deal_id]
        return dict(accepted=True)

    def cancel(self, deal_id):
        self.calls.append(("cancel", deal_id))
        self.wo = [w for w in self.wo if w["deal_id"] != deal_id]
        return dict(accepted=True)

    def closed(self):
        return []

    def orders_sent(self):
        return [c for c in self.calls if c[0] in ("market", "limit")]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / "instrumenten.json").write_text(json.dumps(report()))
        self.p = mock.patch.multiple(broker, STATE_FILES={"demo": d / "demo_staat.json", "live": d / "live_staat.json"}, HERE=d,
                                     INSTRUMENTS_FILE=d / "instrumenten.json")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def go(self, fake, c=None, env=DEMO_ENV, st=None, stat=None, now=NOW):
        self.st = st if st is not None else {}
        return broker.run(stat or status(), c or cfg(), env, self.st, connect=lambda m: fake, now=now)


class Mode(Base):
    def test_default_is_demo(self):
        m = broker.resolve_mode(cfg(), DEMO_ENV)
        self.assertEqual(m["modus"], "demo")
        self.assertEqual(m["problemen"], [])

    def test_demo_without_secrets_does_nothing(self):
        out = broker.run(status(), cfg(), {}, {}, connect=lambda m: self.fail("mag niet verbinden"), now=NOW)
        self.assertFalse(out["gekoppeld"])

    def test_live_requires_every_opt_in(self):
        for missing in LIVE_ENV:
            env = {k: v for k, v in LIVE_ENV.items() if k != missing}
            out = broker.run(status(), live_cfg(), env, {}, connect=lambda m: self.fail("mag niet verbinden"), now=NOW)
            self.assertEqual(out["modus"], "geblokkeerd", missing)
        for bad in (dict(limieten_gevalideerd=False), dict(strategieen=[]), dict(limieten=dict(risico_pct=2.0))):
            m = broker.resolve_mode(live_cfg(**bad), LIVE_ENV)
            self.assertEqual(m["modus"], "geblokkeerd", bad)

    def test_live_never_falls_back_to_demo(self):
        m = broker.resolve_mode(live_cfg(), dict(DEMO_ENV))
        self.assertEqual(m["modus"], "geblokkeerd")

    def test_live_with_all_opt_ins(self):
        m = broker.resolve_mode(live_cfg(), LIVE_ENV)
        self.assertEqual(m["modus"], "live")
        self.assertEqual(bc.URLS["live"], "https://api-capital.backend-capital.com/api/v1")

    def test_live_account_must_match(self):
        fake = FakeCapital(account_id="ANDER999")
        out = self.go(fake, live_cfg(), LIVE_ENV)
        self.assertIn("account niet bevestigd", out["blokkade"])
        self.assertEqual(fake.orders_sent(), [])

    def test_live_only_allowed_strategies(self):
        fake = FakeCapital(account_id="LIVE123456")
        self.go(fake, live_cfg(strategieen=["NQ:trend"]), LIVE_ENV)
        self.assertEqual(fake.orders_sent(), [])
        self.assertIn("niet vrijgegeven", list(self.st["orders"].values())[0]["reden"])

    def test_live_order_when_everything_ok(self):
        fake = FakeCapital(account_id="LIVE123456")
        out = self.go(fake, live_cfg(), LIVE_ENV)
        self.assertEqual(out["modus"], "live")
        self.assertEqual(len(fake.orders_sent()), 1)


class Orders(Base):
    def test_places_one_protected_order(self):
        fake = FakeCapital()
        out = self.go(fake)
        sent = fake.orders_sent()
        self.assertEqual(len(sent), 1)
        _, epic, side, size, stop, tp = sent[0]
        self.assertEqual((epic, side, stop, tp), ("GOLD", 1, 2390.4, 2420.4))
        # 0,5% van 10.000 EUR = 50 EUR = 55 USD; per unit 10 + 0,4 spread + 0,5 slippage = 10,9 -> 5,04
        self.assertAlmostEqual(size, 5.04)
        self.assertEqual(out["modus"], "demo")
        self.assertEqual(list(self.st["orders"].values())[0]["status"], "geplaatst")

    def test_same_signal_twice_gives_one_order(self):
        fake = FakeCapital()
        self.go(fake)
        self.go(fake, st=self.st)
        self.assertEqual(len(fake.orders_sent()), 1)

    def test_state_lost_but_position_exists(self):
        fake = FakeCapital()
        self.go(fake)
        self.go(fake, st={})                     # staat kwijt (bv. cache weg): de broker voorkomt een dubbele order
        self.assertEqual(len(fake.orders_sent()), 1)

    def test_journal_written_before_sending(self):
        fake = FakeCapital()
        seen = {}
        orig = fake.place_market

        def spy(*a):
            seen.update(json.loads(broker.STATE_FILES["demo"].read_text()))
            return orig(*a)
        fake.place_market = spy
        self.go(fake)
        self.assertEqual(list(seen["orders"].values())[0]["status"], "verzenden")

    def test_timeout_is_unknown_and_never_resent(self):
        fake = FakeCapital()
        fake.place_error = bc.UnknownOutcome("time-out")
        self.go(fake)
        self.assertEqual(list(self.st["orders"].values())[0]["status"], "onbekend")
        fake.place_error = None
        self.go(fake, st=self.st, now=NOW + timedelta(minutes=3))
        self.assertEqual(len(fake.orders_sent()), 1)          # niet opnieuw verstuurd

    def test_unknown_order_found_at_broker(self):
        fake = FakeCapital()
        fake.place_error = bc.UnknownOutcome("time-out")
        self.go(fake)
        rec = list(self.st["orders"].values())[0]
        fake.pos.append(dict(deal_id="X1", epic="GOLD", side=1, size=rec["size"], level=2400.4, stop=rec["stop"], tp=rec["tp"],
                             created=NOW, upl=0.0, bid=2400.0, ask=2400.4))
        self.go(fake, st=self.st, now=NOW + timedelta(minutes=3))
        self.assertEqual(rec["status"], "geplaatst")
        self.assertEqual(rec["deal_id"], "X1")

    def test_unknown_order_not_found(self):
        fake = FakeCapital()
        fake.place_error = bc.UnknownOutcome("time-out")
        self.go(fake)
        fake.place_error = None
        self.go(fake, st=self.st, now=NOW + timedelta(minutes=20))
        self.assertEqual(list(self.st["orders"].values())[0]["status"], "niet gevonden")

    def test_broker_rejection(self):
        fake = FakeCapital()
        fake.place_error = bc.BrokerError(400, "error.invalid.stoploss")
        self.go(fake)
        self.assertEqual(list(self.st["orders"].values())[0]["status"], "geweigerd")

    def test_missing_protection_is_closed(self):
        fake = FakeCapital()
        fake.drop_stop = True
        self.go(fake)
        self.assertIn(("close", "D1"), fake.calls)
        self.assertEqual(list(self.st["orders"].values())[0]["status"], "teruggedraaid")

    def test_stale_status_blocks(self):
        fake = FakeCapital()
        s = status()
        s["gemaakt"] = (NOW - timedelta(minutes=30)).isoformat()
        out = self.go(fake, stat=s)
        self.assertIn("verouderd", out["blokkade"])
        self.assertEqual(fake.orders_sent(), [])

    def test_old_signal_ignored(self):
        fake = FakeCapital()
        self.go(fake, stat=status(age_min=25))
        self.assertEqual(fake.orders_sent(), [])

    def test_future_signal_ignored(self):
        """Een signaal met een tijd in de toekomst (lopende candle) mag nooit tot een order leiden."""
        fake = FakeCapital()
        self.go(fake, stat=status(age_min=-30))
        self.assertEqual(fake.orders_sent(), [])

    def test_wide_spread_skips(self):
        fake = FakeCapital()
        fake.quote = dict(bid=2400.0, ask=2404.0)
        self.go(fake)
        self.assertEqual(fake.orders_sent(), [])
        self.assertIn("spread", list(self.st["orders"].values())[0]["reden"])


class LimitOrders(Base):
    def ict_status(self):
        t = (NOW - timedelta(minutes=10)).isoformat()
        return dict(gemaakt=(NOW - timedelta(minutes=1)).isoformat(), alle_markten=[],
                    markten=[dict(naam="GOUD", koers=2400.2, data_min_oud=5, setups=[dict(tijd=t, telt=True, status="wacht op entry",
                                  kant="LONG", entry=2395.0, stop=2390.0, tp=2405.0)])])

    def test_limit_with_distances_is_protected(self):
        fake = FakeCapital()
        self.go(fake, stat=self.ict_status())
        self.assertEqual([c[0] for c in fake.calls if c[0] in ("limit", "cancel")], ["limit"])
        self.assertEqual(list(self.st["orders"].values())[0]["status"], "geplaatst")

    def test_filled_limit_linked_by_working_order_id(self):
        fake = FakeCapital()
        self.go(fake, stat=self.ict_status())
        w = fake.wo.pop()
        fake.pos.append(dict(deal_id="P7", epic=w["epic"], side=1, size=w["size"], level=w["level"], stop=None, tp=None,
                             stop_dist=5.0, tp_dist=10.0, working_order_id=w["deal_id"], contract_size=1, created=NOW,
                             upl=0.0, bid=2400.0, ask=2400.4))
        self.go(fake, st=self.st, stat=dict(self.ict_status(), markten=[]))
        self.assertEqual(list(self.st["orders"].values())[0]["positie_id"], "P7")

    def test_unknown_contract_size_blocks_new_orders(self):
        fake = FakeCapital()
        fake.pos.append(dict(deal_id="Z1", epic="US100", side=1, size=1, level=20000, stop=19900, tp=20200, contract_size=10,
                             created=NOW, upl=0, bid=20000, ask=20001))
        self.go(fake)
        self.assertEqual(fake.orders_sent(), [])
        self.assertIn("zonder stop", list(self.st["orders"].values())[0]["reden"])


class EmergencyStop(Base):
    def test_blocks_new_orders_cancels_pending_keeps_positions(self):
        fake = FakeCapital()
        fake.pos.append(dict(deal_id="P1", epic="US100", side=1, size=1, level=20000, stop=19900, tp=20200, created=NOW, upl=0,
                             bid=20000, ask=20001))
        fake.wo.append(dict(deal_id="W9", epic="EURUSD", side=1, size=1000, level=1.08, stop=1.07, tp=1.1, created=NOW, good_till=None))
        st = dict(orders={"x": dict(markt="EURUSD", status="geplaatst", deal_id="W9", t=NOW.isoformat())})
        out = self.go(fake, cfg(noodstop=True), st=st)
        self.assertIn("NOODSTOP", out["blokkade"])
        self.assertEqual(fake.orders_sent(), [])
        self.assertIn(("cancel", "W9"), fake.calls)
        self.assertNotIn(("close", "P1"), fake.calls)
        self.assertEqual(len(fake.pos), 1)

    def test_env_and_file(self):
        self.assertTrue(broker.emergency_stop(cfg(), dict(NOODSTOP="1")))
        (broker.HERE / "NOODSTOP").write_text("")
        self.assertTrue(broker.emergency_stop(cfg(), {}))


class CapitalClient(unittest.TestCase):
    """De echte client met een nep-HTTP-laag."""

    def make(self, routes, modus="demo"):
        calls = []

        def transport(method, url, headers, body):
            calls.append((method, url))
            for (m, path), resp in routes.items():
                if m == method and url.endswith(path):
                    r = resp.pop(0) if isinstance(resp, list) else resp
                    if isinstance(r, Exception):
                        raise r
                    return r
            return 404, {"errorCode": "error.not-found"}, {}
        ok_login = (200, dict(currentAccountId="A1", hasActiveDemoAccounts=True), {"CST": "c", "X-SECURITY-TOKEN": "x"})
        routes.setdefault(("POST", "/session"), [ok_login, ok_login])
        c = bc.Capital(modus, "KEY", "me@example.com", "PW-123", transport=transport, sleep=lambda s: None)
        return c, calls

    def test_urls(self):
        c, calls = self.make({})
        self.assertTrue(calls[0][1].startswith("https://demo-api-capital.backend-capital.com/api/v1"))
        c, calls = self.make({}, modus="live")
        self.assertTrue(calls[0][1].startswith("https://api-capital.backend-capital.com/api/v1"))

    def test_order_timeout_is_unknown_and_not_retried(self):
        c, calls = self.make({("POST", "/positions"): [socket.timeout("t")]})
        with self.assertRaises(bc.UnknownOutcome):
            c.place_market("GOLD", 1, 1.0, 2390, 2420)
        self.assertEqual(sum(1 for m, u in calls if u.endswith("/positions")), 1)

    def test_read_retries_on_network_error(self):
        c, calls = self.make({("GET", "/positions"): [socket.timeout("t"), (200, dict(positions=[]), {})]})
        self.assertEqual(c.positions(), [])

    def test_expired_session_relogin(self):
        c, calls = self.make({("GET", "/positions"): [(401, {"errorCode": "error.invalid.session.token"}, {}), (200, dict(positions=[]), {})]})
        self.assertEqual(c.positions(), [])
        self.assertEqual(sum(1 for m, u in calls if u.endswith("/session")), 2)

    def test_confirm_waits_for_404(self):
        c, _ = self.make({("POST", "/positions"): (200, dict(dealReference="o_1"), {}),
                          ("GET", "/confirms/o_1"): [(404, {}, {}), (200, dict(dealStatus="ACCEPTED", affectedDeals=[dict(dealId="D9")]), {})]})
        r = c.place_market("GOLD", 1, 1.0, 2390, 2420)
        self.assertTrue(r["accepted"])
        self.assertEqual(r["deal_id"], "D9")

    def test_rejected_confirm(self):
        c, _ = self.make({("POST", "/positions"): (200, dict(dealReference="o_1"), {}),
                          ("GET", "/confirms/o_1"): (200, dict(dealStatus="REJECTED", reason="RISK_CHECK"), {})})
        self.assertFalse(c.place_market("GOLD", 1, 1.0, 2390, 2420)["accepted"])

    def test_errors_never_contain_secrets(self):
        try:
            self.make({("POST", "/session"): [(401, {"errorCode": "error.invalid.details"}, {})]})
        except bc.BrokerError as ex:
            msg = str(ex)
        self.assertNotIn("PW-123", msg)
        self.assertNotIn("KEY", msg)

    def test_instrument_fail_closed(self):
        c, _ = self.make({("GET", "/markets/GOLD"): (200, dict(instrument=dict(currency="USD", lotSize=1), dealingRules={}, snapshot={}), {})})
        with self.assertRaises(bc.InstrumentError):
            c.instrument("GOUD", "GOLD")


class ClosedBars(unittest.TestCase):
    def test_running_candle_dropped(self):
        import pandas as pd
        import live_status
        idx = pd.date_range("2026-11-02 13:00", periods=4, freq="1h", tz="UTC")
        df = pd.DataFrame(dict(Open=1, High=1, Low=1, Close=1), index=idx)
        out = live_status.closed_bars(df, pd.Timedelta(hours=1), pd.Timestamp("2026-11-02 16:03", tz="UTC"))
        self.assertEqual(out.index[-1], pd.Timestamp("2026-11-02 15:00", tz="UTC"))


if __name__ == "__main__":
    unittest.main()
