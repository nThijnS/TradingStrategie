#!/usr/bin/env python3
"""Toets van de vijf ideeën uit rapport 9 (protocol research/vijf_protocol.json). Plaatst nooit orders.

    python -W ignore -m research.vijf <map met capitaldata> [--uit rapport/vijf.json]
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backtesting import engine
from backtesting.metrics import deflated_sharpe
from core.data import load_histdata, to5
from core.markets import LAB_MARKETS
from core.sessions import NY
from execution.markets import EPICS
from learning import selector
from research import registry
from research.tijdframes import MODEL_KOSTEN
from storage import paths
from strategies import lab as strat

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "research" / "vijf_protocol.json"
D = paths.DATA / "onderzoek5"
SCAN = 876
PROEVEN_EXTRA = 11 + 4 + 9
FAM = [k for k in strat.STRATS if k != "ict"]
BASIS = [(f, v) for f in FAM for v in strat.STRATS[f]["varianten"]]
EXITS_LAB = engine.Exits(max_bars=strat.MAX_BARS, gap_hours=strat.GAP_HOURS)
H1_MARKTEN = ("NQ", "ES", "DAX", "GOUD", "EURUSD", "USDJPY")
COT = {"GOUD": ("088691", 1), "ZILVER": ("084691", 1), "OLIE": ("067651", 1), "ES": ("13874A", 1), "NQ": ("209742", 1),
       "EURUSD": ("099741", 1), "GBPUSD": ("096742", 1), "USDJPY": ("097741", -1)}
MAX_SPREAD_R = 0.25
BAR1H = pd.Timedelta(hours=1)


# ------------- Bouwstenen, los getest -------------
def drempelsignaal(es, zn, delta=0.02, start=0.6):
    """60/40-weging. Signaal = gewicht min 60% vóór herbalancering; boven delta terug naar 60%."""
    w, out = start, {}
    r = pd.concat([es.pct_change(), zn.pct_change()], axis=1, keys=["e", "z"]).dropna()
    for t, (re, rz) in zip(r.index, r.to_numpy()):
        w = w * (1 + re) / (w * (1 + re) + (1 - w) * (1 + rz))
        s = w - start
        out[t] = s
        if abs(s) > delta:
            w = start
    return pd.Series(out)


def spec_druk(cot, code, teken=1, weken=52, lag_dagen=3):
    """Speculatieve druk per beschikbare datum (meetdatum + lag), gemiddeld over 52 weken."""
    d = cot[cot["CFTC Contract Market Code"].astype(str).str.strip() == code].copy()
    d["t"] = pd.to_datetime(d["As of Date in Form YYYY-MM-DD"])
    d = d.sort_values("t").drop_duplicates("t").set_index("t")
    L, S = d["Noncommercial Positions-Long (All)"].astype(float), d["Noncommercial Positions-Short (All)"].astype(float)
    sp = ((L - S) / (L + S)).rolling(weken).mean() * teken
    sp.index = sp.index + pd.Timedelta(days=lag_dagen)
    return sp.dropna()


def grote_dag(r, n=60, kw=2 / 3):
    """True als |r| boven het kwantiel van de vorige n dagen ligt (vandaag telt niet mee)."""
    a = r.abs()
    return a > a.shift(1).rolling(n).quantile(kw)


def funding_aan(f, n=21, jaar=365):
    """Dagelijks om 00:00 UTC: gemiddelde funding over 7 dagen boven het 80e percentiel van de vorige 365 dagen."""
    m = f["f"].rolling(n).mean().resample("1D").last().ffill()
    m.index = m.index + pd.Timedelta(days=1)                 # stand aan het einde van de dag geldt voor 00:00 de dag erna
    return m > m.shift(1).rolling(jaar).quantile(0.8)


# ------------- Kosten -------------
def laad(pad, epic):
    with gzip.open(Path(pad) / f"{epic}.csv.gz", "rt") as f:
        d = pd.read_csv(f, index_col=0)
    d.index = pd.to_datetime(d.index, utc=True).tz_convert(NY)
    return d[~d.index.duplicated()].sort_index()


def rente(fee, side):
    r = (fee or {}).get("longRate" if side > 0 else "shortRate")
    return max(0.0, -r) if r is not None else 0.0


def rij(tr, spread, fee, spread_kost=True, tag=None):
    """Trade naar dict; None als de spread boven de grens ligt."""
    if not np.isfinite(spread) or spread > MAX_SPREAD_R * tr.risk:
        return None
    c = 1.5 * spread / tr.risk if spread_kost else 0.0
    f = engine.rollovers(tr.entry_time, tr.exit_time) * rente(fee, tr.side) / 100 * tr.entry / tr.risk
    return dict(t=tr.entry_time.tz_convert("UTC"), uit=tr.exit_time.tz_convert("UTC"), bruto=float(tr.gross_r), R=float(tr.gross_r - c - f),
                R15=float(tr.gross_r - selector.COST_X * c - f), kosten=float(c + f), side=tr.side, tag=tag)


def dagrange(d, n=20):
    td = pd.Index([(t + pd.Timedelta(hours=6)).date() for t in d.index])
    g = d.groupby(td)
    r = (g["High"].max() - g["Low"].min()).rolling(n).mean().shift(1)
    return r.dropna()


# ------------- Hypotheses -------------
def stromen(d, fee, naam, lab_kost):
    """Basisvarianten op uurcandles. Geeft per stroom de trades, plus de vergelijking aanname tegen meting."""
    X = strat.indicators(d)
    sp = d["spread"].to_numpy()
    out, aanname, gemeten = {}, [], []
    for fam, v in BASIS:
        up, dn, stopd, target = strat.signals(fam, X, v)
        rows = []
        for i, tr in strat.run_signals(X, up, dn, stopd, target, engine.Costs(), EXITS_LAB):
            if tr.reason == "open":
                continue
            s = sp[min(i + 1, len(sp) - 1)]
            aanname.append(lab_kost * tr.entry / tr.risk)
            gemeten.append(1.5 * s / tr.risk)
            x = rij(tr, s, fee)
            if x:
                rows.append(x)
        out[f"{naam}|{fam}|{json.dumps(v, sort_keys=True)}"] = rows
    return out, float(np.mean(aanname)), float(np.mean(gemeten)), len(aanname)


def portefeuille(streams):
    """Per dag de som van R van sluitende trades, gedeeld door het aantal stromen."""
    n = max(len(streams), 1)
    t = {}
    for rows in streams.values():
        for x in rows:
            k = x["uit"].normalize()
            a = t.setdefault(k, dict(t=k, R=0.0, R15=0.0, bruto=0.0))
            for f in ("R", "R15", "bruto"):
                a[f] += x[f] / n
    return [t[k] for k in sorted(t)]


def h1(data, fees, cut):
    S = {}
    for m in H1_MARKTEN:
        S.update(stromen(data[m], fees[m], m, 0)[0])
    plus = {k: v for k, v in S.items() if v and np.mean([x["R15"] for x in v if x["t"] < cut] or [-1]) > 0}
    return {json.dumps(dict(weging="alle")): portefeuille(S), json.dumps(dict(weging="train_plus")): portefeuille(plus)}, dict(stromen=len(S), plus=len(plus))


def h2(data, fees, es, zn, naam):
    s = drempelsignaal(es, zn)
    d = data[naam]
    B = engine.Bars(d, bar=BAR1H)
    rng = dagrange(d)
    sp = d["spread"].to_numpy()
    out = []
    ex = engine.Exits(max_hours=22)
    for dag, v in s.items():
        if abs(v) < 0.01:
            continue
        t0 = pd.Timestamp(dag).tz_localize(NY) + pd.Timedelta(hours=18)
        i = B.index_at(t0)
        k = rng.index.searchsorted(dag.date(), side="right") - 1
        if i >= B.n or k < 0 or d.index[i] - t0 > pd.Timedelta(hours=3):
            continue
        side, px, risk = -int(np.sign(v)), float(B.o[i]), 0.5 * float(rng.iloc[k])
        tr = engine.simulate(B, side, px, px - side * risk, None, i, "MARKET", ex, engine.Costs())
        if tr and tr.reason != "open":
            x = rij(tr, sp[i], fees[naam])
            if x:
                out.append(x)
    return out


def h3(naam, sym, cap, fee):
    m1 = load_histdata(sym)
    d = to5(m1)
    d = d[d.index.strftime("%H:%M") < "16:00"]
    rng = dagrange(d)
    sp = cap["spread"]
    days = sorted(set(d.index.date))
    close = d.groupby(d.index.date)["Close"].last()
    pre = d[d.index.strftime("%H:%M") == "15:25"].copy()
    pre.index = pre.index.date
    prev = close.shift(1)
    r = np.log(pre["Close"] / prev.reindex(pre.index)).dropna()
    groot = grote_dag(r)
    B = engine.Bars(d, bar=pd.Timedelta(minutes=5))
    ex = engine.Exits(close_at="16:00")
    out = []
    for day in r.index[groot.to_numpy()]:
        t0 = pd.Timestamp(day).tz_localize(NY) + pd.Timedelta(hours=15, minutes=30)
        i = B.index_at(t0)
        k = rng.index.searchsorted(day, side="right") - 1
        if i >= B.n or d.index[i] != t0 or k < 0:
            continue
        side, px, risk = int(np.sign(r[day])), float(B.o[i]), 0.5 * float(rng.iloc[k])
        tr = engine.simulate(B, side, px, px - side * risk, None, i, "MARKET", ex, engine.Costs())
        if tr and tr.reason != "open":
            j = sp.index.searchsorted(t0, side="right") - 1
            x = rij(tr, float(sp.iloc[j]), fee) if j >= 0 else None
            if x:
                out.append(x)
    return out, len(days)


def cot_keuze(sp, datum):
    v = {m: s[s.index <= datum].iloc[-1] for m, s in sp.items() if (s.index <= datum).any()}
    r = sorted(v, key=v.get, reverse=True)
    return r[:3], r[-3:]


def h4(data, fees, cot):
    sp = {m: spec_druk(cot, c, t) for m, (c, t) in COT.items()}
    months = pd.date_range("2024-12-01", "2026-11-01", freq="MS")
    out = []
    for a, b in zip(months[:-1], months[1:]):
        lang, kort = cot_keuze(sp, a - pd.Timedelta(days=1))
        for m, side in [(x, 1) for x in lang] + [(x, -1) for x in kort]:
            d = data[m]
            B = engine.Bars(d, bar=BAR1H)
            t0 = pd.Timestamp(a).tz_localize(NY) + pd.Timedelta(hours=9)
            i = B.index_at(t0)
            rng = dagrange(d)
            k = rng.index.searchsorted(a.date(), side="right") - 1
            if i >= B.n or k < 0:
                continue
            px, risk = float(B.o[i]), 3 * float(rng.iloc[k])
            hrs = (pd.Timestamp(b).tz_localize(NY) + pd.Timedelta(hours=9) - d.index[i]).total_seconds() / 3600
            tr = engine.simulate(B, side, px, px - side * risk, None, i, "MARKET", engine.Exits(max_hours=hrs), engine.Costs())
            if tr and tr.reason != "open":
                x = rij(tr, float(d["spread"].iloc[i]), fees[m], tag=m)
                if x:
                    out.append(x)
    return out


def h5(naam, d, fee):
    sym = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}[naam]
    aan = funding_aan(pd.read_pickle(D / f"funding_{sym}.pkl"))
    B = engine.Bars(d, bar=BAR1H)
    rng = dagrange(d)
    sp = d["spread"].to_numpy()
    ex = engine.Exits(max_hours=24)
    out, gisteren = [], None
    for t in aan.index[aan.to_numpy()]:
        if t < d.index[0].tz_convert("UTC"):
            continue
        i = B.index_at(t.tz_convert(NY))
        k = rng.index.searchsorted(t.date(), side="right") - 1
        if i >= B.n or k < 0:
            continue
        px, risk = float(B.o[i]), float(rng.iloc[k])
        tr = engine.simulate(B, -1, px, px + risk, None, i, "MARKET", ex, engine.Costs())
        if not tr or tr.reason == "open":
            continue
        doorloop = gisteren == t - pd.Timedelta(days=1)
        x = rij(tr, sp[i], fee, spread_kost=not doorloop)
        if x:
            out.append(x)
        gisteren = None if tr.reason == "stop" else t
    return out


# ------------- Oordeel -------------
def oordeel(markt, sid, by, cut, mid, proeven):
    f = selector.evaluate_family(markt, sid, by, cut, proeven)
    p, k = f["poort"], f["variant"]
    uit = dict(markt=markt, hypothese=sid, variant=k, geslaagd=p["geslaagd"], redenen=p["redenen"], train=p["train"], evaluatie=p["validatie"],
               evaluatie_15x=p["validatie_kosten15"], ondergrens=p["ondergrens"], dsr=p["dsr"], proeven=proeven, varianten={v: len(t) for v, t in by.items()})
    t = by.get(k) or []
    if not t:
        uit.update(toelaatbaar=False, dsr_scan=0.0)
        return uit
    va = [x for x in t if x["t"] >= cut]
    e1, e2 = [x["R15"] for x in va if x["t"] < mid], [x["R15"] for x in va if x["t"] >= mid]
    tr = [x for x in t if x["t"] < cut]
    d = deflated_sharpe([x["R"] for x in t], SCAN)
    m = lambda xs: round(float(np.mean(xs)), 3) if len(xs) else None
    uit.update(e1=m(e1), e2=m(e2), bruto_train=m([x["bruto"] for x in tr]), bruto_eval=m([x["bruto"] for x in va]), dsr_scan=round(d, 3),
               toelaatbaar=bool(p["geslaagd"] and d >= selector.DSR_MIN and e1 and e2 and np.mean(e1) > 0 and np.mean(e2) > 0))
    return uit


# ------------- Informatief, lange reeksen, bruto -------------
def t_stat(x):
    x = np.asarray(x, float)
    return round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2) if len(x) > 2 else None


def info_h2(es, zn):
    s = drempelsignaal(es, zn)
    r = es.pct_change().shift(-1).reindex(s.index)
    x = (-np.sign(s) * r)[s.abs() >= 0.01].dropna() * 1e4
    out = dict(alles=dict(n=len(x), bp=round(float(x.mean()), 2), t=t_stat(x)))
    for a, b in (("2001", "2012"), ("2013", "2019"), ("2020", "2026")):
        y = x[a:b]
        out[f"{a}-{b}"] = dict(n=len(y), bp=round(float(y.mean()), 2), t=t_stat(y))
    return out


def info_h4(cot):
    import yfinance as yf
    sym = dict(GOUD="GC=F", ZILVER="SI=F", OLIE="CL=F", ES="ES=F", NQ="NQ=F", EURUSD="6E=F", GBPUSD="6B=F", USDJPY="6J=F")
    px = {}
    for m, s in sym.items():
        d = yf.download(s, interval="1d", period="max", progress=False, auto_adjust=False)
        d.columns = d.columns.get_level_values(0)
        px[m] = d["Close"]
    sp = {m: spec_druk(cot, c, t) for m, (c, t) in COT.items()}
    P = pd.DataFrame(px).ffill()
    me = P.resample("MS").first()
    ret = me.pct_change().shift(-1)
    ret["USDJPY"] = -ret["USDJPY"]            # 6J is de yen: USDJPY-kant gebruiken
    out = []
    for a in ret.index[ret.index >= "2014-02-01"]:
        if ret.loc[a].isna().any():
            continue
        lang, kort = cot_keuze(sp, a - pd.Timedelta(days=1))
        out.append((a, ret.loc[a, lang].mean() - ret.loc[a, kort].mean()))
    x = pd.Series(dict(out)).dropna() * 100
    return dict(maanden=len(x), gem_pct=round(float(x.mean()), 3), t=t_stat(x), jaar_sharpe=round(float(x.mean() / x.std() * np.sqrt(12)), 2),
                sinds_2021=dict(gem_pct=round(float(x["2021":].mean()), 3), t=t_stat(x["2021":])))


def info_h5():
    out = {}
    for n, sym in (("BTC", "BTCUSDT"), ("ETH", "ETHUSDT")):
        aan = funding_aan(pd.read_pickle(D / f"funding_{sym}.pkl"))
        aan.index = aan.index.tz_localize(None)
        c = pd.read_pickle(D / f"dag_{n}.pkl")["Close"]
        f = (c.shift(-7) / c - 1).reindex(aan.index).dropna() * 100
        a = aan.reindex(f.index)
        v = f[f.index >= "2021-01-01"]
        s = a[v.index]
        out[n] = dict(aan=dict(dagen=int(s.sum()), gem_pct=round(float(v[s].mean()), 2), slechtste_5pct=round(float(v[s].quantile(.05)), 1)),
                      uit=dict(dagen=int((~s).sum()), gem_pct=round(float(v[~s].mean()), 2), slechtste_5pct=round(float(v[~s].quantile(.05)), 1)))
    return out


def per_lab(n):
    d = json.loads((ROOT / "lab.json").read_text())
    ms = d.get("markten", d)
    for m in ms if isinstance(ms, list) else ms.values():
        if m.get("naam") == n:
            return (m.get("kandidaten") or {}).get("proeven") or 40
    return 40


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("--uit", default="rapport/vijf.json")
    a = ap.parse_args()
    sha = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    gek = json.loads((Path(a.map) / "markten.json").read_text())["gekozen"]
    namen = [m["naam"] for m in LAB_MARKETS]
    data = {n: laad(a.map, EPICS[n]) for n in namen}
    fees = {n: (gek[EPICS[n]].get("details") or {}).get("financiering") for n in namen}
    einde = max(d.index[-1] for d in data.values()).tz_convert("UTC")
    cut, mid = einde - pd.Timedelta(days=selector.VAL_DAYS), einde - pd.Timedelta(days=selector.VAL_DAYS / 2)
    res = []

    kost = {}
    for m in LAB_MARKETS:
        n = m["naam"]
        _, aan, gem, tr = stromen(data[n], fees[n], n, MODEL_KOSTEN[n])   # de aanname van vóór PR #8, zoals in rapport 10
        kost[n] = dict(trades=tr, aanname_r=round(aan, 3), gemeten_r=round(gem, 3), verschil_r=round(gem - aan, 3))
        print("kosten", n, kost[n], flush=True)

    by, info1 = h1(data, fees, cut)
    res.append(oordeel("portefeuille", "H1_combineren", by, cut, mid, 40 + PROEVEN_EXTRA))
    es, zn = (pd.read_pickle(D / f"dag_{x}.pkl")["Close"] for x in ("ES", "ZN"))
    es.index, zn.index = pd.to_datetime(es.index), pd.to_datetime(zn.index)
    for n in ("ES", "NQ"):
        res.append(oordeel(n, "H2_herbalancering", {"{}": h2(data, fees, es, zn, n)}, cut, mid, per_lab(n) + PROEVEN_EXTRA))
    for n, sym in (("ES", "SPXUSD"), ("NQ", "NSXUSD")):
        t, _ = h3(n, sym, data[n], fees[n])
        e = max(x["t"] for x in t)
        res.append(oordeel(n, "H3_slotmomentum", {"{}": t}, e - pd.Timedelta(days=selector.VAL_DAYS), e - pd.Timedelta(days=selector.VAL_DAYS / 2), per_lab(n) + PROEVEN_EXTRA))
    cot = pd.read_pickle(D / "cot.pkl")
    res.append(oordeel("portefeuille", "H4_cot", {"{}": h4(data, fees, cot)}, cut, mid, 40 + PROEVEN_EXTRA))
    for n in ("BTC", "ETH"):
        res.append(oordeel(n, "H5_funding", {"{}": h5(n, data[n], fees[n])}, cut, mid, per_lab(n) + PROEVEN_EXTRA))
    for r in res:
        print(json.dumps(r, ensure_ascii=False, default=str), flush=True)
    uit = dict(protocol="vijf-v1", protocol_sha256=sha, kosten=kost, h1=info1, uitslag=res, informatief=dict(H2=info_h2(es, zn), H4=info_h4(cot), H5=info_h5()),
               toelaatbaar=[f"{x['markt']} {x['hypothese']}" for x in res if x.get("toelaatbaar")])
    Path(a.uit).write_text(json.dumps(uit, indent=1, ensure_ascii=False, default=str))
    registry.record("vijf-v1", params=dict(protocol_sha256=sha), results=dict(combinaties=9, toelaatbaar=uit["toelaatbaar"]))
    print(json.dumps(uit["informatief"], ensure_ascii=False), "\ntoelaatbaar:", uit["toelaatbaar"])


if __name__ == "__main__":
    main()
