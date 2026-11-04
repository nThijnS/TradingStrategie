"""Risicologica: positiegrootte, instrument/koers, orderniveaus en portefeuillelimieten.  python -m unittest discover tests"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import risico as r  # noqa: E402

NOW = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)


def inst(**kw):
    d = dict(markt="NQ", epic="US100", ccy="USD", lot_size=1.0, scaling=1.0, min_size=0.01, max_size=None, step=0.01,
             decimals=1, min_stop=2.0, max_stop=None, bid=20000.0, ask=20001.0, status="TRADEABLE", quote_time=NOW)
    d.update(kw)
    return r.Instrument(**d)


def sig(**kw):
    d = dict(kant="LONG", entry=20000.0, stop=19960.0, tp=20080.0, soort="MARKET", ref=20000.5)
    d.update(kw)
    return d


def book(**kw):
    d = dict(equity=10000.0, day_start=10000.0, peak=10000.0, start=10000.0, open_risks=[], exposures=[], used_notional=0.0)
    d.update(kw)
    return r.Book(**d)


class Instrument(unittest.TestCase):
    def test_contract_size_must_be_verified(self):
        self.assertIn("contractgrootte", r.check_instrument(inst(lot_size=10)))
        self.assertIn("contractgrootte", r.check_instrument(inst(scaling=100)))
        self.assertIsNone(r.check_instrument(inst()))

    def test_quote_checks(self):
        self.assertIsNone(r.check_quote(inst(), NOW, 180))
        self.assertIn("s oud", r.check_quote(inst(quote_time=NOW - timedelta(minutes=5)), NOW, 180))
        self.assertIsNone(r.check_quote(inst(quote_time=NOW - timedelta(seconds=180)), NOW, 180))
        self.assertIn("onbekend", r.check_quote(inst(quote_time=None), NOW, 180))
        self.assertIn("toekomst", r.check_quote(inst(quote_time=NOW + timedelta(hours=1)), NOW, 180))
        self.assertIsNone(r.check_quote(inst(quote_time=NOW + timedelta(seconds=30)), NOW, 180))
        self.assertIn("niet verhandelbaar", r.check_quote(inst(status="CLOSED"), NOW, 180))
        self.assertIn("ongeldige koers", r.check_quote(inst(bid=0), NOW, 180))
        self.assertIn("ongeldige koers", r.check_quote(inst(bid=20002, ask=20001), NOW, 180))


class Levels(unittest.TestCase):
    lim = r.Limits()

    def test_market_order_keeps_distances_and_rounds(self):
        p, why = r.plan_levels(sig(), inst(), self.lim)
        self.assertIsNone(why)
        self.assertEqual((p.entry, p.stop, p.tp), (20001.0, 19961.0, 20081.0))   # instap op de ask

    def test_wrong_side_rejected(self):
        _, why = r.plan_levels(sig(stop=20040.0), inst(), self.lim)
        self.assertIn("verkeerde kant", why)

    def test_spread_too_wide(self):
        _, why = r.plan_levels(sig(), inst(ask=20015.0), self.lim)   # spread 15 > 0,25 x 40
        self.assertIn("spread", why)

    def test_price_drifted_too_far(self):
        _, why = r.plan_levels(sig(), inst(bid=20020.0, ask=20021.0), self.lim)   # 21/40 = 0,52R
        self.assertIn("van het signaal weg", why)

    def test_target_from_data_unless_minimum_set(self):
        p, why = r.plan_levels(sig(tp=20060.0), inst(), self.lim)          # 1:1,5 mag: het doel komt uit de data
        self.assertIsNone(why)
        _, why = r.plan_levels(sig(tp=20060.0), inst(), r.Limits(min_rr=2.0))   # optionele ondergrens
        self.assertIn("risk/reward", why)

    def test_limit_beyond_market(self):
        _, why = r.plan_levels(sig(soort="LIMIT", entry=20005.0, stop=19965.0, tp=20085.0), inst(), self.lim)
        self.assertIn("limietprijs", why)

    def test_basis_shift_for_limit(self):
        p, why = r.plan_levels(sig(soort="LIMIT", entry=19990.0, stop=19950.0, tp=20070.0), inst(), self.lim, basis=-3.0)
        self.assertIsNone(why)
        self.assertEqual((p.entry, p.stop, p.tp), (19987.0, 19947.0, 20067.0))

    def test_min_stop_distance(self):
        _, why = r.plan_levels(sig(stop=19999.0), inst(min_stop=2.0, ask=20000.2), self.lim)
        self.assertTrue("brokerminimum" in why or "spread" in why)


class Sizing(unittest.TestCase):
    def test_size_includes_costs(self):
        lim = r.Limits(risico_pct=0.5, slippage_r=0.05)
        p, _ = r.plan_levels(sig(), inst(), lim)
        self.assertIsNone(r.size_plan(p, inst(), lim, 10000.0, 1.0))
        # budget 50; per unit 40 (stop) + 1 (spread) + 2 (slippage) = 43 -> 1,16
        self.assertAlmostEqual(p.size, 1.16)
        self.assertLessEqual(p.risico_acc, 50.0 + 1e-9)

    def test_currency_conversion(self):
        lim = r.Limits()
        p, _ = r.plan_levels(sig(), inst(), lim)
        r.size_plan(p, inst(), lim, 10000.0, 0.5)      # 1 USD = 0,5 accountvaluta: dubbele grootte
        self.assertAlmostEqual(p.size, 2.32)

    def test_too_small_and_missing_fx(self):
        lim = r.Limits()
        p, _ = r.plan_levels(sig(), inst(), lim)
        self.assertIn("te klein", r.size_plan(p, inst(min_size=5.0), lim, 10000.0, 1.0))
        self.assertIn("wisselkoers", r.size_plan(p, inst(), lim, 10000.0, None))

    def test_max_size_cap(self):
        lim = r.Limits()
        p, _ = r.plan_levels(sig(), inst(), lim)
        r.size_plan(p, inst(max_size=0.5), lim, 10000.0, 1.0)
        self.assertEqual(p.size, 0.5)

    def test_floor_step(self):
        self.assertEqual(r.floor_step(0.3, 0.1), 0.3)
        self.assertEqual(r.floor_step(1234.9, 1), 1234)


class Portfolio(unittest.TestCase):
    def plan(self, risk=50.0, side=1, notional=20000.0):
        return r.Plan(side=side, soort="MARKET", entry=1, stop=0, tp=2, size=1, risico_acc=risk, notional_acc=notional)

    def test_ok(self):
        self.assertIsNone(r.check_portfolio(book(), r.Limits(), self.plan(), "NQ"))

    def test_max_open_risk_with_simultaneous_signals(self):
        lim, b = r.Limits(max_open_risico_pct=1.5, max_open=5, max_per_groep=5), book()
        approved = 0
        for m in ("NQ", "GOUD", "EURUSD", "BTC"):
            p = self.plan()
            if r.check_portfolio(b, lim, p, m) is None:
                r.add_to_book(b, p, m)
                approved += 1
        self.assertEqual(approved, 3)            # 3 x 0,5% = 1,5%; de vierde past niet meer

    def test_day_limit_worst_case(self):
        lim = r.Limits(max_open_risico_pct=2.9)
        b = book(equity=9750.0, day_start=10000.0)    # al 2,5% verlies vandaag
        self.assertIn("daglimiet", r.check_portfolio(b, lim, self.plan(60.0), "NQ"))

    def test_trailing_total_limit(self):
        b = book(equity=9520.0, peak=10000.0)
        self.assertIn("maximale-verliesgrens", r.check_portfolio(b, r.Limits(dagverlies_pct=9), self.plan(), "NQ"))
        self.assertIn("maximaal verlies geraakt", r.check_portfolio(book(equity=9490.0, peak=10000.0, day_start=9490.0), r.Limits(), self.plan(), "NQ"))

    def test_position_without_stop_blocks(self):
        self.assertIn("zonder stop", r.check_portfolio(book(open_risks=[None], exposures=[("GOUD", 1)]), r.Limits(), self.plan(), "NQ"))

    def test_correlated_group(self):
        b = book(open_risks=[40.0], exposures=[("NQ", 1)])
        self.assertIn("groep", r.check_portfolio(b, r.Limits(), self.plan(side=1), "NVDA"))
        self.assertIsNone(r.check_portfolio(b, r.Limits(), self.plan(side=-1), "ES"))     # andere richting mag

    def test_dollar_direction(self):
        b = book(open_risks=[40.0], exposures=[("EURUSD", 1)])    # EURUSD long = dollar short
        self.assertIn("groep", r.check_portfolio(b, r.Limits(), self.plan(side=-1), "USDJPY"))   # ook dollar short
        self.assertIsNone(r.check_portfolio(b, r.Limits(), self.plan(side=1), "USDJPY"))

    def test_leverage(self):
        self.assertIn("hefboom", r.check_portfolio(book(used_notional=290000.0), r.Limits(), self.plan(notional=20000.0), "NQ"))

    def test_max_open(self):
        b = book(open_risks=[1.0] * 3, exposures=[("BTC", 1), ("GOUD", 1), ("DAX", 1)])
        self.assertIn("max 3", r.check_portfolio(b, r.Limits(), self.plan(), "EURUSD"))


class LimitSanity(unittest.TestCase):
    def test_live_is_stricter(self):
        lim = r.Limits(risico_pct=1.5)
        self.assertEqual(lim.problems(live=False), [])
        self.assertTrue(any("risico_pct" in p for p in lim.problems(live=True)))

    def test_open_risk_below_day_limit(self):
        self.assertTrue(r.Limits(max_open_risico_pct=3.0, dagverlies_pct=3.0).problems())


if __name__ == "__main__":
    unittest.main()
