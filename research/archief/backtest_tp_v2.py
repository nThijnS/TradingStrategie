#!/usr/bin/env python3
"""
ARCHIEF (bevroren, november 2026): afgerond onderzoek; draait niet in de cloud. Bij de refactor zijn alleen de
imports aangepast. Backtests via backtest.simulate gebruiken nu de centrale engine (kleine verschillen met de
oorspronkelijke cijfers: zie docs/refactor/3_engine_vergelijking.md).

TradingPool-model v2: aangepast op wat hij in zijn video's laat zien (zie tp_videos.py voor de datacheck).
backtest_tp_model.py blijft ongewijzigd; met alle vlaggen uit en de oude lader geeft tradingpool_v2 dezelfde trades.

Verschillen met v1 (elk een vlag):
  dst      data met zomertijd-correctie (HistData-tijden zijn NY-lokaal mét zomertijd)
  bos50    4H-structuur zoals hij hem definieert: alleen een breuk als een volle candle (body >= 50% van de range)
           met minstens de helft van de body voorbij het niveau sluit; trend draait pas bij breuk van de protected low/high.
           Alles daarvoor is een "no close" (+S) en de trend blijft staan.
  smt      gecorreleerde markt voor de divergentie (bv. EURUSD i.p.v. zilver bij goud)
  rej15    rejectie-candle ook op de 15m: instap pas op de close van een 15m-candle in jouw richting
  weak     TP op de eerste weak high/low: de meest recente onaangetaste swing (niet de dichtstbijzijnde >= 1R); skip bij < 1R
  htf      "sweep4h": 4H-richting draait ook op een no close + sweep van een 4H-swing;
           anders richting uit de dag ("1D"), week ("1W") of dag en 4H samen ("1D+4h"), met de bos50-regel
  news     alleen 3SL-vensters binnen 20 uur na een groot USD-nieuwsmoment (8:30, 10:00 of 14:00 ET-spike in EURUSD)

Gebruik:
  python backtest_tp_v2.py
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))   # repo-root (archief)

import numpy as np
import pandas as pd

from backtest import load_m1, stats, to5
from backtest_tp_model import MARKETS, SPLIT, exit_trade, ours, report, smt_flags, window_name
from tp_videos import load_dst
from tradingstrategie import align_htf, htf_state, pivots

NEWS_SLOTS = ["08:30", "10:00", "14:00"]   # ET
NEWS_RATIO = 3.0
NEWS_HOURS = 20


def htf_bos50(df5, rule="4h", piv=3, sweep=False):
    """Bias per HTF-candle volgens TradingPool: breuk = volle candle met >= 50% body voorbij het niveau.
    Bij een bullish breuk wordt de laagste low van het been de protected low; de trend draait pas als die breekt.
    sweep=True: een "no close + sweep" van een swing low (wick eronder, geen breuk) zet de richting ook op long
    (zo las hij de 4H bij de goudtrade van 15-10-2026), en omgekeerd voor highs."""
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    if rule == "1W":   # weken van zondag 18:00 tot vrijdag 17:00 NY
        d = df5.resample("1D", offset="18h", label="left", closed="left").agg(agg).dropna()
        h = d.resample("W-FRI").agg(agg).dropna()
        h.index = pd.DatetimeIndex(d.index.to_series().resample("W-FRI").min().loc[h.index].tolist())
    else:
        offset = {"4h": "2h", "1D": "18h"}.get(rule)
        h = df5.resample(rule, offset=offset, label="left", closed="left").agg(agg).dropna()
    O, H, L, C = (h[c].values for c in ["Open", "High", "Low", "Close"])
    ph, pl = pivots(list(H), list(L), piv)
    b, sh, sl, sh_i, sl_i, pL, pH = 0, None, None, 0, 0, None, None
    rows = []

    def full(i):
        return abs(C[i] - O[i]) >= 0.5 * (H[i] - L[i])

    for i in range(len(h)):
        if ph[i] is not None:
            sh, sh_i = ph[i], i - piv
        if pl[i] is not None:
            sl, sl_i = pl[i], i - piv
        body = abs(C[i] - O[i])
        up = lambda lvl: lvl is not None and C[i] > O[i] and full(i) and C[i] - lvl >= 0.5 * body
        dn = lambda lvl: lvl is not None and C[i] < O[i] and full(i) and lvl - C[i] >= 0.5 * body
        if b >= 0 and up(sh):                       # continuation of start up
            b, pL, sh = 1, L[sh_i:i + 1].min(), None
        elif b <= 0 and dn(sl):
            b, pH, sl = -1, H[sl_i:i + 1].max(), None
        elif b == 1 and dn(pL):                     # protected low breekt: trend draait
            b, pH, pL, sl = -1, H[sl_i:i + 1].max() if sl is not None else H[i], None, None
        elif b == -1 and up(pH):
            b, pL, pH, sh = 1, L[sh_i:i + 1].min() if sh is not None else L[i], None, None
        elif sweep and sl is not None and L[i] < sl and not dn(sl):
            b, pL, sl = 1, L[i], None
        elif sweep and sh is not None and H[i] > sh and not up(sh):
            b, pH, sh = -1, H[i], None
        rows.append(b)
    out = pd.DataFrame({"bias": rows}, index=h.index)
    out["avail"] = out.index + (pd.Timedelta("5D") - pd.Timedelta("1h") if rule == "1W" else pd.Timedelta(rule))
    return out


def news_times(eu1):
    """Tijdstippen (ET) van grote USD-nieuwsspikes: 5m-range op een nieuwsslot >= NEWS_RATIO x mediaan van dat slot."""
    m5 = to5(eu1)
    rng = (m5["High"] - m5["Low"])
    out = []
    for slot in NEWS_SLOTS:
        s = rng[m5.index.strftime("%H:%M") == slot]
        base = s.rolling(20, min_periods=10).median().shift(1)
        out += list(s[s >= NEWS_RATIO * base].index)
    return pd.DatetimeIndex(sorted(out))


def tradingpool_v2(m1, o1, m5, o5, tick, cost, double, bos50=False, rej15=False, weak=False, news=None,
                   htf="4h"):
    idx = m5.index
    O, H, L, C = (m5[c].values for c in ["Open", "High", "Low", "Close"])
    st = htf_bos50(m5) if bos50 else htf_state(m5, "4h", 3)
    bias = align_htf(m5, st)["bias"].fillna(0).values
    if htf == "sweep4h":
        bias = align_htf(m5, htf_bos50(m5, "4h", 3, sweep=True))["bias"].fillna(0).values
    elif htf != "4h":   # richting van de dag/week (zijn HTF); "1D+4h" = dag en 4H moeten het eens zijn
        hb = align_htf(m5, htf_bos50(m5, htf.split("+")[0], 2))["bias"].fillna(0).values
        bias = np.where(hb == bias, hb, 0) if "+" in htf else hb
    ph, pl = pivots(list(H), list(L), 3)
    smt_bull, smt_bear = smt_flags(m5, o5)
    if double:
        b1, s1 = smt_flags(m1, o1)
        b1 = pd.Series(b1, index=m1.index).resample("5min").max().reindex(idx).fillna(0).astype(bool).values
        s1 = pd.Series(s1, index=m1.index).resample("5min").max().reindex(idx).fillna(0).astype(bool).values
    if rej15:
        m15 = m5.resample("15min", label="left", closed="left").agg({"Open": "first", "Close": "last"}).dropna()
        dir15 = np.sign(m15["Close"] - m15["Open"])
    allowed = None
    if news is not None:
        nt = news.values
        nxt = np.searchsorted(nt, idx.values, side="right") - 1     # laatste nieuws voor deze candle
        age = np.where(nxt >= 0, (idx.values - nt[np.maximum(nxt, 0)]) / np.timedelta64(1, "h"), 1e9)
        allowed = age <= NEWS_HOURS
    utc = idx.tz_convert("UTC")
    highs, lows = [], []          # (prijs, index) van onaangetaste swings
    trades, busy_until = [], idx[0]
    per_sess, day_r = {}, {}
    pending, pending_sess = None, None
    for i in range(len(idx)):
        if ph[i] is not None:
            highs.append((ph[i], i))
        if pl[i] is not None:
            lows.append((pl[i], i))
        t = idx[i]
        win = window_name(utc[i])
        swept_low = [l for l, _ in lows if L[i] < l]
        swept_high = [h for h, _ in highs if H[i] > h]
        lows = [x for x in lows if L[i] >= x[0]]
        highs = [x for x in highs if H[i] <= x[0]]

        if (pending is None and win is not None and t >= busy_until
                and (allowed is None or allowed[i])
                and per_sess.get((t.date(), win), 0) < 4 and day_r.get(t.date(), 0) > -4):
            if bias[i] == 1 and swept_low and C[i] > max(swept_low) and smt_bull[i] and (not double or b1[i]):
                pending, pending_sess = ("LONG", max(swept_low), L[i], i), win
            elif bias[i] == -1 and swept_high and C[i] < min(swept_high) and smt_bear[i] and (not double or s1[i]):
                pending, pending_sess = ("SHORT", min(swept_high), H[i], i), win

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
        t_in = t + pd.Timedelta(minutes=5)
        entry = C[i]
        if rej15:   # wachten op de close van de 15m-candle waar deze 5m-candle in valt; die moet ook meegaan
            q = t.floor("15min")
            if q not in dir15.index or dir15[q] != (1 if long else -1):
                pending = (side, lvl, ext, k0) if i - k0 < 3 else None
                continue
            q_end = q + pd.Timedelta(minutes=15)
            if q_end > t_in:
                bars = m1.loc[t_in:q_end - pd.Timedelta(minutes=1)]
                if len(bars):
                    if (bars["Low"].min() < ext) if long else (bars["High"].max() > ext):
                        pending = None
                        continue
                    entry = bars["Close"].iloc[-1]
                t_in = q_end
        pending = None
        stop = ext - 4 * tick if long else ext + 4 * tick
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        if weak:
            cand = [x for x in highs if x[0] > entry] if long else [x for x in lows if x[0] < entry]
            if not cand:
                continue
            tp = max(cand, key=lambda x: x[1])[0]       # meest recente onaangetaste swing = eerste weak level
            if abs(tp - entry) < risk:
                continue
        else:
            w = [h for h, _ in highs if h >= entry + risk] if long else [l for l, _ in lows if l <= entry - risk]
            tp = (min(w) if long else max(w)) if w else (entry + 2 * risk if long else entry - 2 * risk)
        r = exit_trade(m1, side, entry, stop, tp, t_in, cost)
        if r is None:
            continue
        trades.append(dict(t=t, side=side, R=r, sess=pending_sess, entry=entry, stop=stop, tp=tp))
        key = (t.date(), pending_sess)
        per_sess[key] = per_sess.get(key, 0) + 1
        day_r[t.date()] = day_r.get(t.date(), 0) + r
        busy_until = t_in + pd.Timedelta(hours=1)
    return trades


SMT_ALT = {"GOUD": "EURUSD", "NQ": "SPXUSD", "EURUSD": "GBPUSD"}
VARIANTS = [   # naam, dict met vlaggen
    ("v1 (zoals eerst)",               dict(dst=False)),
    ("v1 + dst-fix",                   dict()),
    ("+ bos50",                        dict(bos50=True)),
    ("+ bos50 + weak",                 dict(bos50=True, weak=True)),
    ("+ bos50 + weak + rej15",         dict(bos50=True, weak=True, rej15=True)),
    ("+ bos50 + weak + news",          dict(bos50=True, weak=True, news=True)),
    ("+ bos50 + weak + rej15 + news",  dict(bos50=True, weak=True, rej15=True, news=True)),
    ("+ bos50 + news (TP oud)",        dict(bos50=True, news=True)),
    ("+ bos50 + weak + news, smt-alt", dict(bos50=True, weak=True, news=True, alt=True)),
    ("bos50 + weak, bias dag",         dict(bos50=True, weak=True, htf="1D")),
    ("bos50 + weak, dag+4H",           dict(bos50=True, weak=True, htf="1D+4h")),
    ("bos50 + weak + news, dag",       dict(bos50=True, weak=True, news=True, htf="1D")),
    ("bos50 + weak, sweep4h",          dict(bos50=True, weak=True, htf="sweep4h")),
    ("bos50 + weak + news, sweep4h",   dict(bos50=True, weak=True, news=True, htf="sweep4h")),
    ("bos50 + weak + news, dag+4H",    dict(bos50=True, weak=True, news=True, htf="1D+4h")),
]


def main():
    allt = []
    eu_news = news_times(load_dst("EURUSD"))
    print(f"{len(eu_news)} nieuwsmomenten gevonden", flush=True)
    for mkt, m in MARKETS.items():
        print(f"\n===== {mkt} =====", flush=True)
        for dst in (False, True):
            L = load_dst if dst else load_m1
            m1, o1 = L(m["sym"]), L(m["smt"])
            m5, o5 = to5(m1), to5(o1)
            report(f"Onze strategie (NY AM){' dst' if dst else ''}", ours(m1, m5, o5, mkt, m["cost"]))
        alt1 = load_dst(SMT_ALT[mkt])
        alt5 = to5(alt1)
        for name, v in VARIANTS:
            L = load_m1 if v.get("dst", True) is False else load_dst
            m1, o1 = L(m["sym"]), L(m["smt"])
            m5, o5 = to5(m1), to5(o1)
            if v.get("alt"):
                o1, o5 = alt1, alt5
            for double in (False, True):
                tr = pd.DataFrame(tradingpool_v2(m1, o1, m5, o5, m["tick"], m["cost"], double,
                                                 bos50=v.get("bos50", False), rej15=v.get("rej15", False),
                                                 weak=v.get("weak", False), news=eu_news if v.get("news") else None,
                                                 htf=v.get("htf", "4h")))
                label = f"{name} {'dubbel' if double else 'enkel'}"
                report(label, tr)
                if len(tr):
                    allt.append(tr.assign(mkt=mkt, var=label))
    pd.concat(allt).to_pickle("data/trades_tp_v2.pkl")


if __name__ == "__main__":
    main()
