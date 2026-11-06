#!/usr/bin/env python3
"""Verdieping op rapport 8: FVG tegen toeval, ronde getallen (Osler), breedte, staarten, spread in stress, moment van
dagtop en dagbodem. Beschrijvend: geen strategieën, geen poort, en bewust NIET de vijf hypotheses uit rapport 8
(maandeinde, COT, funding, slotmomentum, combinaties), zodat die later zuiver getoetst kunnen worden.

    python -W ignore -m research.marktonderzoek2 <map met capitaldata> [--uit rapport/marktonderzoek2.json]
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from core.data import load_histdata, to5
from core.markets import LAB_MARKETS
from execution.markets import EPICS
from research.marktonderzoek import BIN, HIST, daily, laad, tday
from storage import paths

FVG_MARKETEN = ("NQ", "ES", "GOUD", "EURUSD", "GBPUSD", "BTC")
ROND = {"EURUSD": 0.01, "GBPUSD": 0.01, "NQ": 100.0, "ES": 50.0, "GOUD": 10.0, "ZILVER": 1.0, "BTC": 1000.0}
RNG = np.random.default_rng(20261105)
FILL_BARS = 12


def bars5(n):
    if n in HIST:
        return to5(load_histdata(HIST[n]))
    return pd.read_pickle(paths.DATA / "binance" / f"{BIN[n]}_5m.pkl")[["Open", "High", "Low", "Close"]]


def shuffled_within_day(d):
    """Zelfde candles per dag, in willekeurige volgorde: elke opbouw over tijd is weg, dagvolatiliteit blijft."""
    o, h, l, c = (np.log(d[x].to_numpy()) for x in ("Open", "High", "Low", "Close"))
    gap = np.r_[0, o[1:] - c[:-1]]
    parts = np.c_[gap, h - o, l - o, c - o]
    days = tday(d.index)
    u, inv = np.unique(np.asarray(days, dtype="datetime64[D]"), return_inverse=True)
    order = np.lexsort((RNG.random(len(d)), inv))
    p = parts[order]
    cc = np.cumsum(p[:, 0] + p[:, 3]) + o[0]
    oo = cc - p[:, 3]
    return pd.DataFrame(np.exp(np.c_[oo, oo + p[:, 1], oo + p[:, 2], cc]), index=d.index, columns=["Open", "High", "Low", "Close"])


def fvg_stats(d, mask):
    H, L, C = d["High"].to_numpy(), d["Low"].to_numpy(), d["Close"].to_numpy()
    tr = np.maximum(H - L, np.maximum(np.abs(H - np.r_[C[0], C[:-1]]), np.abs(L - np.r_[C[0], C[:-1]])))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    n, gaps, fills, after = len(d), 0, 0, []
    for i in np.flatnonzero(mask):
        if i < 2 or i + FILL_BARS * 2 >= n:
            continue
        for side, top, bot in ((1, L[i], H[i - 2]), (-1, L[i - 2], H[i])):
            if top <= bot:
                continue
            gaps += 1
            mid = (top + bot) / 2
            w = (L[i + 1:i + 1 + FILL_BARS] <= mid) if side > 0 else (H[i + 1:i + 1 + FILL_BARS] >= mid)
            if w.any():
                fills += 1
                j = i + 1 + int(np.argmax(w))
                after.append((C[j + FILL_BARS] - mid) * side / atr[j])
    a = np.array(after)
    return dict(candles=int(mask.sum()), gaps=gaps, per_100=round(gaps / max(mask.sum(), 1) * 100, 1), gevuld_pct=round(fills / max(gaps, 1) * 100, 1),
                na_vulling_atr=round(float(a.mean()), 3) if len(a) else None, se=round(float(a.std(ddof=1) / np.sqrt(len(a))), 3) if len(a) > 1 else None,
                richting_ok_pct=round(float((a > 0).mean() * 100), 1) if len(a) else None)


def round_numbers(n, step):
    d = load_histdata(HIST[n]) if n in HIST else bars5(n)
    wait = 15 if n in HIST else 3
    d = d[(d.index.hour >= 9) & (d.index.hour < 16)]
    res = {"rond": [0, 0], "willekeurig": [0, 0]}
    for _, g in d.groupby(d.index.date):
        H, L, C = g["High"].to_numpy(), g["Low"].to_numpy(), g["Close"].to_numpy()
        if len(C) < wait + 2:
            continue
        lo, hi = L.min(), H.max()
        for kind, offs in (("rond", (0.0,)), ("willekeurig", (0.37, 0.71))):
            for off in offs:
                k0 = np.floor(lo / step)
                for k in np.arange(k0, np.ceil(hi / step) + 1):
                    lvl = (k + off) * step
                    hit = np.flatnonzero((L[1:] <= lvl) & (H[1:] >= lvl))
                    if not len(hit):
                        continue
                    t = hit[0] + 1
                    if t + wait >= len(C) or C[t - 1] == lvl:
                        continue
                    side = np.sign(C[t - 1] - lvl)
                    res[kind][0] += 1
                    res[kind][1] += int((C[t + wait] - lvl) * side > 0)
    f = lambda v: dict(n=v[0], terug_pct=round(v[1] / max(v[0], 1) * 100, 1), se=round(float(np.sqrt(.25 / max(v[0], 1))) * 100, 1))
    return {k: f(v) for k, v in res.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("--uit", default="rapport/marktonderzoek2.json")
    a = ap.parse_args()
    out = dict(fvg={}, ronde_getallen={}, staarten={}, spread_stress={}, dagtop={})
    for n in FVG_MARKETEN:
        d = bars5(n)
        m = lambda x: np.array([(9, 30) <= (t.hour, t.minute) < (11, 30) for t in x.index])
        r = shuffled_within_day(d)
        out["fvg"][n] = dict(echt=fvg_stats(d, m(d)), door_elkaar=fvg_stats(r, m(r)))
        print(n, out["fvg"][n], flush=True)
    for n, s in ROND.items():
        out["ronde_getallen"][n] = round_numbers(n, s)
        print(n, out["ronde_getallen"][n], flush=True)
    ret = {}
    for m in LAB_MARKETS:
        n = m["naam"]
        d = laad(a.map, EPICS[n])
        dd = daily(d)
        dd = dd[dd["n"] >= 5]
        r = np.log(dd["C"]).diff().dropna()
        ret[n] = r
        tr = pd.concat([d["High"] - d["Low"], (d["High"] - d["Close"].shift()).abs(), (d["Low"] - d["Close"].shift()).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
        gapmask = d.index.to_series().diff() > pd.Timedelta(hours=2)
        gap = ((d["Open"] - d["Close"].shift()).abs() / atr)[gapmask.values]
        multi = (tr / atr).dropna()
        out["staarten"][n] = dict(kurtosis_dag=round(float(r.kurt()), 1), slechtste_dag_pct=round(float(r.min() * 100), 1), beste_dag_pct=round(float(r.max() * 100), 1),
                                  dag_gt_3sd=int((r.abs() > 3 * r.std()).sum()), uur_gt_3atr_pct=round(float((multi > 3).mean() * 100), 2), max_uur_atr=round(float(multi.max()), 1),
                                  gaten=int(len(gap)), gat_p50_atr=round(float(gap.median()), 2) if len(gap) else None, gat_p95_atr=round(float(gap.quantile(.95)), 2) if len(gap) else None,
                                  gat_max_atr=round(float(gap.max()), 1) if len(gap) else None)
        sp = d["spread"] / d["Close"] * 100
        dv = (d["High"] - d["Low"]).div(d["Close"]).groupby(tday(d.index)).sum()
        topdays = set(dv.sort_values(ascending=False).head(10).index)
        isT = pd.Series(tday(d.index), index=d.index).isin(topdays)
        ny = (d.index.hour >= 9) & (d.index.hour < 16)
        out["spread_stress"][n] = dict(mediaan=round(float(sp[ny].median()), 4), top10dagen=round(float(sp[ny & isT.values].median()), 4), p99=round(float(sp.quantile(.99)), 4), max=round(float(sp.max()), 3))
        h = d.index.hour
        s = pd.Series(np.select([(h >= 20) | (h < 2), (h >= 2) & (h < 9), (h >= 9) & (h < 12), (h >= 12) & (h < 16)], ["Azië", "Londen", "NY-ochtend", "NY-middag"], "Avond"), index=d.index)
        g = d.assign(td=tday(d.index), sess=s.values)
        hi = g.loc[g.groupby("td")["High"].idxmax(), "sess"].value_counts(normalize=True)
        lo = g.loc[g.groupby("td")["Low"].idxmin(), "sess"].value_counts(normalize=True)
        out["dagtop"][n] = dict(top=(hi * 100).round(0).to_dict(), bodem=(lo * 100).round(0).to_dict(), uren=(s.value_counts(normalize=True) * 100).round(0).to_dict())
    R = pd.DataFrame(ret).dropna()
    lam = np.linalg.eigvalsh(R.corr().to_numpy())[::-1]
    cum = np.cumsum(lam) / lam.sum()
    out["breedte"] = dict(eigen=[round(float(x), 2) for x in lam], effectief_n=round(float(lam.sum() ** 2 / (lam ** 2).sum()), 1), factoren_80pct=int(np.argmax(cum >= .8) + 1),
                          eerste_factor_pct=round(float(lam[0] / lam.sum() * 100), 1), dagen=len(R))
    Path(a.uit).write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    print(out["breedte"], out["staarten"], out["spread_stress"], out["dagtop"], sep="\n")


if __name__ == "__main__":
    main()
