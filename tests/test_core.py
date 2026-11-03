"""Configuratie, opslag en data-integriteit."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import fixtures  # noqa: E402
from core import config, data, markets  # noqa: E402
from storage import jsonstore, migrations, paths  # noqa: E402


class Config(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def write(self, name, obj):
        (self.d / name).write_text(json.dumps(obj))
        return self.d / name

    def test_defaults_without_file(self):
        s = config.load_settings(self.d / "bestaat-niet.json")
        self.assertEqual(s, config.DEFAULT_SETTINGS)
        self.assertIsNot(s, config.DEFAULT_SETTINGS)

    def test_merge_and_unknown_keys_ignored(self):
        s = config.load_settings(self.write("c.json", {"markten": {"NQ": False}, "onbekend": 1, "max_per_day": 2}))
        self.assertEqual(s["markten"], {"NQ": False, "EURUSD": True, "GOUD": True})
        self.assertNotIn("onbekend", s)
        self.assertEqual(s["max_per_day"], 2)

    def test_apply_settings_is_idempotent_and_in_place(self):
        cfg_ref, set_ref = config.CFG, config.SET
        c1 = self.write("c1.json", {"markten": {"GOUD": False}, "sessies": {"London": False}})
        none = self.d / "geen-learned.json"
        config.apply_settings(c1, none)
        self.assertEqual([m["name"] for m in config.CFG["markets"]], ["NQ", "EURUSD"])
        self.assertEqual(config.CFG["trade_sess"], [("09:30", "11:30"), ("13:30", "15:30")])
        config.apply_settings(self.write("c2.json", {}), none)       # tweede keer: weer alles aan
        self.assertEqual(len(config.CFG["markets"]), 3)
        self.assertEqual(len(config.CFG["trade_sess"]), 3)
        self.assertIs(config.CFG, cfg_ref)
        self.assertIs(config.SET, set_ref)
        self.assertEqual(config.BASE_CFG["markets"][0]["cfg"], {})  # de standaard zelf blijft ongemoeid

    def test_apply_learned(self):
        learned = self.write("l.json", {"markten": {"NQ": dict(actief=False, cfg=dict(tp_r=1.5), kans_sess=["NY AM"],
                                                               need_bias_b=True, variant="x")}})
        config.apply_settings(self.write("c.json", {}), learned)
        nq, goud = config.CFG["markets"][0], config.CFG["markets"][2]
        self.assertEqual((nq["actief"], nq["cfg"]["tp_r"], nq["cfg"]["need_bias_b"]), (False, 1.5, True))
        self.assertFalse(goud["actief"])                              # learn_only zonder keuze: niet melden
        config.apply_settings(self.write("c.json", {}), self.d / "x.json")

    def test_ntfy_from_env(self):
        with mock.patch.dict("os.environ", {"NTFY_TOPIC": "test-onderwerp"}):
            config.apply_settings(self.d / "x.json", self.d / "y.json")
        self.assertEqual(config.CFG["ntfy_topic"], "test-onderwerp")

    def test_market_definitions_complete(self):
        for m in markets.ICT_MARKETS:
            self.assertTrue({"name", "symbol", "smt", "dec", "cfg", "cost", "histdata"} <= set(m), m["name"])
        names = [m["naam"] for m in markets.LAB_MARKETS + markets.CANDIDATES]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(markets.fin_rate(dict(soort="crypto")), 0.20)
        self.assertEqual(markets.fin_rate(dict(soort="aandeel")), 0.065)


class Storage(unittest.TestCase):
    def test_atomic_save_and_load(self):
        d = Path(tempfile.mkdtemp())
        p = jsonstore.save(d / "a.json", {"x": [1, 2], "é": True})
        self.assertEqual(jsonstore.load(p), {"x": [1, 2], "é": True})
        self.assertFalse((d / "a.json.tmp").exists())
        jsonstore.save(d / "b.json", {"a": 1}, compact=True)
        self.assertEqual((d / "b.json").read_text(), '{"a":1}')
        (d / "kapot.json").write_text("{niet af")
        self.assertEqual(jsonstore.load(d / "kapot.json", "standaard"), "standaard")

    def test_backup_and_restore(self):
        d = Path(tempfile.mkdtemp())
        f = d / "geheugen.json"
        f.write_text('{"a": 1}')
        with mock.patch.object(paths, "BACKUPS", d / "backups"), mock.patch.object(paths, "ROOT", d):
            b = migrations.backup([f], "test")
            f.write_text('{"a": 2}')
            migrations.restore(b)
        self.assertEqual(json.loads(f.read_text()), {"a": 1})

    def test_paths_are_at_repo_root(self):
        # de keten en de website verwachten deze bestanden precies hier
        for p in (paths.CONFIG, paths.LEARNED, paths.LAB, paths.LAB_HISTORY, paths.LEREN_HISTORY, paths.NOODSTOP):
            self.assertEqual(p.parent, ROOT)
        self.assertTrue(paths.CONFIG.exists() and paths.LEARNED.exists() and paths.LAB.exists())


class Data(unittest.TestCase):
    def test_fixture_is_clean(self):
        m1, o1 = fixtures.minute_bars(days=5)
        self.assertEqual(data.check_ohlc(m1), [])
        self.assertEqual(data.check_ohlc(fixtures.hourly_bars(500)), [])

    def test_clean_removes_bad_rows(self):
        idx = pd.date_range("2026-01-05", periods=5, freq="1h", tz="UTC")
        df = pd.DataFrame(dict(Open=[1, 1, 1, 1, 1.0], High=[2, 2, 0.5, 2, 2.0], Low=[0.5, 0.5, 0.4, 0.5, 0.5],
                               Close=[1, 1, 1, 1, 1.0]), index=idx)
        df = pd.concat([df, df.iloc[[1]]])
        df.iloc[3, 0] = float("nan")
        out, q = data.clean(df)
        self.assertEqual((q["dubbel"], q["leeg"], q["ongeldig"], q["candles"]), (1, 1, 1, 3))
        self.assertEqual(data.check_ohlc(out), [])

    def test_resample_4h_starts_at_18_ny(self):
        m1, _ = fixtures.minute_bars(days=3)
        h4 = data.resample(m1, "4h")
        self.assertTrue(set(h4.index.hour) <= {2, 6, 10, 14, 18, 22})
        self.assertAlmostEqual(h4["High"].max(), m1["High"].max())

    def test_histdata_dst_conversion(self):
        """Een HistData-tijd van 08:30 in juli is 08:30 NY (EDT), niet 09:30: de zomertijd-correctie."""
        d = Path(tempfile.mkdtemp())
        (d / "raw").mkdir()
        (d / "raw" / "DAT_ASCII_TEST_M1_2025.csv").write_text("20250715 083000;1;2;0.5;1.5;0\n20250115 083000;1;2;0.5;1.5;0\n")
        with mock.patch.object(paths, "DATA", d), mock.patch.object(paths, "HISTDATA_RAW", d / "raw"):
            new, old = data.load_histdata("TEST"), data.load_histdata_est("TEST")
        self.assertEqual([t.strftime("%m-%d %H:%M") for t in new.index], ["01-15 08:30", "07-15 08:30"])
        self.assertEqual(old.index[1].strftime("%H:%M"), "09:30")   # de oude lader: 1 uur verschoven in de zomer


if __name__ == "__main__":
    unittest.main()
