#!/usr/bin/env python3
"""Beschrijvend marktonderzoek (rapport 8): 15 markten, 2 jaar. Geen strategieën, geen poort, geen orders.

    python -W ignore -m research.marktonderzoek <map met capitaldata> [--uit rapport/marktonderzoek.json]
Uurdata: artifact van workflow Capitaldata (middenkoers en spread). 5m: HistData, Binance of Yahoo (60 dagen).
"""
import argparse
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from core.data import load_histdata, to5
from core.markets import LAB_MARKETS, fin_rate
from core.sessions import NY
from execution.markets import EPICS
from storage import paths

HIST = {"NQ": "NSXUSD", "ES": "SPXUSD", "GOUD": "XAUUSD", "ZILVER": "XAGUSD", "EURUSD": "EURUSD", "GBPUSD": "GBPUSD"}
BIN = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
SESS = {"Azië 20-02": (20, 2), "Londen 02-09": (2, 9), "NY-ochtend 09-12": (9, 12), "NY-middag 12-16": (12, 16), "Avond 16-20": (16, 20)}
HORIZON = 4         # uren na de sweep


def laad(pad, epic):
    with gzip.open(Path(pad) / f"{epic}.csv.gz", "rt") as f:
        d = pd.read_csv(f, index_col=0)
    d.index = pd.to_datetime(d.index, utc=True).tz_convert(NY)
    return d[~d.index.duplicated()].sort_index()


def vr(r, k):
    """Variantieverhouding (Lo-MacKinlay) met robuuste standaardfout. >1 trend, <1 terugkeer, 1 toeval."""
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 10 * k:
        return None
    m = r.mean()
    d = r - m
    v1 = (d ** 2).sum() / (n - 1)
    c = np.cumsum(r)
    rk = c[k - 1:] - np.r_[0, c[:-k]]
    vk = ((rk - k * m) ** 2).sum() / (k * (n - k + 1) * (1 - k / n))
    th = 0.0
    den = (d ** 2).sum() ** 2
    for j in range(1, k):
        delta = n * ((d[j:] ** 2) * (d[:-j] ** 2)).sum() / den
        th += (2 * (k - j) / k) ** 2 * delta
    return dict(vr=round(float(vk / v1), 3), se=round(float(np.sqrt(th / n)), 3), ac1=round(float(pd.Series(r).autocorr(1)), 3), n=n)


def intraday_rets(d):
    """Log-rendement binnen aaneengesloten handel: sprongen over een sluiting tellen niet mee."""
    r = np.log(d["Close"]).diff()
    gap = d.index.to_series().diff() > 3 * d.index.to_series().diff().median()
    return r[~gap.values]


def tday(idx):
    return pd.Index([(t + pd.Timedelta(hours=6)).date() for t in idx])


def daily(d):
    g = d.assign(td=tday(d.index)).groupby("td")
    return g.agg(O=("Open", "first"), H=("High", "max"), L=("Low", "min"), C=("Close", "last"), n=("Close", "size"))


def session_table(d):
    rng = (d["High"] - d["Low"]) / d["Close"] * 100
    out = {}
    h = d.index.hour
    for name, (a, b) in SESS.items():
        mask = (h >= a) & (h < b) if a < b else (h >= a) | (h < b)
        out[name] = dict(range_pct=round(float(rng[mask].median()), 3) if mask.any() else None,
                         spread_pct=round(float((d["spread"] / d["Close"] * 100)[mask].median()), 4) if mask.any() else None, uren=int(mask.sum()))
    byh = rng.groupby(h).median()
    sp = (d["spread"] / d["Close"] * 100).groupby(h).median()
    return out, dict(piekuur=int(byh.idxmax()), piek_pct=round(float(byh.max()), 3), dal_pct=round(float(byh.min()), 3),
                     spread_uur=sp.round(4).to_dict())


