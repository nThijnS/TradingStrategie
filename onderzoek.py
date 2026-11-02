#!/usr/bin/env python3
"""
Onderzoek (fase 3-5): extra markten en strategieën, met een vooraf vastgelegd, strikt chronologisch testprotocol.

PROTOCOL (vastgelegd vóór het draaien; niet aanpassen na het zien van de eindtest)
  Perioden (gelijk voor alle markten):
    1h-data (Yahoo, ~730 dagen)   train < 2025-11-01 ≤ validatie < 2026-05-01 ≤ EINDTEST
    dagdata (Yahoo, vanaf 2010)   train < 2023-01-01 ≤ validatie < 2026-05-01 ≤ EINDTEST
    1m-data (HistData, NQ/ES)     train < 2025-11-01 ≤ validatie < 2026-05-01 ≤ EINDTEST (t/m 23 okt 2026)
  De eindtest wordt pas gebruikt NADAT alle keuzes vastliggen, en alleen om ze te rapporteren.

  Selectiepoort (alleen train + validatie), alle vijf nodig:
    P1  minstens 30 trades in de validatie
    P2  validatie: gemiddelde R bij 1,5x kosten > 0 én block-bootstrap 95%-ondergrens (eenzijdig) > 0
    P3  train: gemiddelde R > 0 (zelfde richting in beide perioden)
    P4  Deflated Sharpe Ratio (train+validatie, gecorrigeerd voor ALLE geprobeerde varianten) ≥ 0,95
    P5  validatie zonder de 5 beste trades nog > 0 (niet afhankelijk van een paar uitschieters)
  Wie slaagt: "papertrade/demo". Live vraagt daarnaast een positieve eindtest én ≥ 3 maanden demo.

  Voor/na-vergelijking op dezelfde eindtest:
    VOOR  het bestaande lab-protocol (strategielab.choose: beste walk-forward-ondergrens), alleen data vóór de eindtest
    NA    de selectiepoort hierboven; geen strategie geslaagd = "geen trade" (0R)

KOSTEN (aannames; per instrument te verifiëren met capital_instrumenten.py)
  spread+commissie: de bestaande lab-kosten (deel van de prijs) per markt, kandidaten zie CANDIDATES
  slippage: 0,02R per trade extra; financiering: per nacht (rollover 17:00 NY) rente/365 x positiewaarde,
  6,5%/jaar indices/grondstoffen/aandelen, 2%/jaar forex, 20%/jaar crypto (bewust ruim; long én short).
  Stop en doel in dezelfde candle: stop eerst (conservatief). Instap op de open van de volgende candle.

    python onderzoek.py            # alles; schrijft rapport/onderzoek.json en rapport/2_onderzoek.md
"""
import itertools
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import strategielab as lab

HERE = Path(__file__).resolve().parent
OUT = HERE / "rapport"
VAL_1H, HOLD = pd.Timestamp("2025-11-01", tz="UTC"), pd.Timestamp("2026-05-01", tz="UTC")
VAL_1D = pd.Timestamp("2023-01-01", tz="UTC")
COST_X = 1.5
SLIP_R = 0.02
FIN = dict(crypto=0.20, forex=0.02)          # rest 0,065
RISK_PCT = 0.5                                 # om R naar % accountrendement te vertalen (benchmark)
RNG = np.random.default_rng(20261102)

# Kandidaat-markten (fase 3). Kosten zijn voorzichtige schattingen, NIET geverifieerd bij Capital.com.
CANDIDATES = [
    dict(naam="AUDUSD", symbool="AUDUSD=X", soort="forex", titel="AUD/USD", kosten=0.00010),
    dict(naam="USDCAD", symbool="CAD=X", soort="forex", titel="USD/CAD", kosten=0.00010),
    dict(naam="USDCHF", symbool="CHF=X", soort="forex", titel="USD/CHF", kosten=0.00012),
    dict(naam="NZDUSD", symbool="NZDUSD=X", soort="forex", titel="NZD/USD", kosten=0.00015),
    dict(naam="EURGBP", symbool="EURGBP=X", soort="forex", titel="EUR/GBP", kosten=0.00012),
    dict(naam="EURJPY", symbool="EURJPY=X", soort="forex", titel="EUR/JPY", kosten=0.00012),
    dict(naam="US30", symbool="YM=F", soort="index", titel="Dow Jones", kosten=0.00008),
    dict(naam="FTSE", symbool="^FTSE", soort="index", titel="FTSE 100", kosten=0.00012),
    dict(naam="NIKKEI", symbool="^N225", soort="index", titel="Nikkei 225", kosten=0.00020),
    dict(naam="CAC", symbool="^FCHI", soort="index", titel="CAC 40", kosten=0.00015),
    dict(naam="BRENT", symbool="BZ=F", soort="grondstof", titel="Brent-olie", kosten=0.0005),
    dict(naam="KOPER", symbool="HG=F", soort="grondstof", titel="Koper", kosten=0.0008),
    dict(naam="GAS", symbool="NG=F", soort="grondstof", titel="Aardgas", kosten=0.0015),
]
ALL = lab.MARKETS + CANDIDATES
TRIALS = []                                    # elke geprobeerde variant (voor DSR en de telling)


def fin_rate(m):
    return FIN.get(m["soort"], 0.065)


