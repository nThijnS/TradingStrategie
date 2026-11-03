#!/usr/bin/env python3
"""Hoeveel veranderen de ICT-uitkomsten door de centrale engine, en waardoor? (lokaal, HistData nodig)

Vergelijkt met tests/golden/histdata_oude_code.json (de oude leren.simulate5 op 5m en backtest.simulate op 1m,
vastgelegd vóór de refactor). Zelfde protocol: NY AM, max 1 trade per dag, max 5 uur, train 2025 / test 2026.
Stap voor stap worden de oude eigenaardigheden uitgezet, zodat elk verschil een oorzaak krijgt:
  oud-nagebootst  engine met de oude regels (TP telt in de vulcandle, 5u05m/5u01m, DOL-terugval 2R bij leren)
  + vulcandle     doel in de vulcandle telt niet meer
  + 5 uur         precies 5 uur (sluiten op de close van de laatste candle die vóór de deadline eindigt)
  = nieuw         + DOL-terugval zoals de app (cfg tp_r = 1R) — dit is wat leren en de backtests nu gebruiken

    python -m research.engine_vergelijking      # schrijft docs/refactor/3_engine_vergelijking.md
"""
import json

import pandas as pd

from backtesting import engine
from backtesting.ict import trade
from core.config import CFG
from core.data import load_histdata, to5
from core.markets import ict_market
from core.sessions import NY, sess_name
from learning.ict import DISP
from storage import paths
from strategies.ict_tjr import analyse

GOLD = paths.ROOT / "tests" / "golden" / "histdata_oude_code.json"
OUT = paths.ROOT / "docs" / "refactor" / "3_engine_vergelijking.md"
SPLIT = pd.Timestamp("2026-01-01", tz=NY)
TICK = {"NQ": 0.25, "EURUSD": 0.00002, "GOUD": 0.1}
TARGETS = ("1.0", "1.5", "2.0", "DOL")


def steps(sim):
    """(naam, exits, dol-terugval in R) per stap; sim = "leren5" (5m) of "bt1m" (1m)."""
    old_h = 5 + 5 / 60 if sim == "leren5" else 5 + 1 / 60
    old_close = None if sim == "leren5" else "16:01"
    new_close = None if sim == "leren5" else "16:00"
    old_fb = 2.0 if sim == "leren5" else 1.0
    return [("oud-nagebootst", engine.Exits(max_hours=old_h, close_at=old_close, tp_on_fill_bar=True), old_fb),
            ("+ vulcandle", engine.Exits(max_hours=old_h, close_at=old_close), old_fb),
            ("+ 5 uur", engine.Exits(max_hours=5, close_at=new_close), old_fb),
            ("= nieuw", engine.Exits(max_hours=5, close_at=new_close), 1.0)]


def run():
    gold = json.loads(GOLD.read_text())
    res = {}
    for mkt in ("NQ", "EURUSD", "GOUD"):
        m = ict_market(mkt)
        sym, smt = m["histdata"]
        m1, o1 = load_histdata(sym), load_histdata(smt)
        m5, o5 = to5(m1), to5(o1)
        B5, B1 = engine.Bars(m5), engine.Bars(m1, bar=pd.Timedelta(minutes=1))
        costs = engine.Costs(price=m["cost"])
        for vn, over in DISP.items():
            setups, _ = analyse(m5, o5, dict(CFG, tick=TICK[mkt], max_per_day=6, **over))
            # zelfde selectie als de golden-opname: NY AM, met entry, eerste per dag (op basis van de oude uitkomst)
            sel, days = [], set()
            for s in setups:
                if sess_name(s["time"]) != "NY AM" or s["entry_hit"] is None or s["time"].date() in days:
                    continue
                days.add(s["time"].date())
                sel.append(s)
            row = dict(setups=len(setups))
            for tg in TARGETS:
                g = gold[f"{mkt}|{vn}"][tg]
                cell = dict(oud=dict(leren5=(g["leren5_2025"], g["leren5_2026"]), bt1m=(g["bt1m_2025"], g["bt1m_2026"]), n=g["n"]))
                for sim, B in (("leren5", B5), ("bt1m", B1)):
                    for name, ex, fb in steps(sim):
                        a = b = 0.0
                        n = 0
                        for s in sel:
                            t = trade(B, s, tg, ex, costs, fb)
                            if t is None or (sim == "leren5" and t.reason == "open"):
                                continue
                            n += 1
                            if s["time"] < SPLIT:
                                a += t.net_r
                            else:
                                b += t.net_r
                        cell.setdefault(sim, {})[name] = (round(a, 2), round(b, 2), n)
                row[tg] = cell
            res[f"{mkt}|{vn}"] = row
            print(mkt, vn, flush=True)
    return res


