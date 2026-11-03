#!/usr/bin/env python3
"""
ARCHIEF (bevroren, november 2026): afgerond onderzoek; draait niet in de cloud. Bij de refactor zijn alleen de
imports aangepast. Backtests via backtest.simulate gebruiken nu de centrale engine (kleine verschillen met de
oorspronkelijke cijfers: zie docs/refactor/3_engine_vergelijking.md).

Test van de TradingPool-ideeën bovenop onze strategie (NQ en EURUSD, HistData 1-minuut data).

Varianten:
  no_close   na de sweep mag geen 5m-candle buiten het geveegde niveau sluiten
  smt        divergentie (SMT) verplicht
  rejectie   niet blind op 50% FVG instappen, maar wachten op een 5m-candle in jouw richting
             die de entry-zone raakt; instap op de close van die candle
  pre-NY     venster 07:00-09:30 NY (TradingPool "3 session lock") i.p.v. NY AM

Gebruik:
  python backtest_tradingpool.py
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))   # repo-root (archief)

import numpy as np
import pandas as pd

from backtest import CACHE, load_m1, prop_sim, simulate, stats, to5
from tradingstrategie import CFG, analyse

MAX_HOURS = 5
SPLIT = pd.Timestamp("2026-01-01", tz="America/New_York")
MARKETS = {
    "NQ":     dict(sym="NSXUSD", smt="SPXUSD", cost=2.0, target=1.0),
    "EURUSD": dict(sym="EURUSD", smt="GBPUSD", cost=0.00008, target="DOL"),
}
WINDOWS = {"NY AM": [("09:30", "11:30")], "pre-NY": [("07:00", "09:30")]}
FILTERS = {
    "nu":               dict(),
    "no_close":         dict(no_close=True),
    "smt":              dict(need_smt=True),
    "no_close+smt":     dict(no_close=True, need_smt=True),
}


def simulate_reject(m1, m5, s, target, cost, entry_win=12):
    """Instap op de close van de eerste 5m-candle die de entry-zone raakt en in jouw richting sluit."""
    long = s["side"] == "LONG"
    e0, stop = s["entry"], s["stop"]
    bars = m5.loc[s["time"]:].iloc[1:entry_win + 1]
    touched, entry, t_in = False, None, None
    for t, o, h, l, c in zip(bars.index, bars["Open"], bars["High"], bars["Low"], bars["Close"]):
        if (l <= stop) if long else (h >= stop):
            return None                     # stop geraakt voordat er een bevestiging kwam
        touched = touched or ((l <= e0) if long else (h >= e0))
        if touched and ((c > o) if long else (c < o)):
            entry, t_in = c, t + pd.Timedelta(minutes=5)
            break
    if entry is None:
        return None
    risk = (entry - stop) if long else (stop - entry)
    if risk <= 0:
        return None
    dol = s.get("dol")
    if target == "DOL" and dol is not None and ((dol > entry) if long else (dol < entry)):
        tp = dol
    else:
        r_t = 1.0 if target == "DOL" else target
        tp = entry + r_t * risk if long else entry - r_t * risk
    end = min(t_in + pd.Timedelta(hours=MAX_HOURS), t_in.normalize() + pd.Timedelta(hours=16))
    after = m1.loc[t_in:end]
    if after.empty:
        return None
    H, L, C = after["High"].values, after["Low"].values, after["Close"].values
    for k in range(len(after)):
        if (L[k] <= stop) if long else (H[k] >= stop):
            return -1.0 - cost / risk
        if (H[k] >= tp) if long else (L[k] <= tp):
            return abs(tp - entry) / risk - cost / risk
    return ((C[-1] - entry) if long else (entry - C[-1])) / risk - cost / risk


def main():
    rows = []
    for mkt, m in MARKETS.items():
        m1, o1 = load_m1(m["sym"]), load_m1(m["smt"])
        m5, o5 = to5(m1), to5(o1)
        mk_cfg = next(x for x in CFG["markets"] if x["name"] == mkt)["cfg"]
        for wname, win in WINDOWS.items():
            for fname, flt in FILTERS.items():
                cfg = dict(CFG, **mk_cfg, **flt, trade_sess=win)
                setups, _ = analyse(m5, o5, cfg)
                print(f"{mkt} {wname} {fname}: {len(setups)} setups", flush=True)
                for s in setups:
                    for entry_kind in ("limit", "rejectie"):
                        if entry_kind == "limit":
                            out = simulate(m1, s, m["target"], cost=m["cost"], max_hours=MAX_HOURS)
                            r = None if out is None else out[0]
                        else:
                            r = simulate_reject(m1, m5, s, m["target"], m["cost"])
                        if r is not None:
                            rows.append(dict(mkt=mkt, window=wname, filt=fname, entry=entry_kind,
                                             t=s["time"], R=r))
    T = pd.DataFrame(rows)
    T.to_pickle(CACHE / "trades_tradingpool.pkl")

    out = []
    for key, g in T.groupby(["mkt", "window", "filt", "entry"]):
        g = g.sort_values("t")
        # TradingPool-regel: max 1 trade per markt per dag
        g = g[~g["t"].dt.date.duplicated()]
        a, b = stats(g[g.t < SPLIT].R.values), stats(g[g.t >= SPLIT].R.values)
        out.append(dict(zip(["mkt", "venster", "filter", "entry"], key),
                        n25=a["n"], win25=round(a["win"], 2), R25=round(a["totR"], 1),
                        n26=b["n"], win26=round(b["win"], 2), R26=round(b["totR"], 1),
                        maxDD=round(stats(g.R.values)["maxDD"], 1)))
    R = pd.DataFrame(out)
    pd.set_option("display.width", 200)
    print(R.sort_values(["mkt", "venster", "filter", "entry"]).to_string(index=False))
    R.to_pickle(CACHE / "grid_tradingpool.pkl")


if __name__ == "__main__":
    main()