# ------------- Data en datakwaliteit -------------
def fetch(markets, interval, period):
    import yfinance as yf
    raw = yf.download([m["symbool"] for m in markets], interval=interval, period=period, group_by="ticker",
                      auto_adjust=False, progress=False, threads=True)
    out = {}
    for m in markets:
        try:
            out[m["naam"]] = raw[m["symbool"]][["Open", "High", "Low", "Close"]].copy()
        except KeyError:
            out[m["naam"]] = pd.DataFrame(columns=["Open", "High", "Low", "Close"])
    return out


def quality(df, interval):
    """Datakwaliteit: dekking, dubbele/ongeldige candles, platte candles, sprongen (o.a. future-rollover)."""
    d, q = lab.clean(df)
    if len(d) < 50:
        return d, dict(q, ok=False, reden="te weinig data")
    r = np.log(d["Close"]).diff()
    gap_ret = np.log(d["Open"] / d["Close"].shift())
    atr = (d["High"] - d["Low"]).rolling(50).median()
    jumps = int(((gap_ret.abs() * d["Close"]) > 8 * atr).sum())
    flat = float((d["High"] == d["Low"]).mean())
    days = d.index.normalize().unique()
    q.update(dagen=len(days), platte_candles=round(flat, 3), sprongen=jumps, ok=True)
    if interval == "1h":
        per_day = d.groupby(d.index.normalize()).size()
        q["candles_per_dag_mediaan"] = float(per_day.median())
        if flat > 0.05:
            q.update(ok=False, reden=f"{flat:.0%} platte candles (geen echte koers)")
        if len(days) < 400:
            q.update(ok=False, reden=f"maar {len(days)} handelsdagen")
    return d, q


# ------------- Simulatie -------------
def simulate(X, up, dn, stopd, target, cost_frac, fin, max_bars, exit_long=None, exit_short=None, rollover_h=22):
    """Instap op de open van de volgende candle; stop/doel op high/low (stop eerst). Geeft trades met R bruto en netto.
    exit_long/short: optionele kanaal-uitstap (bool-reeks, uitstap op de open van de volgende candle)."""
    o, h, l, c = (X[k].to_numpy() for k in ("o", "h", "l", "c"))
    mid = X["mid"].to_numpy() if "mid" in X else None
    sd = stopd.to_numpy()
    t = X.index
    upa, dna = up.fillna(False).to_numpy(), dn.fillna(False).to_numpy()
    exl = exit_long.fillna(False).to_numpy() if exit_long is not None else None
    exs = exit_short.fillna(False).to_numpy() if exit_short is not None else None
    n, busy, out = len(X), -1, []
    for i in np.flatnonzero(upa | dna):
        if i <= busy or i + 1 >= n or not np.isfinite(sd[i]) or sd[i] <= 0:
            continue
        side = 1 if upa[i] else -1
        e, risk = o[i + 1], sd[i]
        stop = e - side * risk
        tp = None if target is None else (e + side * target[1] * risk if target[0] == "R" else mid[i])
        if tp is not None and (tp - e) * side <= 0.3 * risk:
            continue
        exitp, j = None, i + 1
        for j in range(i + 1, min(i + 1 + max_bars, n)):
            if j > i + 1 and max_bars <= 48 and (t[j] - t[j - 1]) > pd.Timedelta(hours=6):
                exitp, j = c[j - 1], j - 1
                break
            if (side > 0 and o[j] <= stop) or (side < 0 and o[j] >= stop):
                exitp = o[j]; break
            if (side > 0 and l[j] <= stop) or (side < 0 and h[j] >= stop):
                exitp = stop; break
            if tp is not None:
                if (side > 0 and o[j] >= tp) or (side < 0 and o[j] <= tp):
                    exitp = o[j]; break
                if (side > 0 and h[j] >= tp) or (side < 0 and l[j] <= tp):
                    exitp = tp; break
            ex = exl if side > 0 else exs
            if ex is not None and ex[j] and j + 1 < n:
                exitp, j = o[j + 1], j + 1
                break
        if exitp is None:
            exitp = c[j]
        nights = rollovers(t[i + 1], t[j], rollover_h)
        gross = (exitp - e) * side / risk
        cost_r = cost_frac * e / risk
        fin_r = fin / 365 * nights * e / risk
        out.append(dict(t=t[i + 1], uit=t[j], bars=j - i, side=side, bruto=gross, kosten_r=cost_r, fin_r=fin_r,
                        rr=abs(tp - e) / risk if tp is not None else 0.0,
                        R=gross - cost_r - fin_r - SLIP_R, R15=gross - COST_X * cost_r - fin_r - SLIP_R))
        busy = j
    return out


def rollovers(a, b, hour_utc):
    """Aantal keer dat de positie over het dagelijkse rollmoment (17:00 NY ≈ 22:00 UTC) heen ging."""
    if b <= a:
        return 0
    first = a.normalize() + pd.Timedelta(hours=hour_utc)
    if first <= a:
        first += pd.Timedelta(days=1)
    return 0 if b < first else int((b - first) / pd.Timedelta(days=1)) + 1


# ------------- Strategieën -------------
def lab_variants():
    """De bestaande lab-strategieën (1h) met hun twee varianten, ongewijzigd."""
    for sid, info in lab.STRATS.items():
        if sid == "ict":
            continue
        for v in info["varianten"]:
            yield sid, v


def run_lab(X, m, sid, v):
    up, dn, stopd, target = lab.signals(sid, X, v)
    return simulate(X, up, dn, stopd, target, m["kosten"], fin_rate(m), lab.MAX_BARS)


