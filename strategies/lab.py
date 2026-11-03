"""Strategielab-strategieën op 1-uurs candles: trend volgen, momentum, mean reversion, breakout en volatiliteit.

Signalen en indicatoren zijn bij de refactor ongewijzigd overgenomen uit strategielab.py. De uitkomst van elke
trade komt uit backtesting/engine.py (instap op de open van de volgende candle, stop eerst, financiering).
"""
import numpy as np
import pandas as pd

from backtesting import engine
from core.markets import fin_rate  # noqa: F401  (hoort bij de lab-API)

MAX_BARS = 12       # een trade duurt hoogstens 12 uur (daytrade)
GAP_HOURS = 6       # weekend/beurs dicht: trade sluiten
MIN_ROOM_R = 0.3    # minder ruimte tot het doel dan dit: signaal overslaan

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



def nights(a, b, hour_utc=22):
    """Hoe vaak de trade over het dagelijkse rollmoment (17:00 NY ≈ 22:00 UTC) heen ging: dan betaal je financiering."""
    return engine.rollovers(a, b, hour_utc)


def run_signals(X, up, dn, stopd, target, costs, exits, exit_long=None, exit_short=None):
    """Signalen (bool-reeksen op de slot van candle i) door de engine halen: instap op de open van candle i+1,
    één trade tegelijk per markt. target: ("R", x) = x keer de stopafstand, ("mid",) = het 20-uurs gemiddelde,
    None = geen doel. Geeft (signaalindex i, Trade)-paren."""
    B = engine.Bars(X)
    o = B.o
    mid = X["mid"].to_numpy() if "mid" in X else None
    sd = stopd.to_numpy()
    upa, dna = up.fillna(False).to_numpy(), dn.fillna(False).to_numpy()
    exl = exit_long.fillna(False).to_numpy() if exit_long is not None else None
    exs = exit_short.fillna(False).to_numpy() if exit_short is not None else None
    busy, out = -1, []
    for i in np.flatnonzero(upa | dna):
        if i <= busy or i + 1 >= B.n or not np.isfinite(sd[i]) or sd[i] <= 0:
            continue
        side = 1 if upa[i] else -1
        e, risk = o[i + 1], sd[i]
        stop = e - side * risk
        tp = None if target is None else (e + side * target[1] * risk if target[0] == "R" else mid[i])
        if tp is not None and (tp - e) * side <= MIN_ROOM_R * risk:          # te weinig ruimte tot het doel
            continue
        tr = engine.simulate(B, side, e, stop, tp, i + 1, "MARKET", exits, costs, exit_long=exl, exit_short=exs)
        out.append((int(i), tr))
        busy = tr.exit_i
    return out


def simulate(X, up, dn, stopd, target, cost, fin=0.0):
    """Lab-trades als dicts (formaat van lab.json en live_status). Kosten: spread/commissie (deel van de prijs)
    plus financiering per nacht (fin = rente per jaar)."""
    exits = engine.Exits(max_bars=MAX_BARS, gap_hours=GAP_HOURS)
    trend, vol = X["trend"].to_numpy(), X["vol"].to_numpy()
    out = []
    for i, tr in run_signals(X, up, dn, stopd, target, engine.Costs(frac=cost, financing=fin), exits):
        out.append(dict(t=tr.entry_time, R=tr.net_r, bruto=tr.gross_r, rr=abs(tr.tp - tr.entry) / tr.risk,
                        open=tr.reason == "open", kant="LONG" if tr.side > 0 else "SHORT", trend=trend[i], vol=vol[i],
                        entry=float(tr.entry), stop=float(tr.stop), tp=float(tr.tp), i=int(i)))
    return out
