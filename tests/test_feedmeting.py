"""Feedmeting (research/feedmeting.py): alleen lezen, geen geheimen in uitvoer en een streng oordeel over de feed."""
import ast
import unittest
from pathlib import Path

import pandas as pd

from research import feedmeting as fm

ROOT = Path(__file__).resolve().parents[1]
GOOD = dict(rest_metingen=10, vertraging_max=0, max_leeftijd_s=None, niet_verhandelbaar=0,
            ws=dict(updates=500, grootste_gat_s=10.0, ontbrekende_candles_pct=0.0, verbroken=0, leeftijd_max_s=1.0))


class FakeClient:
    h = {"CST": "cst-geheim"}

    def __init__(self):
        self.calls = []

    def call(self, method, path, body=None, order=False):
        self.calls.append((method, path))
        return {}


def price(t, bid=100.0, ask=100.2):
    p = dict(bid=bid, ask=ask)
    return dict(snapshotTimeUTC=t, openPrice=p, highPrice=dict(bid=bid + 1, ask=ask + 1), lowPrice=dict(bid=bid - 1, ask=ask - 1), closePrice=p)


class ReadOnlySafety(unittest.TestCase):
    def test_only_get_goes_out(self):
        c = FakeClient()
        fm.ReadOnly(c).get("/markets/US100")
        self.assertEqual(c.calls, [("GET", "/markets/US100")])

    def test_wrapper_has_no_write_method(self):
        self.assertEqual({n for n in dir(fm.ReadOnly) if not n.startswith("_")}, {"get", "tokens"})

    def test_module_never_names_an_order_call(self):
        src = (ROOT / "research" / "feedmeting.py").read_text()
        tree = ast.parse(src)
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertFalse(attrs & {"place_market", "place_limit", "_place", "call", "close_position", "cancel", "select_account"} - {"call"})
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "call"]
        self.assertEqual([c.args[0].value for c in calls], ["GET"])       # enkel ReadOnly.get

    def test_workflow_has_read_only_repo_rights_and_no_live_secrets(self):
        y = (ROOT / ".github" / "workflows" / "feedmeting.yml").read_text()
        self.assertIn("contents: read", y)
        self.assertNotIn("contents: write", y)
        self.assertNotIn("LIVE", y)


class Scrub(unittest.TestCase):
    def test_tokens_removed(self):
        out = fm.scrub('fout cst="abc123" X-SECURITY-TOKEN: def456 password=hunter2')
        for s in ("abc123", "def456", "hunter2"):
            self.assertNotIn(s, out)

    def test_known_secret_removed(self):
        self.assertEqual(fm.scrub("waarde geheim-1 lekt", ["geheim-1"]), "waarde *** lekt")

    def test_stream_keeps_no_raw_messages(self):
        st = fm.Stream(["US100"])
        st.handle(dict(destination="quote", cst="cst-geheim", payload=dict(epic="US100", bid=1, ofr=2, timestamp=1)), 1.0)
        self.assertNotIn("cst-geheim", repr(st.__dict__))


class Credentials(unittest.TestCase):
    def test_whitespace_stripped_like_the_runner(self):
        env = dict(CAPITAL_API_KEY=" k\n", CAPITAL_IDENTIFIER="i\n", CAPITAL_PASSWORD="p ")
        self.assertEqual(fm.credentials(env), ("k", "i", "p"))


class Health(unittest.TestCase):
    def test_good_feed(self):
        self.assertEqual(fm.feed_health(GOOD, True), dict(oordeel="bruikbaar", redenen=[]))

    def test_closed_market_proves_nothing(self):
        self.assertEqual(fm.feed_health(GOOD, False)["oordeel"], "niet gemeten")

    def test_each_problem_marks_unusable(self):
        bad = [dict(GOOD, max_leeftijd_s=fm.MAX_AGE_S + 1), dict(GOOD, vertraging_max=5), dict(GOOD, niet_verhandelbaar=1),
               dict(GOOD, rest_metingen=0), dict(GOOD, ws=None), dict(GOOD, ws=dict(GOOD["ws"], updates=0)),
               dict(GOOD, ws=dict(GOOD["ws"], leeftijd_max_s=fm.MAX_AGE_S + 1)), dict(GOOD, ws=dict(GOOD["ws"], leeftijd_max_s=None)),
               dict(GOOD, ws=dict(GOOD["ws"], grootste_gat_s=fm.MAX_GAP_S + 1)), dict(GOOD, ws=dict(GOOD["ws"], ontbrekende_candles_pct=2.0)),
               dict(GOOD, ws=dict(GOOD["ws"], verbroken=1))]
        for row in bad:
            self.assertEqual(fm.feed_health(row, True)["oordeel"], "onbruikbaar", row)


