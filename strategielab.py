#!/usr/bin/env python3
"""
Strategielab: vergelijkt per markt verschillende soorten strategieën en kiest er voorzichtig één.

Draait elke dag na de beurs (workflow leren.yml, na leren.py). Plaatst nooit orders: alleen backtest en papertrade.

1. Haalt per markt ~2 jaar 1-uurs candles op (Yahoo Finance) en controleert de datakwaliteit.
2. Test zes soorten strategieën: ICT (uit het geheugen van leren.py), trend volgen, momentum, mean reversion,
   breakout en volatiliteit (squeeze). Elke soort heeft maar twee varianten, zodat er weinig te "fitten" valt.
3. Walk-forward: kies de beste variant op 240 dagen trainingsdata, test die op de 60 dagen erna (die hij nog
   niet kende), schuif 60 dagen op, enzovoort. Alleen die testtrades tellen als "op nieuwe data".
4. Kiest per markt de strategie met de beste ondergrens (gemiddelde R min 1 standaardfout) op nieuwe data,
   met minstens MIN_OOS trades. Wisselt alleen bij een duidelijk betere (MARGIN), en kiest "geen trade" als
   niets boven 0 komt. Elke keuze komt als versie in lab_versies.json (terugdraaien = vorige versie).
5. Schrijft lab.json (voor het dashboard) en een dagregel in lab_geschiedenis.json.

    python strategielab.py
    python strategielab.py --markt BTC   # alleen deze markt (test)
"""
import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
LAB = HERE / "lab.json"
VERSIONS = HERE / "lab_versies.json"
HISTORY = HERE / "lab_geschiedenis.json"
MEMORY = HERE / "leren_geheugen.json"     # ICT-uitkomsten van leren.py
NY = ZoneInfo("America/New_York")

# kosten = spread + commissie heen en terug, als deel van de prijs (voorzichtig geschat)
MARKETS = [
    dict(naam="BTC", symbool="BTC-USD", soort="crypto", titel="Bitcoin", kosten=0.0008),
    dict(naam="ETH", symbool="ETH-USD", soort="crypto", titel="Ethereum", kosten=0.0008),
    dict(naam="SOL", symbool="SOL-USD", soort="crypto", titel="Solana", kosten=0.0012),
    dict(naam="EURUSD", symbool="EURUSD=X", soort="forex", titel="EUR/USD", kosten=0.00007),
    dict(naam="GBPUSD", symbool="GBPUSD=X", soort="forex", titel="GBP/USD", kosten=0.00009),
    dict(naam="USDJPY", symbool="JPY=X", soort="forex", titel="USD/JPY", kosten=0.00008),
    dict(naam="NQ", symbool="NQ=F", soort="index", titel="Nasdaq 100", kosten=0.00008),
    dict(naam="ES", symbool="ES=F", soort="index", titel="S&P 500", kosten=0.00008),
    dict(naam="DAX", symbool="^GDAXI", soort="index", titel="DAX 40", kosten=0.0001),
    dict(naam="GOUD", symbool="GC=F", soort="grondstof", titel="Goud", kosten=0.0001),
    dict(naam="ZILVER", symbool="SI=F", soort="grondstof", titel="Zilver", kosten=0.0006),
    dict(naam="OLIE", symbool="CL=F", soort="grondstof", titel="Olie (WTI)", kosten=0.0005),
    dict(naam="AAPL", symbool="AAPL", soort="aandeel", titel="Apple", kosten=0.0005),
    dict(naam="NVDA", symbool="NVDA", soort="aandeel", titel="Nvidia", kosten=0.0005),
    dict(naam="MSFT", symbool="MSFT", soort="aandeel", titel="Microsoft", kosten=0.0005),
]
ICT_MARKETS = ("NQ", "EURUSD", "GOUD")   # alleen daar heeft leren.py een geheugen

MAX_BARS = 12       # een trade duurt hoogstens 12 uur (daytrade)
TRAIN_D, TEST_D = 240, 60
MIN_TRAIN = 10      # minimaal aantal trades om een variant op trainingsdata te mogen kiezen
MIN_OOS = 30        # minimaal aantal trades op nieuwe data voordat een strategie gekozen mag worden
MARGIN = 0.05       # alleen wisselen als de nieuwe minstens zoveel R per trade beter scoort
Z = 1.0

