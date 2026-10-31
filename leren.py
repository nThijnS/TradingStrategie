#!/usr/bin/env python3
"""
Zelflerende laag van TradingStrategie. Draait elke werkdag na de beurs (GitHub Actions, workflow leren.yml).

1. Haalt per markt de laatste 60 dagen 5m-data op en zoekt alle setups met elke combinatie van instellingen:
   displacement (basis/strenger) x doel (1R, 1,5R, 2R, DOL) x sessies (NY AM / + London / alle) x biasfilter (geen / 1H mee).
2. Bewaart de uitkomst van elke setup in het geheugen (leren_geheugen.json). Dat groeit elke dag, ook voorbij 60 dagen.
3. Kiest per markt de variant met de beste voorzichtige score: gemiddelde R min een onzekerheidsmarge,
   recente trades tellen zwaarder (halfwaardetijd 60 dagen). Remmen tegen toeval:
     - minstens MIN_TRADES trades, anders blijft de huidige instelling staan;
     - alleen wisselen als de nieuwe variant minstens SWITCH_MARGIN R per trade beter scoort;
     - een markt waarvan zelfs de beste variant onder 0 scoort, gaat op pauze (geen meldingen, wel loggen en leren).
4. Schrijft de keuze naar learned.json (de app leest dat elke minuut) en het Obsidian-journaal (journaal/).

Gebruik:
  python leren.py              # leren + journaal bijwerken
  python leren.py --geen-data  # alleen opnieuw kiezen en journaal schrijven uit het bestaande geheugen
  python leren.py --histdata   # eenmalig: geheugen ook vullen met de lokale HistData (jan 2025 - okt 2026)
"""
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import tradingstrategie as ts

HERE = Path(__file__).resolve().parent
MEMORY = HERE / "leren_geheugen.json"
LEARNED = HERE / "learned.json"
HISTORY = HERE / "leren_geschiedenis.json"
JOURNAL = HERE / "journaal"

COST = {"NQ": 2.0, "EURUSD": 0.00008, "GOUD": 0.35}
DISP = {"basis": dict(disp_pct=0.6, disp_atr=1.2), "strenger": dict(disp_pct=0.7, disp_atr=1.5)}
TARGETS = ["1.0", "1.5", "2.0", "DOL"]
SESSIONS = {"NY AM": ["NY AM"], "NY AM + London": ["NY AM", "London"], "alle sessies": ["London", "NY AM", "NY PM"]}
BIAS = {"geen": False, "1H mee": True}
MIN_TRADES = 20
SWITCH_MARGIN = 0.05
HALF_LIFE_DAYS = 60
Z = 1.0                 # onzekerheidsmarge: gemiddelde - 1 standaardfout
MAX_HOURS = 5


# ------------- Uitkomst op 5m-candles -------------
def simulate5(df, s, target, cost):
    if s["entry_hit"] is None:
        return None
    long = s["side"] == "LONG"
    e, stop = s["entry"], s["stop"]
    risk = abs(e - stop)
    if risk <= 0:
        return None
    if target == "DOL":
        tp = s.get("dol") or (e + 2 * risk if long else e - 2 * risk)
    else:
        tp = e + float(target) * risk if long else e - float(target) * risk
    after = df.loc[s["entry_hit"]:s["entry_hit"] + pd.Timedelta(hours=MAX_HOURS)]
    if after.index[-1] < s["entry_hit"] + pd.Timedelta(hours=MAX_HOURS) and after.index[-1] >= df.index[-1]:
        open_trade = True
    else:
        open_trade = False
    for _, row in after.iterrows():
        if (row["Low"] <= stop) if long else (row["High"] >= stop):
            return -1.0 - cost / risk
        if (row["High"] >= tp) if long else (row["Low"] <= tp):
            return abs(tp - e) / risk - cost / risk
    if open_trade:
        return None          # loopt nog: morgen opnieuw
    c = after["Close"].iloc[-1]
    return ((c - e) if long else (e - c)) / risk - cost / risk


# ------------- Geheugen -------------
def load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


HISTDATA = {"NQ": ("NSXUSD", "SPXUSD"), "EURUSD": ("EURUSD", "GBPUSD"), "GOUD": ("XAUUSD", "XAGUSD")}


def histdata(m):
    """Eenmalige startvulling: 5m-candles uit de lokale HistData (zomertijd gecorrigeerd)."""
    from backtest import to5
    from tp_videos import load_dst
    sym, smt = HISTDATA[m["name"]]
    return to5(load_dst(sym)), to5(load_dst(smt))


