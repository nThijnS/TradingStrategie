#!/usr/bin/env python3
"""
Dezelfde TJR-strategie op meerdere markten (HistData 1-minuut data in data/raw).
Per markt: eigen tick/stopbuffer, kosten en een SMT-partner. Trades sluiten na max 5 uur.

Gebruik:
  python backtest_multi.py        # simuleert alles en slaat data/trades_multi.pkl op
"""
import pandas as pd

from backtest import CACHE, load_m1, simulate, to5
from tradingstrategie import CFG, analyse, sess_name

MAX_HOURS = 5

# tick * buf_ticks = stopbuffer; cost = spread + commissie + slippage per trade (rondgang)
MARKETS = {
    "NQ":     dict(sym="NSXUSD", smt="SPXUSD", tick=0.25,    cost=2.0),
    "GOUD":   dict(sym="XAUUSD", smt="XAUUSD", tick=0.05,    cost=0.35),
    "EURUSD": dict(sym="EURUSD", smt="GBPUSD", tick=0.00002, cost=0.00008),
    "GBPUSD": dict(sym="GBPUSD", smt="EURUSD", tick=0.00002, cost=0.00012),
}
VARIANTS = {
    "basis":    dict(disp_pct=0.6, disp_atr=1.2),
    "strenger": dict(disp_pct=0.7, disp_atr=1.5),
}
TARGETS = (1.0, 1.5, 2.0, "DOL")


def main():
    rows = []
    for mkt, m in MARKETS.items():
        print(f"{mkt}: data laden...", flush=True)
        m1, o1 = load_m1(m["sym"]), load_m1(m["smt"])
        m5, o5 = to5(m1), to5(o1)
        for vname, over in VARIANTS.items():
            cfg = dict(CFG, tick=m["tick"], max_per_day=6, **over)
            setups, _ = analyse(m5, o5, cfg)
            print(f"  {vname}: {len(setups)} setups", flush=True)
            for s in setups:
                sign = 1 if s["side"] == "LONG" else -1
                for target in TARGETS:
                    out = simulate(m1, s, target, cost=m["cost"], max_hours=MAX_HOURS)
                    if out is None:
                        continue
                    r, mins = out
                    rows.append(dict(mkt=mkt, variant=vname, target=str(target), t=s["entry_hit"],
                                     sess=sess_name(s["time"]), side=s["side"], score=s["score"],
                                     with_bias=s["bias_b"] == sign, R=r, mins=mins))
    T = pd.DataFrame(rows)
    T.to_pickle(CACHE / "trades_multi.pkl")
    print(f"{len(T)} trade-simulaties opgeslagen", flush=True)


if __name__ == "__main__":
    main()
