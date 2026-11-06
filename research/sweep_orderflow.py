#!/usr/bin/env python3
"""Onderzoek sweep-orderflow-v1: een mislukte sweep die uitbraak wordt, en echte orderflow op crypto.

    python -W ignore -m research.sweep_orderflow binance      # data ophalen (openbare Binance-klines, alleen lezen)
    python -W ignore -m research.sweep_orderflow toets        # protocol draaien -> rapport/sweep_orderflow.json

Regels staan in research/sweep_orderflow_protocol.json en liggen vast vóór de eerste uitslag. Deze module verandert
niets aan de bot: geen orders, geen wijziging aan de poort, de selector of de ICT-detectie.
"""
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from backtesting import engine
from backtesting.metrics import deflated_sharpe
from core.config import CFG
from core.data import load_histdata, to5
from core.markets import HISTDATA_RESEARCH, LAB_MARKETS
from core.sessions import NY, in_sess
from learning import selector
from research import registry
from storage import paths
from strategies.ict_tjr import analyse

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "research" / "sweep_orderflow_protocol.json"
OUT = ROOT / "rapport" / "sweep_orderflow.json"
BINANCE = paths.DATA / "binance"
SYMBOLS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
START, END = "2024-11-04", "2026-11-04"     # END is exclusief
TICK = {"BTC": 0.01, "ETH": 0.01, "SOL": 0.01}
TARGETS = (1.0, 2.0)
EXITS = engine.Exits(max_hours=5)
DR_MIN, RELVOL_MIN = 0.10, 1.5
SCAN = 867
EXTRA_PROEVEN = 6 + 5
CFG_RUN = dict(CFG, disp_pct=0.7, disp_atr=1.5, tp_mode="R", tp_r=1.0, need_bias_b=False, max_per_day=6)


# ------------- Data -------------
def fetch_binance(symbol, start=START, end=END):
    """5m-klines met taker-buy-volume. Openbaar, geen sleutel; alleen koersdata."""
    t = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    stop = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    rows = []
    while t < stop:
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=5m&startTime={t}&endTime={stop - 1}&limit=1000"
        with urllib.request.urlopen(url, timeout=30) as r:
            batch = json.load(r)
        if not batch:
            break
        rows += batch
        t = batch[-1][0] + 300000
        time.sleep(0.1)
    d = pd.DataFrame([(x[0], *map(float, x[1:6]), float(x[9])) for x in rows],
                     columns=["t", "Open", "High", "Low", "Close", "Volume", "TakerBuy"])
    d.index = pd.to_datetime(d.pop("t"), unit="ms", utc=True).dt.tz_convert(NY)
    d.index.name = None
    return d[~d.index.duplicated()].sort_index()


def download():
    BINANCE.mkdir(exist_ok=True)
    for name, sym in SYMBOLS.items():
        d = fetch_binance(sym)
        d.to_pickle(BINANCE / f"{sym}_5m.pkl")
        print(name, d.index[0], d.index[-1], len(d), flush=True)


def load_binance(name):
    return pd.read_pickle(BINANCE / f"{SYMBOLS[name]}_5m.pkl")


