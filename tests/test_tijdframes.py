"""Tijdframeonderzoek (research/tijdframes.py): geen vooruitkijken, geen dubbele trades en de echte risicolimieten."""
import ast
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from backtesting import engine
from research import tijdframes as tf
from strategies import lab as strat

ROOT = Path(__file__).resolve().parents[1]
PROTO, _ = tf.load_protocol()
START = pd.Timestamp("2026-03-02 10:00", tz="UTC")


def candles(n, freq="5min", start=START, seed=1, drift=0.0):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(drift, 0.05, n))
    o = np.concatenate([[100.0], c[:-1]])
    idx = pd.date_range(start, periods=n, freq=freq)
    return pd.DataFrame(dict(Open=o, High=np.maximum(o, c) + 0.02, Low=np.minimum(o, c) - 0.02, Close=c), index=idx)


def trade(market="NQ", side=1, start=0, hours=1, R=1.0, id_=None):
    t = START + pd.Timedelta(hours=start)
    return dict(id=id_ or f"{market}|{start}|{side}", markt=market, kant=side, entry=100.0, risk=1.0, t=t,
                t_uit=t + pd.Timedelta(hours=hours), R=R, R15=R, rr=2.0)


class Protocol(unittest.TestCase):
    def test_four_prescribed_variants_and_baseline_first(self):
        self.assertEqual(list(PROTO["varianten"]), ["V1_1h", "V2_4h_1h", "V3_15m", "V4_5m"])
        self.assertEqual(PROTO["varianten"]["V1_1h"], dict(titel="Huidige 1h-baseline", signaal="1h", context=[], trigger=None))

    def test_one_minute_is_not_a_strategy_variant(self):
        for v in PROTO["varianten"].values():
            self.assertNotEqual(v["signaal"], "1min")
            self.assertNotEqual(v["trigger"], "1min")
            self.assertNotIn("1min", v["context"])

    def test_tests_exactly_ten_base_strategies(self):
        self.assertEqual(len(tf.base_params()), 10)
        self.assertEqual(PROTO["poort"]["proeven_per_markt"], 10 * len(PROTO["varianten"]))

    def test_limits_match_the_active_rules(self):
        from risk.rules import Limits
        lim, u = Limits(), PROTO["uitvoerbaarheid"]
        self.assertEqual((u["max_spread_r"], u["risico_pct"], u["hefboom"]), (lim.max_spread_r, lim.risico_pct, lim.hefboom))

    def test_module_cannot_reach_the_broker(self):
        tree = ast.parse((ROOT / "research" / "tijdframes.py").read_text())
        names = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        names += [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse([n for n in names if n.startswith("execution")])


class NoLookAhead(unittest.TestCase):
    def test_context_known_only_after_the_candle_closed(self):
        idx = pd.date_range(START, periods=30, freq="4h")
        ctx = pd.DataFrame(dict(e20=np.arange(30.0), e50=np.full(30, 10.5)), index=idx)
        low = pd.date_range(START, periods=30 * 16, freq="15min")
        st = tf.closed_state(ctx, low, tf.BARS["15min"], tf.BARS["4h"])
        first_up = idx[11]                                    # e20 (11) > e50 (10,5) op deze candle
        self.assertEqual(st[first_up + pd.Timedelta(hours=3, minutes=30)], -1)   # sluit om +3:45: nog onbekend
        self.assertEqual(st[first_up + pd.Timedelta(hours=3, minutes=45)], 1)    # sluit om +4:00: dan bekend

    def test_changing_the_future_does_not_change_the_past(self):
        df = candles(4000, "15min")
        hi = tf.resample(df, "4h")
        a = tf.closed_state(strat.indicators(hi), df.index, tf.BARS["15min"], tf.BARS["4h"])
        later = df.copy()
        later.iloc[3000:, :] *= 1.5
        b = tf.closed_state(strat.indicators(tf.resample(later, "4h")), df.index, tf.BARS["15min"], tf.BARS["4h"])
        pd.testing.assert_series_equal(a.iloc[:2900], b.iloc[:2900])

    def test_trigger_uses_only_closed_candles(self):
        df = candles(40)
        B = engine.Bars(df)
        t = df.index[10]
        out = tf.apply_trigger([dict(t=t, setup=t, side=1, stopd=1.0, target=("R", 2.0), mid=100.0)], B, 6)
        for s in out:
            self.assertGreater(s["t"], t)
            j = int(B.t.searchsorted(s["t"])) - 1
            self.assertGreater(B.c[j], B.h[j - 1])

    def test_no_trigger_means_no_setup(self):
        df = candles(40)
        df["Close"] = df["Open"]
        df["High"], df["Low"] = df["Open"] + 1, df["Open"] - 1     # nooit een slot voorbij de vorige high
        t = df.index[10]
        self.assertEqual(tf.apply_trigger([dict(t=t, setup=t, side=1, stopd=1.0, target=("R", 2.0), mid=100.0)], engine.Bars(df), 6), [])


class Execute(unittest.TestCase):
    def setUp(self):
        self.df = candles(600).tz_convert("America/New_York")
        self.B = engine.Bars(self.df)

    def run_setups(self, setups, spread=0.0001):
        return tf.execute("NQ", "index", setups, self.B, 0.0002, 0.0, spread, PROTO, 20, "fam|{}")

    def setup(self, i, stopd=1.0):
        t = self.df.index[i]
        return dict(t=t, setup=t, side=1, stopd=stopd, target=("R", 2.0), mid=100.0)

    def test_same_setup_is_never_two_trades(self):
        trades, c = self.run_setups([self.setup(5), self.setup(5)])
        self.assertEqual(len(trades), 1)
        self.assertEqual(len({x["id"] for x in trades}), 1)
        self.assertEqual(c["strategie heeft al een positie"] + c["dubbel"], 1)

    def test_one_position_per_strategy(self):
        trades, c = self.run_setups([self.setup(5, stopd=20.0), self.setup(7, stopd=20.0)])
        self.assertEqual(len(trades), 1)
        self.assertEqual(c["strategie heeft al een positie"], 1)

    def test_spread_rule_rejects_tight_stop(self):
        trades, c = self.run_setups([self.setup(5, stopd=0.5)], spread=0.002)   # spread 0,2 > 0,25 x 0,5
        self.assertEqual(trades, [])
        self.assertEqual(c["spread groter dan 0,25R"], 1)

    def test_too_late_signal_is_skipped(self):
        late = self.df.index[-1] + pd.Timedelta(minutes=1)
        trades, c = self.run_setups([dict(self.setup(5), t=late)])
        self.assertEqual(trades, [])
        self.assertEqual(c["data op"], 1)

    def test_gap_after_signal_is_skipped(self):
        df = self.df.drop(self.df.index[6:40])                    # markt 2,8 uur weg na de signaalcandle
        B = engine.Bars(df)
        s = self.setup(5)
        s["t"] = self.df.index[6]
        trades, c = tf.execute("NQ", "index", [s], B, 0.0002, 0.0, 0.0001, PROTO, 20, "fam|{}")
        self.assertEqual(trades, [])
        self.assertEqual(c["markt dicht"], 1)

    def test_closed_market_rejected(self):
        self.assertEqual(tf.reject_reason("NQ", "index", pd.Timestamp("2026-03-07 12:00", tz="UTC"), 100, 1, 0.01, PROTO), "markt dicht")

    def test_friday_close_rejected(self):
        t = pd.Timestamp("2026-03-06 16:57", tz="America/New_York")
        self.assertEqual(tf.reject_reason("NQ", "index", t, 100, 1, 0.01, PROTO), "vlak voor het slot")

    def test_leverage_rejected(self):
        t = pd.Timestamp("2026-03-04 12:00", tz="UTC")
        why = tf.reject_reason("NQ", "index", t, 100, 0.0155, 0.0001, PROTO)    # stop 0,0155%: 32x hefboom
        self.assertEqual(why, "hefboom boven 1:30")


class Portfolio(unittest.TestCase):
    def test_limits_max_three_open(self):
        out = tf.portfolio([trade(m, start=0, hours=5) for m in ("NQ", "EURUSD", "GOUD", "OLIE", "BTC")])
        self.assertEqual(len(out["trades"]), 3)
        self.assertEqual(out["max_open"], 3)

    def test_one_per_correlated_group_same_direction(self):
        out = tf.portfolio([trade("NQ"), trade("ES")])
        self.assertEqual(len(out["trades"]), 1)

    def test_dollar_group_uses_dollar_direction(self):
        self.assertEqual(len(tf.portfolio([trade("EURUSD", 1), trade("USDJPY", -1)])["trades"]), 1)   # beide dollar short
        self.assertEqual(len(tf.portfolio([trade("EURUSD", 1), trade("USDJPY", 1)])["trades"]), 2)

    def test_slot_frees_after_exit(self):
        self.assertEqual(len(tf.portfolio([trade("NQ", start=0), trade("ES", start=1)])["trades"]), 2)

    def test_trade_closed_in_entry_candle_does_not_stay_open(self):
        x = trade("NQ", start=0, hours=0, R=-1.0)
        self.assertEqual(len(tf.portfolio([x, trade("ES", start=1)])["trades"]), 2)

    def test_same_signal_only_once(self):
        out = tf.portfolio([trade("NQ", id_="x"), trade("NQ", id_="x")])
        self.assertEqual(len(out["trades"]), 1)
        self.assertEqual(out["afgewezen"]["dubbel signaal"], 1)

    def test_trailing_limit_stops_new_trades(self):
        losses = [trade("NQ", start=i * 24, hours=1, R=-2.0, id_=f"a{i}") for i in range(10)]
        out = tf.portfolio(losses)
        self.assertLess(len(out["trades"]), 10)
        self.assertLess(out["max_dd_pct"], 6.0)

    def test_correlated_trades_count_as_one_bet(self):
        self.assertEqual(tf.effective_bets([trade("NQ"), trade("ES"), trade("ES", start=1)]), 1)
        self.assertEqual(tf.effective_bets([trade("NQ"), trade("GOUD")]), 2)


class Decision(unittest.TestCase):
    def test_all_parts_needed(self):
        base = dict(per_week=2.0)
        good = dict(n=50, per_week=3.0, gem15=0.1, onder=0.01)
        pf = dict(grensbreuken={})
        self.assertTrue(tf.verdict({}, good, base, dict(gem=0.1), dict(gem=0.1), pf)["interessant"])
        self.assertFalse(tf.verdict({}, dict(good, per_week=2.9), base, dict(gem=0.1), dict(gem=0.1), pf)["interessant"])
        self.assertFalse(tf.verdict({}, dict(good, onder=-0.01), base, dict(gem=0.1), dict(gem=0.1), pf)["interessant"])
        self.assertFalse(tf.verdict({}, good, base, dict(gem=-0.1), dict(gem=0.1), pf)["interessant"])
        self.assertFalse(tf.verdict({}, good, base, dict(gem=0.1), dict(gem=0.1), dict(grensbreuken=dict(dag=1)))["interessant"])

    def test_missing_bootstrap_is_not_a_pass(self):
        v = tf.verdict({}, dict(n=3, per_week=3.0, gem15=0.1, onder=None), dict(per_week=1.0), dict(gem=0.1), dict(gem=0.1), dict(grensbreuken={}))
        self.assertFalse(v["na_kosten"])


class Costs(unittest.TestCase):
    def test_cost_uses_highest_of_model_and_measured_plus_slippage(self):
        rep = dict(huidig=dict(GOUD=dict(spread_pct=0.02), ES=dict(spread_pct=0.001)))
        self.assertAlmostEqual(tf.cost_frac("GOUD", rep), 1.5 * 0.0002)
        self.assertAlmostEqual(tf.cost_frac("ES", rep), 1.5 * 0.00008)

    def test_unknown_spread_falls_back_to_model(self):
        self.assertAlmostEqual(tf.cost_frac("ES", {}), 1.5 * 0.00008)
        self.assertIsNone(tf.spread_frac("ES", {}))


if __name__ == "__main__":
    unittest.main()
