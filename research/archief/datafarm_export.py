#!/usr/bin/env python3
"""
ARCHIEF (bevroren, november 2026): afgerond onderzoek; draait niet in de cloud. Bij de refactor zijn alleen de
imports aangepast. Backtests via backtest.simulate gebruiken nu de centrale engine (kleine verschillen met de
oorspronkelijke cijfers: zie docs/refactor/3_engine_vergelijking.md).

Zet de uitkomst van datafarm.py klaar voor de viewer (farm_artifact/): overzicht, dagstudies en per dag
de candles (2m/5m/15m/1h) met alle events, voor de laatste DAYS handelsdagen per markt.

Gebruik:
  python datafarm_export.py
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))   # repo-root (archief)

import json

import numpy as np
import pandas as pd

from backtest import stats
from datafarm import MARKETS, OUT, SPLIT, TFS, bars
from tp_videos import load_dst

ART = OUT.parent.parent / "farm_artifact"
DAYS = 30
KEEP = ["id", "kind", "tf", "t", "side", "scope", "level", "dir", "brk", "n_pivots", "disp", "price", "label", "at",
        "top", "bot", "reason", "result", "R", "R_net", "entry", "stop", "tp", "rr", "conf", "setup_tf", "grade",
        "ext", "n_pools", "n_candles", "anchor", "held", "ob", "fire", "mss", "sweep", "fvg", "start"]


def ts(x):
    return int(pd.Timestamp(x).timestamp())


def clean(v):
    if isinstance(v, (pd.Timestamp,)):
        return ts(v)
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else round(float(v), 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def ev_rows(df):
    out = []
    for r in df.to_dict("records"):
        e = {}
        for k in KEEP:
            v = r.get(k)
            if v is None or (not isinstance(v, (list, tuple)) and pd.isna(v)):
                continue
            if isinstance(v, (list, tuple)):
                e[k] = list(v)
            else:
                e[k] = clean(v)
        out.append(e)
    return out


def main():
    (ART / "data" / "day").mkdir(parents=True, exist_ok=True)
    overview = {"markets": {}, "days": {}}
    for mkt, cfg in MARKETS.items():
        ev = pd.read_pickle(OUT / f"events_{mkt}.pkl")
        ev = ev[pd.to_datetime(ev.day).dt.weekday < 5]          # alleen handelsdagen (CME-dag ma-vr)
        studies = [st for st in json.loads((OUT / f"studies_{mkt}.json").read_text())
                   if pd.Timestamp(st["day"]).weekday() < 5]
        (ART / "data" / f"studies_{mkt}.json").write_text(json.dumps(studies, ensure_ascii=False))
        o = ev[ev.kind == "lit_outcome"].sort_values("t")
        f = ev[ev.kind == "lit_fire"].set_index("id")
        per = {}
        for lab, part in (("2025", o[o.t < SPLIT]), ("2026", o[o.t >= SPLIT]), ("totaal", o)):
            a, b = stats(part.R.values), stats(part.R_net.values)
            per[lab] = dict(n=a["n"], win=round(a["win"], 3), R=round(a["totR"], 1), R_net=round(b["totR"], 1),
                            dd_net=round(b["maxDD"], 1))
        eq = o.assign(d=o.t.dt.strftime("%Y-%m-%d")).groupby("d").R_net.sum().cumsum().round(2)
        conf = o.assign(c=o.fire.map(f.conf).map(len)).groupby("c").agg(n=("R_net", "size"), R=("R_net", "sum")).round(1)
        overview["markets"][mkt] = dict(
            counts={k: int(v) for k, v in ev.kind.value_counts().items()},
            lit=per, equity=[[d, float(v)] for d, v in eq.items()],
            by_conf={int(k): dict(n=int(r.n), R=float(r.R)) for k, r in conf.iterrows()},
            by_tf={k: round(float(g.R_net.sum()), 1) for k, g in o.assign(tf=o.fire.map(f.setup_tf)).groupby("tf")},
            refusals={k: int(v) for k, v in ev[ev.kind == "lit_refusal"].reason.value_counts().items()},
            first=str(ev.day.min()), last=str(ev.day.max()))
        overview["days"][mkt] = {str(d): int(n) for d, n in ev.groupby("day").size().items()}

        # Per dag: candles + events voor de chart
        m1 = load_dst(cfg["sym"])
        days = sorted(ev.day.unique())[-DAYS:]
        B = {tf: bars(m1, tf) for tf in ("2m", "5m", "15m", "1h")}
        for d in days:
            start = pd.Timestamp(d, tz="America/New_York") - pd.Timedelta(hours=6)
            end = start + pd.Timedelta(hours=24)
            day = {"market": mkt, "day": str(d), "bars": {}}
            for tf, b in B.items():
                lo = start - (pd.Timedelta("3D") if tf == "1h" else pd.Timedelta(0))
                w = b.loc[lo:end - pd.Timedelta(minutes=1)]
                day["bars"][tf] = [[ts(t), *[round(float(x), 2) for x in r]] for t, r in
                                   zip(w.index, w[["Open", "High", "Low", "Close"]].values)]
            de = ev[(ev.t >= start) & (ev.t < end) & ev.tf.isin(list(TFS))]
            day["events"] = ev_rows(de)
            (ART / "data" / "day" / f"{mkt}_{d}.json").write_text(json.dumps(day, separators=(",", ":")))
        overview.setdefault("chart_days", {})[mkt] = [str(d) for d in days]
        print(f"{mkt}: {len(days)} dagen geëxporteerd", flush=True)
    (ART / "data" / "overview.json").write_text(json.dumps(overview, ensure_ascii=False))


if __name__ == "__main__":
    main()
