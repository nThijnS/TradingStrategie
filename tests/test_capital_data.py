"""Capital-data (research/capital_data.py): alleen lezen, vaste marktkeuze en vensters onder de candlegrens."""
import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research import capital_data as cd

ROOT = Path(__file__).resolve().parents[1]


class Fake:
    def __init__(self, tree):
        self.tree, self.paden = tree, []

    def get(self, path):
        self.paden.append(path)
        return self.tree[path]


class Veiligheid(unittest.TestCase):
    def test_module_never_names_a_write_call(self):
        tree = ast.parse((ROOT / "research" / "capital_data.py").read_text())
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertFalse(attrs & {"call", "place_market", "place_limit", "_place", "close_position", "cancel", "select_account"})

    def test_workflow_read_only(self):
        y = (ROOT / ".github" / "workflows" / "capitaldata.yml").read_text()
        self.assertIn("contents: read", y)
        self.assertNotIn("contents: write", y)
        self.assertNotIn("LIVE", y)


class Keuze(unittest.TestCase):
    def markt(self, soort, bid, offer):
        return dict(instrumentType=soort, bid=bid, offer=offer)

    def test_rule_is_on_spread_and_keeps_known_markets(self):
        m = dict(A=self.markt("CRYPTOCURRENCIES", 100, 100.1), B=self.markt("CRYPTOCURRENCIES", 100, 101), C=self.markt("SHARES", 100, 100.01))
        self.assertEqual(cd.kies(m, ["ZZ"]), ["A", "ZZ"])

    def test_cap_per_type_takes_lowest_spreads(self):
        m = {f"E{i}": self.markt("INDICES", 100000, 100000 + i + 1) for i in range(30)}
        out = cd.kies(m)
        self.assertEqual(len(out), cd.REGEL["INDICES"][1])
        self.assertIn("E0", out)

    def test_missing_quote_skipped(self):
        self.assertEqual(cd.kies(dict(A=dict(instrumentType="INDICES", bid=None, offer=None))), [])


class Vensters(unittest.TestCase):
    def test_no_gap_and_under_limit(self):
        e = datetime(2026, 11, 4, tzinfo=timezone.utc)
        w = list(cd.vensters(e, 730))
        self.assertEqual(w[-1][1], e)
        for (a, b), (c, _) in zip(w, w[1:]):
            self.assertEqual(b, c)
        self.assertTrue(all((b - a).total_seconds() / 3600 <= 1000 for a, b in w))


class Navigatie(unittest.TestCase):
    def test_walks_only_requested_groups(self):
        f = Fake({"/marketnavigation": dict(nodes=[dict(id="c", name="Cryptocurrencies"), dict(id="s", name="Shares")]),
                  "/marketnavigation/c?limit=500": dict(nodes=[dict(id="c2", name="x")], markets=[dict(epic="BTC")]),
                  "/marketnavigation/c2?limit=500": dict(nodes=[], markets=[dict(epic="ETH")])})
        self.assertEqual(set(cd.crawl(f)), {"BTC", "ETH"})
        self.assertFalse(any("/s?" in p for p in f.paden))


if __name__ == "__main__":
    unittest.main()