def daily_X(d):
    X = pd.DataFrame(dict(o=d["Open"], h=d["High"], l=d["Low"], c=d["Close"]))
    tr = pd.concat([X.h - X.l, (X.h - X.c.shift()).abs(), (X.l - X.c.shift()).abs()], axis=1).max(axis=1)
    X["atr"] = tr.rolling(20).mean()
    return X


def donchian(X, m, n_in=55, n_out=20, k=2.0):
    """Turtle-achtige breakout: slot boven de hoogste high van n_in dagen = long (onder de laagste = short),
    stop k x ATR20, uitstap bij een slot voorbij het tegenoverliggende n_out-kanaal."""
    hi, lo = X.h.rolling(n_in).max().shift(), X.l.rolling(n_in).min().shift()
    up, dn = (X.c > hi) & (X.c.shift() <= hi.shift()), (X.c < lo) & (X.c.shift() >= lo.shift())
    ex_l, ex_s = X.c < X.l.rolling(n_out).min().shift(), X.c > X.h.rolling(n_out).max().shift()
    return simulate(X, up, dn, k * X.atr, None, m["kosten"], fin_rate(m), 400, ex_l, ex_s)


def tsmom(X, m, horizons=(21, 63, 252), k=3.0):
    """Time-series momentum: elke maand de richting van de meerderheid van de rendementen over 1, 3 en 12 maanden.
    Stop k x ATR20; uitstap als de richting bij de volgende maandwissel omdraait."""
    vote = sum(np.sign(X.c / X.c.shift(hz) - 1) for hz in horizons)
    month_start = pd.Series(X.index.to_period("M"), index=X.index) != pd.Series(X.index.to_period("M"), index=X.index).shift()
    up, dn = month_start & (vote > 0), month_start & (vote < 0)
    ex_l, ex_s = month_start & (vote <= 0), month_start & (vote >= 0)
    return simulate(X, up, dn, k * X.atr, None, m["kosten"], fin_rate(m), 400, ex_l, ex_s)


def orb(sym, minutes=30, tp=2.0, last_entry="11:30", cost_pts=2.5):
    """Opening-range-breakout NQ/ES op HistData 1m (zomertijd-correct). Range 09:30 + `minutes` NY;
    instap op de open na het eerste 5m-slot buiten de range (uiterlijk last_entry), stop aan de overkant
    van de range, doel tp x R, anders dicht om 15:55. Geen trade als de range < 0,1% of > 1,5% van de prijs."""
    import tp_videos
    d = tp_videos.load_dst(sym)
    d = d.tz_convert("America/New_York")
    d5 = d.resample("5min", label="left", closed="left").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    out = []
    for day, g in d5.groupby(d5.index.date):
        hm = g.index.strftime("%H:%M")
        rng = g[(hm >= "09:30") & (hm < (pd.Timestamp("09:30") + pd.Timedelta(minutes=minutes)).strftime("%H:%M"))]
        if len(rng) < minutes // 5:
            continue
        hi, lo = rng.High.max(), rng.Low.min()
        mid = (hi + lo) / 2
        if not (0.001 <= (hi - lo) / mid <= 0.015):
            continue
        after = g[(hm >= rng.index[-1].strftime("%H:%M")) & (hm < "15:55")].iloc[1:]
        sig = None
        for k, (t, row) in enumerate(after.iterrows()):
            if t.strftime("%H:%M") > last_entry:
                break
            if row.Close > hi or row.Close < lo:
                sig = k
                break
        if sig is None or sig + 1 >= len(after):
            continue
        side = 1 if after.Close.iloc[sig] > hi else -1
        e = after.Open.iloc[sig + 1]
        stop = lo if side > 0 else hi
        risk = (e - stop) * side
        if risk <= 0:
            continue
        target = e + side * tp * risk
        exitp, tx = after.Close.iloc[-1], after.index[-1]
        for t, row in after.iloc[sig + 1:].iterrows():
            if (side > 0 and row.Low <= stop) or (side < 0 and row.High >= stop):
                exitp, tx = stop, t; break
            if (side > 0 and row.High >= target) or (side < 0 and row.Low <= target):
                exitp, tx = target, t; break
        gross = (exitp - e) * side / risk
        c = cost_pts / risk
        out.append(dict(t=after.index[sig + 1].tz_convert("UTC"), uit=tx.tz_convert("UTC"), bars=1, side=side, bruto=gross, rr=tp,
                        kosten_r=c, fin_r=0.0, R=gross - c - SLIP_R, R15=gross - COST_X * c - SLIP_R))
    return out


# ------------- Statistiek -------------
def split(trades, val_start):
    tr = [x for x in trades if x["t"] < val_start]
    va = [x for x in trades if val_start <= x["t"] < HOLD]
    ho = [x for x in trades if x["t"] >= HOLD]
    return tr, va, ho


def block_bootstrap(trades, key="R", block_weeks=4, n=2000):
    """Onzekerheid van de gemiddelde R per trade met weekblokken (trades die dicht bij elkaar liggen hangen samen)."""
    if len(trades) < 5:
        return None
    wk = pd.Series([x[key] for x in trades], index=pd.DatetimeIndex([x["t"] for x in trades])).groupby(pd.Grouper(freq="W"))
    sums, cnts = wk.sum().to_numpy(), wk.count().to_numpy()
    W = len(sums)
    if W < 2 * block_weeks:
        return None
    nb = math.ceil(W / block_weeks)
    starts = RNG.integers(0, W - block_weeks + 1, size=(n, nb))
    idx = (starts[:, :, None] + np.arange(block_weeks)).reshape(n, -1)[:, :W]
    s, c = sums[idx].sum(1), cnts[idx].sum(1)
    means = s[c > 0] / c[c > 0]
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.05)), float(np.quantile(means, 0.975))]


