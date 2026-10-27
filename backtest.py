#!/usr/bin/env python3
"""
Backtest van TradingStrategie op HistData 1-minuut data (data/raw).
NSXUSD = Nasdaq 100, SPXUSD = S&P 500 (voor SMT). Tijden in de bestanden: EST zonder zomertijd.

Gebruik:
  python backtest.py              # train (2025) vs test (2026), beste instellingen + prop firm simulatie
"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from tradingstrategie import CFG, NY, analyse, sess_name

HERE = Path(__file__).resolve().parent
RAW = HERE / "data" / "raw"
CACHE = HERE / "data"

COST_PTS = 2.0          # spread + slippage per trade in punten (rondgang)
SPLIT = "2026-01-01"    # alles hiervoor = train, hierna = test (niet gebruikt bij het kiezen)


# ------------- Data -------------
def load_m1(sym):
    pq = CACHE / f"{sym}_m1.pkl"
    if pq.exists():
        return pd.read_pickle(pq)
    parts = []
    for f in sorted(RAW.glob(f"DAT_ASCII_{sym}_M1_*.csv")):
        d = pd.read_csv(f, sep=";", header=None, names=["t", "Open", "High", "Low", "Close", "V"])
        parts.append(d)
    d = pd.concat(parts)
    d.index = (pd.to_datetime(d["t"], format="%Y%m%d %H%M%S")
               .dt.tz_localize("Etc/GMT+5").dt.tz_convert(NY))
    d = d[["Open", "High", "Low", "Close"]].sort_index()
    d = d[~d.index.duplicated()]
    d.to_pickle(pq)
    return d


def to5(m1):
    return m1.resample("5min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()


# ------------- Uitkomst per trade (op 1-minuut candles) -------------
def simulate(m1, s, target, be_at=None, cost=COST_PTS, max_hours=None):
    """Geeft (R, minuten in trade) of None als de entry niet gevuld werd.
    target: getal = vaste R, "DOL" = de liquiditeit (s["dol"]) of anders het TP van de setup.
    be_at: stop naar entry na zoveel R. max_hours: trade sluiten na zoveel uur."""
    if s["entry_hit"] is None:
        return None
    long = s["side"] == "LONG"
    e, stop = s["entry"], s["stop"]
    risk = abs(e - stop)
    if target == "DOL":
        tp = s.get("dol") or s["tp"]
    else:
        tp = e + target * risk if long else e - target * risk
    day_end = s["entry_hit"].normalize() + pd.Timedelta(hours=16)
    bars = m1.loc[s["entry_hit"]:day_end]
    H, L, C, T = bars["High"].values, bars["Low"].values, bars["Close"].values, bars.index
    filled = False
    cur_stop = stop
    for k in range(len(bars)):
        if not filled:
            if (L[k] <= e) if long else (H[k] >= e):
                filled, t0 = True, T[k]
            else:
                continue
        if max_hours is not None and (T[k] - t0).total_seconds() >= max_hours * 3600:
            r = ((C[k] - e) if long else (e - C[k])) / risk
            return r - cost / risk, (T[k] - t0).total_seconds() / 60
        # stop eerst (conservatief als stop en TP in dezelfde minuut vallen)
        if (L[k] <= cur_stop) if long else (H[k] >= cur_stop):
            r = (cur_stop - e) / risk if long else (e - cur_stop) / risk
            return r - cost / risk, (T[k] - t0).total_seconds() / 60
        if (H[k] >= tp) if long else (L[k] <= tp):
            r = abs(tp - e) / risk
            return r - cost / risk, (T[k] - t0).total_seconds() / 60
        if be_at is not None:
            fav = (H[k] - e) / risk if long else (e - L[k]) / risk
            if fav >= be_at:
                cur_stop = e
    if not filled:
        return None
    r = ((C[-1] - e) if long else (e - C[-1])) / risk
    return r - cost / risk, (T[-1] - t0).total_seconds() / 60


# ------------- Statistiek -------------
def stats(rs):
    rs = np.array(rs)
    if len(rs) == 0:
        return dict(n=0, win=0, avgR=0, totR=0, pf=0, maxDD=0)
    eq = np.cumsum(rs)
    dd = (np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq).max()
    gains, losses = rs[rs > 0].sum(), -rs[rs < 0].sum()
    return dict(n=len(rs), win=(rs > 0).mean(), avgR=rs.mean(), totR=rs.sum(),
                pf=gains / losses if losses > 0 else 99, maxDD=dd)


def prop_sim(trades, risk_pct, size=10_000, target=0.10, max_loss=0.10, daily=0.05, max_days=None):
    """FTMO-achtige challenge: start op elke handelsdag, kijk of je eerst +target haalt of een limiet raakt.
    trades: lijst (tijd, R). Risico per trade = risk_pct van de startbalans."""
    if not trades:
        return dict(starts=0, passed=0, failed=0, open=0)
    df = pd.DataFrame(trades, columns=["t", "R"]).sort_values("t")
    days = sorted({t.date() for t in df["t"]})
    res = {"passed": 0, "failed": 0, "open": 0, "days_to_pass": []}
    for d0 in days:
        bal, day, day_start = size, None, size
        out = "open"
        for t, r in df[df["t"].dt.date >= d0].itertuples(index=False):
            if t.date() != day:
                day, day_start = t.date(), bal
            bal += r * risk_pct * size
            if bal <= size * (1 - max_loss) or bal <= day_start - daily * size:
                out = "failed"
                break
            if bal >= size * (1 + target):
                out = "passed"
                res["days_to_pass"].append((t.date() - d0).days)
                break
        res[out] += 1
    res["starts"] = len(days)
    res["median_days"] = float(np.median(res["days_to_pass"])) if res["days_to_pass"] else None
    del res["days_to_pass"]
    return res


# ------------- Run -------------
def run_setups(df5, es5, m1, **over):
    cfg = dict(CFG, **over)
    setups, _ = analyse(df5, es5, cfg)
    return setups


def main():
    print("Data laden...", flush=True)
    nq1, es1 = load_m1("NSXUSD"), load_m1("SPXUSD")
    nq5, es5 = to5(nq1), to5(es1)
    print(f"NQ: {nq5.index[0]:%d-%m-%Y} t/m {nq5.index[-1]:%d-%m-%Y}, {len(nq5)} candles van 5m", flush=True)

    # Varianten die de detectie zelf veranderen (analyse opnieuw draaien)
    variants = {
        "basis 50%":    dict(max_per_day=6),
        "entry rand":   dict(max_per_day=6, entry_mode="Rand"),
        "strenger":     dict(max_per_day=6, disp_pct=0.7, disp_atr=1.5),
    }
    rows = []
    for vname, over in variants.items():
        print(f"Analyse: {vname}...", flush=True)
        for s in run_setups(nq5, es5, nq1, **over):
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
    print(f"{len(T)} trade-simulaties opgeslagen", flush=True)


if __name__ == "__main__":
    main()
