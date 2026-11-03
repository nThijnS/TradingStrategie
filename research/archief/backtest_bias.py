#!/usr/bin/env python3
"""
ARCHIEF (bevroren, november 2026): afgerond onderzoek; draait niet in de cloud. Bij de refactor zijn alleen de
imports aangepast. Backtests via backtest.simulate gebruiken nu de centrale engine (kleine verschillen met de
oorspronkelijke cijfers: zie docs/refactor/3_engine_vergelijking.md).

Top-down check: helpt het als de hogere timeframe (dag / 4H / 1H) de richting verplicht bepaalt?
Gecorrigeerde tijden (tp_videos.load_dst), NY AM, max 1 trade per dag, max 5 uur, zoals backtest_dst.py.

Bias per setup (1 = bullish, -1 = bearish, 0 = geen):
  bias_a  4H uit de app (htf_state)     bias_b  1H uit de app
  bias_d  dag (htf_state, swings van 2)  bias_d50 dag met de 50%-body-regel (backtest_tp_v2.htf_bos50)

Gebruik:
  python backtest_bias.py           # simuleert en slaat data/trades_bias.pkl op
  python backtest_bias.py --report  # alleen het overzicht
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))   # repo-root (archief)

import sys

import pandas as pd

from backtest import CACHE, simulate, stats, to5
from backtest_multi import MARKETS, MAX_HOURS, TARGETS, VARIANTS
from backtest_tp_v2 import htf_bos50
from tp_videos import load_dst
from tradingstrategie import CFG, align_htf, analyse, htf_state, sess_name

SPLIT = pd.Timestamp("2026-01-01", tz="America/New_York")
FILTERS = {
    "geen":            lambda d: d.R == d.R,
    "1H mee":          lambda d: d.bias_b == d.sign,
    "4H mee":          lambda d: d.bias_a == d.sign,
    "dag mee":         lambda d: d.bias_d == d.sign,
    "dag50 mee":       lambda d: d.bias_d50 == d.sign,
    "4H + 1H mee":     lambda d: (d.bias_a == d.sign) & (d.bias_b == d.sign),
    "dag + 4H mee":    lambda d: (d.bias_d == d.sign) & (d.bias_a == d.sign),
    "dag + 4H + 1H":   lambda d: (d.bias_d == d.sign) & (d.bias_a == d.sign) & (d.bias_b == d.sign),
}


def daily_bias(m5, st):
    return pd.Series(align_htf(m5, st)["bias"].fillna(0).values, index=m5.index)


def simulate_all():
    rows = []
    for mkt, m in MARKETS.items():
        print(f"{mkt}...", flush=True)
        m1, o1 = load_dst(m["sym"]), load_dst(m["smt"])
        m5, o5 = to5(m1), to5(o1)
        bd = daily_bias(m5, htf_state(m5.shift(6, freq="h"), "1D", 2).shift(-6, freq="h")
                        .assign(avail=lambda x: x.avail - pd.Timedelta(hours=6)))
        bd50 = daily_bias(m5, htf_bos50(m5, "1D", 2))
        for vname, over in VARIANTS.items():
            cfg = dict(CFG, tick=m["tick"], max_per_day=6, **over)
            setups, _ = analyse(m5, o5, cfg)
            for s in setups:
                for target in TARGETS:
                    out = simulate(m1, s, target, cost=m["cost"], max_hours=MAX_HOURS)
                    if out is None:
                        continue
                    rows.append(dict(mkt=mkt, variant=vname, target=str(target), t=s["entry_hit"],
                                     sess=sess_name(s["time"]), sign=1 if s["side"] == "LONG" else -1,
                                     bias_a=s["bias_a"], bias_b=s["bias_b"],
                                     bias_d=bd.asof(s["time"]), bias_d50=bd50.asof(s["time"]), R=out[0]))
    T = pd.DataFrame(rows)
    T.to_pickle(CACHE / "trades_bias.pkl")
    return T


def report(T):
    T = T[T.sess == "NY AM"].copy()
    T["t"] = pd.to_datetime(T.t, utc=True).dt.tz_convert("America/New_York")
    T = T.sort_values("t")
    out = []
    for (mkt, var, tgt), g in T.groupby(["mkt", "variant", "target"]):
        for fname, f in FILTERS.items():
            x = g[f(g)]
            x = x[~x.t.dt.date.duplicated()]
            a, b = stats(x[x.t < SPLIT].R.values), stats(x[x.t >= SPLIT].R.values)
            out.append(dict(mkt=mkt, variant=var, target=tgt, filter=fname, n25=a["n"], win25=a["win"], R25=a["totR"],
                            n26=b["n"], win26=b["win"], R26=b["totR"], dd=stats(x.R.values)["maxDD"]))
    S = pd.DataFrame(out).round({"win25": 2, "R25": 1, "win26": 2, "R26": 1, "dd": 1})
    pd.set_option("display.width", 200)
    for mkt, g in S.groupby("mkt"):
        print(f"\n===== {mkt}: per filter, gemiddeld over alle varianten/doelen =====")
        print(g.groupby("filter", sort=False)[["n25", "R25", "n26", "R26"]].mean().round(1).to_string())
        print(f"--- {mkt}: beste 8 op 2025 (min. 15 trades) ---")
        print(g[g.n25 >= 15].sort_values("R25", ascending=False).head(8).drop(columns="mkt").to_string(index=False))


if __name__ == "__main__":
    T = pd.read_pickle(CACHE / "trades_bias.pkl") if "--report" in sys.argv else simulate_all()
    report(T)
