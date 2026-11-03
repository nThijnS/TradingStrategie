#!/usr/bin/env python3
"""ICT/TJR-backtests op HistData 1-minuut data (lokaal in data/raw, git-ignored). Was backtest.py en backtest_multi.py.

Detectie op 5m (strategies/ict_tjr.py), uitkomst op 1m via backtesting/engine.py: limietorder gevuld in de
5m-candle van de entry, stop eerst, doel niet in de vulcandle, uiterlijk 16:00 NY of na max_hours dicht,
kosten in prijspunten (spread + commissie + slippage).

Tijden: standaard de zomertijd-correcte lader (core/data.load_histdata). Met --oud de oude EST-lader, alleen
om resultaten van vóór 29 oktober 2026 te reproduceren.

Gebruik:
  python backtest.py              # NQ: varianten x doelen x breakeven -> data/trades.pkl
  python backtest_multi.py        # NQ, goud, EURUSD, GBPUSD -> data/trades_multi.pkl
"""
import sys

import pandas as pd

from backtesting import engine
from backtesting.ict import trade
from backtesting.metrics import basic_stats as stats  # noqa: F401  (gebruikt door research/archief)
from backtesting.prop import prop_sim  # noqa: F401
from core.config import CFG
from core.data import load_histdata, load_histdata_est, to5
from core.markets import HISTDATA_RESEARCH
from core.sessions import NY, sess_name  # noqa: F401
from research import registry
from storage import paths
from strategies.ict_tjr import analyse

RAW = paths.HISTDATA_RAW
CACHE = paths.DATA

COST_PTS = 2.0          # spread + slippage per trade in punten (rondgang), NQ
SPLIT = "2026-01-01"    # alles hiervoor = train, hierna = test (niet gebruikt bij het kiezen)
MAX_HOURS = 5           # backtest_multi: trades sluiten na max 5 uur

MARKETS = HISTDATA_RESEARCH
VARIANTS = {
    "basis":    dict(disp_pct=0.6, disp_atr=1.2),
    "strenger": dict(disp_pct=0.7, disp_atr=1.5),
}
TARGETS = (1.0, 1.5, 2.0, "DOL")


def load_m1(sym):
    """1m-candles; met --oud op de commandoregel de oude (zomertijd-foute) lader."""
    return load_histdata_est(sym) if "--oud" in sys.argv else load_histdata(sym)


_BARS = {}


def _bars(m1):
    key = id(m1)
    if key not in _BARS:
        _BARS.clear()
        _BARS[key] = (m1, engine.Bars(m1, bar=pd.Timedelta(minutes=1)))
    return _BARS[key][1]


def simulate(m1, s, target, be_at=None, cost=COST_PTS, max_hours=None):
    """Geeft (R netto, minuten in trade) of None als de entry niet gevuld werd.
    target: getal = vaste R, "DOL" = de liquiditeit (s["dol"]) of anders het TP van de setup.
    be_at: stop naar entry na zoveel R. max_hours: trade sluiten na zoveel uur (anders 16:00 NY)."""
    if target == "DOL" and s.get("dol") is None:
        target = None
    exits = engine.Exits(close_at="16:00", max_hours=max_hours, be_at=be_at)
    tr = trade(_bars(m1), s, target, exits, engine.Costs(price=cost))
    if tr is None:
        return None
    return tr.net_r, tr.minutes


def run_setups(df5, es5, m1=None, **over):
    return analyse(df5, es5, dict(CFG, **over))[0]


def main():
    """NQ: drie detectievarianten x vijf doelen x breakeven, opgeslagen in data/trades.pkl."""
    print("Data laden...", flush=True)
    nq1, es1 = load_m1("NSXUSD"), load_m1("SPXUSD")
    nq5, es5 = to5(nq1), to5(es1)
    print(f"NQ: {nq5.index[0]:%d-%m-%Y} t/m {nq5.index[-1]:%d-%m-%Y}, {len(nq5)} candles van 5m", flush=True)
    variants = {
        "basis 50%":    dict(max_per_day=6),
        "entry rand":   dict(max_per_day=6, entry_mode="Rand"),
        "strenger":     dict(max_per_day=6, disp_pct=0.7, disp_atr=1.5),
    }
    rows = []
    for vname, over in variants.items():
        print(f"Analyse: {vname}...", flush=True)
        for s in run_setups(nq5, es5, **over):
            for target in (1.0, 1.5, 2.0, 3.0, "DOL"):
                for be in (None, 1.0):
                    out = simulate(nq1, s, target, be)
                    if out is None:
                        continue
                    r, mins = out
                    rows.append(dict(variant=vname, target=str(target), be=str(be), t=s["entry_hit"],
                                     sess=sess_name(s["time"]), side=s["side"], score=s["score"],
                                     with_bias=s["bias_b"] == (1 if s["side"] == "LONG" else -1),
                                     with_a=s["bias_a"] == (1 if s["side"] == "LONG" else -1),
                                     risk=abs(s["entry"] - s["stop"]), R=r, mins=mins))
    T = pd.DataFrame(rows)
    T.to_pickle(CACHE / "trades.pkl")
    registry.record("backtest NQ", params=dict(variants=variants, oud="--oud" in sys.argv),
                    data=dict(NQ=registry.fingerprint(nq1)), results=dict(simulaties=len(T)))
    print(f"{len(T)} trade-simulaties opgeslagen", flush=True)


def multi():
    """Dezelfde TJR-strategie op meerdere markten; per markt eigen tick/stopbuffer, kosten en SMT-partner."""
    rows, fps = [], {}
    for mkt, m in MARKETS.items():
        print(f"{mkt}: data laden...", flush=True)
        m1, o1 = load_m1(m["sym"]), load_m1(m["smt"])
        fps[mkt] = registry.fingerprint(m1)
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
    registry.record("backtest multi", params=dict(markets=MARKETS, variants=VARIANTS, max_hours=MAX_HOURS,
                                                  oud="--oud" in sys.argv), data=fps, results=dict(simulaties=len(T)))
    print(f"{len(T)} trade-simulaties opgeslagen", flush=True)


if __name__ == "__main__":
    multi() if "--multi" in sys.argv else main()
