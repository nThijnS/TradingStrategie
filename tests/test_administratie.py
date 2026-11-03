"""Saldo-administratie: stortingen en opnames apart van het handelsresultaat, risicobasis, statusmigratie en de
invloed op de limieten. Nep-broker en testwaarden; de situatie van 3 november 2026 (995,05 + storting 10000) dient
als voorbeeld."""
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import broker  # noqa: E402
from risk import administratie as adm_mod  # noqa: E402
from test_broker import DEMO_ENV, Base, FakeCapital, cfg  # noqa: E402

T0 = datetime(2026, 11, 3, 13, 22, 58, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 3, 14, 0, tzinfo=timezone.utc)
ADMIN = dict(startkapitaal=dict(bedrag=1000.0), geldstromen=[dict(t=T0.isoformat(), bedrag=10000.0, omschrijving="demo aangevuld")])
# de opgeslagen stand zoals die er na de storting uitzag (start_saldo, piek en dagstart van de oude code)
EQUITY = [["2026-11-02T16:30+00:00", 1000.0], ["2026-11-02T19:56+00:00", 995.05], ["2026-11-03T13:11+00:00", 995.05],
          ["2026-11-03T13:28+00:00", 10995.05]]
OLD_STATE = dict(account="DEMO1", start_saldo=1000.0, piek=10995.05, dag="2026-11-03", dag_start=995.05, equity=EQUITY, orders={}, log=[])


def load(admin=ADMIN):
    return adm_mod.load(dict(administratie=admin), 1000.0)


class Ledger(unittest.TestCase):
    def test_deposit_is_not_trading_result(self):
        a = load()
        self.assertEqual(adm_mod.inleg(a, T0 - timedelta(seconds=1)), 1000.0)
        self.assertEqual(adm_mod.inleg(a, NOW), 11000.0)
        st = dict(administratie=dict(resultaat_piek=0.0, resultaat_dag_start=-4.95))
        rv = adm_mod.risk_view(10995.05, a, st, None, NOW)
        self.assertEqual(rv["handelsresultaat"], -4.95)
        curve = adm_mod.trading_curve(EQUITY, a)
        self.assertEqual([v for _, v in curve], [1000.0, 995.05, 995.05, 995.05])     # geen sprong door de storting

    def test_risk_basis_caps_sizing_at_10000(self):
        a = load()
        st = dict(administratie=dict(resultaat_piek=0.0, resultaat_dag_start=-4.95))
        rv = adm_mod.risk_view(10995.05, a, st, 10000, NOW)
        self.assertEqual(rv["risicobasis"], 10000.0)
        self.assertAlmostEqual(rv["risicovermogen"], 9995.05)
        self.assertLessEqual(rv["sizing_vermogen"] * 0.5 / 100, 50.0)
        # winst boven de basis: positiegrootte blijft op de basis
        self.assertEqual(adm_mod.risk_view(12000.0, a, st, 10000, NOW)["sizing_vermogen"], 10000.0)
        # opname onder de basis: nooit met meer rekenen dan er staat
        a2 = load(dict(ADMIN, geldstromen=ADMIN["geldstromen"] + [dict(t=NOW.isoformat(), bedrag=-6000.0)]))
        self.assertEqual(adm_mod.risk_view(4995.05, a2, st, 10000, NOW)["risicovermogen"], 4995.05)

    def test_without_risk_capital_basis_is_the_deposit_total(self):
        rv = adm_mod.risk_view(10995.05, load(), dict(administratie=dict(resultaat_piek=0.0, resultaat_dag_start=-4.95)), None, NOW)
        self.assertEqual((rv["risicobasis"], rv["risicovermogen"]), (11000.0, 10995.05))

    def test_invalid_entries_become_problems(self):
        a = load(dict(startkapitaal=dict(bedrag=-5), geldstromen=[dict(t="2026-11-03T13:22", bedrag=10), dict(t=T0.isoformat())]))
        self.assertEqual(len(a["problemen"]), 3)
        self.assertEqual(a["geldstromen"], [])

    def test_start_capital_falls_back_to_first_seen_balance(self):
        a = adm_mod.load({}, 1000.0)
        self.assertEqual((a["startkapitaal"], a["geldstromen"]), (1000.0, []))
        self.assertIn("eerste saldo", a["bron"])

    def test_deposit_confirmed_in_series(self):
        c = adm_mod.confirm_in_series(EQUITY, load())
        self.assertEqual((c[0]["in_equityreeks"], c[0]["sprong"]), ("ja", 10000.0))
        wrong = adm_mod.confirm_in_series(EQUITY, load(dict(ADMIN, geldstromen=[dict(t=T0.isoformat(), bedrag=5000.0)])))
        self.assertEqual(wrong[0]["in_equityreeks"], "andere sprong")