STRATS = {
    "ict": dict(titel="ICT / Smart Money", uitleg="Liquiditeit-sweep, daarna een structuurbreuk met sterke beweging en instap in de FVG (de bestaande bot)."),
    "trend": dict(titel="Trend volgen", uitleg="Kopen als het 20-uurs gemiddelde boven het 50-uurs kruist en de prijs boven het 200-uurs gemiddelde staat (verkopen andersom).",
                  varianten=[dict(tp=2.0), dict(tp=3.0)]),
    "momentum": dict(titel="Momentum", uitleg="Instappen als de prijs een nieuwe 10-uurs top (of bodem) maakt in een markt die efficiënt één kant op beweegt.",
                     varianten=[dict(er=0.3), dict(er=0.5)]),
    "meanrev": dict(titel="Mean reversion", uitleg="In een zijwaartse markt tegen een uitschieter buiten de Bollinger-band in handelen, met het gemiddelde als doel.",
                    varianten=[dict(k=2.0), dict(k=2.5)]),
    "breakout": dict(titel="Breakout", uitleg="Instappen als de prijs voor het eerst boven de hoogste (of onder de laagste) prijs van de laatste 1 of 2 dagen sluit.",
                     varianten=[dict(n=24), dict(n=48)]),
    "volatiliteit": dict(titel="Volatiliteit (squeeze)", uitleg="Na een periode van ongewoon kleine bewegingen instappen in de richting van de eerste uitbraak uit de band.",
                         varianten=[dict(p=0.1), dict(p=0.2)]),
}


def vtxt(sid, v):
    if not v:
        return "standaard"
    return {"trend": lambda: f"doel {v['tp']:g}R", "momentum": lambda: f"efficiëntie > {v['er']}",
            "meanrev": lambda: f"band {v['k']} st.dev.", "breakout": lambda: f"kanaal {v['n']} uur",
            "volatiliteit": lambda: f"squeeze onderste {int(v['p'] * 100)}%",
            "ict": lambda: v.get("variant", "")}[sid]()


# ------------- Data -------------
def fetch_all(markets, interval="1h", period="730d"):
    import yfinance as yf
    syms = [m["symbool"] for m in markets]
    raw = yf.download(syms, interval=interval, period=period, group_by="ticker", auto_adjust=False,
                      progress=False, threads=True)
    out = {}
    for m in markets:
        try:
            df = raw[m["symbool"]] if isinstance(raw.columns, pd.MultiIndex) else raw
            out[m["naam"]] = df[["Open", "High", "Low", "Close"]].copy()
        except KeyError:
            out[m["naam"]] = pd.DataFrame(columns=["Open", "High", "Low", "Close"])
    return out


def clean(df):
    """Datakwaliteit: dubbele, lege en onmogelijke candles eruit, en tellen wat er mis was."""
    df = df.dropna(how="all")    # lege rijen ontstaan doordat markten met verschillende uren samen worden opgehaald
    q = dict(ruw=len(df))
    if len(df) and df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    dup = df.index.duplicated(keep="last")
    df = df[~dup]
    nan = df.isna().any(axis=1)
    df = df[~nan]
    bad = (df[["Open", "High", "Low", "Close"]] <= 0).any(axis=1) | (df["High"] < df["Low"]) | \
          (df["High"] < df[["Open", "Close"]].max(axis=1) - 1e-12) | (df["Low"] > df[["Open", "Close"]].min(axis=1) + 1e-12)
    df = df[~bad].sort_index()
    q.update(dubbel=int(dup.sum()), leeg=int(nan.sum()), ongeldig=int(bad.sum()), candles=len(df),
             van=df.index[0].isoformat() if len(df) else None, tot=df.index[-1].isoformat() if len(df) else None)
    return df, q


