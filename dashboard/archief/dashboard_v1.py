#!/usr/bin/env python3
"""
ARCHIEF (bevroren, november 2026): afgerond onderzoek; draait niet in de cloud. Bij de refactor zijn alleen de
imports aangepast. Backtests via backtest.simulate gebruiken nu de centrale engine (kleine verschillen met de
oorspronkelijke cijfers: zie docs/refactor/3_engine_vergelijking.md).

Dashboard voor TradingStrategie: een lokale webpagina met
  - Live: de setups van de afgelopen 30 dagen (NQ en EURUSD) met grafiek, entry/stop/TP en uitkomst
  - Voorbeelden: trades uit de backtest (HistData, jan 2025 - okt 2026) die volgens de strategie goed waren,
    plus een paar verliezers, en de winstcurve van alle "kans"-trades

Gebruik:
  python dashboard.py            maakt dashboard.html, opent hem en ververst elke 2 minuten
  python dashboard.py --once     alleen één keer maken
  python dashboard.py --rebuild  voorbeelden opnieuw uit de backtest-data berekenen
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))   # repo-root (archief)

import argparse
import json
import subprocess
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from tradingstrategie import CFG, NY, analyse, analyse_market, sess_name

warnings.filterwarnings("ignore")

HERE = Path(__file__).resolve().parents[2]
OUT = HERE / "dashboard.html"
EXAMPLES = HERE / "data" / "voorbeelden.json"
NL = ZoneInfo("Europe/Amsterdam")
REFRESH_SEC = 120

# Backtest-data per markt (HistData-symbolen) en kosten per trade, zoals in backtest_multi.py
HIST = {"NQ": ("NSXUSD", "SPXUSD", 2.0), "EURUSD": ("EURUSD", "GBPUSD", 0.00008)}


def jsonable(o):
    """numpy-getallen en dergelijke omzetten voor json.dumps."""
    return o.item() if hasattr(o, "item") else str(o)


def ts(t):
    """Tijd als 'Nederlandse klok' in seconden, zodat de grafiek NL-tijd toont."""
    return int(t.tz_convert(NL).tz_localize(None).timestamp())


def candles(df, start, end):
    part = df.loc[start:end]
    return [dict(time=ts(t), open=round(r.Open, 6), high=round(r.High, 6), low=round(r.Low, 6), close=round(r.Close, 6))
            for t, r in part.iterrows()]


def window(s, t_end):
    """Grafiekvenster: vanaf ~1,5 uur voor de sweep tot een uur na de exit."""
    start = min(s["sweep_t"], s["time"]) - timedelta(minutes=90)
    return start, max(t_end, s["time"]) + timedelta(minutes=60)


def card(s, mkt, dec, df, result, r, t_exit):
    start, end = window(s, t_exit or s["time"] + timedelta(hours=2))
    return dict(
        mkt=mkt, dec=dec, side=s["side"], grade=s["grade"], score=s["score"], good=bool(s["good"]),
        sess=sess_name(s["time"]), sweep=s["sweep"], rr=round(float(s["rr"]), 2),
        entry=s["entry"], stop=s["stop"], tp=s["tp"],
        time=ts(s["time"]), sweep_t=ts(s["sweep_t"]), mss_t=ts(s["mss_t"]),
        entry_t=ts(s["entry_hit"]) if s["entry_hit"] is not None else None,
        exit_t=ts(t_exit) if t_exit is not None else None,
        result=result, R=round(float(r), 2),
        checks=[[k, bool(v)] for k, v in s["checks"].items()],
        candles=candles(df, start, end),
    )


# ------------- Live -------------
def live_outcome(df, s):
    """Zoals outcome() in de app, maar geeft ook het tijdstip van de exit terug."""
    if s["entry_hit"] is None:
        return "geen entry", 0.0, None
    long = s["side"] == "LONG"
    risk = abs(s["entry"] - s["stop"])
    for t, row in df[df.index >= s["entry_hit"]].iterrows():
        if (row.Low <= s["stop"]) if long else (row.High >= s["stop"]):
            return "stop", -1.0, t
        if (row.High >= s["tp"]) if long else (row.Low <= s["tp"]):
            return "TP", float(s["rr"]), t
        if t.strftime("%H:%M") >= "16:00" or t.date() != s["entry_hit"].date():
            return "dicht 16:00", ((row.Close - s["entry"]) if long else (s["entry"] - row.Close)) / risk, t
    return "loopt nog", 0.0, None


def build_live():
    cards, errors = [], []
    for m in CFG["markets"]:
        try:
            df, setups, _ = analyse_market(m)
        except Exception as ex:
            errors.append(f"{m['name']}: {ex}")
            continue
        for s in setups:
            res, r, t_exit = live_outcome(df, s)
            cards.append(card(s, m["name"], m["dec"], df, res, r, t_exit))
    cards.sort(key=lambda c: c["time"], reverse=True)
    return cards, errors


# ------------- Voorbeelden uit de backtest -------------
def build_examples():
    from backtest import load_m1, simulate, to5
    trades, picks = [], []
    for m in CFG["markets"]:
        sym, smt, cost = HIST[m["name"]]
        m1 = load_m1(sym)
        m5 = to5(m1)
        setups, _ = analyse(m5, to5(load_m1(smt)), dict(CFG, max_per_day=6, **m["cfg"]))
        target = "DOL" if m["cfg"].get("tp_mode") == "DOL" else CFG["tp_r"]
        for s in setups:
            if not s["good"]:
                continue
            out = simulate(m1, s, target, cost=cost, max_hours=5)
            if out is None:
                continue
            r, mins = out
            t_exit = s["entry_hit"] + timedelta(minutes=mins + 5)
            trades.append(dict(mkt=m["name"], t=ts(s["entry_hit"]), R=round(r, 3)))
            picks.append((r, m, s, m5, t_exit))
    trades.sort(key=lambda x: x["t"])
    # Beste winnaars verspreid over de tijd (max 1 per maand, 5 per markt) en een paar verliezers
    winners, seen, per_mkt = [], set(), {}
    for r, m, s, m5, t_exit in sorted(picks, key=lambda p: -p[0]):
        key = (m["name"], s["time"].strftime("%Y-%m"))
        if r > 0 and key not in seen and per_mkt.get(m["name"], 0) < 5:
            seen.add(key)
            per_mkt[m["name"]] = per_mkt.get(m["name"], 0) + 1
            winners.append((r, m, s, m5, t_exit))
    winners.sort(key=lambda p: p[2]["time"], reverse=True)
    losers = [p for p in picks if p[0] < 0][::max(1, len([p for p in picks if p[0] < 0]) // 3)][:3]
    ex = []
    for r, m, s, m5, t_exit in winners + losers:
        res = "TP" if r > 0.5 else "stop" if r < -0.5 else "dicht na 5 uur"
        ex.append(card(s, m["name"], m["dec"], m5, res, r, t_exit))
    data = dict(trades=trades, examples=ex, made=datetime.now(NL).strftime("%d-%m-%Y %H:%M"))
    EXAMPLES.write_text(json.dumps(data, default=jsonable))
    return data


def load_examples(rebuild=False):
    if EXAMPLES.exists() and not rebuild:
        return json.loads(EXAMPLES.read_text())
    print("Voorbeelden berekenen uit de backtest-data (eenmalig, ~1 minuut)...", flush=True)
    return build_examples()


# ------------- HTML -------------
def render(live, errors, examples, auto_refresh):
    data = dict(live=live, errors=errors, examples=examples,
                updated=datetime.now(NL).strftime("%H:%M"), today=datetime.now(NL).strftime("%Y-%m-%d"),
                refresh=REFRESH_SEC if auto_refresh else 0)
    js = json.dumps(data, default=jsonable).replace("</", "<\\/")
    html = TEMPLATE.replace("__DATA__", js)
    if auto_refresh:
        html = html.replace("<!--REFRESH-->", f'<meta http-equiv="refresh" content="{REFRESH_SEC}">')
    OUT.write_text(html)


def make(rebuild=False, auto_refresh=True):
    examples = load_examples(rebuild)
    live, errors = build_live()
    render(live, errors, examples, auto_refresh)
    print(f"{datetime.now(NL):%H:%M:%S} dashboard bijgewerkt: {len(live)} live setups", flush=True)


TEMPLATE = r"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!--REFRESH-->
<title>TradingStrategie Dashboard</title>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
:root {
  color-scheme: light;
  --surface-0: #f4f3f0; --surface-1: #fcfcfb; --border: #e2e1dc;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #7a7974;
  --grid: #ecebe7; --candle-up: #b9b8b2; --candle-down: #52514e;
  --entry: #2a78d6; --good: #0ca30c; --critical: #d03b3b; --warning: #fab219; --neutral: #7a7974;
  --chip: #ecebe7;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --surface-0: #121211; --surface-1: #1a1a19; --border: #2e2e2c;
    --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #8f8e88;
    --grid: #262624; --candle-up: #8f8e88; --candle-down: #4a4a46;
    --entry: #3987e5; --chip: #262624;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface-0: #121211; --surface-1: #1a1a19; --border: #2e2e2c;
  --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #8f8e88;
  --grid: #262624; --candle-up: #8f8e88; --candle-down: #4a4a46;
  --entry: #3987e5; --chip: #262624;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface-0); color: var(--text-primary);
  font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
header { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: baseline; padding: 20px 24px 8px; }
h1 { font-size: 20px; margin: 0; }
.sub { color: var(--text-secondary); font-size: 13px; }
nav { display: flex; gap: 8px; padding: 8px 24px 0; flex-wrap: wrap; align-items: center; }
nav button, nav select { font: inherit; padding: 6px 14px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--surface-1); color: var(--text-primary); cursor: pointer; }
nav button[aria-selected="true"] { background: var(--text-primary); color: var(--surface-1); border-color: var(--text-primary); }
nav .spacer { flex: 1; }
main { padding: 16px 24px 40px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; margin-bottom: 16px; }
.kpi { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; }
.kpi .v { font-size: 26px; font-weight: 600; font-variant-numeric: tabular-nums; }
.kpi .l { color: var(--text-secondary); font-size: 12px; }
.panel { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 14px; margin-bottom: 16px; }
.panel h2 { font-size: 15px; margin: 0 0 4px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 460px), 1fr)); gap: 16px; }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.card .head { padding: 12px 14px 6px; display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; }
.card .title { font-weight: 600; }
.chip { font-size: 12px; padding: 2px 8px; border-radius: 999px; background: var(--chip); color: var(--text-secondary); }
.res { font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 999px; border: 1px solid currentColor; }
.res.win { color: var(--good); } .res.loss { color: var(--critical); } .res.flat { color: var(--text-secondary); }
.chart { height: 260px; }
.meta { padding: 8px 14px 12px; font-size: 13px; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.meta b { color: var(--text-primary); font-weight: 600; }
.checks { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 6px; font-size: 12px; }
.checks .off { color: var(--text-muted); }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 12px; color: var(--text-secondary); margin: 0 0 12px; }
.legend i { display: inline-block; width: 14px; height: 0; border-top: 2px solid; vertical-align: middle; margin-right: 6px; }
.empty { color: var(--text-secondary); padding: 24px; text-align: center; }
.err { color: var(--critical); font-size: 13px; padding: 0 24px; }
details summary { cursor: pointer; color: var(--text-secondary); font-size: 13px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--border); }
@media (max-width: 600px) { header, nav, main { padding-left: 16px; padding-right: 16px; } }
</style>
</head>
<body>
<header>
  <h1>TradingStrategie</h1>
  <span class="sub" id="status"></span>
</header>
<nav>
  <button id="tab-live" role="tab" aria-selected="true">Live (30 dagen)</button>
  <button id="tab-ex" role="tab" aria-selected="false">Voorbeelden uit het verleden</button>
  <span class="spacer"></span>
  <select id="f-mkt" aria-label="Markt"><option value="">Alle markten</option><option>NQ</option><option>EURUSD</option></select>
  <select id="f-kans" aria-label="Soort"><option value="">Kans + lage kans</option><option value="1">Alleen kans</option></select>
</nav>
<div class="err" id="errors"></div>
<main id="main"></main>
<script>
const D = __DATA__;
const $ = s => document.querySelector(s);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
                set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} } };
let tab = store.get("tab") || "live";
$("#f-mkt").value = store.get("mkt") || "";
$("#f-kans").value = store.get("kans") || "";
const fmtTime = t => new Date(t * 1000).toLocaleString("nl-NL", { timeZone: "UTC", weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const fmtDate = t => new Date(t * 1000).toLocaleDateString("nl-NL", { timeZone: "UTC", day: "2-digit", month: "short", year: "numeric" });
const px = (c, v) => Number(v).toFixed(c.dec);
const R = v => (v > 0 ? "+" : "") + v.toFixed(2) + "R";

$("#status").textContent = "Bijgewerkt " + D.updated + " (NL-tijd)" + (D.refresh ? " · ververst elke " + D.refresh / 60 + " min" : "") +
  " · data ~10 min vertraagd · tijden in grafieken: NL";
if (D.errors.length) $("#errors").textContent = "Geen data voor: " + D.errors.join("; ");

function resultBadge(c) {
  if (c.result === "geen entry") return '<span class="res flat">&#8211; geen entry</span>';
  if (c.result === "loopt nog") return '<span class="res flat">&#9711; loopt nog</span>';
  const cls = c.R > 0.05 ? "win" : c.R < -0.05 ? "loss" : "flat";
  const icon = cls === "win" ? "&#10003;" : cls === "loss" ? "&#10005;" : "&#8776;";
  return `<span class="res ${cls}">${icon} ${c.result} ${R(c.R)}</span>`;
}

function cardHtml(c, i) {
  const checks = c.checks.map(([k, v]) => `<span class="${v ? "" : "off"}">${v ? "&#10003;" : "&#9675;"} ${k}</span>`).join("");
  return `<article class="card">
    <div class="head">
      <span class="title">${c.mkt} ${c.side}</span>
      <span class="chip">${c.good ? "kans" : "lage kans"}</span>
      <span class="chip">${c.grade} · ${c.score}/10</span>
      <span class="chip">${c.sess}</span>
      ${resultBadge(c)}
    </div>
    <div class="chart" id="ch-${i}"></div>
    <div class="meta">
      ${fmtTime(c.time)} · sweep <b>${c.sweep}</b><br>
      Entry <b>${px(c, c.entry)}</b> · Stop <b>${px(c, c.stop)}</b> · TP <b>${px(c, c.tp)}</b> (${c.rr.toFixed(1)}R)
      <details><summary>Checklist</summary><div class="checks">${checks}</div></details>
    </div>
  </article>`;
}

function chartOpts(el) {
  return { width: el.clientWidth, height: el.clientHeight,
    layout: { background: { color: css("--surface-1") }, textColor: css("--text-secondary"), fontSize: 11 },
    grid: { vertLines: { color: css("--grid") }, horzLines: { color: css("--grid") } },
    rightPriceScale: { borderColor: css("--border") },
    timeScale: { borderColor: css("--border"), timeVisible: true, secondsVisible: false },
    crosshair: { mode: 0 }, handleScroll: false, handleScale: false };
}

function nearestBar(cs, t) {
  if (t == null || !cs.length) return null;
  let best = cs[0].time;
  for (const b of cs) { if (b.time <= t) best = b.time; else break; }
  return best;
}

function drawSetup(c, el) {
  const chart = LightweightCharts.createChart(el, chartOpts(el));
  const s = chart.addCandlestickSeries({
    upColor: css("--candle-up"), downColor: css("--candle-down"), borderVisible: false,
    wickUpColor: css("--candle-up"), wickDownColor: css("--candle-down"),
    priceFormat: { type: "price", precision: c.dec, minMove: Math.pow(10, -c.dec) } });
  s.setData(c.candles);
  const line = (price, color, title, style) => s.createPriceLine({ price, color, lineWidth: 2, lineStyle: style, axisLabelVisible: true, title });
  line(c.entry, css("--entry"), "Entry", 0);
  line(c.stop, css("--critical"), "Stop", 2);
  line(c.tp, css("--good"), "TP", 2);
  const up = c.side === "LONG";
  const marks = [
    { time: nearestBar(c.candles, c.sweep_t), position: up ? "belowBar" : "aboveBar", color: css("--text-secondary"), shape: up ? "arrowUp" : "arrowDown", text: "Sweep" },
    { time: nearestBar(c.candles, c.mss_t), position: up ? "aboveBar" : "belowBar", color: css("--text-secondary"), shape: "circle", text: "MSS" },
  ];
  if (c.entry_t) marks.push({ time: nearestBar(c.candles, c.entry_t), position: up ? "belowBar" : "aboveBar", color: css("--entry"), shape: "circle", text: "In" });
  if (c.exit_t && c.result !== "loopt nog") marks.push({ time: nearestBar(c.candles, c.exit_t), position: "aboveBar",
    color: c.R > 0 ? css("--good") : c.R < 0 ? css("--critical") : css("--text-secondary"), shape: "square", text: "Uit" });
  s.setMarkers(marks.filter(m => m.time != null).sort((a, b) => a.time - b.time));
  chart.timeScale().fitContent();
  new ResizeObserver(() => { chart.applyOptions({ width: el.clientWidth }); chart.timeScale().fitContent(); }).observe(el);
}

function drawEquity(trades, el) {
  const chart = LightweightCharts.createChart(el, { ...chartOpts(el), handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false }, handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: true }, crosshair: { mode: 1 } });
  const s = chart.addLineSeries({ color: css("--entry"), lineWidth: 2, priceFormat: { type: "custom", formatter: v => R(v) } });
  let cum = 0, last = 0;
  const pts = trades.map(t => { cum += t.R; const time = Math.max(t.t, last + 1); last = time; return { time, value: +cum.toFixed(2) }; });
  s.setData(pts);
  s.createPriceLine({ price: 0, color: css("--text-muted"), lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: "" });
  chart.timeScale().fitContent();
  new ResizeObserver(() => { chart.applyOptions({ width: el.clientWidth }); chart.timeScale().fitContent(); }).observe(el);
}

function stats(list) {
  const done = list.filter(c => c.result !== "geen entry" && c.result !== "loopt nog");
  const wins = done.filter(c => c.R > 0).length;
  const tot = done.reduce((a, c) => a + c.R, 0);
  return { n: done.length, win: done.length ? Math.round(100 * wins / done.length) : 0, tot };
}

function kpi(v, l) { return `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`; }
const legend = `<div class="legend"><span><i style="border-color:var(--entry)"></i>Entry</span>
  <span><i style="border-color:var(--critical);border-top-style:dashed"></i>Stop</span>
  <span><i style="border-color:var(--good);border-top-style:dashed"></i>TP</span>
  <span>&#9650; Sweep · &#9679; MSS · In = entry geraakt · Uit = exit</span></div>`;

function filtered(list) {
  const m = $("#f-mkt").value, k = $("#f-kans").value;
  return list.filter(c => (!m || c.mkt === m) && (!k || c.good));
}

function renderLive() {
  const list = filtered(D.live);
  const isToday = c => new Date(c.time * 1000).toISOString().slice(0, 10) === D.today;
  const kans = list.filter(c => c.good), st = stats(kans);
  $("#main").innerHTML = `<div class="kpis">
      ${kpi(list.filter(isToday).length, "Setups vandaag")}
      ${kpi(kans.length, "Kans-setups (30 dagen)")}
      ${kpi(st.n, "Kans-trades met entry")}
      ${kpi(st.n ? st.win + "%" : "-", "Winrate kans-trades")}
      ${kpi(st.n ? R(st.tot) : "-", "Resultaat kans-trades (zonder kosten)")}
    </div>${legend}
    ${list.length ? '<div class="grid">' + list.map(cardHtml).join("") + "</div>" : '<div class="empty">Geen setups met deze filters.</div>'}`;
  list.forEach((c, i) => drawSetup(c, document.getElementById("ch-" + i)));
}

function renderExamples() {
  const E = D.examples, m = $("#f-mkt").value;
  const trades = E.trades.filter(t => !m || t.mkt === m);
  const wins = trades.filter(t => t.R > 0).length, tot = trades.reduce((a, t) => a + t.R, 0);
  let cum = 0, peak = 0, dd = 0; trades.forEach(t => { cum += t.R; peak = Math.max(peak, cum); dd = Math.max(dd, peak - cum); });
  const ex = filtered(E.examples);
  $("#main").innerHTML = `<div class="kpis">
      ${kpi(trades.length, "Kans-trades in de backtest")}
      ${kpi(trades.length ? Math.round(100 * wins / trades.length) + "%" : "-", "Winrate")}
      ${kpi(R(tot), "Totaal (na kosten)")}
      ${kpi(dd.toFixed(1) + "R", "Grootste daling")}
    </div>
    <div class="panel"><h2>Winstcurve: opgeteld resultaat van alle kans-trades</h2>
      <div class="sub">${trades.length ? fmtDate(trades[0].t) + " t/m " + fmtDate(trades[trades.length - 1].t) : ""} · in R (1R = je risico per trade) · sleep om te verschuiven, beweeg erover voor de waarde</div>
      <div class="chart" id="equity" style="height:240px;margin-top:8px"></div></div>
    <div class="panel"><h2>Voorbeelden</h2><div class="sub">De beste winnaars (één per maand per markt) en ook een paar verliezers, want die horen erbij.</div></div>
    ${legend}
    <div class="grid">${ex.map(cardHtml).join("")}</div>`;
  drawEquity(trades, document.getElementById("equity"));
  ex.forEach((c, i) => drawSetup(c, document.getElementById("ch-" + i)));
}

function render() {
  $("#tab-live").setAttribute("aria-selected", tab === "live");
  $("#tab-ex").setAttribute("aria-selected", tab === "ex");
  if (typeof LightweightCharts === "undefined") { $("#main").innerHTML = '<div class="empty">Grafiekbibliotheek kon niet laden (geen internet?).</div>'; return; }
  tab === "live" ? renderLive() : renderExamples();
}
$("#tab-live").onclick = () => { tab = "live"; store.set("tab", tab); render(); };
$("#tab-ex").onclick = () => { tab = "ex"; store.set("tab", tab); render(); };
$("#f-mkt").onchange = e => { store.set("mkt", e.target.value); render(); };
$("#f-kans").onchange = e => { store.set("kans", e.target.value); render(); };
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="één keer maken, niet verversen")
    ap.add_argument("--rebuild", action="store_true", help="voorbeelden opnieuw berekenen")
    args = ap.parse_args()
    make(args.rebuild, auto_refresh=not args.once)
    if sys.platform == "darwin":
        subprocess.run(["open", str(OUT)], check=False)
    if not args.once:
        print(f"Dashboard draait, ververst elke {REFRESH_SEC // 60} minuten | stoppen: Ctrl+C", flush=True)
        while True:
            time.sleep(REFRESH_SEC)
            try:
                make()
            except Exception as ex:  # netwerk even weg: volgende keer opnieuw
                print("Fout:", ex, flush=True)