def report(res):
    L = ["# Engine-vergelijking ICT (HistData, oud tegenover nieuw)", "",
         "Gemaakt met `python -m research.engine_vergelijking`. Protocol: NY AM, max 1 trade per dag, kosten zoals in "
         "`core/markets.py`, R netto, **2025 / 2026**. \"oud\" = de echte oude code (golden-opname vóór de refactor).",
         "", "De ICT-detectie zelf is identiek (zelfde setups, zie `tests/test_golden.py`); alleen de afhandeling van de trade verschilt.", ""]
    for sim, title in (("leren5", "Leren (5m-candles, Yahoo-formaat)"), ("bt1m", "HistData-backtest (1m-candles)")):
        L += [f"## {title}", "", "| markt | variant | doel | oud | oud-nagebootst | + vulcandle | + 5 uur | **nieuw** |", "|---|---|---|---|---|---|---|---|"]
        for key, row in res.items():
            mkt, vn = key.split("|")
            for tg in TARGETS:
                c = row[tg]
                o = c["oud"][sim]
                f = lambda x: f"{x[0]:+.1f} / {x[1]:+.1f}"
                L.append(f"| {mkt} | {vn} | {tg} | {f(o)} | {f(c[sim]['oud-nagebootst'])} | {f(c[sim]['+ vulcandle'])} | "
                         f"{f(c[sim]['+ 5 uur'])} | **{f(c[sim]['= nieuw'])}** |")
        L.append("")
    L += ["## Uitleg van de correcties", "",
          "1. **Doel in de vulcandle telt niet meer.** Bij een limietorder op 5m-candles is niet te zien of het doel vóór of ná "
          "de vulling werd geraakt. De oude code telde dat als winst (optimistisch); de engine telt alleen de stop in die candle.",
          "2. **Precies 5 uur.** De oude leren-simulatie nam de candle op +5:00 nog mee (5u05m); de oude 1m-backtest sloot pas op "
          "de close van de candle op of na 5 uur en 16:00 (een minuut te laat, zonder stopcontrole). Nu sluit een trade op de close "
          "van de laatste candle die vóór of op de deadline eindigt.",
          "3. **DOL zonder liquiditeit = 1R (zoals de app).** Het leren rekende dan met 2R, terwijl de app met `tp_r` (1R) handelt. "
          "Het leren beoordeelde dus andere trades dan de app werkelijk neemt.",
          "4. **Open voorbij de stop/het doel** sluit op de open (gat). Op 1m/5m binnen een sessie komt dat zelden voor. "
          "Het grootste geval: NQ basis/strenger 2R in 2025 (−4,5R in één trade). Op 10 oktober 2025 (tariefcrash) ontbreekt "
          "in de HistData de candle van 10:58; de koers viel in die minuut ruim door de stop. De oude code nam de stopprijs "
          "(optimistisch), de engine de open van 10:59 (voorzichtig). De echte vulling ligt daartussen.", "",
          "Verder is er niets veranderd: zelfde setups, zelfde kosten, zelfde selectie. Het verschil tussen \"oud\" en "
          "\"oud-nagebootst\" laat zien hoe goed de engine de oude regels kan nabootsen (resterende verschillen: punt 4 "
          "en de zoekgrens van de 1m-vulling)."]
    OUT.write_text("\n".join(L) + "\n")


def main():
    report(run())
    print(OUT)


if __name__ == "__main__":
    main()