# ------------- Indicatoren en marktconditie -------------
def indicators(df):
    X = pd.DataFrame(index=df.index)
    o, h, l, c = (df[k] for k in ("Open", "High", "Low", "Close"))
    X["o"], X["h"], X["l"], X["c"] = o, h, l, c
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    X["atr"] = tr.rolling(14).mean()
    for n in (20, 50, 200):
        X[f"e{n}"] = c.ewm(span=n, adjust=False).mean()
    X["mid"], X["sd"] = c.rolling(20).mean(), c.rolling(20).std()
    move = c.diff().abs()
    X["er"] = (c - c.shift(20)).abs() / move.rolling(20).sum()
    X["er48"] = (c - c.shift(48)).abs() / move.rolling(48).sum()
    X["atr_pct"] = (X["atr"] / c).rolling(500, min_periods=100).rank(pct=True)
    X["bbw_pct"] = (4 * X["sd"] / X["mid"]).rolling(120, min_periods=60).rank(pct=True)
    up = X["e50"] > X["e50"].shift(24)
    X["trend"] = np.where(X["er48"] > 0.25, np.where(up, "Uptrend", "Downtrend"), "Zijwaarts")
    X["vol"] = np.where(X["atr_pct"] > 0.8, "Hoge volatiliteit", np.where(X["atr_pct"] < 0.2, "Lage volatiliteit", "Normale volatiliteit"))
    return X


def regime_now(df):
    """Marktconditie op dagbasis: richting, volatiliteit en of die aan het veranderen is."""
    d = df.resample("1D").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    if len(d) < 60:
        return dict(trend="onbekend", vol="onbekend", veranderend=False, uitleg="Te weinig dagdata.")
    c = d["Close"]

    def label(i):
        cc = c.iloc[:i]
        er = abs(cc.iloc[-1] - cc.iloc[-21]) / cc.diff().abs().iloc[-20:].sum()
        e = cc.ewm(span=20, adjust=False).mean()
        if er > 0.3:
            return ("Uptrend" if e.iloc[-1] > e.iloc[-6] else "Downtrend"), er
        return "Zijwaarts", er

    now, er = label(len(c))
    before, _ = label(len(c) - 10)
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - c.shift()).abs(), (d["Low"] - c.shift()).abs()], axis=1).max(axis=1)
    atrp = (tr.rolling(14).mean() / c).dropna()
    pct = float((atrp.iloc[-250:] <= atrp.iloc[-1]).mean())
    vol = "Hoge volatiliteit" if pct > 0.8 else "Lage volatiliteit" if pct < 0.2 else "Normale volatiliteit"
    change = now != before
    uitleg = (f"De laatste 20 dagen bewoog de prijs {'vooral één kant op' if er > 0.3 else 'heen en weer'} "
              f"(efficiëntie {er:.2f}; boven 0,30 = trend). De dagelijkse beweweging is groter dan op {pct:.0%} van de dagen dit jaar."
              + (f" Tien handelsdagen geleden was het nog '{before}': de markt verandert." if change else ""))
    return dict(trend=now, vol=vol, veranderend=bool(change), efficientie=round(float(er), 2),
                vol_percentiel=round(pct, 2), uitleg=uitleg.replace("beweweging", "beweging"))


# ------------- Strategieën -------------
def signals(sid, X, v):
    c, atr = X["c"], X["atr"]
    if sid == "trend":
        x_up = (X["e20"] > X["e50"]) & (X["e20"].shift() <= X["e50"].shift())
        x_dn = (X["e20"] < X["e50"]) & (X["e20"].shift() >= X["e50"].shift())
        return x_up & (c > X["e200"]), x_dn & (c < X["e200"]), 2 * atr, ("R", v["tp"])
    if sid == "momentum":
        up = (c > X["h"].rolling(10).max().shift()) & (X["er"] > v["er"]) & (c > X["e50"])
        dn = (c < X["l"].rolling(10).min().shift()) & (X["er"] > v["er"]) & (c < X["e50"])
        return up, dn, 1.5 * atr, ("R", 2.0)
    if sid == "meanrev":
        rng = X["er"] < 0.3
        return (c < X["mid"] - v["k"] * X["sd"]) & rng, (c > X["mid"] + v["k"] * X["sd"]) & rng, 1.5 * atr, ("mid",)
    if sid == "breakout":
        hi, lo = X["h"].rolling(v["n"]).max().shift(), X["l"].rolling(v["n"]).min().shift()
        return (c > hi) & (c.shift() <= hi.shift()), (c < lo) & (c.shift() >= lo.shift()), 1.5 * atr, ("R", 2.0)
    if sid == "volatiliteit":
        sq = X["bbw_pct"].shift() < v["p"]
        return sq & (c > X["mid"] + 2 * X["sd"]), sq & (c < X["mid"] - 2 * X["sd"]), 1.5 * atr, ("R", 2.0)
    raise ValueError(sid)


