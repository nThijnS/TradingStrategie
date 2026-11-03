"""Obsidian-journaal van het leren (journaal/): huidige strategie, leerlog en dagnotities met SVG-charts."""
from datetime import datetime

import pandas as pd

from core.sessions import NY
from storage import jsonstore, paths

LEARN_HOURS = 5


def svg_chart(df, s, width=640, height=260):
    """Kleine candle-chart (SVG) rond een setup met entry, stop en TP."""
    t0 = s["time"] - pd.Timedelta(hours=2)
    t1 = s["time"] + pd.Timedelta(hours=LEARN_HOURS)
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


def write_selection(results):
    """Huidige strategie.md: per markt welke strategie de selector koos (actief/onderzoek/pauze) en waarom."""
    paths.JOURNAL.mkdir(exist_ok=True)
    now = datetime.now(NY)
    order = {"actief": 0, "onderzoek": 1, "pauze": 2}
    rows = sorted((r for r in results if r.get("keuze")), key=lambda r: (order.get(r["keuze"].get("status"), 3), r["naam"]))
    lines = ["# Huidige strategie", "", f"Bijgewerkt: {now:%Y-%m-%d %H:%M} NY. De bot kiest dit per markt zelf uit alle "
             "strategieën (ICT is er één van) met een vaste poort tegen overfitting; zie learning/selector.py.", "",
             "| markt | status | strategie | ondergrens validatie | sinds | reden |", "|---|---|---|---|---|---|"]
    for r in rows:
        k = r["keuze"]
        lb = f"{k['ondergrens']:+.3f}R ({k['n']} trades)" if k.get("ondergrens") is not None else "-"
        lines.append(f"| {r['naam']} | {k.get('status', '-')} | {k.get('titel', '-')} {k.get('variant_txt') or ''} | {lb} | "
                     f"{k.get('sinds', '-')} | {k.get('reden_vandaag', '')} |")
    lines += ["", "Status: **actief** = haalt de poort, signalen tellen (orders op het demo-account); **onderzoek** = in train "
              "en validatie positief maar nog niet genoeg bewijs, wordt gevolgd zonder orders; **pauze** = niets."]
    (paths.JOURNAL / "Huidige strategie.md").write_text("\n".join(lines) + "\n")


def write_journal(choice, report, mem):
    paths.JOURNAL.mkdir(exist_ok=True)
    (paths.JOURNAL / "charts").mkdir(exist_ok=True)
    (paths.JOURNAL / "Dagen").mkdir(exist_ok=True)
    now = datetime.now(NY)
    # Leerlog: nieuwste bovenaan
    log = paths.JOURNAL / "Leren.md"
    old = log.read_text().split("\n", 2)[2] if log.exists() else ""
    entry = [f"## {now:%Y-%m-%d %H:%M} NY", ""]
    for name, r in report.items():
        entry += [f"### {name} (ICT-varianten, ter informatie): {r['waarom']}", f"Geheugen: {r['n_data']} uitkomsten.", "",
                  "| variant | trades | win | gem R | score | totaal R |", "|---|---|---|---|---|---|"]
        entry += [f"| {t['variant']} | {t['n']} | {t['win']:.0%} | {t['gem']:+.3f} | {t['score']:+.3f} | {t['totaal']:+.1f} |" for t in r["top"]]
        v = r.get("validatie")
        if v:
            entry.append(f"\nControle op de laatste {v['dagen']} dagen (alleen ter informatie, verandert de keuze niet): "
                         f"train {v['train']['gem']:+.3f}R over {v['train']['n']} trades, "
                         f"nieuw {v['nieuw']['gem']:+.3f}R over {v['nieuw']['n']} trades.")
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
    (paths.JOURNAL / "Dagen" / f"{day}.md").write_text("\n".join(lines))


def days_from_logbook(data):
    """Dagnotities uit logboek.json (als de cloud dat heeft) met een chart per setup."""
    book = jsonstore.load(paths.LOGBOOK, {})
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
                (paths.JOURNAL / "charts" / fn).write_text(svg)
                s["chart"] = fn          # Obsidian vindt het plaatje op naam
        journal_day(sorted(lst, key=lambda x: x["tijd"]))

