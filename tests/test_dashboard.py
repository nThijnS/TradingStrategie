"""Dashboard (docs/index.html): demoFigures() rekent de getallen en de grafiekreeks van het demo-blok uit demo.json.
De functie wordt uit de pagina gehaald en met Node op de uitvoer van een echte runnerronde gedraaid. Zonder Node
worden deze tests overgeslagen."""
import json
import re
import shutil
import subprocess
import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_administratie import NOW, DepositRounds  # noqa: E402

NODE = shutil.which("node")


def figures(demo):
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    fn = re.search(r"^function demoFigures\(D\) \{.*?^\}$", html, re.S | re.M).group(0)
    js = (f"const nlDT = s => String(s);\n{fn}\n"
          f"process.stdout.write(JSON.stringify(demoFigures({json.dumps(demo)})));")
    return json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True).stdout)


@unittest.skipUnless(NODE, "node niet gevonden")
class DemoFigures(DepositRounds):
    def demo(self, provisional=True):
        st, f, out = self.provisional_round()
        if not provisional:
            c = self.c()
            c["administratie"]["geldstromen"].append(dict(t=(NOW + timedelta(minutes=1)).isoformat(), bedrag=1000.0))
            out = self.run_at(f, c, st, now=NOW + timedelta(minutes=23))
        return json.loads(json.dumps(out, default=str))

    def test_unresolved_post_shows_provisional_not_profit(self):
        d = self.demo()
        F = figures(d)
        self.assertTrue(F["provisional"])
        self.assertIsNone(F["result"])                     # geen +950,05 als handelsresultaat
        self.assertIsNone(F["pct"])
        self.assertIsNone(F["dayPct"])
        self.assertIsNone(F["dayUsed"])
        self.assertIsNone(F["totUsed"])
        self.assertEqual((F["unexplained"], F["confirmed"], F["inclUnexplained"]), (1000.0, -4.95, 950.05))

    def test_chart_matches_confirmed_value(self):
        d = self.demo()
        F = figures(d)
        self.assertEqual(F["series"], d["administratie"]["equity_zonder_geldstromen"])
        self.assertAlmostEqual(F["series"][-1][1] - d["administratie"]["startkapitaal"], F["confirmed"], places=2)
        self.assertIn("voorlopig", F["seriesLabel"])
        self.assertNotIn(1950.05, [v for _, v in F["series"]])

    def test_final_after_recording(self):
        d = self.demo(provisional=False)
        F = figures(d)
        self.assertFalse(F["provisional"])
        self.assertEqual(F["result"], -49.95)
        self.assertAlmostEqual(F["pct"], -0.4995, places=6)
        self.assertEqual(F["series"], d["administratie"]["equity_zonder_geldstromen"])
        self.assertNotIn("voorlopig", F["seriesLabel"])

    def test_old_demo_json_with_open_post_is_provisional(self):
        # demo.json van vóór dit veld (handelsresultaat = NAV - inleg, geen status) met een onverklaarde post
        d = self.demo()
        a = d["administratie"]
        for k in ("handelsresultaat_status", "handelsresultaat_bevestigd", "bevestigd_t", "onverklaard_bedrag",
                  "handelsresultaat_incl_onverklaard", "equity_voorlopig"):
            a.pop(k)
        a["handelsresultaat"] = 950.05
        F = figures(d)
        self.assertTrue(F["provisional"])
        self.assertIsNone(F["result"])
        self.assertEqual(F["series"], [])                  # de oude reeks kan de storting bevatten

    def test_without_administration_unchanged(self):
        d = dict(nav=1010.0, start_saldo=1000.0, dag_start=1000.0, piek=1020.0, equity=[["2026-11-03T14:00+00:00", 1010.0]])
        F = figures(d)
        self.assertFalse(F["provisional"])
        self.assertAlmostEqual(F["result"], 10.0)
        self.assertEqual(F["series"], d["equity"])


if __name__ == "__main__":
    unittest.main()