# ------------- Niveaus (zelfde definitie als strategies/ict_tjr.analyse) -------------
def session_state(df, cfg):
    """Per candle: H, L, C, O, ATR, PDH/PDL en lopende Asia/London-niveaus, zonder toekomstige informatie."""
    idx = df.index
    O, H, L, C = (df[c].to_numpy() for c in ("Open", "High", "Low", "Close"))
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - df["Close"].shift()).abs(),
                    (df["Low"] - df["Close"].shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    tday = [(t + pd.Timedelta(hours=6)).date() for t in idx]
    daily = df.assign(td=tday).groupby("td").agg(H=("High", "max"), L=("Low", "min")).shift(1)
    pdh, pdl = daily["H"].reindex(tday).to_numpy(), daily["L"].reindex(tday).to_numpy()
    n = len(df)
    levels_hi, levels_lo, in_trade = [None] * n, [None] * n, np.zeros(n, bool)
    asiaH = asiaL = londH = londL = None
    pa = pl = False
    for i, t in enumerate(idx):
        a, l = in_sess(t, cfg["asia_sess"]), in_sess(t, cfg["lond_sess"])
        if a and not pa:
            asiaH, asiaL = H[i], L[i]
        elif a:
            asiaH, asiaL = max(asiaH, H[i]), min(asiaL, L[i])
        if l and not pl:
            londH, londL = H[i], L[i]
        elif l:
            londH, londL = max(londH, H[i]), min(londL, L[i])
        pa, pl = a, l
        levels_hi[i] = (pdh[i], asiaH, londH)
        levels_lo[i] = (pdl[i], asiaL, londL)
        in_trade[i] = in_sess(t, cfg["trade_sess"])
    return dict(O=O, H=H, L=L, C=C, atr=atr, hi=levels_hi, lo=levels_lo, trade=in_trade)


def _swept(st, i, side):
    """Geveegd niveau op candle i (side +1 = een hoog), of None. Sluiten moet terug op of voorbij het niveau."""
    H, L, C = st["H"], st["L"], st["C"]
    if i == 0:
        return None
    for lvl in (st["hi"] if side > 0 else st["lo"])[i]:
        if lvl is None or not np.isfinite(lvl):
            continue
        if side > 0 and H[i] > lvl and H[i - 1] <= lvl and C[i] <= lvl:
            return lvl
        if side < 0 and L[i] < lvl and L[i - 1] >= lvl and C[i] >= lvl:
            return lvl
    return None


def failed_sweeps(df, cfg, tick):
    """Signalen van sweep_uitbraak. side = richting van de trade (na een geveegd hoog: long).
    Geeft dicts met i (candle van de uitbraak), side, stop, sweep_i."""
    st = session_state(df, cfg)
    O, H, L, C, atr, trade = st["O"], st["H"], st["L"], st["C"], st["atr"], st["trade"]
    armed, done, out = {1: None, -1: None}, {1: False, -1: False}, []
    for i in range(len(df)):
        if trade[i] and not (i > 0 and trade[i - 1]):
            armed, done = {1: None, -1: None}, {1: False, -1: False}
        for side in (1, -1):
            a = armed[side]
            if a is not None:
                far, opp = a["far"], min(a["opp"], L[i]) if side > 0 else max(a["opp"], H[i])
                rng = H[i] - L[i]
                body = abs(C[i] - O[i]) / rng if rng > 0 else 0
                disp = (C[i] > O[i] if side > 0 else C[i] < O[i]) and body >= cfg["disp_pct"] and rng >= cfg["disp_atr"] * atr[i]
                if not trade[i] or i - a["bar"] > cfg["mss_window"]:
                    armed[side] = None
                elif disp and (C[i] > far if side > 0 else C[i] < far):
                    stop = opp - cfg["buf_ticks"] * tick if side > 0 else opp + cfg["buf_ticks"] * tick
                    out.append(dict(i=i, side=side, stop=stop, sweep_i=a["bar"]))
                    armed[side], done[side] = None, True
                else:
                    a["opp"] = opp
                    a["far"] = max(far, H[i]) if side > 0 else min(far, L[i])
            if armed[side] is None and not done[side] and trade[i] and _swept(st, i, side) is not None:
                armed[side] = dict(bar=i, far=H[i] if side > 0 else L[i], opp=L[i] if side > 0 else H[i])
    return out


def cvd_reversals(df, cfg, tick):
    """Signalen van c_cvd_divergentie: side = richting van de trade (tegen de sweep in)."""
    st = session_state(df, cfg)
    H, L, trade = st["H"], st["L"], st["trade"]
    delta = 2 * df["TakerBuy"] - df["Volume"]
    cvd = delta.rolling(20).sum().to_numpy()
    done, out = {1: False, -1: False}, []
    for i in range(len(df)):
        if trade[i] and not (i > 0 and trade[i - 1]):
            done = {1: False, -1: False}
        if not trade[i] or not np.isfinite(cvd[i]):
            continue
        for swept in (1, -1):
            side = -swept
            if done[side] or _swept(st, i, swept) is None or cvd[i] * swept >= 0:
                continue
            stop = H[i] + cfg["buf_ticks"] * tick if swept > 0 else L[i] - cfg["buf_ticks"] * tick
            out.append(dict(i=i, side=side, stop=stop, sweep_i=i))
            done[side] = True
    return out


def flow_columns(df):
    dr = ((2 * df["TakerBuy"] - df["Volume"]) / df["Volume"].replace(0, np.nan)).to_numpy()
    relvol = (df["Volume"] / df["Volume"].rolling(20).mean().shift(1)).to_numpy()
    return dr, relvol


def fvg_entry(df, sig, cfg):
    """Limiet op 50% van de eerste FVG in de richting van de trade binnen fvg_window candles vanaf de uitbraak.
    Geeft (prijs, signaalcandle, nieuwe stop) of None."""
    H, L = df["High"].to_numpy(), df["Low"].to_numpy()
    i, side = sig["i"], sig["side"]
    for j in range(i, min(i + cfg["fvg_window"] + 1, len(df))):
        if j < 2:
            continue
        if side > 0 and L[j] > H[j - 2]:
            return (L[j] + H[j - 2]) / 2, j
        if side < 0 and H[j] < L[j - 2]:
            return (H[j] + L[j - 2]) / 2, j
    return None


# ------------- Trades -------------
def row(tr):
    return dict(t=tr.entry_time.tz_convert("UTC"), R=float(tr.net_r), R15=float(tr.gross_r - 1.5 * tr.cost_r - tr.fin_r - tr.slip_r),
                bruto=float(tr.gross_r), side=tr.side, reden=tr.reason)


def market_trades(df5, B, sigs, target, costs, entry="markt", cfg=CFG_RUN):
    """Signalen door de engine. B: engine.Bars op 1m (HistData) of 5m (crypto). Eén trade tegelijk."""
    out, busy = [], None
    bar5 = pd.Timedelta(minutes=5)
    idx = df5.index
    for s in sigs:
        i, side = s["i"], s["side"]
        if i + 1 >= len(idx):
            continue
        if entry == "markt":
            t0 = idx[i + 1]
            start = B.index_at(t0)
            if start >= B.n or (busy is not None and t0 <= busy):
                continue
            px = float(B.o[start])
            risk = (px - s["stop"]) * side
            if risk <= 0:
                continue
            tr = engine.simulate(B, side, px, s["stop"], px + side * target * risk, start, "MARKET", EXITS, costs)
        else:
            e = fvg_entry(df5, s, cfg)
            if e is None:
                continue
            px, j = e
            risk = (px - s["stop"]) * side
            if risk <= 0 or j + 1 >= len(idx):
                continue
            t0 = idx[j + 1]
            if busy is not None and t0 <= busy:
                continue
            start = B.index_at(t0)
            last = min(j + cfg["entry_win"], len(idx) - 1)
            until = B.index_at(idx[last] + bar5) - 1
            tr = engine.simulate(B, side, px, s["stop"], px + side * target * risk, start, "LIMIT", EXITS, costs, fill_until_i=until)
        if tr is None or tr.reason == "open":
            continue
        busy = tr.exit_time
        out.append(row(tr))
    return out


def ict_setups(df, tick):
    """ICT-signalen met de sweepcandle erbij, voor het absorptiefilter."""
    setups, _ = analyse(df, df, dict(CFG_RUN, tick=tick))
    return [s for s in setups if s.get("entry_hit") is not None]


def ict_trades(df5, B, setups, target, costs):
    out, busy = [], None
    bar5 = pd.Timedelta(minutes=5)
    for s in setups:
        side = 1 if s["side"] == "LONG" else -1
        start = B.index_at(s["entry_hit"])
        if busy is not None and s["entry_hit"] <= busy:
            continue
        risk = abs(s["entry"] - s["stop"])
        until = B.index_at(s["entry_hit"] + bar5) - 1
        tr = engine.simulate(B, side, s["entry"], s["stop"], s["entry"] + side * target * risk, start, "LIMIT", EXITS, costs, fill_until_i=until)
        if tr is None or tr.reason == "open":
            continue
        busy = tr.exit_time
        out.append(row(tr))
    return out


# ------------- Toets -------------
def split_stats(trades, cut):
    va = sorted((x for x in trades if x["t"] >= cut), key=lambda x: x["t"])
    h = len(va) // 2
    m = lambda xs, k: round(float(np.mean([x[k] for x in xs])), 3) if xs else None
    return dict(e1=m(va[:h], "R15"), e2=m(va[h:], "R15"), bruto_train=m([x for x in trades if x["t"] < cut], "bruto"),
                bruto_eval=m(va, "bruto"), kosten15_eval=round(float(np.mean([x["bruto"] - x["R15"] for x in va])), 3) if va else None)


def judge(market, family, by_variant, cut, trials):
    f = selector.evaluate_family(market, family, by_variant, cut, trials)
    k, p = f["variant"], f["poort"]
    out = dict(markt=market, strategie=family, variant=k, geslaagd=p["geslaagd"], redenen=p["redenen"], train=p["train"], evaluatie=p["validatie"],
               evaluatie_15x=p["validatie_kosten15"], ondergrens=p["ondergrens"], dsr=p["dsr"], proeven=trials,
               varianten={v: len(t) for v, t in by_variant.items()})
    if k is None:
        out.update(toelaatbaar=False)
        return out
    t = by_variant[k]
    s = split_stats(t, cut)
    dsr_scan = deflated_sharpe([x["R"] for x in t], SCAN)
    out.update(s, dsr_scan=round(dsr_scan, 3), toelaatbaar=bool(p["geslaagd"] and dsr_scan >= selector.DSR_MIN and (s["e1"] or -1) > 0 and (s["e2"] or -1) > 0))
    return out


def per_lab(name):
    d = json.loads((ROOT / "lab.json").read_text())
    ms = d.get("markten", d)
    for m in ms if isinstance(ms, list) else ms.values():
        if m.get("naam") == name:
            return (m.get("kandidaten") or {}).get("proeven") or 40
    return 40


def run_prices():
    res = []
    for name, m in HISTDATA_RESEARCH.items():
        m1 = load_histdata(m["sym"])
        df5, B = to5(m1), engine.Bars(m1, bar=pd.Timedelta(minutes=1))
        costs = engine.Costs(price=m["cost"])
        sigs = failed_sweeps(df5, CFG_RUN, m["tick"])
        cut = df5.index[-1].tz_convert("UTC") - pd.Timedelta(days=selector.VAL_DAYS)
        by = {}
        for e in ("markt", "fvg"):
            for t in TARGETS:
                by[json.dumps(dict(instap=e, doel=t))] = market_trades(df5, B, sigs, t, costs, e)
        res.append(judge(name, "sweep_uitbraak", by, cut, per_lab(name) + EXTRA_PROEVEN + 4))
        print(json.dumps(res[-1], ensure_ascii=False, default=str), flush=True)
    return res


def run_crypto():
    res, filters = [], []
    for name, sym in SYMBOLS.items():
        df = load_binance(name)
        B = engine.Bars(df, bar=pd.Timedelta(minutes=5))
        kost = next(x for x in LAB_MARKETS if x["naam"] == name)["kosten"]
        costs = engine.Costs(frac=kost)
        tick = TICK[name]
        cut = df.index[-1].tz_convert("UTC") - pd.Timedelta(days=selector.VAL_DAYS)
        trials = per_lab(name) + EXTRA_PROEVEN + 10
        dr, relvol = flow_columns(df)
        sigs = failed_sweeps(df, CFG_RUN, tick)
        flow = [s for s in sigs if np.nan_to_num(dr[s["i"]]) * s["side"] >= DR_MIN and np.nan_to_num(relvol[s["i"]]) >= RELVOL_MIN]
        setups = ict_setups(df, tick)
        pos = df.index.get_indexer([s["sweep_t"] for s in setups])
        absorb = [s for s, p in zip(setups, pos) if np.nan_to_num(dr[p]) * (-1 if s["side"] == "LONG" else 1) >= DR_MIN]
        cvd = cvd_reversals(df, CFG_RUN, tick)
        fams = {
            "c_uitbraak": {json.dumps(dict(doel=t)): market_trades(df, B, sigs, t, costs) for t in TARGETS},
            "c_uitbraak_flow": {json.dumps(dict(doel=t)): market_trades(df, B, flow, t, costs) for t in TARGETS},
            "c_ict": {json.dumps(dict(doel=t)): ict_trades(df, B, setups, t, costs) for t in TARGETS},
            "c_ict_absorptie": {json.dumps(dict(doel=t)): ict_trades(df, B, absorb, t, costs) for t in TARGETS},
            "c_cvd_divergentie": {json.dumps(dict(doel=t)): market_trades(df, B, cvd, t, costs) for t in TARGETS},
        }
        for fam, by in fams.items():
            res.append(judge(name, fam, by, cut, trials))
            print(json.dumps(res[-1], ensure_ascii=False, default=str), flush=True)
        for filt, base in (("c_uitbraak_flow", "c_uitbraak"), ("c_ict_absorptie", "c_ict")):
            for t in TARGETS:
                k = json.dumps(dict(doel=t))
                row_ = dict(markt=name, filter=filt, doel=t)
                for tag, part in (("train", lambda x: x["t"] < cut), ("evaluatie", lambda x: x["t"] >= cut)):
                    a = [x["R15"] for x in fams[filt][k] if part(x)]
                    b = [x["R15"] for x in fams[base][k] if part(x)]
                    row_[tag] = dict(n_filter=len(a), gem_filter=round(float(np.mean(a)), 3) if a else None,
                                     n_nul=len(b), gem_nul=round(float(np.mean(b)), 3) if b else None)
                filters.append(row_)
    return res, filters


def main():
    if sys.argv[1:] == ["binance"]:
        download()
        return
    sha = hashlib.sha256(PROTOCOL.read_bytes()).hexdigest()
    prijs = run_prices()
    crypto, filters = run_crypto()
    out = dict(protocol="sweep-orderflow-v1", protocol_sha256=sha, prijs=prijs, crypto=crypto, flowfilter=filters,
               toelaatbaar=[f"{x['markt']} {x['strategie']}" for x in prijs + crypto if x.get("toelaatbaar")])
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    registry.record("sweep-orderflow-v1", params=dict(protocol_sha256=sha),
                    results=dict(combinaties=46, toelaatbaar=out["toelaatbaar"]))
    print("toelaatbaar:", out["toelaatbaar"])


if __name__ == "__main__":
    main()