def sweeps(d):
    """Eerste veging per niveau per dag tussen 09:00 en 16:00 NY op uurcandles. Beschrijvend, geen strategie.
    Uitkomst: beweging HORIZON uur later, in ATR, met het teken zo dat + terug van het niveau af betekent."""
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - d["Close"].shift()).abs(), (d["Low"] - d["Close"].shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    H, L, C = d["High"].to_numpy(), d["Low"].to_numpy(), d["Close"].to_numpy()
    idx, td = d.index, tday(d.index)
    hours = idx.hour
    dd = daily(d)
    pdh, pdl = dd["H"].shift(1), dd["L"].shift(1)
    rows = []
    days = pd.unique(td)
    for day in days:
        pos = np.flatnonzero(td == day)
        if len(pos) < 6 or day not in pdh.index or not np.isfinite(pdh[day]):
            continue
        a = pos[(hours[pos] >= 20) | (hours[pos] < 2)]
        l = pos[(hours[pos] >= 2) & (hours[pos] < 5)]
        lv = {"vorige dag": (pdh[day], pdl[day])}
        if len(a):
            lv["Azië"] = (H[a].max(), L[a].min())
        if len(l):
            lv["Londen"] = (H[l].max(), L[l].min())
        ny = pos[(hours[pos] >= 9) & (hours[pos] < 16)]
        if not len(ny):
            continue
        for name, (hi, lo) in lv.items():
            for side, lvl in ((1, hi), (-1, lo)):
                rows.append(dict(niveau=name, geveegd=False, side=side))
                if len(ny) and (H[ny[0]] > lvl if side > 0 else L[ny[0]] < lvl) and (C[ny[0] - 1] > lvl if side > 0 else C[ny[0] - 1] < lvl):
                    rows[-1]["voorbij_open"] = True       # stond er al voorbij: geen veging
                    continue
                for i in ny:
                    if (H[i] > lvl and C[i - 1] <= lvl) if side > 0 else (L[i] < lvl and C[i - 1] >= lvl):
                        j = i + HORIZON
                        if j >= len(C):
                            break
                        back = (C[i] <= lvl) if side > 0 else (C[i] >= lvl)
                        rows[-1].update(geveegd=True, terug=bool(back), r=float((C[i] - C[j]) * side / atr[i]))
                        break
    t = pd.DataFrame(rows)
    out = {}
    for name, g in t.groupby("niveau"):
        s = g[g["geveegd"]]
        b, c = s[s["terug"].astype(bool)], s[~s["terug"].astype(bool)]
        f = lambda x: dict(n=len(x), gem_atr=round(float(x["r"].mean()), 3) if len(x) else None,
                           se=round(float(x["r"].std(ddof=1) / np.sqrt(len(x))), 3) if len(x) > 1 else None,
                           terugloop_pct=round(float((x["r"] > 0).mean() * 100), 1) if len(x) else None)
        out[name] = dict(kans_per_dag_kant=round(len(s) / max(len(g), 1) * 100, 1), sluit_terug_pct=round(len(b) / max(len(s), 1) * 100, 1),
                         alle=f(s), sluit_terug=f(b), sluit_voorbij=f(c))
    return out


def five_min(name, sym_yahoo):
    try:
        if name in HIST:
            return to5(load_histdata(HIST[name])), "HistData"
        if name in BIN:
            return pd.read_pickle(paths.DATA / "binance" / f"{BIN[name]}_5m.pkl"), "Binance"
        from core.data import fetch
        return fetch(sym_yahoo, "60d"), "Yahoo 60d"
    except Exception as ex:
        print(name, "geen 5m:", ex, flush=True)
        return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("--uit", default="rapport/marktonderzoek.json")
    a = ap.parse_args()
    res, closes = {}, {}
    for m in LAB_MARKETS:
        n = m["naam"]
        d = laad(a.map, EPICS[n])
        dd = daily(d)
        dd = dd[dd["n"] >= 5]
        dr = np.log(dd["C"]).diff().dropna()
        closes[n] = dr
        tr = pd.concat([d["High"] - d["Low"], (d["High"] - d["Close"].shift()).abs(), (d["Low"] - d["Close"].shift()).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
        sp = d["spread"] / d["Close"] * 100
        sess, hour = session_table(d)
        per_year = 365 if m["soort"] == "crypto" else 252
        d5, bron5 = five_min(n, m["symbool"])
        cut = dd.index[len(dd) // 2]
        rvol30 = dr.rolling(30).std() * np.sqrt(per_year) * 100
        res[n] = dict(soort=m["soort"], epic=EPICS[n], bron_1h=f"Capital.com {d.index[0]:%Y-%m-%d} t/m {d.index[-1]:%Y-%m-%d}, {len(d)} candles",
                      bron_5m=(f"{bron5} {d5.index[0]:%Y-%m-%d} t/m {d5.index[-1]:%Y-%m-%d}" if d5 is not None else None),
                      jaar_vol_pct=round(float(dr.std() * np.sqrt(per_year) * 100), 1), vol30_min=round(float(rvol30.min()), 1), vol30_max=round(float(rvol30.max()), 1),
                      vol30_max_dag=str(rvol30.idxmax()), dagrange_pct=round(float(((dd["H"] - dd["L"]) / dd["C"] * 100).median()), 2),
                      uurrange_pct=round(float(((d["High"] - d["Low"]) / d["Close"] * 100).median()), 3),
                      rendement_pct=round(float((dd["C"].iloc[-1] / dd["O"].iloc[0] - 1) * 100), 1),
                      sessies=sess, uurprofiel=hour,
                      vr=dict(m5=vr(intraday_rets(d5), 12) if d5 is not None else None, h1=vr(intraday_rets(d), 24), d1=vr(dr, 5)),
                      vr_1e_helft=vr(dr[dr.index < cut], 5), vr_2e_helft=vr(dr[dr.index >= cut], 5),
                      spread_pct=round(float(sp.median()), 4), spread_p90=round(float(sp.quantile(.9)), 4),
                      spread_op_uuratr=round(float((d["spread"] / atr).median()), 3), spread_op_dagrange=round(float(sp.median() / ((dd["H"] - dd["L"]) / dd["C"] * 100).median()), 3),
                      fin_pct_jaar_aanname=fin_rate(m) * 100, sweeps=sweeps(d))
        print(n, res[n]["bron_1h"], res[n]["bron_5m"], flush=True)
    R = pd.DataFrame(closes).dropna()
    corr = R.corr().round(2)
    stress = R["ES"] <= R["ES"].quantile(.05)
    rust = R.loc[~stress].corr()
    st = R.loc[stress].corr()
    tri = np.triu_indices(len(corr), 1)
    big = {k: [(str(t), round(float(v * 100), 2)) for t, v in R[k].reindex(R[k].abs().sort_values(ascending=False).index).head(6).items()] for k in ("ES", "BTC", "GOUD", "OLIE", "EURUSD")}
    es_v = R["ES"].rolling(30).std() * np.sqrt(252) * 100
    out = dict(markten=res, correlatie=corr.to_dict(), gem_corr_rust=round(float(rust.to_numpy()[tri].mean()), 3), gem_corr_stress=round(float(st.to_numpy()[tri].mean()), 3),
               stress_dagen=int(stress.sum()), stress_es_met={k: round(float(st.loc["ES", k]), 2) for k in R}, rust_es_met={k: round(float(rust.loc["ES", k]), 2) for k in R},
               grootste_dagen=big, es_vol_per_kwartaal=es_v.groupby(pd.PeriodIndex(pd.to_datetime(es_v.index), freq="Q")).mean().round(1).rename(str).to_dict())
    Path(a.uit).write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