def sharpe(R):
    R = np.asarray(R, float)
    return float(R.mean() / R.std(ddof=1)) if len(R) > 2 and R.std(ddof=1) > 0 else 0.0


def deflated_sharpe(R, n_trials):
    """Deflated Sharpe Ratio (Bailey & López de Prado, 2014): kans dat de echte Sharpe > 0 is, na correctie voor
    het beste van N onafhankelijke proeven, scheefheid en dikke staarten. Sharpe per trade (niet geannualiseerd).
    Nulverdeling van de geschatte Sharpe: variantie 1/(T-1). (De spreiding over alle varianten zelf gebruiken
    werkt hier niet: varianten met weinig trades blazen die op.) N = aantal markt x strategiefamilie-combinaties,
    omdat varianten binnen één familie sterk samenhangen; dat is een benadering."""
    from statistics import NormalDist
    R = np.asarray(R, float)
    T, N = len(R), max(int(n_trials), 2)
    if T < 10:
        return 0.0
    sr = sharpe(R)
    nd = NormalDist()
    g = 0.5772156649
    sr0 = math.sqrt(1 / (T - 1)) * ((1 - g) * nd.inv_cdf(1 - 1 / N) + g * nd.inv_cdf(1 - 1 / (N * math.e)))
    z = (R - R.mean()) / (R.std(ddof=1) or 1)
    skew, kurt = float(np.mean(z ** 3)), float(np.mean(z ** 4))
    den = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr ** 2))
    return float(nd.cdf((sr - sr0) * math.sqrt(T - 1) / den))


