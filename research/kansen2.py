"""Protocol kansen-v2: tijdstip-effecten en dagverloop op Capital.com-prijzen, plus trendvolging op dagcandles als informatie.

Alleen onderzoek: plaatst geen orders en raakt de actieve configuratie niet.
Gebruik: python -W ignore -m research.kansen2 <map> [--trend] --uit rapport/kansen2.json
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backtesting import engine
from backtesting.metrics import deflated_sharpe
from learning import selector
from research import kansen as K
from research import registry
from risk import rules

PROTOCOL = Path(__file__).with_name("kansen2_protocol.json")
TZ = "America/New_York"
ATR_DAGEN = 20
STOP_X = 0.5
BAND_DAGEN = 14
LIMITS = rules.Limits()

TREND_MARKTEN = {"ES=F": "US500", "NQ=F": "US100", "YM=F": "US30", "RTY=F": "RTY", "GC=F": "GOLD", "SI=F": "SILVER", "HG=F": "COPPER", "CL=F": "OIL_CRUDE",
                 "BZ=F": "OIL_BRENT", "HO=F": "HEATINGOIL", "6E=F": "EURUSD", "6B=F": "GBPUSD", "6J=F": "USDJPY", "6A=F": "AUDUSD", "^GDAXI": "DE40", "^FTSE": "UK100",
                 "BTC-USD": "BTCUSD", "ETH-USD": "ETHUSD"}


def load_protocol(path=PROTOCOL):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def vorige_atr(df, n=ATR_DAGEN):
    """Gemiddelde dagrange van de vorige n dagen per kalenderdag (New Yorkse tijd), zonder de dag zelf."""
    ny = df.tz_convert(TZ)
    d = ny.resample("1D").agg(dict(High="max", Low="min", Close="last")).dropna()
    pc = d["Close"].shift(1)
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - pc).abs(), (d["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean().shift(1)


def rondgang(markt, fam, df, i, j, kant, afstand, fee):
    """Eén trade: instap op de open van candle i, uit op de open van candle j of eerder op de stop. Geeft None als de spread te hoog is."""
    o, h, l = df["Open"].to_numpy(), df["High"].to_numpy(), df["Low"].to_numpy()
    entry, stop = o[i], o[i] - kant * afstand
    uit, k_uit = o[j], j
    for k in range(i, j):
        if (kant > 0 and l[k] <= stop) or (kant < 0 and h[k] >= stop):
            uit = stop if k == i else (min(stop, o[k]) if kant > 0 else max(stop, o[k]))
            k_uit = k + 1
            break
    s = float(df["spread"].iloc[i])
    if not np.isfinite(s) or s > LIMITS.max_spread_r * afstand or afstand <= 0:
        return None
    t, t_uit = df.index[i], df.index[min(k_uit, len(df) - 1)]
    bruto = (uit - entry) * kant / afstand
    c = 1.5 * s / afstand
    f = engine.rollovers(t, t_uit) * K.rente(fee, kant) / 100 * entry / afstand
    return dict(id=f"{markt}|{fam}|{t.isoformat()}", markt=markt, fam=fam, kant=kant, entry=float(entry), risk=float(afstand), t=t, t_uit=t_uit, rr=0.0,
                bruto=float(bruto), R=float(bruto - c - f), R15=float(bruto - selector.COST_X * c - f))


def uren(df):
    """{datum: {uur: positie}} in New Yorkse tijd."""
    ny = df.index.tz_convert(TZ)
    out = {}
    for p, (d, u) in enumerate(zip(ny.date, ny.hour)):
        out.setdefault(d, {})[u] = p
    return out


def tijdvak(markt, fam, df, fee, begin, eind, volgende_dag=False, geen_vrijdag=False):
    """Vaste long-periode per dag. Bij volgende_dag ligt de uitstap op de eerstvolgende datum, hoogstens 18 uur later."""
    atr, u = vorige_atr(df), uren(df)
    data = sorted(u)
    out = []
    for n, d in enumerate(data):
        if d.weekday() > 4 or (geen_vrijdag and d.weekday() == 4) or begin not in u[d]:
            continue
        doel = u[data[n + 1]] if volgende_dag and n + 1 < len(data) else (None if volgende_dag else u[d])
        if not doel or eind not in doel:
            continue
        i, j = u[d][begin], doel[eind]
        a = atr.get(pd.Timestamp(d, tz=TZ))
        if a is None or not np.isfinite(a) or j <= i or (df.index[j] - df.index[i]) > pd.Timedelta(hours=18):
            continue
        tr = rondgang(markt, fam, df, i, j, 1, STOP_X * a, fee)
        if tr:
            out.append(tr)
    return out


def late_momentum(markt, fam, df, fee):
    atr, u = vorige_atr(df), uren(df)
    data = sorted(u)
    c = df["Close"].to_numpy()
    o = df["Open"].to_numpy()
    out = []
    for n, d in enumerate(data):
        if n == 0 or d.weekday() > 4 or 15 not in u[d] or 16 not in u[d] or 15 not in u[data[n - 1]]:
            continue
        i, j = u[d][15], u[d][16]
        richting = np.sign(o[i] - c[u[data[n - 1]][15]])
        a = atr.get(pd.Timestamp(d, tz=TZ))
        if richting == 0 or a is None or not np.isfinite(a):
            continue
        tr = rondgang(markt, fam, df, i, j, int(richting), STOP_X * a, fee)
        if tr:
            out.append(tr)
    return out


def band_momentum(markt, fam, df, fee):
    u = uren(df)
    data = sorted(u)
    o, c = df["Open"].to_numpy(), df["Close"].to_numpy()
    afwijking = {}
    out = []
    for d in data:
        if d.weekday() > 4 or 10 not in u[d] or 16 not in u[d]:
            continue
        ref = o[u[d][10]]
        gedaan = False
        for h in range(10, 15):
            if h not in u[d]:
                continue
            p = u[d][h]
            hist = afwijking.get(h, [])
            if not gedaan and len(hist) >= BAND_DAGEN:
                band = float(np.mean(hist[-BAND_DAGEN:]))
                if abs(c[p] / ref - 1) > band:
                    gedaan = True
                    kant = 1 if c[p] > ref else -1
                    i, j = p + 1, u[d][16]
                    if i < j and abs(o[i] - ref) > 0 and (o[i] - ref) * kant > 0:
                        tr = rondgang(markt, fam, df, i, j, kant, abs(o[i] - ref), fee)
                        if tr:
                            out.append(tr)
            afwijking.setdefault(h, []).append(abs(c[p] / ref - 1))
    return out


def crypto_avond(markt, fam, df, fee):
    atr = vorige_atr(df)
    idx = df.index
    pos = {t: p for p, t in enumerate(idx)}
    out = []
    for t in idx[idx.hour == 21]:
        j = pos.get(t + pd.Timedelta(hours=2))
        a = atr.get(t.tz_convert(TZ).normalize())
        if j is None or a is None or not np.isfinite(a):
            continue
        tr = rondgang(markt, fam, df, pos[t], j, 1, STOP_X * a, fee)
        if tr:
            out.append(tr)
    return out


def trades_van(fam, markt, df, fee):
    if fam == "europa_open":
        return tijdvak(markt, fam, df, fee, 2, 6)
    if fam == "nacht":
        return tijdvak(markt, fam, df, fee, 16, 9, volgende_dag=True, geen_vrijdag=True)
    if fam == "late_momentum":
        return late_momentum(markt, fam, df, fee)
    if fam == "band_momentum":
        return band_momentum(markt, fam, df, fee)
    return crypto_avond(markt, fam, df, fee)


def trend_trades(d, spread_pct, fee, markt):
    """Dagelijkse trendvolging op één markt. d: dagcandles. Kosten in R met de spread en rente van nu."""
    hi55, lo55 = d["High"].rolling(55).max().shift(1), d["Low"].rolling(55).min().shift(1)
    hi20, lo20 = d["High"].rolling(20).max().shift(1), d["Low"].rolling(20).min().shift(1)
    pc = d["Close"].shift(1)
    atr = pd.concat([d["High"] - d["Low"], (d["High"] - pc).abs(), (d["Low"] - pc).abs()], axis=1).max(axis=1).rolling(20).mean().shift(1)
    o, h, l, c = (d[k].to_numpy() for k in ("Open", "High", "Low", "Close"))
    out = []
    n = len(d)
    i = 55
    while i < n - 1:
        kant = 1 if c[i] > hi55.iloc[i] else (-1 if c[i] < lo55.iloc[i] else 0)
        if kant == 0 or not np.isfinite(atr.iloc[i]):
            i += 1
            continue
        e, afstand = o[i + 1], 3 * atr.iloc[i]
        stop, uit, k = e - kant * afstand, None, i + 1
        while k < n:
            if (kant > 0 and l[k] <= stop) or (kant < 0 and h[k] >= stop):
                uit = stop if k == i + 1 else (min(stop, o[k]) if kant > 0 else max(stop, o[k]))
                break
            if (kant > 0 and c[k] < lo20.iloc[k]) or (kant < 0 and c[k] > hi20.iloc[k]):
                uit = c[k]
                break
            k += 1
        if uit is None:
            break
        nachten = (d.index[k] - d.index[i + 1]).days
        rk = spread_pct * 1.5 / 100 * e / afstand
        rf = nachten * K.rente(fee, kant) / 100 * e / afstand
        bruto = (uit - e) * kant / afstand
        out.append(dict(markt=markt, kant=kant, t=d.index[i + 1], t_uit=d.index[k], bruto=float(bruto), R=float(bruto - rk - rf), R15=float(bruto - 1.5 * rk - rf)))
        i = k + 1
    return out


def jaarwinst(tr, kol, groep):
    """Eenvoudige portefeuille: 0,5% risico, 3 open, 1 per groep en richting, zonder verliesstop. Geeft rendement per jaar in procent."""
    open_, uit = [], {}
    for x in sorted(tr, key=lambda y: y["t"]):
        open_ = [o for o in open_ if o["t_uit"] > x["t"]]
        if len(open_) >= 3 or any(o["markt"] == x["markt"] or (groep.get(o["markt"]) == groep.get(x["markt"]) and o["kant"] == x["kant"]) for o in open_):
            continue
        open_.append(x)
        uit[x["t"].year] = uit.get(x["t"].year, 0.0) + 0.5 * x[kol]
    return {k: round(v, 1) for k, v in sorted(uit.items())}


def trend_info(meta, groep):
    import yfinance as yf
    alle = []
    for sym, epic in TREND_MARKTEN.items():
        d = yf.download(sym, start="2005-01-01", interval="1d", auto_adjust=False, progress=False)
        if d is None or not len(d):
            continue
        d.columns = [c[0] if isinstance(c, tuple) else c for c in d.columns]
        d = d[["Open", "High", "Low", "Close"]].dropna()
        d = d[(d["Low"] > 0) & (d["High"] >= d["Low"])]
        info = (meta["gekozen"].get(epic) or {})
        sp = info.get("spread_nu_pct") or 0.05
        alle += trend_trades(d, sp, (info.get("details") or {}).get("financiering"), epic)
    per = {}
    for tr in alle:
        per.setdefault(tr["t"].year // 5 * 5, []).append(tr)
    groepen = {k: dict(n=len(v), bruto=round(float(np.mean([x["bruto"] for x in v])), 3), gem=round(float(np.mean([x["R"] for x in v])), 3), gem15=round(float(np.mean([x["R15"] for x in v])), 3)) for k, v in sorted(per.items())}
    jr = jaarwinst(alle, "R", groep)
    return dict(n=len(alle), bruto=round(float(np.mean([x["bruto"] for x in alle])), 3), gem=round(float(np.mean([x["R"] for x in alle])), 3), gem15=round(float(np.mean([x["R15"] for x in alle])), 3),
                per_5_jaar=groepen, rendement_per_jaar_pct=jr, gem_jaar_pct=round(float(np.mean(list(jr.values()))), 1), laatste_5_jaar_pct=round(float(np.mean(list(jr.values())[-5:])), 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("--trend", action="store_true")
    ap.add_argument("--uit", default="rapport/kansen2.json")
    a = ap.parse_args()
    proto, sha = load_protocol()
    meta = json.loads((Path(a.map) / "markten.json").read_text())
    lab = {m["naam"]: (m.get("kandidaten") or {}).get("proeven") for m in json.loads(Path("lab.json").read_text())["markten"]}
    data = {e: K.laad(a.map, e) for s in proto["strategieen"].values() for e in s["markten"]}
    einde = max(df.index[-1] for df in data.values())
    cut, mid = einde - pd.Timedelta(days=selector.VAL_DAYS), einde - pd.Timedelta(days=selector.VAL_DAYS / 2)
    scan = 803 + sum(len(s["markten"]) for s in proto["strategieen"].values())
    rijen = []
    for fam, s in proto["strategieen"].items():
        for e in s["markten"]:
            m = K.NAAM.get(e, e)
            fee = (meta["gekozen"][e].get("details") or {}).get("financiering")
            tr = trades_van(fam, m, data[e], fee)
            trials = (lab.get(m) or 40) + 6 + sum(e in x["markten"] for x in proto["strategieen"].values())
            r = selector.evaluate_family(m, fam, {"vast": tr}, cut, trials)
            g = r["poort"]
            va, on = [x for x in tr if x["t"] >= cut], [x for x in tr if x["t"] < cut]
            dsr = deflated_sharpe([x["R"] for x in tr], scan) if tr else 0.0
            rijen.append(dict(markt=m, epic=e, familie=fam, geslaagd=g["geslaagd"], redenen=[x[:2] for x in g["redenen"]], ontwikkeling=K.samen(on), evaluatie=K.samen(va),
                              ondergrens=g["ondergrens"], dsr=g["dsr"], dsr_scan=round(float(dsr), 3), toelaatbaar=K.toelaatbaar(g, va, mid, dsr)))
    out = dict(protocol=proto["naam"], protocol_sha256=sha, einde=str(einde), proeven_scan=scan, geslaagd=[r for r in rijen if r["geslaagd"]], toelaatbaar=[r for r in rijen if r["toelaatbaar"]], rijen=rijen)
    if a.trend:
        groep = {rules_epic: g for g, ms in rules.CORR_GROUPS.items() for m in ms for rules_epic in (m, K.EPICS.get(m, m))}
        out["trend_info"] = trend_info(meta, groep)
    registry.record("kansen2", dict(protocol_sha256=sha, proeven_scan=scan), dict(combinaties=len(rijen), geslaagd=sum(r["geslaagd"] for r in rijen), toelaatbaar=sum(r["toelaatbaar"] for r in rijen)),
                    {e: registry.fingerprint(df) for e, df in data.items()})
    Path(a.uit).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    for r in rijen:
        print(r["markt"], r["familie"], "ont", r["ontwikkeling"].get("n"), r["ontwikkeling"].get("gem15"), "eval", r["evaluatie"].get("n"), r["evaluatie"].get("gem15"), "dsr", r["dsr"], r["redenen"], flush=True)
    print("toelaatbaar", [(r["markt"], r["familie"]) for r in out["toelaatbaar"]])
    if a.trend:
        print(json.dumps(out["trend_info"], ensure_ascii=False))


if __name__ == "__main__":
    main()
