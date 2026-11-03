#!/usr/bin/env python3
"""
ARCHIEF (bevroren, november 2026): afgerond onderzoek; draait niet in de cloud. Bij de refactor zijn alleen de
imports aangepast. Backtests via backtest.simulate gebruiken nu de centrale engine (kleine verschillen met de
oorspronkelijke cijfers: zie docs/refactor/3_engine_vergelijking.md).

TradingPool-model zo letterlijk mogelijk nagebouwd, naast onze strategie, op goud, NQ en EURUSD.

TradingPool-regels (vertaald naar code):
  1. Alleen in de "3 session lock": 23-01, 06-08 en 11-13 UTC (2 uur voor Asia, London en NY open)
  2. Alleen continuation: richting van de 4H-structuur (MTF)
  3. Sweep met "no close": de 5m-candle prikt onder de laatste swing low (long) maar sluit erboven
  4. Divergentie: op dat moment maakt de gecorreleerde markt GEEN nieuwe low (goud-zilver, NQ-ES, EUR-GBP)
  5. Rejectie-candle: instap op de close van de eerste 5m-candle in jouw richting (max 3 candles na de sweep)
     variant "dubbel": ook op de 1m een sweep met divergentie in dezelfde 5m-candle
  6. Stop onder de sweep, TP op de dichtstbijzijnde weak high (swing high die nog niet geraakt is), anders 2R
  7. Risico: max 4 trades per sessie, stoppen na -4R op een dag (0,5% risico / 2% dagverlies), max 5 uur per trade

Gebruik:
  python backtest_tp_model.py
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))   # repo-root (archief)

import numpy as np
import pandas as pd

from backtest import CACHE, load_m1, simulate, stats, to5
from tradingstrategie import CFG, align_htf, analyse, htf_state, pivots

SPLIT = pd.Timestamp("2026-01-01", tz="America/New_York")
MAX_HOURS = 5
MARKETS = {
    "GOUD":   dict(sym="XAUUSD", smt="XAGUSD", tick=0.05, cost=0.35),
    "NQ":     dict(sym="NSXUSD", smt="SPXUSD", tick=0.25, cost=2.0),
    "EURUSD": dict(sym="EURUSD", smt="GBPUSD", tick=0.00002, cost=0.00008),
}
WINDOWS_UTC = {"Asia 3SL": (23, 1), "London 3SL": (6, 8), "NY 3SL": (11, 13)}
SMT_LEN = 20


def window_name(t_utc):
    h = t_utc.hour
    for name, (a, b) in WINDOWS_UTC.items():
        if (a <= h < b) if a < b else (h >= a or h < b):
            return name
    return None


def smt_flags(main, other, n=SMT_LEN):
    o = other.reindex(main.index).ffill()
    bull = (main["Low"] < main["Low"].rolling(n).min().shift(1)) & (o["Low"] >= o["Low"].rolling(n).min().shift(1))
    bear = (main["High"] > main["High"].rolling(n).max().shift(1)) & (o["High"] <= o["High"].rolling(n).max().shift(1))
    return bull.values, bear.values


def exit_trade(m1, side, entry, stop, tp, t_in, cost):
    long = side == "LONG"
    risk = abs(entry - stop)
    after = m1.loc[t_in:t_in + pd.Timedelta(hours=MAX_HOURS)]
    H, L, C = after["High"].values, after["Low"].values, after["Close"].values
    for k in range(len(after)):
        if (L[k] <= stop) if long else (H[k] >= stop):
            return -1.0 - cost / risk
        if (H[k] >= tp) if long else (L[k] <= tp):
            return abs(tp - entry) / risk - cost / risk
    if not len(after):
        return None
    return ((C[-1] - entry) if long else (entry - C[-1])) / risk - cost / risk


def tradingpool(m1, o1, m5, o5, tick, cost, double):
    idx = m5.index
    O, H, L, C = (m5[c].values for c in ["Open", "High", "Low", "Close"])
    bias = align_htf(m5, htf_state(m5, "4h", 3))["bias"].fillna(0).values
    ph, pl = pivots(list(H), list(L), 3)
    smt_bull, smt_bear = smt_flags(m5, o5)
    if double:   # 1m-sweep met divergentie binnen dezelfde 5m-candle
        b1, s1 = smt_flags(m1, o1)
        b1 = pd.Series(b1, index=m1.index).resample("5min").max().reindex(idx).fillna(0).astype(bool).values
        s1 = pd.Series(s1, index=m1.index).resample("5min").max().reindex(idx).fillna(0).astype(bool).values
    utc = idx.tz_convert("UTC")
    highs, lows = [], []          # onaangetaste swing highs/lows (weak levels)
    trades, busy_until = [], idx[0]
    per_sess, day_r = {}, {}
    pending, pending_sess = None, None
    for i in range(len(idx)):
        if ph[i] is not None:
            highs.append(ph[i])
        if pl[i] is not None:
            lows.append(pl[i])
        t = idx[i]
        win = window_name(utc[i])
        # Geraakte swing levels zijn geen weak level meer
        swept_low = [l for l in lows if L[i] < l]
        swept_high = [h for h in highs if H[i] > h]
        lows = [l for l in lows if L[i] >= l]
        highs = [h for h in highs if H[i] <= h]

        # Nieuwe sweep met no close + divergentie, in de richting van de 4H
        if (pending is None and win is not None and t >= busy_until
                and per_sess.get((t.date(), win), 0) < 4 and day_r.get(t.date(), 0) > -4):
            if bias[i] == 1 and swept_low and C[i] > max(swept_low) and smt_bull[i] and (not double or b1[i]):
                pending, pending_sess = ("LONG", max(swept_low), L[i], i), win
            elif bias[i] == -1 and swept_high and C[i] < min(swept_high) and smt_bear[i] and (not double or s1[i]):
                pending, pending_sess = ("SHORT", min(swept_high), H[i], i), win

        # Rejectie-candle afwachten (de sweep-candle zelf telt ook)
        if pending is None:
            continue
        side, lvl, ext, k0 = pending
        long = side == "LONG"
        ext = min(ext, L[i]) if long else max(ext, H[i])
        if (C[i] < lvl if long else C[i] > lvl) or i - k0 > 3:
            pending = None
            continue
        if not ((C[i] > O[i]) if long else (C[i] < O[i])):
            pending = (side, lvl, ext, k0)
            continue
        pending = None
        entry = C[i]
        stop = ext - 4 * tick if long else ext + 4 * tick
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        weak = [h for h in highs if h >= entry + risk] if long else [l for l in lows if l <= entry - risk]
        tp = (min(weak) if long else max(weak)) if weak else (entry + 2 * risk if long else entry - 2 * risk)
        t_in = t + pd.Timedelta(minutes=5)
        r = exit_trade(m1, side, entry, stop, tp, t_in, cost)
        if r is None:
            continue
        trades.append(dict(t=t, side=side, R=r, sess=pending_sess))
        key = (t.date(), pending_sess)
        per_sess[key] = per_sess.get(key, 0) + 1
        day_r[t.date()] = day_r.get(t.date(), 0) + r
        busy_until = t_in + pd.Timedelta(hours=1)
    return trades


def ours(m1, m5, o5, mkt, cost):
    mk = next((x for x in CFG["markets"] if x["name"] == mkt), None)
    cfg = {**CFG, **(mk["cfg"] if mk else {}), "tick": MARKETS[mkt]["tick"]}
    target = "DOL" if cfg.get("tp_mode") == "DOL" else 1.0
    setups, _ = analyse(m5, o5, cfg)
    out = []
    for s in setups:
        if not s["good"]:
            continue
        o = simulate(m1, s, target, cost=cost, max_hours=MAX_HOURS)
        if o is not None:
            out.append(dict(t=s["time"], side=s["side"], R=o[0], sess="NY AM"))
    df = pd.DataFrame(out)
    return df[~df.t.dt.date.duplicated()] if len(df) else df   # max 1 per dag, zoals in de app


def report(name, df):
    if not len(df):
        print(f"{name:34} geen trades")
        return
    a, b, c = stats(df[df.t < SPLIT].R.values), stats(df[df.t >= SPLIT].R.values), stats(df.sort_values("t").R.values)
    months = max((df.t.max() - df.t.min()).days / 30.4, 1)
    print(f"{name:34} {c['n']:4} trades ({c['n'] / months:4.1f}/mnd) | 2025: {a['win']:4.0%} win {a['totR']:+6.1f}R"
          f" | 2026: {b['win']:4.0%} win {b['totR']:+6.1f}R | maxDD {c['maxDD']:4.1f}R", flush=True)


def main():
    for mkt, m in MARKETS.items():
        m1, o1 = load_m1(m["sym"]), load_m1(m["smt"])
        m5, o5 = to5(m1), to5(o1)
        print(f"\n===== {mkt} =====", flush=True)
        report("Onze strategie (NY AM)", ours(m1, m5, o5, mkt, m["cost"]))
        for double in (False, True):
            tr = pd.DataFrame(tradingpool(m1, o1, m5, o5, m["tick"], m["cost"], double))
            label = "TradingPool " + ("dubbele bevestiging" if double else "enkele bevestiging")
            report(label, tr)
            if len(tr):
                for sess, g in tr.groupby("sess"):
                    report(f"   waarvan {sess}", g)


if __name__ == "__main__":
    main()