class Candles(unittest.TestCase):
    def test_mid_and_spread(self):
        df = fm.candles(dict(prices=[price("2026-10-20T14:00:00")]))
        self.assertAlmostEqual(df["Close"].iloc[0], 100.1)
        self.assertAlmostEqual(df["spread"].iloc[0], 0.2)
        self.assertEqual(str(df.index.tz), "UTC")

    def test_incomplete_candle_skipped(self):
        self.assertEqual(len(fm.candles(dict(prices=[dict(snapshotTimeUTC="2026-10-20T14:00:00")]))), 0)

    def test_spread_by_hour(self):
        df = fm.candles(dict(prices=[price("2026-10-20T14:00:00"), price("2026-10-20T15:00:00", ask=100.4)]))
        s = fm.spread_by_hour(df)
        self.assertLess(s[14], s[15])

    def test_boundaries(self):
        idx = pd.date_range("2026-10-20", periods=4, freq="5min", tz="UTC")
        self.assertTrue(fm.boundaries_ok(pd.DataFrame(dict(Close=1.0), index=idx), 5))
        self.assertFalse(fm.boundaries_ok(pd.DataFrame(dict(Close=1.0), index=idx + pd.Timedelta(minutes=1)), 5))

    def test_compare_finds_a_shifted_clock(self):
        idx = pd.date_range("2026-10-20", periods=200, freq="1h", tz="UTC")
        c = pd.Series(range(200), index=idx, dtype=float) % 17 + 100
        a = pd.DataFrame(dict(Close=c))
        b = a.copy()
        b.index = b.index + pd.Timedelta(minutes=60)
        self.assertEqual(fm.compare(a, b)["beste_verschuiving_min"], 60)
        self.assertEqual(fm.compare(a, a)["beste_verschuiving_min"], 0)


class FutureTime(unittest.TestCase):
    def test_time_far_in_the_future_is_not_a_fresh_quote(self):
        out = fm.poll_summary([dict(age=-3599.0, velden=["updateTime"], status="TRADEABLE", delay=0, spread_pct=0.01)])
        self.assertIsNone(out["max_leeftijd_s"])
        self.assertEqual(out["tijdvelden"], dict(updateTime=1))

    def test_stale_stream_marks_unusable_even_with_future_rest_time(self):
        row = dict(GOOD, ws=dict(GOOD["ws"], leeftijd_max_s=500.0))
        self.assertEqual(fm.feed_health(row, True)["oordeel"], "onbruikbaar")


class History(unittest.TestCase):
    def test_probe_window_is_a_weekday_and_under_the_candle_limit(self):
        from datetime import datetime, timezone
        for d in fm.PROBE_DAYS:
            a, b = fm.probe_window(datetime(2026, 11, 4, tzinfo=timezone.utc), d)
            self.assertEqual(a.weekday(), 2)
            self.assertLessEqual((b - a).total_seconds() / 60, 1000)

    def test_candles_outside_the_window_do_not_count(self):
        from datetime import datetime, timezone

        class Latest:
            def get(self, path):
                return dict(prices=[price("2026-11-03T12:00:00")])      # negeert from/to
        out = fm.history(Latest(), "US100", datetime(2026, 11, 4, tzinfo=timezone.utc))
        self.assertEqual(set(out.values()), {0})


class StreamCounters(unittest.TestCase):
    def quote(self, st, t, bid=1.0, ts=None):
        st.handle(dict(destination="quote", payload=dict(epic="US100", bid=bid, ofr=bid + 1, timestamp=ts if ts is not None else t)), t)

    def test_counts_duplicates_gaps_and_backward_time(self):
        st = fm.Stream(["US100"])
        self.quote(st, 1.0)
        self.quote(st, 1.0)                        # dubbel
        self.quote(st, 200.0, bid=2.0)             # gat van 199 s
        self.quote(st, 201.0, bid=3.0, ts=5.0)     # tijd loopt terug
        s = st.summary("US100", 10)
        self.assertEqual((s["updates"], s["dubbel"], s["terug_in_tijd"]), (4, 1, 1))
        self.assertAlmostEqual(s["grootste_gat_s"], 199.0)

    def test_missing_one_minute_candles(self):
        st = fm.Stream(["US100"])
        for t in (0, 60, 180):
            st.handle(dict(destination="ohlc.event", payload=dict(epic="US100", resolution="MINUTE", t=t * 1000)), 1.0)
        self.assertEqual(st.summary("US100", 10)["ontbrekende_candles_pct"], 25.0)

    def test_quote_age_and_candle_close(self):
        st = fm.Stream(["US100"])
        st.handle(dict(destination="quote", payload=dict(epic="US100", bid=1, ofr=2, timestamp=100000)), 1.0, 100.5)
        for t, wall in ((60, 61.0), (120, 121.5)):
            st.handle(dict(destination="ohlc.event", payload=dict(epic="US100", resolution="MINUTE", t=t * 1000)), 1.0, wall)
        s = st.summary("US100", 1)
        self.assertEqual(s["leeftijd_max_s"], 0.5)
        self.assertEqual(s["candle_slot_na_s"], 1.5)

    def test_unknown_epic_ignored(self):
        st = fm.Stream(["US100"])
        st.handle(dict(destination="quote", payload=dict(epic="ANDERS", bid=1, ofr=2, timestamp=1)), 1.0)
        self.assertEqual(st.summary("US100", 1)["updates"], 0)


if __name__ == "__main__":
    unittest.main()