def collect(mem, source="yahoo"):
    """Nieuwe setups in het geheugen zetten (bestaande uitkomsten blijven staan).
    source "yahoo": laatste 60 dagen live data; "histdata": de lokale 1m-data van jan 2025 tot okt 2026."""
    for m in ts.CFG["markets"]:
        name = m["name"]
        try:
            df, es = histdata(m) if source == "histdata" else (ts.fetch(m["symbol"], "60d"), ts.fetch(m["smt"], "60d"))
        except Exception as ex:
            print(f"{name}: geen data ({ex})", flush=True)
            continue
        added = 0
        for dname, over in DISP.items():
            cfg = {**ts.CFG, **m["cfg"], **over, "max_per_day": 6, "need_bias_b": False,
                   "trade_sess": [("02:00", "05:00"), ("09:30", "11:30"), ("13:30", "15:30")]}
            setups, _ = ts.analyse(df, es, cfg)
            for s in setups:
                for target in TARGETS:
                    key = f"{name}|{dname}|{target}|{s['time'].isoformat()}|{s['side']}"
                    if key in mem:
                        continue
                    r = simulate5(df, s, target, COST.get(name, 0))
                    if r is None:
                        continue
                    mem[key] = dict(markt=name, disp=dname, target=target, t=s["time"].isoformat(),
                                    sess=ts.sess_name(s["time"]), bias_mee=s["bias_b"] == (1 if s["side"] == "LONG" else -1),
                                    R=round(float(r), 3), bron=source)
                    added += 1
        print(f"{name}: {added} nieuwe uitkomsten", flush=True)
    return mem


# ------------- Kiezen -------------
def variants():
    for d in DISP:
        for tg in TARGETS:
            for sn in SESSIONS:
                for b in BIAS:
                    yield dict(disp=d, target=tg, sessies=sn, bias=b)


def vid(v):
    return f"{v['disp']} · TP {v['target']} · {v['sessies']} · bias {v['bias']}"


def score(rows, v, now):
    sel = [r for r in rows if r["disp"] == v["disp"] and r["target"] == v["target"]
           and r["sess"] in SESSIONS[v["sessies"]] and (r["bias_mee"] or not BIAS[v["bias"]])]
    # zoals de app: per dag alleen de eerste trade
    sel.sort(key=lambda r: r["t"])
    seen, trades = set(), []
    for r in sel:
        d = r["t"][:10]
        if d not in seen:
            seen.add(d)
            trades.append(r)
    n = len(trades)
    if n < 2:
        return dict(n=n, gem=0.0, score=-9.0, win=0.0, totaal=0.0)
    w = [0.5 ** ((now - datetime.fromisoformat(r["t"])).days / HALF_LIFE_DAYS) for r in trades]
    R = [r["R"] for r in trades]
    sw = sum(w)
    mean = sum(wi * ri for wi, ri in zip(w, R)) / sw
    var = sum(wi * (ri - mean) ** 2 for wi, ri in zip(w, R)) / sw
    n_eff = sw ** 2 / sum(wi ** 2 for wi in w)
    return dict(n=n, gem=round(mean, 3), score=round(mean - Z * math.sqrt(var / n_eff), 3),
                win=round(sum(r > 0 for r in R) / n, 3), totaal=round(sum(R), 1))


def choose(mem, learned):
    now = datetime.now(ts.NY)
    out, report = {}, {}
    for m in ts.CFG["markets"]:
        name = m["name"]
        rows = [r for r in mem.values() if r["markt"] == name]
        ranked = sorted(((score(rows, v, now), v) for v in variants()), key=lambda x: -x[0]["score"])
        ranked_ok = [x for x in ranked if x[0]["n"] >= MIN_TRADES]
        old = learned.get(name)
        old_score = None
        if old:
            old_score = score(rows, old["variant"], now)
        best = ranked_ok[0] if ranked_ok else None
        if best is None:
            pick, why = old, f"nog geen variant met {MIN_TRADES} trades: niets veranderd"
        elif old is None:
            pick, why = dict(variant=best[1]), "eerste keuze"
        elif best[1] == old["variant"]:
            pick, why = old, "huidige variant is nog steeds de beste"
        elif old_score["n"] >= MIN_TRADES and best[0]["score"] < old_score["score"] + SWITCH_MARGIN:
            pick, why = old, f"nieuwe beste is minder dan {SWITCH_MARGIN}R per trade beter: blijven"
        else:
            pick, why = dict(variant=best[1]), "gewisseld naar een duidelijk betere variant"
        if pick is not None:
            sc = score(rows, pick["variant"], now)
            pick = dict(variant=pick["variant"], score=sc, actief=sc["n"] >= MIN_TRADES and sc["score"] > 0,
                        sinds=pick.get("sinds") if old and pick["variant"] == old["variant"] else now.date().isoformat())
            if not pick["actief"]:
                why += "; score <= 0 of te weinig trades: markt op pauze"
            out[name] = pick
        report[name] = dict(waarom=why, top=[dict(variant=vid(v), **s) for s, v in ranked[:8]], n_data=len(rows))
    return out, report