def pbo_cscv(matrix, S=8):
    """Probability of Backtest Overfitting via CSCV: verdeel de tijd in S blokken; kies op elke helft de beste
    variant en kijk waar die op de andere helft eindigt. PBO = aandeel keren dat hij onder de mediaan valt."""
    M = np.asarray(matrix, float)               # rijen: tijdblokken, kolommen: varianten (som R per blok)
    T, N = M.shape
    if T < S or N < 2:
        return None
    blocks = np.array_split(np.arange(T), S)
    logits = []
    for combo in itertools.combinations(range(S), S // 2):
        is_idx = np.concatenate([blocks[i] for i in combo])
        os_idx = np.concatenate([blocks[i] for i in range(S) if i not in combo])
        best = int(np.argmax(M[is_idx].sum(0)))
        rank = (M[os_idx].sum(0) < M[os_idx].sum(0)[best]).sum() + 0.5
        w = rank / N
        logits.append(math.log(w / (1 - w)))
    return float(np.mean(np.array(logits) <= 0))


def summary(trades, bench=None):
    if not trades:
        return dict(n=0)
    R = np.array([x["R"] for x in trades])
    G = np.array([x["bruto"] for x in trades])
    wins, losses = R[R > 0], R[R <= 0]
    eq = np.cumsum(R)
    dd = float(-(eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min())
    top = np.sort(R)[::-1]
    s = dict(n=len(R), gem_R=round(float(R.mean()), 3), bruto_gem_R=round(float(G.mean()), 3),
             gem_R_kosten15=round(float(np.mean([x["R15"] for x in trades])), 3), netto_R=round(float(R.sum()), 1),
             win=round(float((R > 0).mean()), 3), gem_winst=round(float(wins.mean()), 2) if len(wins) else 0.0,
             gem_verlies=round(float(losses.mean()), 2) if len(losses) else 0.0,
             pf=round(float(wins.sum() / -losses.sum()), 2) if losses.sum() < 0 else None, max_dd_R=round(dd, 1),
             zonder_top5=round(float(top[5:].mean()), 3) if len(top) > 10 else None,
             rendement_pct=round(float(R.sum()) * RISK_PCT, 1))
    ci = block_bootstrap(trades)
    if ci:
        s["ci95"], s["ondergrens95_eenzijdig"] = [round(ci[0], 3), round(ci[2], 3)], round(ci[1], 3)
    if bench is not None:
        s["kopen_houden_pct"] = bench
    return s


def bench(d, a, b):
    c = d["Close"][(d.index >= a) & (d.index < b)]
    return round(float((c.iloc[-1] / c.iloc[0] - 1) * 100), 1) if len(c) > 1 else None


def exposure(trades, d, a, b):
    if not trades:
        return 0.0
    bars = int(((d.index >= a) & (d.index < b)).sum())
    return round(sum(x["bars"] for x in trades) / bars, 3) if bars else 0.0


def gate(tr, va, dsr):
    """De vooraf vastgelegde selectiepoort. Geeft (geslaagd, redenen-waarom-niet)."""
    why = []
    if len(va) < 30:
        why.append(f"P1: {len(va)} validatietrades (< 30)")
    ci = block_bootstrap(va, key="R15")
    m15 = np.mean([x["R15"] for x in va]) if va else -1
    if not (m15 > 0 and ci and ci[1] > 0):
        why.append(f"P2: validatie bij 1,5x kosten {m15:+.3f}R, ondergrens {ci[1] if ci else float('nan'):+.3f}R")
    if not tr or np.mean([x["R"] for x in tr]) <= 0:
        why.append(f"P3: train {np.mean([x['R'] for x in tr]) if tr else float('nan'):+.3f}R")
    if dsr < 0.95:
        why.append(f"P4: Deflated Sharpe {dsr:.2f} (< 0,95)")
    top = sorted((x["R"] for x in va), reverse=True)
    if len(top) <= 10 or np.mean(top[5:]) <= 0:
        why.append("P5: zonder de 5 beste validatietrades niet positief")
    return not why, why


# ------------- Hoofdprogramma -------------
def main():
    OUT.mkdir(exist_ok=True)
    print("data ophalen…", flush=True)
    h1 = fetch(ALL, "1h", "730d")
    d1 = fetch(ALL, "1d", "max")
    res = dict(gemaakt=datetime.now().isoformat(timespec="minutes"), protocol=dict(
        val_1h=str(VAL_1H.date()), val_1d=str(VAL_1D.date()), eindtest=str(HOLD.date()), kosten_x=COST_X, slippage_R=SLIP_R,
        financiering=dict(FIN, overig=0.065)), markten={}, strategieen=[])

    # Fase 3: datakwaliteit en spreiding
    daily_ret = {}
    clean1h, cleand = {}, {}
    for m in ALL:
        d, q = quality(h1.get(m["naam"], pd.DataFrame()), "1h")
        dd, qd = quality(d1.get(m["naam"], pd.DataFrame()), "1d")
        clean1h[m["naam"]], cleand[m["naam"]] = d, dd
        if len(dd):
            r = np.log(dd["Close"]).diff()
            r.index = pd.DatetimeIndex(dd.index.tz_convert(None) if dd.index.tz is None else dd.index.tz_localize(None)).normalize()
            daily_ret[m["naam"]] = r[~r.index.duplicated(keep="last")]   # kalenderdatum: Europa/Japan sluiten op lokale middernacht
        res["markten"][m["naam"]] = dict(titel=m["titel"], soort=m["soort"], symbool=m["symbool"], kandidaat=m in CANDIDATES,
                                         kosten_aanname=m["kosten"], data_1h=q, data_1d=dict(van=qd.get("van"), dagen=qd.get("dagen"), sprongen=qd.get("sprongen")))
    R = pd.DataFrame(daily_ret)
    R = R[R.index >= pd.Timestamp("2024-11-01")].resample("W-FRI").sum(min_count=1)   # week: Europa/Japan sluiten eerder
    corr = R.corr(min_periods=60)
    existing = [m["naam"] for m in lab.MARKETS]
    for m in ALL:
        n = m["naam"]
        if n not in corr:
            continue
        others = corr[n].drop(n).dropna()
        ex = others[[o for o in others.index if o in existing]]
        res["markten"][n]["max_corr_bestaand"] = [ex.abs().idxmax(), round(float(ex[ex.abs().idxmax()]), 2)] if len(ex) else None

    # Fase 4/5: alle varianten, per markt
    rows = []
    for m in ALL:
        d = clean1h[m["naam"]]
        if res["markten"][m["naam"]]["data_1h"].get("ok"):
            X = lab.indicators(d)
            for sid, v in lab_variants():
                rows.append((m, f"lab:{sid}", json.dumps(v), run_lab(X, m, sid, v), VAL_1H, d))
            # regimefilter (hypothese: alleen trendstrategieën in een trendmarkt, mean reversion in een zijwaartse)
            for sid, v in lab_variants():
                tr = run_lab(X, m, sid, v)
                want = "Zijwaarts" if sid == "meanrev" else ("Uptrend", "Downtrend")
                keep = [x for x in tr if (X["trend"].asof(x["t"] - pd.Timedelta(hours=1)) in want)]
                rows.append((m, f"lab+regime:{sid}", json.dumps(v), keep, VAL_1H, d))
        dd = cleand[m["naam"]]
        if len(dd) > 1500:
            Xd = daily_X(dd)
            rows.append((m, "donchian", "55/20, 2xATR", donchian(Xd, m), VAL_1D, dd))
            rows.append((m, "tsmom", "21/63/252, 3xATR", tsmom(Xd, m), VAL_1D, dd))
    print("ORB (HistData 1m)…", flush=True)
    for naam, sym, pts in (("NQ", "NSXUSD", 2.5), ("ES", "SPXUSD", 0.75)):
        m = next(x for x in lab.MARKETS if x["naam"] == naam)
        try:
            for mins, tp in ((30, 2.0), (15, 2.0), (60, 2.0), (30, 1.5), (30, 3.0)):
                rows.append((m, "orb", f"{mins}m, {tp:g}R", orb(sym, mins, tp, cost_pts=pts), VAL_1H, None))
        except Exception as ex:
            print("ORB niet mogelijk:", ex)

    # Deflated Sharpe: N = alle geprobeerde varianten, SR-spreiding over die varianten (train+validatie)
    TRIALS.extend((m["naam"], s, v) for m, s, v, _, _, _ in rows)
    n_eff = len({(m["naam"], s.split(":")[-1]) for m, s, _, _, _, _ in rows})
    res["effectieve_proeven"] = n_eff
    for m, sid, v, trades, vs, d in rows:
        tr, va, ho = split(trades, vs)
        dsr = deflated_sharpe([x["R"] for x in tr + va], n_eff)
        ok, why = gate(tr, va, dsr)
        e = dict(markt=m["naam"], kandidaat=m in CANDIDATES, strategie=sid, variant=v, dsr=round(dsr, 3), geslaagd=ok, redenen=why,
                 train=summary(tr), validatie=summary(va), eindtest=summary(ho, bench(d, HOLD, pd.Timestamp.now(tz="UTC")) if d is not None else None))
        if d is not None:
            e["blootstelling_validatie"] = exposure(va, d, vs, HOLD)
        rows_regime = {}
        for x in tr + va:
            rows_regime.setdefault(str(x["t"].year) + ("H1" if x["t"].month <= 6 else "H2"), []).append(x["R"])
        e["per_halfjaar"] = {k: [len(v_), round(float(np.sum(v_)), 1)] for k, v_ in sorted(rows_regime.items())}
        res["strategieen"].append(e)

    # PBO over alle 1h-lab-varianten van de bestaande markten (de keuze "beste markt x strategie")
    cols = {}
    for m, sid, v, trades, vs, d in rows:
        if sid.startswith("lab:") and m in lab.MARKETS:
            s = pd.Series([x["R"] for x in trades if x["t"] < HOLD], index=pd.DatetimeIndex([x["t"] for x in trades if x["t"] < HOLD]), dtype=float)
            cols[f"{m['naam']}|{sid}|{v}"] = s.resample("MS").sum()
    M = pd.DataFrame(cols).fillna(0.0)
    res["pbo_lab"] = dict(pbo=pbo_cscv(M.to_numpy(), S=8), varianten=M.shape[1], maanden=M.shape[0])
    res["aantal_varianten"] = len(TRIALS)

    # VOOR/NA op dezelfde eindtest
    voor = before_after(rows, clean1h)
    na = {}
    for e in res["strategieen"]:          # per markt de geslaagde variant met de hoogste validatie-ondergrens
        if e["geslaagd"] and (e["markt"] not in na or e["validatie"].get("ondergrens95_eenzijdig", -9) > na[e["markt"]]["lb"]):
            na[e["markt"]] = dict(strategie=e["strategie"], variant=e["variant"], lb=e["validatie"].get("ondergrens95_eenzijdig", -9),
                                  eindtest=e["eindtest"])
    na_same = {k: v for k, v in na.items() if k in voor}   # zelfde markten als VOOR
    res["voor_na"] = dict(voor=voor, na=na, totaal=dict(voor=totals(voor), na_zelfde_markten=totals(na_same), na_alle=totals(na)))
    (OUT / "onderzoek.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    write_report(json.loads((OUT / "onderzoek.json").read_text()))
    print(f"{len(TRIALS)} varianten; geslaagd: {[(e['markt'], e['strategie'], e['variant']) for e in res['strategieen'] if e['geslaagd']]}")
    print("PBO lab:", res["pbo_lab"])
    print("voor/na:", json.dumps(res["voor_na"]["totaal"], ensure_ascii=False))


def before_after(rows, clean1h):
    """VOOR: lab-protocol (walk-forward + beste ondergrens) met data tot de eindtest. NA: de selectiepoort."""
    by_market = {}
    for m, sid, v, trades, vs, d in rows:
        if sid.startswith("lab:") and m in lab.MARKETS:
            by_market.setdefault(m["naam"], {}).setdefault(sid[4:], {})[v] = trades
    voor = {}
    for naam, strats in by_market.items():
        d = clean1h[naam]
        start = d.index[0]
        best, best_lb, best_key = None, None, None
        for sid, by_v in strats.items():
            pre = {k: [dict(x, t=x["t"]) for x in t if x["t"] < HOLD] for k, t in by_v.items()}
            oos, _ = lab.walk_forward(pre, start, HOLD)
            st = lab.stats(oos, full=False) if oos else dict(n=0)
            if st.get("n", 0) >= lab.MIN_OOS and st.get("ondergrens") is not None and (best_lb is None or st["ondergrens"] > best_lb):
                key = lab.current_variant(pre, HOLD) or max(pre, key=lambda k: np.mean([x["R"] for x in pre[k]]) if pre[k] else -9)
                best, best_lb, best_key = sid, st["ondergrens"], key
        if best and best_lb > 0:
            ho = [x for x in strats[best][best_key] if x["t"] >= HOLD]
            voor[naam] = dict(strategie=best, variant=best_key, ondergrens_wf=best_lb, eindtest=summary(ho))
        else:
            voor[naam] = dict(strategie=None, eindtest=dict(n=0))
    return voor


def totals(dct):
    return dict(trades=sum(x["eindtest"].get("n", 0) for x in dct.values()),
                netto_R=round(sum(x["eindtest"].get("netto_R", 0) for x in dct.values()), 1),
                markten_met_trades=sum(1 for x in dct.values() if x["eindtest"].get("n")))


# ------------- Rapport -------------
DECISIONS = {   # fase 3: besluit per kandidaat, op basis van datakwaliteit en spreiding (zie tabel)
    "AUDUSD": ("uitgesteld", "data goed; deels dollar-factor (0,69 met GBP/USD); instrumentgegevens nog niet geverifieerd"),
    "USDCAD": ("uitgesteld", "data goed; vooral dollar-factor (−0,69 met EUR/USD); instrumentgegevens nog niet geverifieerd"),
    "USDCHF": ("afgewezen", "−0,82 met EUR/USD: vrijwel dezelfde weddenschap, geen spreiding"),
    "NZDUSD": ("afgewezen", "0,80 met GBP/USD en een hogere spread: weinig spreiding voor meer kosten"),
    "EURGBP": ("uitgesteld", "beste spreiding van de forexparen (0,36 met EUR/USD); instrumentgegevens nog niet geverifieerd"),
    "EURJPY": ("uitgesteld", "0,65 met USD/JPY; instrumentgegevens nog niet geverifieerd"),
    "US30": ("afgewezen", "0,90 met S&P 500: geen spreiding (de correlatiegroep telt ze toch als één)"),
    "FTSE": ("uitgesteld", "0,73 met DAX; Yahoo geeft alleen de beursuren (9 candles/dag), de CFD handelt bijna de hele dag: databron sluit niet aan"),
    "NIKKEI": ("uitgesteld", "matige samenhang (0,59 met Nasdaq), Aziatische uren; Yahoo-uren (7/dag) sluiten niet aan op de CFD"),
    "CAC": ("afgewezen", "0,86 met DAX: geen spreiding"),
    "BRENT": ("afgewezen", "0,92 met WTI-olie: geen spreiding"),
    "KOPER": ("uitgesteld", "redelijke spreiding (0,50 met zilver); spread en instrument nog niet geverifieerd"),
    "GAS": ("afgewezen", "13 prijssprongen in de Yahoo-future (rollovers): data sluit niet aan op een CFD; hoge kosten"),
}


def fmt(x, nd=2):
    return "–" if x is None else (f"{x:+.{nd}f}" if isinstance(x, (int, float)) else str(x))


def write_report(res):
    S = res["strategieen"]
    L = []
    a = L.append
    a("# Fase 3–5 — Onderzoek markten en strategieën\n")
    a(f"Gemaakt {res['gemaakt']} met `python onderzoek.py` (gegevens: `rapport/onderzoek.json`). "
      "Het protocol staat bovenaan `onderzoek.py` en lag vast voordat de eindtest werd bekeken.\n")
    a("## Kernpunten\n")
    a(f"- **{res['aantal_varianten']} varianten** getest ({res['effectieve_proeven']} markt × strategiefamilie-combinaties). "
      f"**Geen enkele** haalt de selectiepoort (P1–P5). Geen variant faalt alléén op de Deflated Sharpe: elke variant faalt ook op minstens één eenvoudige toets.")
    pbo = res["pbo_lab"]
    a(f"- **PBO (CSCV)** van de lab-keuze \"beste markt × strategie\": **{pbo['pbo']:.0%}** "
      f"({pbo['varianten']} varianten, {pbo['maanden']} maanden). Boven 50% betekent: de in-sample beste is vaker wel dan niet "
      "een slechte keuze voor de periode erna.")
    t = res["voor_na"]["totaal"]
    a(f"- **Voor/na op dezelfde eindtest (vanaf {res['protocol']['eindtest']}):**")
    a(f"  - VOOR (het lab-protocol): {t['voor']['trades']} trades in {t['voor']['markten_met_trades']} markten, netto **{t['voor']['netto_R']:+.1f}R**.")
    a(f"  - NA (de selectiepoort): {t['na_alle']['trades']} trades, **{t['na_alle']['netto_R']:+.1f}R** (\"geen trade\").")
    a("  - Dat \"na\" niet verliest, is geen bewezen verbetering. Het betekent alleen dat er niets wordt gehandeld dat niet bewezen is.\n")
    a("## Voor: wat het lab-protocol koos (alleen data vóór de eindtest) en hoe dat uitpakte\n")
    a("| Markt | Strategie | Variant | WF-ondergrens | Eindtest n | gem. R | netto R | 95%-interval (blokken) |")
    a("|---|---|---|---|---|---|---|---|")
    for k, v in res["voor_na"]["voor"].items():
        if v["strategie"]:
            e = v["eindtest"]
            a(f"| {k} | {v['strategie']} | `{v['variant']}` | {fmt(v['ondergrens_wf'], 3)} | {e.get('n', 0)} | {fmt(e.get('gem_R'), 3)} | {fmt(e.get('netto_R'), 1)} | {e.get('ci95') or '–'} |")
    a("\nDe andere bestaande markten kregen ook in het oude protocol \"geen trade\". ICT is hier buiten beschouwing gelaten; "
      "die wordt apart door `leren.py` gekozen (eerdere toets met zomertijd-correcte data: geen voordeel op NQ/EURUSD in 2026).\n")
    a("## Markten (fase 3)\n")
    a("Bron Yahoo Finance. Dagen = handelsdagen met 1h-data. Sprongen = openingsgaten groter dan 8× de mediane candle "
      "(vaak future-rollovers). Correlatie = weekrendementen sinds nov 2024 (dagrendementen onderschatten de samenhang tussen markten die op verschillende tijden sluiten), hoogste absolute met een bestaande markt.\n")
    a("| Markt | Kandidaat | 1h-dagen | candles/dag | platte candles | sprongen | hoogste correlatie | Besluit |")
    a("|---|---|---|---|---|---|---|---|")
    for k, v in res["markten"].items():
        q = v["data_1h"]
        c = v.get("max_corr_bestaand")
        dec = DECISIONS.get(k, ("bestaand", ""))
        a(f"| {k} ({v['titel']}) | {'ja' if v['kandidaat'] else 'nee'} | {q.get('dagen', '–')} | {q.get('candles_per_dag_mediaan', '–')} | "
          f"{q.get('platte_candles', '–')} | {q.get('sprongen', '–')} | {c[0] + ' ' + fmt(c[1]) if c else '–'} | "
          f"{dec[0]}{': ' + dec[1] if dec[1] else ''} |")
    a("\nGeen enkele kandidaat is toegevoegd. Twee redenen:")
    a("- De instrumentgegevens bij Capital.com (epic, contractgrootte, spread, financiering, uren) zijn nog niet uitgelezen. "
      "Dat doet `capital_instrumenten.py`, met de demo-sleutels in GitHub.")
    a("- Geen strategie haalt op deze markten de poort.\n")
    a("Bestaande markten die sterk samenhangen (NQ–ES 0,95, BTC–ETH 0,82, EUR/USD–GBP/USD 0,82, goud–zilver 0,76, NVDA–NQ 0,71) blijven bestaan. "
      "`risico.py` telt ze voortaan als één groep: max 1 positie per groep en richting.\n")
    a("## Strategieën (fase 4): beste per familie\n")
    a("Per familie de variant met de hoogste validatie-ondergrens. gem. R is netto (kosten, slippage 0,02R en financiering); "
      "×1,5 = met 50% hogere kosten. Interval = block-bootstrap per week, 95%.\n")
    a("| Markt | Strategie | Variant | Train n / gem. R | Validatie n / gem. R / ×1,5 | Val. ondergrens | DSR | Eindtest n / gem. R / interval | Faalt op |")
    a("|---|---|---|---|---|---|---|---|---|")
    fams = {}
    for e in S:
        k = (e["markt"], e["strategie"])
        if k not in fams or (e["validatie"].get("ondergrens95_eenzijdig") or -9) > (fams[k]["validatie"].get("ondergrens95_eenzijdig") or -9):
            fams[k] = e
    best = sorted(fams.values(), key=lambda e: -(e["validatie"].get("ondergrens95_eenzijdig") or -9))
    for e in best[:25] + [x for x in best[25:] if x["strategie"] in ("orb",) or (x["markt"] == "NQ" and x["strategie"] == "lab:trend")]:
        tr, va, ho = e["train"], e["validatie"], e["eindtest"]
        a(f"| {e['markt']} | {e['strategie']} | `{e['variant']}` | {tr.get('n', 0)} / {fmt(tr.get('gem_R'), 3)} | "
          f"{va.get('n', 0)} / {fmt(va.get('gem_R'), 3)} / {fmt(va.get('gem_R_kosten15'), 3)} | {fmt(va.get('ondergrens95_eenzijdig'), 3)} | "
          f"{e['dsr']:.2f} | {ho.get('n', 0)} / {fmt(ho.get('gem_R'), 3)} / {ho.get('ci95') or '–'} | {', '.join(w.split(':')[0] for w in e['redenen'])} |")
    a("\n### Per hypothese\n")
    a("- **Donchian 55/20 en time-series momentum (21/63/252 dagen), dagdata:**")
    a("  - Te weinig trades in de validatie (meestal 6–19 per markt). P1 faalt dus overal.")
    a("  - De resultaten springen per markt alle kanten op.")
    a("  - Er komt financiering per nacht bij.")
    a("  - Deze strategieën houden posities dagen tot weken vast. Dat past niet bij de daytrade-opzet en de prop-regels van de bot.")
    a("  - **Afgewezen voor nu.**")
    a("- **Opening-range-breakout NQ/ES (HistData 1m, zomertijd-correct):**")
    a("  - Alle 10 varianten zijn negatief of rond 0, in train, validatie én eindtest.")
    a("  - **Afgewezen.**")
    a("- **VWAP-pullback:**")
    a("  - Niet getest. Voor forex en CFD's is er geen betrouwbare volumedata, en Yahoo-futures geven maar 60 dagen 5m-data.")
    a("  - **Uitgesteld**, tot er een volumebron is die aansluit op de broker.")
    a("- **Regimefilter op de lab-strategieën** (trendstrategieën alleen in een trendmarkt, mean reversion alleen in een zijwaartse markt):")
    a("  - Haalt ook nergens de poort; meestal te weinig trades.")
    a("  - Behandeld als filter, niet als eigen strategie. **Niet ingevoerd.**")
    a("- **Bestaande lab-strategieën:** geen enkele combinatie slaagt.")
    a("  - Nasdaq 100 trend volgen (op de site: +0,12R, interval −0,08 tot +0,32) was in de validatie (nov 2025 – apr 2026) negatief.")
    a("  - De positieve eindtest daarna heeft maar 24 trades en een interval dat ruim door 0 loopt.\n")
    a("## Beperkingen\n")
    a("- **Data:**")
    a("  - Yahoo 1h gaat ~730 dagen terug, dus de eindtest is maar 6 maanden.")
    a("  - Futures zijn continue contracten met rollovers. Capital.com handelt CFD's met andere uren en prijzen.")
    a("  - Yahoo-futures lopen 10–15 minuten achter.")
    a("- **Kosten:** dit zijn schattingen, niet bij Capital.com geverifieerd.")
    a("  - De spread is per markt vast gekozen.")
    a("  - Financiering is ruim gerekend.")
    a("  - Spreads bij nieuws en 's nachts zijn breder dan hier aangenomen.")
    a("- **Statistiek:**")
    a("  - Voor de DSR is aangenomen dat de proeven onafhankelijk zijn, met N = markt × familie. Varianten hangen samen, dus de echte N ligt lager.")
    a("  - De DSR rekent met de Sharpe per trade.")
    a("  - Het block-bootstrap-interval gebruikt weekblokken.")
    a("  - PBO is berekend op maandsommen.")
    a("- **Overlevingsbias:** de markten zijn vandaag gekozen. Aandelen als NVDA zijn achteraf winnaars, en dat vertekent kopen-en-houden en trendstrategieën.")
    a("- **Eindtest:** die is nu één keer bekeken. Een volgende ronde moet een nieuwe, latere eindtest gebruiken.")
    (OUT / "2_onderzoek.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    import sys
    if "--rapport" in sys.argv:
        write_report(json.loads((OUT / "onderzoek.json").read_text()))
    else:
        main()