class Migration(unittest.TestCase):
    def test_migration_keeps_old_values_and_rebases_peak_and_day_start(self):
        st = copy.deepcopy(OLD_STATE)
        day_start = datetime(2026, 11, 3, 0, 0, tzinfo=timezone(timedelta(hours=1)))
        s = adm_mod.migrate(st, load(), NOW, day_start)
        self.assertEqual(s["migratie"]["oud"], dict(start_saldo=1000.0, piek=10995.05, dag="2026-11-03", dag_start=995.05))
        self.assertEqual(s["resultaat_piek"], 0.0)                 # niet 9995,05: de storting is geen winst
        self.assertAlmostEqual(s["resultaat_dag_start"], -4.95)
        self.assertEqual(st["equity"], EQUITY)                      # ruwe reeks onaangeroerd
        self.assertEqual((st["piek"], st["dag_start"]), (10995.05, 995.05))


class Jumps(unittest.TestCase):
    def setUp(self):
        self.st = copy.deepcopy(OLD_STATE)
        self.a = load()
        adm_mod.migrate(self.st, self.a, NOW, NOW - timedelta(hours=15))

    def step(self, saldo, t, open_=False, closed=False, a=None):
        adm_mod.update(self.st, a or self.a, dict(nav=saldo, saldo=saldo), t, "2026-11-03", NOW - timedelta(hours=15), open_, closed)
        return adm_mod.unresolved(self.st, a or self.a)

    def test_unexplained_change_is_flagged_and_freezes_peak(self):
        self.assertEqual(self.step(10995.05, NOW), [])
        j = self.step(11495.05, NOW + timedelta(minutes=3))
        self.assertEqual([x["verschil"] for x in j], [500.0])
        self.assertEqual(self.st["administratie"]["resultaat_piek"], 0.0)      # +500 telt niet als nieuwe piek
        # vastleggen als geldstroom in die periode: opgelost, en de piek blijft op het handelsresultaat
        later = load(dict(ADMIN, geldstromen=ADMIN["geldstromen"] + [dict(t=(NOW + timedelta(minutes=2)).isoformat(), bedrag=500.0)]))
        self.assertEqual(self.step(11495.05, NOW + timedelta(minutes=6), a=later), [])
        self.assertEqual(self.st["administratie"]["resultaat_piek"], 0.0)

    def test_accepting_by_id(self):
        self.step(10995.05, NOW)
        j = self.step(10994.05, NOW + timedelta(minutes=3))            # bijvoorbeeld kosten van de broker
        ok = load(dict(ADMIN, geaccepteerd=[j[0]["id"]]))
        self.assertEqual(adm_mod.unresolved(self.st, ok), [])

    def test_no_flag_with_positions_or_closed_trades(self):
        self.step(10995.05, NOW)
        self.assertEqual(self.step(10950.0, NOW + timedelta(minutes=3), open_=True), [])
        self.assertEqual(self.step(10900.0, NOW + timedelta(minutes=6), closed=True), [])

    def test_recorded_deposit_is_not_flagged(self):
        st = copy.deepcopy(OLD_STATE)
        a = load()
        adm_mod.migrate(st, a, T0 - timedelta(minutes=5), NOW - timedelta(hours=15))
        adm_mod.update(st, a, dict(nav=995.05, saldo=995.05), T0 - timedelta(minutes=2), "2026-11-03", NOW, False, False)
        adm_mod.update(st, a, dict(nav=10995.05, saldo=10995.05), T0 + timedelta(minutes=1), "2026-11-03", NOW, False, False)
        self.assertEqual(adm_mod.unresolved(st, a), [])


