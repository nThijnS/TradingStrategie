#!/usr/bin/env python3
"""
ARCHIEF (bevroren, november 2026): afgerond onderzoek; draait niet in de cloud. Bij de refactor zijn alleen de
imports aangepast. Backtests via backtest.simulate gebruiken nu de centrale engine (kleine verschillen met de
oorspronkelijke cijfers: zie docs/refactor/3_engine_vergelijking.md).

Onze TJR-strategie opnieuw getest met de zomertijd-correctie (tp_videos.load_dst), naast de oude data.
Zelfde markten, varianten en doelen als backtest_multi.py; max 5 uur per trade, max 1 trade per dag (zoals de app).
Instellingen kiezen op 2025 (train), daarna alleen kijken naar 2026 (test).

Gebruik:
  python backtest_dst.py          # simuleert en slaat data/trades_dst.pkl op, print daarna het overzicht
  python backtest_dst.py --report # alleen het overzicht uit data/trades_dst.pkl
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))   # repo-root (archief)

import sys

import pandas as pd

from backtest import CACHE, load_m1, simulate, stats, to5
from backtest_multi import MARKETS, MAX_HOURS, TARGETS, VARIANTS
from tp_videos import load_dst
from tradingstrategie import CFG, analyse, sess_name

SPLIT = pd.Timestamp("2026-01-01", tz="America/New_York")


def simulate_all():
    rows = []
    for data, loader in (("oud", load_m1), ("dst", load_dst)):
        for mkt, m in MARKETS.items():
            print(f"{data} {mkt}...", flush=True)
            m1, o1 = loader(m["sym"]), loader(m["smt"])
            m5, o5 = to5(m1), to5(o1)
            for vname, over in VARIANTS.items():
                cfg = dict(CFG, tick=m["tick"], max_per_day=6, **over)
                setups, _ = analyse(m5, o5, cfg)
                for s in setups:
                    for target in TARGETS:
                        out = simulate(m1, s, target, cost=m["cost"], max_hours=MAX_HOURS)
                        if out is None:
                            continue
                        rows.append(dict(data=data, mkt=mkt, variant=vname, target=str(target), t=s["entry_hit"],
                                         sess=sess_name(s["time"]), good=s["good"], R=out[0]))
    T = pd.DataFrame(rows)
    T.to_pickle(CACHE / "trades_dst.pkl")
    return T


def report(T):
    T = T[T.sess == "NY AM"].copy()
    T["t"] = pd.to_datetime(T.t, utc=True).dt.tz_convert("America/New_York")
    T = T.sort_values("t")
    out = []
    for key, g in T.groupby(["data", "mkt", "variant", "target", "good"]):
        g = g[~g.t.dt.date.duplicated()]      # max 1 per dag
        a, b = stats(g[g.t < SPLIT].R.values), stats(g[g.t >= SPLIT].R.values)
        out.append(dict(zip(["data", "mkt", "variant", "target", "good"], key),
                        n25=a["n"], win25=a["win"], R25=a["totR"], n26=b["n"], win26=b["win"], R26=b["totR"],
                        dd=stats(g.R.values)["maxDD"]))
    S = pd.DataFrame(out)
    pd.set_option("display.width", 200)
    fmt = S.round({"win25": 2, "R25": 1, "win26": 2, "R26": 1, "dd": 1})
    for mkt, g in fmt.groupby("mkt"):
        print(f"\n===== {mkt} =====")
        print(g.drop(columns="mkt").sort_values(["data", "R25"], ascending=[False, False]).to_string(index=False))
    # Keuze op 2025 per markt (alleen dst), en wat dat in 2026 doet
    print("\n===== Beste op 2025 gekozen (dst-data), resultaat 2026 =====")
    d = S[(S.data == "dst") & (S.n25 >= 15)]
    for mkt, g in d.groupby("mkt"):
        r = g.sort_values("R25", ascending=False).iloc[0]
        print(f"{mkt:7} {r.variant:9} TP {r.target:4} good={r.good!s:5} | 2025: {r.n25:3} tr {r.win25:4.0%} {r.R25:+6.1f}R"
              f" | 2026: {r.n26:3} tr {r.win26:4.0%} {r.R26:+6.1f}R | maxDD {r.dd:4.1f}R")


if __name__ == "__main__":
    T = pd.read_pickle(CACHE / "trades_dst.pkl") if "--report" in sys.argv else simulate_all()
    report(T)