def simulate(X, up, dn, stopd, target, cost):
    """Instap op de open van de volgende candle; stop en doel op high/low (stop eerst als beide geraakt)."""
    o, h, l, c = (X[k].to_numpy() for k in ("o", "h", "l", "c"))
    mid, sd = X["mid"].to_numpy(), stopd.to_numpy()
    times, trend, vol = X.index, X["trend"].to_numpy(), X["vol"].to_numpy()
    sig = np.flatnonzero((up | dn).fillna(False).to_numpy())
    upa = up.fillna(False).to_numpy()
    n, busy, out = len(X), -1, []
    for i in sig:
        if i <= busy or i + 1 >= n or not np.isfinite(sd[i]) or sd[i] <= 0:
            continue
        side = 1 if upa[i] else -1
        e, risk = o[i + 1], sd[i]
        stop = e - side * risk
        tp = e + side * target[1] * risk if target[0] == "R" else mid[i]
        if (tp - e) * side <= 0.3 * risk:          # te weinig ruimte tot het doel
            continue
        exitp, j = None, i + 1
        for j in range(i + 1, min(i + 1 + MAX_BARS, n)):
            if j > i + 1 and (times[j] - times[j - 1]) > pd.Timedelta(hours=6):   # weekend/beurs dicht: sluiten
                exitp, j = c[j - 1], j - 1
                break
            if (side > 0 and o[j] <= stop) or (side < 0 and o[j] >= stop):
                exitp = o[j]; break
            if (side > 0 and l[j] <= stop) or (side < 0 and h[j] >= stop):
                exitp = stop; break
            if (side > 0 and o[j] >= tp) or (side < 0 and o[j] <= tp):
                exitp = o[j]; break
            if (side > 0 and h[j] >= tp) or (side < 0 and l[j] <= tp):
                exitp = tp; break
        still_open = exitp is None and j == n - 1 and j < i + MAX_BARS   # data houdt op terwijl de trade nog loopt
        if exitp is None:
            exitp = c[j]
        gross = (exitp - e) * side / risk
        out.append(dict(t=times[i + 1], R=gross - cost * e / risk, bruto=gross, rr=abs(tp - e) / risk, open=bool(still_open),
                        kant="LONG" if side > 0 else "SHORT", trend=trend[i], vol=vol[i],
                        entry=float(e), stop=float(stop), tp=float(tp), i=int(i)))
        busy = j
    return out


def ict_trades(name, X):
    """ICT-trades per variant uit het geheugen van leren.py (R is daar al na kosten)."""
    try:
        import leren
        mem = json.loads(MEMORY.read_text())
    except Exception:
        return {}
    rows = [r for r in mem.values() if r["markt"] == name]
    out = {}
    for v in leren.variants():
        sel = sorted((r for r in rows if r["disp"] == v["disp"] and r["target"] == v["target"]
                      and r["sess"] in leren.SESSIONS[v["sessies"]] and (r["bias_mee"] or not leren.BIAS[v["bias"]])),
                     key=lambda r: r["t"])
        seen, trades = set(), []
        for r in sel:
            if r["t"][:10] in seen:
                continue
            seen.add(r["t"][:10])
            t = pd.Timestamp(r["t"]).tz_convert("UTC")
            k = X.index.searchsorted(t) - 1
            rr = 2.0 if v["target"] == "DOL" else float(v["target"])
            trades.append(dict(t=t, R=r["R"], bruto=None, rr=rr, kant=None,
                               trend=X["trend"].iloc[k] if 0 <= k < len(X) else "onbekend",
                               vol=X["vol"].iloc[k] if 0 <= k < len(X) else "onbekend"))
        out[leren.vid(v)] = trades
    return out