class RunnerWithDeposit(Base):
    """Volledige ronde met de nep-broker op de stand van 3 november."""

    def c(self, **demo):
        c = cfg()
        c["administratie"] = copy.deepcopy(ADMIN)
        c["risicokapitaal"] = demo.get("risicokapitaal", 10000)
        return c

    def fake(self, nav=10995.05):
        f = FakeCapital(nav=nav)
        f.acc.update(saldo=nav)
        f.closed = lambda: [dict(instrument="GOLD", dicht="2026-11-02T19:40:31+00:00", pl=-4.95)]
        return f

    def run_at(self, fake, c, st, now=NOW, stat=None):
        stat = stat or dict(gemaakt=(now - timedelta(minutes=1)).isoformat(), markten=[], alle_markten=[])
        return broker.run(stat, c, DEMO_ENV, st, connect=lambda m: fake, now=now)

    def test_balance_shown_as_broker_balance_not_profit(self):
        st = copy.deepcopy(OLD_STATE)
        out = self.run_at(self.fake(), self.c(), st)
        a = out["administratie"]
        self.assertEqual((out["nav"], a["saldo_broker"], a["handelsresultaat"], a["inleg"]), (10995.05, 10995.05, -4.95, 11000.0))
        self.assertEqual(a["geldstromen"][0]["bedrag"], 10000.0)
        self.assertEqual(a["max_risico_per_trade"], 49.98)
        self.assertIsNone(out["blokkade"])
        # grenzen als accountwaarde: ~500 onder de piek (5% van 10000), ~300 voor vandaag (3% van 9995,05)
        self.assertAlmostEqual(out["grens"], 10500.0, places=2)
        self.assertAlmostEqual(out["daggrens"], 10695.2, places=2)
        self.assertEqual(a["ruw"]["piek"], 10995.05)                       # oude waarde blijft zichtbaar
        self.assertEqual(st["administratie"]["migratie"]["oud"]["piek"], 10995.05)
        self.assertTrue(any(x["actie"] == "administratie" for x in st["log"]))

    def test_old_code_would_have_disabled_the_day_limit(self):
        # zonder administratie (oude werking): dagstart 995,05 tegenover 10995,05 accountwaarde = geen daglimiet meer
        st = copy.deepcopy(OLD_STATE)
        out = self.run_at(self.fake(), self.c(), st)
        self.assertGreater(out["daggrens"], 10000)                           # nieuw: echte daglimiet
        self.assertLess(OLD_STATE["dag_start"] * 0.97, 1000)                  # oud: 965,20

    def test_day_limit_triggers_on_trading_loss_not_on_deposit(self):
        st = copy.deepcopy(OLD_STATE)
        self.run_at(self.fake(), self.c(), st)
        f = self.fake(nav=10995.05)
        f.acc.update(nav=10680.0, open_pl=-315.05)          # open verlies van 315: meer dan 3% van ~10000
        f.pos.append(dict(deal_id="X", epic="SILVER", side=1, size=100.0, level=50.0, stop=49.9, tp=52.0, created=NOW,
                          upl=-315.05, bid=46.85, ask=46.86))
        stat = dict(gemaakt=NOW.isoformat(), markten=[], alle_markten=[dict(
            naam="GOUD", soort="grondstof", open=True, status="live", koers=2400.0, keuze=dict(status="actief", strategie="trend"),
            signalen=[dict(t=(NOW - timedelta(minutes=3)).isoformat(), kant="LONG", entry=2400.0, stop=2390.0, tp=2420.0, status="nieuw")])])
        self.run_at(f, self.c(), st, now=NOW + timedelta(minutes=3), stat=stat)
        rec = next(v for v in st["orders"].values() if v["markt"] == "GOUD")
        self.assertEqual(rec["status"], "overgeslagen")
        self.assertIn("daglimiet", rec["reden"])

    def test_sizing_uses_risk_capital(self):
        st = copy.deepcopy(OLD_STATE)
        f = self.fake()
        stat = dict(gemaakt=NOW.isoformat(), markten=[], alle_markten=[dict(
            naam="GOUD", soort="grondstof", open=True, status="live", koers=2400.0, keuze=dict(status="actief", strategie="momentum"),
            signalen=[dict(t=(NOW - timedelta(minutes=3)).isoformat(), kant="LONG", entry=2400.0, stop=2390.0, tp=2420.0, status="nieuw")])])
        self.run_at(f, self.c(), st, stat=stat)
        rec = next(iter(st["orders"].values()))
        self.assertEqual(rec["status"], "geplaatst", rec)
        self.assertLessEqual(rec["risico"], 50.0)
        self.assertGreater(rec["risico"], 45.0)
        st2 = copy.deepcopy(OLD_STATE)
        self.run_at(self.fake(), self.c(risicokapitaal=None), st2, stat=stat)    # zonder basis: rekent met de inleg
        self.assertGreater(next(iter(st2["orders"].values()))["risico"], 50.0)

    def test_bad_risk_capital_or_admin_blocks_orders(self):
        out = self.run_at(self.fake(), self.c(risicokapitaal="tienduizend"), copy.deepcopy(OLD_STATE))
        self.assertIn("risicokapitaal", out["blokkade"])
        c = self.c()
        c["administratie"]["geldstromen"].append(dict(t="gisteren", bedrag=5))
        out = self.run_at(self.fake(), c, copy.deepcopy(OLD_STATE))
        self.assertIn("saldo-administratie", out["blokkade"])

    def test_unexplained_jump_blocks_until_recorded(self):
        st = copy.deepcopy(OLD_STATE)
        self.run_at(self.fake(), self.c(), st)
        f = self.fake(nav=11495.05)
        f.closed = lambda: []
        out = self.run_at(f, self.c(), st, now=NOW + timedelta(minutes=3))
        self.assertIn("onverklaarde saldowijziging", out["blokkade"])
        c = self.c()
        c["administratie"]["geldstromen"].append(dict(t=(NOW + timedelta(minutes=2)).isoformat(), bedrag=500.0))
        out = self.run_at(f, c, st, now=NOW + timedelta(minutes=6))
        self.assertIsNone(out["blokkade"])
        self.assertEqual(out["administratie"]["handelsresultaat"], -4.95)

    def test_state_survives_json_round_trip(self):
        st = copy.deepcopy(OLD_STATE)
        self.run_at(self.fake(), self.c(), st)
        st = json.loads(json.dumps(st, default=str))
        out = self.run_at(self.fake(), self.c(), st, now=NOW + timedelta(minutes=3))
        self.assertEqual(out["administratie"]["handelsresultaat"], -4.95)
        self.assertEqual(len([x for x in st["log"] if x["actie"] == "administratie"]), 1)     # eenmalig gemigreerd

    def test_deposit_recorded_afterwards_does_not_leave_inflated_peak(self):
        # storting van 2000 terwijl er een positie openstaat: geen saldocontrole mogelijk, dus eerst als winst geteld
        st = copy.deepcopy(OLD_STATE)
        self.run_at(self.fake(), self.c(), st)
        f = self.fake(nav=12995.05)
        f.pos.append(dict(deal_id="X", epic="SILVER", side=1, size=1.0, level=50.0, stop=49.0, tp=52.0, created=NOW,
                          upl=0.0, bid=50.0, ask=50.01))
        t1 = NOW + timedelta(minutes=3)
        st["equity"].append([t1.isoformat(timespec="minutes"), 12995.05])
        self.run_at(f, self.c(), st, now=t1)
        self.assertAlmostEqual(st["administratie"]["resultaat_piek"], 1995.05)       # zonder vastlegging: "winst"
        # nu vastgelegd: piek opnieuw afgeleid, geen valse totaalgrens
        c = self.c()
        c["administratie"]["geldstromen"].append(dict(t=(NOW + timedelta(minutes=1)).isoformat(), bedrag=2000.0))
        f2 = self.fake(nav=12995.05)
        out = self.run_at(f2, c, st, now=NOW + timedelta(minutes=6))
        self.assertEqual(st["administratie"]["resultaat_piek"], 0.0)
        self.assertIsNone(out["blokkade"])
        self.assertEqual(out["administratie"]["handelsresultaat"], -4.95)
        self.assertAlmostEqual(out["grens"], 12500.0, places=2)
        self.assertTrue(st["administratie"]["herberekend"])

    def test_unknown_start_capital_blocks_without_crash(self):
        c = self.c()
        c["administratie"] = {}
        st = copy.deepcopy(OLD_STATE)
        st["start_saldo"] = 0.0
        out = self.run_at(self.fake(), c, st)
        self.assertIn("startkapitaal onbekend", out["blokkade"])

    def test_balance_below_risk_capital_is_explicit(self):
        c = self.c()
        c["administratie"]["geldstromen"] = []                   # alleen 1000 ingelegd, maar risicobasis 10000
        out = self.run_at(self.fake(nav=995.05), c, dict(copy.deepcopy(OLD_STATE), piek=1000.26, dag_start=995.05,
                                                          equity=copy.deepcopy(EQUITY[:3])))
        self.assertIn("lager dan risicobasis", out["blokkade"])

    def test_account_change_resets_administration(self):
        st = copy.deepcopy(OLD_STATE)
        self.run_at(self.fake(), self.c(), st)
        st["account"] = "ANDER"
        self.run_at(self.fake(), self.c(), st, now=NOW + timedelta(minutes=3))
        self.assertTrue(any(x["actie"] == "ander account" for x in st["log"]))
        self.assertIsNone(st["administratie"]["migratie"]["oud"]["piek"])     # nieuwe administratie, niet die van het oude account


if __name__ == "__main__":
    unittest.main()