def to_app(choice):
    """learned.json in het formaat dat tradingstrategie.py leest."""
    app = {"bijgewerkt": datetime.now(ts.NY).isoformat(timespec="minutes"), "markten": {}}
    for name, c in choice.items():
        v = c["variant"]
        cfg = dict(DISP[v["disp"]])
        if v["target"] == "DOL":
            cfg["tp_mode"] = "DOL"
        else:
            cfg.update(tp_mode="R", tp_r=float(v["target"]))
        app["markten"][name] = dict(actief=c["actief"], cfg=cfg, kans_sess=SESSIONS[v["sessies"]],
                                    need_bias_b=BIAS[v["bias"]], variant=vid(v), score=c["score"], sinds=c["sinds"])
    return app


# ------------- Obsidian-journaal -------------
def svg_chart(df, s, width=640, height=260):
    """Kleine candle-chart (SVG) rond een setup met entry, stop en TP."""
    t0 = s["time"] - pd.Timedelta(hours=2)
    t1 = s["time"] + pd.Timedelta(hours=MAX_HOURS)
    w = df.loc[t0:t1]
    if len(w) < 3:
        return None
    lo = min(w["Low"].min(), s["stop"], s["tp"])
    hi = max(w["High"].max(), s["stop"], s["tp"])
    pad = (hi - lo) * 0.05
    lo, hi = lo - pad, hi + pad
    X = lambda i: 10 + i * (width - 70) / max(len(w) - 1, 1)
    Y = lambda p: 10 + (hi - p) / (hi - lo) * (height - 30)
    bw = max(1.5, (width - 70) / len(w) * 0.6)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" font-family="monospace" font-size="10">',
             f'<rect width="{width}" height="{height}" fill="#14171d"/>']
    for i, (t, r) in enumerate(w.iterrows()):
        col = "#3fb68b" if r["Close"] >= r["Open"] else "#e2595b"
        x = X(i)
        parts.append(f'<line x1="{x:.1f}" y1="{Y(r["High"]):.1f}" x2="{x:.1f}" y2="{Y(r["Low"]):.1f}" stroke="{col}"/>')
        y0, y1 = sorted((Y(r["Open"]), Y(r["Close"])))
        parts.append(f'<rect x="{x - bw / 2:.1f}" y="{y0:.1f}" width="{bw:.1f}" height="{max(1, y1 - y0):.1f}" fill="{col}"/>')
    i_s = w.index.get_indexer([s["time"]], method="nearest")[0]
    for lab, p, col in (("TP", s["tp"], "#3fb68b"), ("entry", s["entry"], "#d9dde6"), ("stop", s["stop"], "#e2595b")):
        parts.append(f'<line x1="{X(i_s):.1f}" y1="{Y(p):.1f}" x2="{width - 60}" y2="{Y(p):.1f}" stroke="{col}" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{width - 56}" y="{Y(p) + 3:.1f}" fill="{col}">{lab}</text>')
    parts.append(f'<circle cx="{X(i_s):.1f}" cy="{Y(s["entry"]):.1f}" r="4" fill="#e0a33a"/>')
    for k, anchor in ((0, "start"), (len(w) // 2, "middle"), (len(w) - 1, "end")):
        parts.append(f'<text x="{X(k):.1f}" y="{height - 6}" fill="#8b93a5" text-anchor="{anchor}">{w.index[k]:%H:%M} NY</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def write_journal(choice, report, mem):
    JOURNAL.mkdir(exist_ok=True)
    (JOURNAL / "charts").mkdir(exist_ok=True)
    (JOURNAL / "Dagen").mkdir(exist_ok=True)
    now = datetime.now(ts.NY)
    # Huidige strategie
    lines = ["# Huidige strategie", "", f"Bijgewerkt: {now:%Y-%m-%d %H:%M} NY. De bot kiest dit zelf, zie [Leren](Leren.md).", ""]
    for name, c in choice.items():
        v = c["variant"]
        sc = c["score"]
        lines += [f"## {name}: {'actief' if c['actief'] else 'pauze (wel loggen en leren)'}",
                  f"- Displacement: **{v['disp']}**", f"- Doel: **{'DOL (liquiditeit)' if v['target'] == 'DOL' else v['target'] + 'R'}**",
                  f"- Sessies: **{v['sessies']}**", f"- Biasfilter: **{v['bias']}**",
                  f"- Score: {sc['score']:+.3f}R per trade (voorzichtig), gemiddeld {sc['gem']:+.3f}R, {sc['n']} trades, win {sc['win']:.0%}",
                  f"- Actief sinds: {c['sinds']}", ""]
    (JOURNAL / "Huidige strategie.md").write_text("\n".join(lines))
    # Leerlog: nieuwste bovenaan
    log = JOURNAL / "Leren.md"
    old = log.read_text().split("\n", 2)[2] if log.exists() else ""
    entry = [f"## {now:%Y-%m-%d %H:%M} NY", ""]
    for name, r in report.items():
        entry += [f"### {name}: {r['waarom']}", f"Geheugen: {r['n_data']} uitkomsten.", "",
                  "| variant | trades | win | gem R | score | totaal R |", "|---|---|---|---|---|---|"]
        entry += [f"| {t['variant']} | {t['n']} | {t['win']:.0%} | {t['gem']:+.3f} | {t['score']:+.3f} | {t['totaal']:+.1f} |" for t in r["top"]]
        entry.append("")
    log.write_text("# Leren\n\n" + "\n".join(entry) + "\n" + old)


def journal_day(day_setups):
    """Dagnotitie met elke setup van vandaag uit de logboek-run (chart + details + uitkomst)."""
    if not day_setups:
        return
    day = day_setups[0]["dag"]
    lines = [f"# {day}", "", "Setups die de bot vandaag zag. Uitkomst volgens het logboek.", ""]
    for s in day_setups:
        lines += [f"## {s['markt']} {s['kant']} {s['tijd'][11:16]} ({s['sessie']}, {'kans' if s['kans'] else 'lage kans'})"]
        if s.get("chart"):
            lines.append(f"![chart](../charts/{s['chart']})")   # gewone link: werkt op GitHub én in Obsidian
        lines += [f"- Entry {s['entry']} | stop {s['stop']} | TP {s['tp']} ({s['rr']}R)",
                  f"- Sweep: {s['sweep']} | checks: {', '.join(s['checks']) or '-'}",
                  f"- Uitkomst: **{s['uitkomst']}** ({s['R']:+.2f}R)", ""]
    (JOURNAL / "Dagen" / f"{day}.md").write_text("\n".join(lines))


def days_from_logbook(data):
    """Dagnotities uit logboek.json (als de cloud dat heeft) met een chart per setup."""
    book = load(HERE / "logboek.json", {})
    setups = [v for v in book.values() if v["type"] == "setup"]
    if not setups:
        return
    by_day = {}
    for s in setups:
        by_day.setdefault(s["tijd"][:10], []).append(s)
    for day, lst in sorted(by_day.items())[-10:]:
        for s in lst:
            s["dag"] = day
            df = data.get(s["markt"])
            if df is None:
                continue
            fn = f"{s['markt']}_{s['tijd'][:16].replace(':', '')}_{s['kant']}.svg"
            svg = svg_chart(df, dict(time=pd.Timestamp(s["tijd"]), entry=s["entry"], stop=s["stop"], tp=s["tp"]))
            if svg:
                (JOURNAL / "charts" / fn).write_text(svg)
                s["chart"] = fn          # Obsidian vindt het plaatje op naam
        journal_day(sorted(lst, key=lambda x: x["tijd"]))


def main():
    mem = load(MEMORY, {})
    if "--histdata" in sys.argv:
        mem = collect(mem, "histdata")
    if "--geen-data" not in sys.argv:
        mem = collect(mem)
        MEMORY.write_text(json.dumps(mem, separators=(",", ":")))
    learned_prev = load(LEARNED, {}).get("markten", {})
    prev = {k: dict(variant=_parse(v["variant"]), sinds=v.get("sinds")) for k, v in learned_prev.items() if "variant" in v}
    choice, report = choose(mem, prev)
    LEARNED.write_text(json.dumps(to_app(choice), indent=1, ensure_ascii=False))
    hist = load(HISTORY, [])
    hist.append(dict(t=datetime.now(ts.NY).isoformat(timespec="minutes"),
                     keuze={k: dict(variant=vid(c["variant"]), actief=c["actief"], score=c["score"]) for k, c in choice.items()}))
    HISTORY.write_text(json.dumps(hist[-400:], indent=1, ensure_ascii=False))
    write_journal(choice, report, mem)
    data = {}
    if "--geen-data" not in sys.argv:
        for m in ts.CFG["markets"]:
            try:
                data[m["name"]] = ts.fetch(m["symbol"], "30d")
            except Exception:
                pass
    days_from_logbook(data)
    for name, r in report.items():
        c = choice.get(name)
        if c:
            print(f"{name:7} {'ACTIEF' if c['actief'] else 'pauze '} {vid(c['variant'])} | score {c['score']['score']:+.3f} "
                  f"({c['score']['n']} trades) | {r['waarom']}")
        else:
            print(f"{name:7} standaard | {r['waarom']}")


def _parse(s):
    """Variant-tekst uit learned.json terug naar een dict."""
    disp, tp, sess, bias = [x.strip() for x in s.split("·")]
    return dict(disp=disp, target=tp.replace("TP ", ""), sessies=sess, bias=bias.replace("bias ", ""))


if __name__ == "__main__":
    main()