# ------------- Statistiek -------------
def stats(trades, full=True):
    R = np.array([t["R"] for t in trades], dtype=float)
    n = len(R)
    if n == 0:
        return dict(n=0)
    wins, losses = R[R > 0], R[R <= 0]
    eq = np.cumsum(R)
    dd = eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    se = float(R.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    gross = [t["bruto"] for t in trades if t["bruto"] is not None]
    s = dict(n=n, win=round(float((R > 0).mean()), 3), gem_winst=round(float(wins.mean()), 3) if len(wins) else 0.0,
             gem_verlies=round(float(losses.mean()), 3) if len(losses) else 0.0, expectancy=round(float(R.mean()), 3),
             pf=round(float(wins.sum() / -losses.sum()), 2) if losses.sum() < 0 else None,
             netto=round(float(R.sum()), 2), bruto=round(float(sum(gross)), 2) if len(gross) == n else None,
             max_dd=round(float(-dd.min()), 2), gem_rr=round(float(np.mean([t["rr"] for t in trades])), 2),
             se=round(se, 3) if np.isfinite(se) else None,
             ondergrens=round(float(R.mean() - Z * se), 3) if np.isfinite(se) else None,
             ci95=[round(float(R.mean() - 1.96 * se), 3), round(float(R.mean() + 1.96 * se), 3)] if np.isfinite(se) else None,
             t_stat=round(float(R.mean() / se), 2) if np.isfinite(se) and se > 0 else None,
             van=trades[0]["t"].isoformat(), tot=trades[-1]["t"].isoformat())
    if full:
        month, reg = {}, {}
        for t in trades:
            month.setdefault(t["t"].strftime("%Y-%m"), []).append(t["R"])
            for k in (t["trend"], t["vol"]):
                reg.setdefault(k, []).append(t["R"])
        s["per_maand"] = {k: [len(v), round(sum(v), 2)] for k, v in sorted(month.items())}
        s["per_conditie"] = {k: [len(v), round(sum(v), 2), round(float(np.mean(v)), 3)] for k, v in reg.items()}
        s["trades"] = [[int(t["t"].timestamp()), round(t["R"], 3)] for t in trades]
    return s


def walk_forward(by_variant, start, end):
    """Per periode van TEST_D dagen: de variant met de beste gemiddelde R op de TRAIN_D dagen ervoor."""
    oos, picks = [], []
    t = start + pd.Timedelta(days=TRAIN_D)
    while t < end:
        best, best_mean = None, None
        for vk, trades in by_variant.items():
            tr = [x["R"] for x in trades if t - pd.Timedelta(days=TRAIN_D) <= x["t"] < t]
            if len(tr) >= MIN_TRAIN and (best_mean is None or np.mean(tr) > best_mean):
                best, best_mean = vk, float(np.mean(tr))
        if best is not None:
            oos += [x for x in by_variant[best] if t <= x["t"] < t + pd.Timedelta(days=TEST_D)]
        picks.append(dict(van=t.date().isoformat(), variant=best))
        t += pd.Timedelta(days=TEST_D)
    return sorted(oos, key=lambda x: x["t"]), picks


def current_variant(by_variant, end):
    best, best_mean = None, None
    for vk, trades in by_variant.items():
        tr = [x["R"] for x in trades if end - pd.Timedelta(days=TRAIN_D) <= x["t"]]
        if len(tr) >= MIN_TRAIN and (best_mean is None or np.mean(tr) > best_mean):
            best, best_mean = vk, float(np.mean(tr))
    return best


def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


# ------------- Per markt -------------
def analyse_market(m, df, versions):
    df, q = clean(df)
    res = dict(naam=m["naam"], titel=m["titel"], soort=m["soort"], symbool=m["symbool"], kosten=m["kosten"], data=q)
    if len(df) < 1500:
        res["fout"] = f"te weinig data ({len(df)} candles)"
        return res, None
    X = indicators(df)
    start, end = X.index[0], X.index[-1]
    res["regime"] = regime_now(df)
    strategies, oos_by = [], {}
    for sid, info in STRATS.items():
        if sid == "ict":
            if m["naam"] not in ICT_MARKETS:
                continue
            by_variant = ict_trades(m["naam"], X)
            if not by_variant:
                continue
        else:
            by_variant = {}
            for v in info["varianten"]:
                up, dn, stopd, target = signals(sid, X, v)
                by_variant[json.dumps(v)] = simulate(X, up, dn, stopd, target, m["kosten"])
        hist_key = max(by_variant, key=lambda k: np.mean([x["R"] for x in by_variant[k]]) if len(by_variant[k]) >= MIN_TRAIN else -9)
        oos, picks = walk_forward(by_variant, start, end)
        now_key = current_variant(by_variant, end) or hist_key
        variant = json.loads(now_key) if sid != "ict" else dict(variant=now_key)
        oos_by[sid] = dict(oos=oos, all=by_variant, key=now_key)
        strategies.append(dict(id=sid, titel=info["titel"], uitleg=info["uitleg"], variant=variant, variant_txt=vtxt(sid, variant),
                               varianten_getest=len(by_variant), historisch=stats(by_variant[hist_key], full=False),
                               historisch_variant=vtxt(sid, json.loads(hist_key) if sid != "ict" else dict(variant=hist_key)),
                               nieuw=stats(oos), keuzes_per_periode=picks))
    res["strategieen"] = strategies
    # benchmark: kopen en vasthouden over de testperiode
    t0 = start + pd.Timedelta(days=TRAIN_D)
    c0 = df["Close"][df.index >= t0]
    res["benchmark"] = dict(kopen_houden_pct=round(float((c0.iloc[-1] / c0.iloc[0] - 1) * 100), 1) if len(c0) else None,
                            geen_trade_R=0.0, testperiode=[t0.date().isoformat(), end.date().isoformat()])
    return res, dict(X=X, oos_by=oos_by)


def choose(res, ctx, versions):
    """Kies voorzichtig: beste ondergrens op nieuwe data, met rem op wisselen en 'geen trade' als niets goed is."""
    name, today = res["naam"], datetime.now(NY).date().isoformat()
    hist = versions.setdefault(name, [])
    prev = hist[-1] if hist else None
    ok = [s for s in res["strategieen"] if s["nieuw"].get("n", 0) >= MIN_OOS and s["nieuw"].get("ondergrens") is not None]
    ok.sort(key=lambda s: -s["nieuw"]["ondergrens"])
    best = ok[0] if ok else None
    by_id = {s["id"]: s for s in res["strategieen"]}
    prev_s = by_id.get(prev["strategie"]) if prev and prev.get("strategie") else None
    prev_score = prev_s["nieuw"].get("ondergrens") if prev_s and prev_s["nieuw"].get("n", 0) >= MIN_OOS else None
    rejected = []
    for s in res["strategieen"]:
        if best and s["id"] == best["id"]:
            continue
        h, nw = s["historisch"], s["nieuw"]
        if h.get("n", 0) >= MIN_TRAIN and h.get("expectancy", 0) > 0 and (nw.get("ondergrens") or -1) <= 0:
            rejected.append(dict(strategie=s["titel"], reden=f"op oude data {h['expectancy']:+.2f}R per trade, op nieuwe data {nw.get('expectancy', 0):+.2f}R: houdt geen stand"))
        elif nw.get("n", 0) < MIN_OOS:
            rejected.append(dict(strategie=s["titel"], reden=f"te weinig trades op nieuwe data ({nw.get('n', 0)} < {MIN_OOS})"))
    if best is None or best["nieuw"]["ondergrens"] <= 0:
        pick, why = None, ("geen enkele strategie heeft op nieuwe data een ondergrens boven 0: geen trade"
                           if best else f"nog geen strategie met {MIN_OOS} trades op nieuwe data: geen trade")
    elif prev_s and prev_s["id"] == best["id"]:
        pick, why = best, "de huidige strategie is nog steeds de beste op nieuwe data"
    elif prev_score is not None and prev_score > 0 and best["nieuw"]["ondergrens"] < prev_score + MARGIN:
        pick, why = prev_s, f"{best['titel']} scoort iets beter, maar minder dan {MARGIN}R per trade: niet wisselen"
        rejected.append(dict(strategie=best["titel"], reden=why))
    else:
        pick, why = best, (f"beste ondergrens op nieuwe data ({best['nieuw']['ondergrens']:+.3f}R over {best['nieuw']['n']} trades)"
                           + (f", duidelijk beter dan {prev_s['titel']}" if prev_s else ""))
    entry = dict(sinds=today, strategie=pick["id"] if pick else None, titel=pick["titel"] if pick else "Geen trade",
                 variant=pick["variant"] if pick else None, variant_txt=pick["variant_txt"] if pick else "",
                 ondergrens=pick["nieuw"]["ondergrens"] if pick else None, n=pick["nieuw"]["n"] if pick else 0, reden=why)
    changed = not prev or prev.get("strategie") != entry["strategie"] or prev.get("variant") != entry["variant"]
    if changed:
        hist.append(entry)
    cur = hist[-1]
    # hoe doet de gekozen strategie het sinds de keuze (alleen trades na de keuzedatum: echt nieuwe data)
    since = []
    if cur["strategie"] and cur["strategie"] in ctx["oos_by"]:
        key = json.dumps(cur["variant"]) if cur["strategie"] != "ict" else cur["variant"]["variant"]
        trades = ctx["oos_by"][cur["strategie"]]["all"].get(key, [])
        since = [x for x in trades if x["t"].date().isoformat() >= cur["sinds"]]
    res["keuze"] = dict(cur, reden_vandaag=why, gewisseld=bool(prev) and changed, eerste=not prev)
    res["vorige"] = hist[-2] if len(hist) > 1 else None
    res["sinds_keuze"] = stats(since) if since else dict(n=0)
    res["afgewezen"] = rejected
    res["versies"] = hist[-10:]
    # laatste signalen van de gekozen strategie (papertrades, voor het dashboard)
    res["laatste_signalen"] = []
    if cur["strategie"] and cur["strategie"] != "ict" and cur["strategie"] in ctx["oos_by"]:
        key = json.dumps(cur["variant"])
        for x in ctx["oos_by"][cur["strategie"]]["all"].get(key, [])[-5:]:
            res["laatste_signalen"].append(dict(t=x["t"].isoformat(), kant=x["kant"], entry=round(x["entry"], 6),
                                                stop=round(x["stop"], 6), tp=round(x["tp"], 6), R=round(x["R"], 2)))
    return entry, why, rejected


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--markt", help="alleen deze markt")
    a = ap.parse_args()
    markets = [m for m in MARKETS if not a.markt or m["naam"] == a.markt]
    versions = load(VERSIONS, {})
    data = fetch_all(markets)
    out, day = [], dict(t=datetime.now(NY).isoformat(timespec="minutes"), markten={})
    for m in markets:
        try:
            res, ctx = analyse_market(m, data.get(m["naam"], pd.DataFrame()), versions)
            if ctx:
                entry, why, rejected = choose(res, ctx, versions)
                top = sorted((s for s in res["strategieen"] if s["nieuw"].get("n")), key=lambda s: -(s["nieuw"].get("ondergrens") or -9))
                day["markten"][m["naam"]] = dict(
                    regime=f"{res['regime']['trend']}, {res['regime']['vol'].lower()}", keuze=entry["titel"], variant=entry["variant_txt"],
                    gewisseld=res["keuze"]["gewisseld"], reden=why, afgewezen=rejected,
                    getest=[dict(strategie=s["titel"], varianten=s["varianten_getest"], n=s["nieuw"]["n"],
                                 nieuw=s["nieuw"].get("expectancy"), ondergrens=s["nieuw"].get("ondergrens"),
                                 historisch=s["historisch"].get("expectancy")) for s in top])
        except Exception as ex:   # één markt mag de rest niet tegenhouden
            res = dict(naam=m["naam"], titel=m["titel"], soort=m["soort"], symbool=m["symbool"], fout=f"{type(ex).__name__}: {ex}")
        out.append(res)
        k = res.get("keuze", {})
        print(f"{m['naam']:7} {res.get('fout') or (res['regime']['trend'] + ' / ' + res['regime']['vol']):40} -> {k.get('titel', '-')}: {k.get('reden_vandaag', '')}")
    lab = dict(gemaakt=datetime.now(NY).isoformat(timespec="minutes"), versie=2,
               instellingen=dict(train_dagen=TRAIN_D, test_dagen=TEST_D, min_trades_nieuw=MIN_OOS, wissel_marge=MARGIN,
                                 max_uren_per_trade=MAX_BARS, bron="Yahoo Finance, 1-uurs candles (~2 jaar)"),
               strategieen={k: dict(titel=v["titel"], uitleg=v["uitleg"]) for k, v in STRATS.items()}, markten=out)
    if a.markt:
        LAB.with_name("lab_test.json").write_text(json.dumps(lab, ensure_ascii=False, separators=(",", ":")))
        return
    LAB.write_text(json.dumps(lab, ensure_ascii=False, separators=(",", ":")))
    VERSIONS.write_text(json.dumps(versions, ensure_ascii=False, indent=1))
    hist = load(HISTORY, [])
    hist = [h for h in hist if h["t"][:10] != day["t"][:10]] + [day]   # één regel per dag
    HISTORY.write_text(json.dumps(hist[-180:], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
