#!/usr/bin/env python3
"""Meer handelskansen op brokerprijzen (protocol research/kansen_protocol.json). Plaatst nooit orders.

    python -W ignore -m research.kansen <map met capitaldata> --uit rapport/kansen.json

De kosten komen per trade van de broker: de spread van de instapcandle, een halve spread slippage en de gemeten
dagrente. Keuzes vallen alleen op de ontwikkelperiode; de poort is learning/selector.gate, ongewijzigd.
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
from execution.markets import EPICS
from learning import selector
from research.tijdframes import loss_streak
from risk import rules
from strategies import lab as strat

PROTOCOL = Path(__file__).with_name("kansen_protocol.json")
NAAM = {e: n for n, e in EPICS.items()}
FAM_1H = [k for k in strat.STRATS if k != "ict"]
LIMITS = rules.Limits()


def load_protocol(path=PROTOCOL):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def laad(pad, epic):
    with gzip.open(Path(pad) / f"{epic}.csv.gz", "rt") as f:
        df = pd.read_csv(f, parse_dates=["t"], index_col="t")
    return df[~df.index.duplicated()].sort_index()


def naar_4h(df):
    return df.resample("4h").agg(dict(Open="first", High="max", Low="min", Close="last", spread="median")).dropna()


def pullback(X, v):
    """In een trend terug onder het 20-gemiddelde en op de slot er weer boven. Alleen gesloten candles."""
    c, e20 = X["c"], X["e20"]
    up = (X["e50"] > X["e200"]) & (c > X["e200"]) & (c.shift() < e20.shift()) & (c > e20)
    dn = (X["e50"] < X["e200"]) & (c < X["e200"]) & (c.shift() > e20.shift()) & (c < e20)
    return up, dn, v["sm"] * X["atr"], ("R", v["tp"])


def signalen(fam, X, v):
    if fam == "swing_pullback":
        return pullback(X, v)
    return strat.signals(fam.replace("swing_", ""), X, v)


def rente(fee, side):
    """Betaalde rente in procent per nacht; ontvangen rente telt niet mee."""
    r = (fee or {}).get("longRate" if side > 0 else "shortRate")
    return max(0.0, -r) if r is not None else 0.0


def kosten_r(tr, spread, fee):
    """(spread + slippage in R, financiering in R) van één trade."""
    nights = engine.rollovers(tr.entry_time, tr.exit_time)
    return 1.5 * spread / tr.risk, nights * rente(fee, tr.side) / 100 * tr.entry / tr.risk


def handel(markt, fam, sleutel, X, v, spread, fee, exits, max_spread_x=None):
    """Trades van één variant. spread: reeks in prijspunten per candle (index gelijk aan X)."""
    up, dn, stopd, target = signalen(fam, X, v)
    sp = spread.to_numpy()
    med = float(np.nanmedian(sp))
    t_i = X.index
    out = []
    for i, tr in strat.run_signals(X, up, dn, stopd, target, engine.Costs(), exits):
        if tr.reason == "open":
            continue
        s = sp[min(i + 1, len(sp) - 1)]
        if not np.isfinite(s) or s > LIMITS.max_spread_r * tr.risk:
            continue
        if max_spread_x is not None and s > max_spread_x * med:
            continue
        c, f = kosten_r(tr, s, fee)
        out.append(dict(id=f"{markt}|{fam}|{sleutel}|{tr.entry_time.isoformat()}", markt=markt, fam=fam, kant=tr.side, entry=float(tr.entry), risk=float(tr.risk),
                        t=tr.entry_time, t_uit=tr.exit_time + (t_i[1] - t_i[0]), rr=abs(tr.tp - tr.entry) / tr.risk, bruto=tr.gross_r, R=tr.gross_r - c - f,
                        R15=tr.gross_r - selector.COST_X * c - f))
    return out


def samen(tr):
    if not tr:
        return dict(n=0)
    R = np.array([x["R"] for x in sorted(tr, key=lambda x: x["t"])])
    return dict(n=len(R), bruto=round(float(np.mean([x["bruto"] for x in tr])), 3), gem=round(float(R.mean()), 3), gem15=round(float(np.mean([x["R15"] for x in tr])), 3),
                win=round(float((R > 0).mean()), 3), totaal=round(float(R.sum()), 1), verliesreeks=loss_streak(R))


def toelaatbaar(g, va, mid, scan_dsr):
    """De besluitregel bovenop de poort: DSR met alle proeven van de scan en E1 én E2 positief na 1,5x kosten."""
    e1, e2 = [x["R15"] for x in va if x["t"] < mid], [x["R15"] for x in va if x["t"] >= mid]
    return bool(g["geslaagd"] and scan_dsr >= selector.DSR_MIN and e1 and e2 and np.mean(e1) > 0 and np.mean(e2) > 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("--uit", default="rapport/kansen.json")
    a = ap.parse_args()
    proto, sha = load_protocol()
    meta = json.loads((Path(a.map) / "markten.json").read_text())
    lab = {m["naam"]: (m.get("kandidaten") or {}).get("proeven") for m in json.loads(Path("lab.json").read_text())["markten"]}
    data = {}
    for e, r in meta["gekozen"].items():
        if r.get("candles", 0) > 5000 and (Path(a.map) / f"{e}.csv.gz").exists():
            data[e] = laad(a.map, e)
    einde = max(df.index[-1] for df in data.values())
    cut, mid = einde - pd.Timedelta(days=selector.VAL_DAYS), einde - pd.Timedelta(days=selector.VAL_DAYS / 2)
    print(f"{len(data)} markten, einde {einde}", flush=True)
    ex_1h, ex_4h = engine.Exits(max_bars=strat.MAX_BARS, gap_hours=strat.GAP_HOURS), engine.Exits(max_hours=proto["uitstap_4h"]["max_uren"], gap_hours=proto["uitstap_4h"]["gat_uren"])
    var_1h = [(f, v) for f in FAM_1H for v in strat.STRATS[f]["varianten"]]
    swing = [e for e, r in meta["gekozen"].items() if e in data and (r.get("type") in proto["soorten_4h"] or e in proto["indices_4h"])]
    n_scan = sum(len(v) for v in proto["families_4h"].values()) * len(swing) + len(var_1h) * len(data)
    scan = max(x for x in lab.values() if x) + n_scan
    rijen, aanbod = [], {}
    for e, df in data.items():
        m = NAAM.get(e, e)
        info = meta["gekozen"][e]
        fee = ((info.get("details") or {}).get("financiering"))
        spec = dict(zip(("markt", "epic", "type", "bekend"), (m, e, info.get("type"), e in NAAM)))
        X1, sp1 = strat.indicators(df), df["spread"]
        fam_trades = {}
        for fam, v in var_1h:
            k = json.dumps(v, sort_keys=True)
            tr = handel(m, fam, k, X1, v, sp1, fee, ex_1h)
            fam_trades.setdefault(fam, {})[k] = tr
            soort = "H0_baseline" if e in NAAM else "H3_dekking_1h"
            aanbod.setdefault(soort, []).extend(x for x in tr if x["t"] >= cut)
            if e in NAAM:
                aanbod.setdefault("H1_dure_uren", []).extend(x for x in handel(m, fam, k, X1, v, sp1, fee, ex_1h, 1.5) if x["t"] >= cut)
        if e in swing:
            h = naar_4h(df)
            X4 = strat.indicators(h)
            for fam, vs in proto["families_4h"].items():
                for v in vs:
                    k = json.dumps(v, sort_keys=True)
                    tr = handel(m, fam, k, X4, v, h["spread"], fee, ex_4h)
                    fam_trades.setdefault(fam, {})[k] = tr
                    aanbod.setdefault("H2_vasthouden" if e in NAAM else "H3_dekking_4h", []).extend(x for x in tr if x["t"] >= cut)
        trials = (lab.get(m) or 40) + sum(len(v) for v in proto["families_4h"].values())
        for fam, by in fam_trades.items():
            r = selector.evaluate_family(m, fam, by, cut, trials)
            g = r["poort"]
            va = [x for x in by.get(r["variant"], []) if x["t"] >= cut] if r["variant"] else []
            tr = [x for x in by.get(r["variant"], []) if x["t"] < cut] if r["variant"] else []
            dsr = deflated_sharpe([x["R"] for x in tr + va], scan) if va else 0.0
            rijen.append(dict(spec, familie=fam, variant=r["variant"], geslaagd=g["geslaagd"], redenen=[x[:2] for x in g["redenen"]], ontwikkeling=samen(tr), evaluatie=samen(va),
                              ondergrens=g["ondergrens"], dsr=g["dsr"], dsr_scan=round(float(dsr), 3), toelaatbaar=toelaatbaar(g, va, mid, dsr)))
        print(m, flush=True)
    out = dict(protocol=proto["naam"], protocol_sha256=sha, einde=str(einde), markten=len(data), swing_markten=len(swing), proeven_scan=scan,
               aanbod={k: samen(v) for k, v in aanbod.items()}, geslaagd=[r for r in rijen if r["geslaagd"]], toelaatbaar=[r for r in rijen if r["toelaatbaar"]], rijen=rijen)
    Path(a.uit).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out["aanbod"], indent=0))
    print("geslaagd", [(r["markt"], r["familie"], r["evaluatie"].get("gem15"), r["dsr_scan"]) for r in out["geslaagd"]])
    print("toelaatbaar", [(r["markt"], r["familie"]) for r in out["toelaatbaar"]])


if __name__ == "__main__":
    main()
