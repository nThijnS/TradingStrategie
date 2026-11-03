"""
Onderzoek (fase 3-5): extra markten en strategieën, met een vooraf vastgelegd, strikt chronologisch testprotocol.

PROTOCOL (vastgelegd vóór het draaien; niet aanpassen na het zien van de eindtest)
  Perioden (gelijk voor alle markten):
    1h-data (Yahoo, ~730 dagen)   train < 2025-11-01 ≤ validatie < 2026-05-01 ≤ EINDTEST
    dagdata (Yahoo, vanaf 2010)   train < 2023-01-01 ≤ validatie < 2026-05-01 ≤ EINDTEST
    1m-data (HistData, NQ/ES)     train < 2025-11-01 ≤ validatie < 2026-05-01 ≤ EINDTEST (t/m 23 okt 2026)
  De eindtest wordt pas gebruikt NADAT alle keuzes vastliggen, en alleen om ze te rapporteren.

  Selectiepoort (alleen train + validatie), alle vijf nodig:
    P1  minstens 30 trades in de validatie
    P2  validatie: gemiddelde R bij 1,5x kosten > 0 én block-bootstrap 95%-ondergrens (eenzijdig) > 0
    P3  train: gemiddelde R > 0 (zelfde richting in beide perioden)
    P4  Deflated Sharpe Ratio (train+validatie, gecorrigeerd voor ALLE geprobeerde varianten) ≥ 0,95
    P5  validatie zonder de 5 beste trades nog > 0 (niet afhankelijk van een paar uitschieters)
  Wie slaagt: "papertrade/demo". Live vraagt daarnaast een positieve eindtest én ≥ 3 maanden demo.

  Voor/na-vergelijking op dezelfde eindtest:
    VOOR  het bestaande lab-protocol (strategielab.choose: beste walk-forward-ondergrens), alleen data vóór de eindtest
    NA    de selectiepoort hierboven; geen strategie geslaagd = "geen trade" (0R)

KOSTEN (aannames; per instrument te verifiëren met capital_instrumenten.py)
  spread+commissie: de bestaande lab-kosten (deel van de prijs) per markt, kandidaten zie CANDIDATES
  slippage: 0,02R per trade extra; financiering: per nacht (rollover 17:00 NY) rente/365 x positiewaarde,
  6,5%/jaar indices/grondstoffen/aandelen, 2%/jaar forex, 20%/jaar crypto (bewust ruim; long én short).
  Stop en doel in dezelfde candle: stop eerst (conservatief). Instap op de open van de volgende candle.

    python onderzoek.py            # (= python -m research.protocol) alles; schrijft rapport/onderzoek.json en rapport/2_onderzoek.md
"""
import json
from datetime import datetime

import numpy as np
import pandas as pd

import strategies.lab as strat
from backtesting import engine
from backtesting.metrics import block_bootstrap, deflated_sharpe, lab_stats, pbo_cscv, sharpe  # noqa: F401
from core.data import clean, fetch_all, load_histdata
from core.markets import CANDIDATES, FINANCING, LAB_MARKETS
from research import registry, validation
from research.validation import gate  # noqa: F401
from storage import paths
from strategies.classic import daily_X, donchian_signals, orb_signals, tsmom_signals

OUT = paths.REPORTS
VAL_1H, HOLD = pd.Timestamp("2025-11-01", tz="UTC"), pd.Timestamp("2026-05-01", tz="UTC")
VAL_1D = pd.Timestamp("2023-01-01", tz="UTC")
COST_X = 1.5
SLIP_R = 0.02
FIN = FINANCING                                # rest 0,065
RISK_PCT = 0.5                                 # om R naar % accountrendement te vertalen (benchmark)
ALL = LAB_MARKETS + CANDIDATES
TRIALS = []                                    # elke geprobeerde variant (voor DSR en de telling)


def fin_rate(m):
    return FIN.get(m["soort"], 0.065)


# ------------- Data en datakwaliteit -------------
def fetch(markets, interval, period):
    return fetch_all(markets, interval, period)


def quality(df, interval):
    """Datakwaliteit: dekking, dubbele/ongeldige candles, platte candles, sprongen (o.a. future-rollover)."""
    d, q = clean(df)
    if len(d) < 50:
        return d, dict(q, ok=False, reden="te weinig data")
    r = np.log(d["Close"]).diff()
    gap_ret = np.log(d["Open"] / d["Close"].shift())
    atr = (d["High"] - d["Low"]).rolling(50).median()
    jumps = int(((gap_ret.abs() * d["Close"]) > 8 * atr).sum())
    flat = float((d["High"] == d["Low"]).mean())
    days = d.index.normalize().unique()
    q.update(dagen=len(days), platte_candles=round(flat, 3), sprongen=jumps, ok=True)
    if interval == "1h":
        per_day = d.groupby(d.index.normalize()).size()
        q["candles_per_dag_mediaan"] = float(per_day.median())
        if flat > 0.05:
            q.update(ok=False, reden=f"{flat:.0%} platte candles (geen echte koers)")
        if len(days) < 400:
            q.update(ok=False, reden=f"maar {len(days)} handelsdagen")
    return d, q


# ------------- Simulatie (backtesting/engine.py) -------------
def _trade_dict(i, tr, cost_x=COST_X):
    return dict(t=tr.entry_time, uit=tr.exit_time, bars=tr.exit_i - i, side=tr.side, bruto=tr.gross_r, kosten_r=tr.cost_r,
                fin_r=tr.fin_r, rr=abs(tr.tp - tr.entry) / tr.risk if tr.tp is not None else 0.0,
                R=tr.net_r, R15=tr.gross_r - cost_x * tr.cost_r - tr.fin_r - tr.slip_r)


def simulate(X, up, dn, stopd, target, cost_frac, fin, max_bars, exit_long=None, exit_short=None, rollover_h=22):
    """Instap op de open van de volgende candle; stop/doel op high/low (stop eerst). Geeft trades met R bruto en netto.
    exit_long/short: optionele kanaal-uitstap (bool-reeks, uitstap op de open van de volgende candle)."""
    costs = engine.Costs(frac=cost_frac, financing=fin, slippage_r=SLIP_R, rollover_hour_utc=rollover_h)
    exits = engine.Exits(max_bars=max_bars, gap_hours=strat.GAP_HOURS if max_bars <= 48 else None)
    return [_trade_dict(i, tr) for i, tr in strat.run_signals(X, up, dn, stopd, target, costs, exits, exit_long, exit_short)]


def rollovers(a, b, hour_utc):
    """Aantal keer dat de positie over het dagelijkse rollmoment (17:00 NY ≈ 22:00 UTC) heen ging."""
    return engine.rollovers(a, b, hour_utc)


# ------------- Strategieën -------------
def lab_variants():
    """De bestaande lab-strategieën (1h) met hun twee varianten, ongewijzigd."""
    for sid, info in strat.STRATS.items():
        if sid == "ict":
            continue
        for v in info["varianten"]:
            yield sid, v


def run_lab(X, m, sid, v):
    up, dn, stopd, target = strat.signals(sid, X, v)
    return simulate(X, up, dn, stopd, target, m["kosten"], fin_rate(m), strat.MAX_BARS)


def donchian(X, m, n_in=55, n_out=20, k=2.0):
    """Turtle-achtige breakout (zie strategies/classic.py); uitstap op het tegenoverliggende kanaal."""
    up, dn, stopd, ex_l, ex_s = donchian_signals(X, n_in, n_out, k)
    return simulate(X, up, dn, stopd, None, m["kosten"], fin_rate(m), 400, ex_l, ex_s)


def tsmom(X, m, horizons=(21, 63, 252), k=3.0):
    """Time-series momentum (zie strategies/classic.py); uitstap als de richting bij de maandwissel omdraait."""
    up, dn, stopd, ex_l, ex_s = tsmom_signals(X, horizons, k)
    return simulate(X, up, dn, stopd, None, m["kosten"], fin_rate(m), 400, ex_l, ex_s)


def orb(sym, minutes=30, tp=2.0, last_entry="11:30", cost_pts=2.5):
    """Opening-range-breakout NQ/ES op HistData 1m (zomertijd-correct), zie strategies/classic.orb_signals.
    Instap op de open na het signaal, stop aan de overkant van de range, doel tp x R, anders dicht om 15:55."""
    d5 = load_histdata(sym).tz_convert("America/New_York")
    d5 = d5.resample("5min", label="left", closed="left").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    B = engine.Bars(d5)
    costs = engine.Costs(price=cost_pts, slippage_r=SLIP_R)
    exits = engine.Exits(close_at="15:55")
    out = []
    for sig in orb_signals(d5, minutes, tp, last_entry):
        start = B.index_at(sig.fill_from)
        tr = engine.simulate(B, sig.side, sig.entry, sig.stop, sig.tp, start, "MARKET", exits, costs)
        if tr is None:
            continue
        d = _trade_dict(start, tr)
        d.update(t=tr.entry_time.tz_convert("UTC"), uit=tr.exit_time.tz_convert("UTC"), bars=1, rr=tp, fin_r=0.0)
        out.append(d)
    return out


# ------------- Statistiek -------------
def split(trades, val_start):
    return validation.split(trades, val_start, HOLD)


def summary(trades, bench=None):
    if not trades:
        return dict(n=0)
    R = np.array([x["R"] for x in trades])
    G = np.array([x["bruto"] for x in trades])
    wins, losses = R[R > 0], R[R <= 0]
    eq = np.cumsum(R)
    dd = float(-(eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]).min())
    top = np.sort(R)[::-1]
    s = dict(n=len(R), gem_R=round(float(R.mean()), 3), bruto_gem_R=round(float(G.mean()), 3),
             gem_R_kosten15=round(float(np.mean([x["R15"] for x in trades])), 3), netto_R=round(float(R.sum()), 1),
             win=round(float((R > 0).mean()), 3), gem_winst=round(float(wins.mean()), 2) if len(wins) else 0.0,
             gem_verlies=round(float(losses.mean()), 2) if len(losses) else 0.0,
             pf=round(float(wins.sum() / -losses.sum()), 2) if losses.sum() < 0 else None, max_dd_R=round(dd, 1),
             zonder_top5=round(float(top[5:].mean()), 3) if len(top) > 10 else None,
             rendement_pct=round(float(R.sum()) * RISK_PCT, 1))
    ci = block_bootstrap(trades)
    if ci:
        s["ci95"], s["ondergrens95_eenzijdig"] = [round(ci[0], 3), round(ci[2], 3)], round(ci[1], 3)
    if bench is not None:
        s["kopen_houden_pct"] = bench
    return s


def bench(d, a, b):
    c = d["Close"][(d.index >= a) & (d.index < b)]
    return round(float((c.iloc[-1] / c.iloc[0] - 1) * 100), 1) if len(c) > 1 else None


def exposure(trades, d, a, b):
    if not trades:
        return 0.0
    bars = int(((d.index >= a) & (d.index < b)).sum())
    return round(sum(x["bars"] for x in trades) / bars, 3) if bars else 0.0



def run():
    OUT.mkdir(exist_ok=True)
    print("data ophalen…", flush=True)
    h1 = fetch(ALL, "1h", "730d")
    d1 = fetch(ALL, "1d", "max")
    res = dict(gemaakt=datetime.now().isoformat(timespec="minutes"), protocol=dict(
        val_1h=str(VAL_1H.date()), val_1d=str(VAL_1D.date()), eindtest=str(HOLD.date()), kosten_x=COST_X, slippage_R=SLIP_R,
        financiering=dict(FIN, overig=0.065)), markten={}, strategieen=[])

    # Fase 3: datakwaliteit en spreiding
    daily_ret = {}
    clean1h, cleand = {}, {}
    for m in ALL:
        d, q = quality(h1.get(m["naam"], pd.DataFrame()), "1h")
        dd, qd = quality(d1.get(m["naam"], pd.DataFrame()), "1d")
        clean1h[m["naam"]], cleand[m["naam"]] = d, dd
        if len(dd):
            r = np.log(dd["Close"]).diff()
            r.index = pd.DatetimeIndex(dd.index.tz_convert(None) if dd.index.tz is None else dd.index.tz_localize(None)).normalize()
            daily_ret[m["naam"]] = r[~r.index.duplicated(keep="last")]   # kalenderdatum: Europa/Japan sluiten op lokale middernacht
        res["markten"][m["naam"]] = dict(titel=m["titel"], soort=m["soort"], symbool=m["symbool"], kandidaat=m in CANDIDATES,
                                         kosten_aanname=m["kosten"], data_1h=q, data_1d=dict(van=qd.get("van"), dagen=qd.get("dagen"), sprongen=qd.get("sprongen")))
    R = pd.DataFrame(daily_ret)
    R = R[R.index >= pd.Timestamp("2024-11-01")].resample("W-FRI").sum(min_count=1)   # week: Europa/Japan sluiten eerder
    corr = R.corr(min_periods=60)
    existing = [m["naam"] for m in LAB_MARKETS]
    for m in ALL:
        n = m["naam"]
        if n not in corr:
            continue
        others = corr[n].drop(n).dropna()
        ex = others[[o for o in others.index if o in existing]]
        res["markten"][n]["max_corr_bestaand"] = [ex.abs().idxmax(), round(float(ex[ex.abs().idxmax()]), 2)] if len(ex) else None

    # Fase 4/5: alle varianten, per markt
    rows = []
    for m in ALL:
        d = clean1h[m["naam"]]
        if res["markten"][m["naam"]]["data_1h"].get("ok"):
            X = strat.indicators(d)
            for sid, v in lab_variants():
                rows.append((m, f"lab:{sid}", json.dumps(v), run_lab(X, m, sid, v), VAL_1H, d))
            # regimefilter (hypothese: alleen trendstrategieën in een trendmarkt, mean reversion in een zijwaartse)
            for sid, v in lab_variants():
                tr = run_lab(X, m, sid, v)
                want = "Zijwaarts" if sid == "meanrev" else ("Uptrend", "Downtrend")
                keep = [x for x in tr if (X["trend"].asof(x["t"] - pd.Timedelta(hours=1)) in want)]
                rows.append((m, f"lab+regime:{sid}", json.dumps(v), keep, VAL_1H, d))
        dd = cleand[m["naam"]]
        if len(dd) > 1500:
            Xd = daily_X(dd)
            rows.append((m, "donchian", "55/20, 2xATR", donchian(Xd, m), VAL_1D, dd))
            rows.append((m, "tsmom", "21/63/252, 3xATR", tsmom(Xd, m), VAL_1D, dd))
    print("ORB (HistData 1m)…", flush=True)
    for naam, sym, pts in (("NQ", "NSXUSD", 2.5), ("ES", "SPXUSD", 0.75)):
        m = next(x for x in LAB_MARKETS if x["naam"] == naam)
        try:
            for mins, tp in ((30, 2.0), (15, 2.0), (60, 2.0), (30, 1.5), (30, 3.0)):
                rows.append((m, "orb", f"{mins}m, {tp:g}R", orb(sym, mins, tp, cost_pts=pts), VAL_1H, None))
        except Exception as ex:
            print("ORB niet mogelijk:", ex)

    # Deflated Sharpe: N = alle geprobeerde varianten, SR-spreiding over die varianten (train+validatie)
    TRIALS.extend((m["naam"], s, v) for m, s, v, _, _, _ in rows)
    n_eff = len({(m["naam"], s.split(":")[-1]) for m, s, _, _, _, _ in rows})
    res["effectieve_proeven"] = n_eff
    for m, sid, v, trades, vs, d in rows:
        tr, va, ho = split(trades, vs)
        dsr = deflated_sharpe([x["R"] for x in tr + va], n_eff)
        ok, why = gate(tr, va, dsr)
        e = dict(markt=m["naam"], kandidaat=m in CANDIDATES, strategie=sid, variant=v, dsr=round(dsr, 3), geslaagd=ok, redenen=why,
                 train=summary(tr), validatie=summary(va), eindtest=summary(ho, bench(d, HOLD, pd.Timestamp.now(tz="UTC")) if d is not None else None))
        if d is not None:
            e["blootstelling_validatie"] = exposure(va, d, vs, HOLD)
        rows_regime = {}
        for x in tr + va:
            rows_regime.setdefault(str(x["t"].year) + ("H1" if x["t"].month <= 6 else "H2"), []).append(x["R"])
        e["per_halfjaar"] = {k: [len(v_), round(float(np.sum(v_)), 1)] for k, v_ in sorted(rows_regime.items())}
        res["strategieen"].append(e)

    # PBO over alle 1h-lab-varianten van de bestaande markten (de keuze "beste markt x strategie")
    cols = {}
    for m, sid, v, trades, vs, d in rows:
        if sid.startswith("lab:") and m in LAB_MARKETS:
            s = pd.Series([x["R"] for x in trades if x["t"] < HOLD], index=pd.DatetimeIndex([x["t"] for x in trades if x["t"] < HOLD]), dtype=float)
            cols[f"{m['naam']}|{sid}|{v}"] = s.resample("MS").sum()
    M = pd.DataFrame(cols).fillna(0.0)
    res["pbo_lab"] = dict(pbo=pbo_cscv(M.to_numpy(), S=8), varianten=M.shape[1], maanden=M.shape[0])
    res["aantal_varianten"] = len(TRIALS)

    # VOOR/NA op dezelfde eindtest
    voor = before_after(rows, clean1h)
    na = {}
    for e in res["strategieen"]:          # per markt de geslaagde variant met de hoogste validatie-ondergrens
        if e["geslaagd"] and (e["markt"] not in na or e["validatie"].get("ondergrens95_eenzijdig", -9) > na[e["markt"]]["lb"]):
            na[e["markt"]] = dict(strategie=e["strategie"], variant=e["variant"], lb=e["validatie"].get("ondergrens95_eenzijdig", -9),
                                  eindtest=e["eindtest"])
    na_same = {k: v for k, v in na.items() if k in voor}   # zelfde markten als VOOR
    res["voor_na"] = dict(voor=voor, na=na, totaal=dict(voor=totals(voor), na_zelfde_markten=totals(na_same), na_alle=totals(na)))
    (OUT / "onderzoek.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    write_report(json.loads((OUT / "onderzoek.json").read_text()))
    print(f"{len(TRIALS)} varianten; geslaagd: {[(e['markt'], e['strategie'], e['variant']) for e in res['strategieen'] if e['geslaagd']]}")
    print("PBO lab:", res["pbo_lab"])
    print("voor/na:", json.dumps(res["voor_na"]["totaal"], ensure_ascii=False))
    registry.record("onderzoek", params=res["protocol"], results=dict(
        varianten=res["aantal_varianten"], geslaagd=[(e["markt"], e["strategie"], e["variant"]) for e in res["strategieen"] if e["geslaagd"]],
        pbo_lab=res["pbo_lab"], voor_na=res["voor_na"]["totaal"]))


def before_after(rows, clean1h):
    """VOOR: lab-protocol (walk-forward + beste ondergrens) met data tot de eindtest. NA: de selectiepoort."""
    by_market = {}
    for m, sid, v, trades, vs, d in rows:
        if sid.startswith("lab:") and m in LAB_MARKETS:
            by_market.setdefault(m["naam"], {}).setdefault(sid[4:], {})[v] = trades
    voor = {}
    for naam, strats in by_market.items():
        d = clean1h[naam]
        start = d.index[0]
        best, best_lb, best_key = None, None, None
        for sid, by_v in strats.items():
            pre = {k: [dict(x, t=x["t"]) for x in t if x["t"] < HOLD] for k, t in by_v.items()}
            oos, _ = validation.walk_forward(pre, start, HOLD)
            st = lab_stats(oos, full=False) if oos else dict(n=0)
            if st.get("n", 0) >= validation.MIN_OOS and st.get("ondergrens") is not None and (best_lb is None or st["ondergrens"] > best_lb):
                key = validation.current_variant(pre, HOLD) or max(pre, key=lambda k: np.mean([x["R"] for x in pre[k]]) if pre[k] else -9)
                best, best_lb, best_key = sid, st["ondergrens"], key
        if best and best_lb > 0:
            ho = [x for x in strats[best][best_key] if x["t"] >= HOLD]
            voor[naam] = dict(strategie=best, variant=best_key, ondergrens_wf=best_lb, eindtest=summary(ho))
        else:
            voor[naam] = dict(strategie=None, eindtest=dict(n=0))
    return voor


def totals(dct):
    return dict(trades=sum(x["eindtest"].get("n", 0) for x in dct.values()),
                netto_R=round(sum(x["eindtest"].get("netto_R", 0) for x in dct.values()), 1),
                markten_met_trades=sum(1 for x in dct.values() if x["eindtest"].get("n")))


# ------------- Rapport -------------
DECISIONS = {   # fase 3: besluit per kandidaat, op basis van datakwaliteit en spreiding (zie tabel)
    "AUDUSD": ("uitgesteld", "data goed; deels dollar-factor (0,69 met GBP/USD); instrumentgegevens nog niet geverifieerd"),
    "USDCAD": ("uitgesteld", "data goed; vooral dollar-factor (−0,69 met EUR/USD); instrumentgegevens nog niet geverifieerd"),
    "USDCHF": ("afgewezen", "−0,82 met EUR/USD: vrijwel dezelfde weddenschap, geen spreiding"),
    "NZDUSD": ("afgewezen", "0,80 met GBP/USD en een hogere spread: weinig spreiding voor meer kosten"),
    "EURGBP": ("uitgesteld", "beste spreiding van de forexparen (0,36 met EUR/USD); instrumentgegevens nog niet geverifieerd"),
    "EURJPY": ("uitgesteld", "0,65 met USD/JPY; instrumentgegevens nog niet geverifieerd"),
    "US30": ("afgewezen", "0,90 met S&P 500: geen spreiding (de correlatiegroep telt ze toch als één)"),
    "FTSE": ("uitgesteld", "0,73 met DAX; Yahoo geeft alleen de beursuren (9 candles/dag), de CFD handelt bijna de hele dag: databron sluit niet aan"),
    "NIKKEI": ("uitgesteld", "matige samenhang (0,59 met Nasdaq), Aziatische uren; Yahoo-uren (7/dag) sluiten niet aan op de CFD"),
    "CAC": ("afgewezen", "0,86 met DAX: geen spreiding"),
    "BRENT": ("afgewezen", "0,92 met WTI-olie: geen spreiding"),
    "KOPER": ("uitgesteld", "redelijke spreiding (0,50 met zilver); spread en instrument nog niet geverifieerd"),
    "GAS": ("afgewezen", "13 prijssprongen in de Yahoo-future (rollovers): data sluit niet aan op een CFD; hoge kosten"),
}


def fmt(x, nd=2):
    return "–" if x is None else (f"{x:+.{nd}f}" if isinstance(x, (int, float)) else str(x))


def write_report(res):
    S = res["strategieen"]
    L = []
    a = L.append
    a("# Fase 3–5 — Onderzoek markten en strategieën\n")
    a(f"Gemaakt {res['gemaakt']} met `python onderzoek.py` (gegevens: `rapport/onderzoek.json`). "
      "Het protocol staat bovenaan `onderzoek.py` en lag vast voordat de eindtest werd bekeken.\n")
    a("## Kernpunten\n")
    a(f"- **{res['aantal_varianten']} varianten** getest ({res['effectieve_proeven']} markt × strategiefamilie-combinaties). "
      f"**Geen enkele** haalt de selectiepoort (P1–P5). Geen variant faalt alléén op de Deflated Sharpe: elke variant faalt ook op minstens één eenvoudige toets.")
    pbo = res["pbo_lab"]
    a(f"- **PBO (CSCV)** van de lab-keuze \"beste markt × strategie\": **{pbo['pbo']:.0%}** "
      f"({pbo['varianten']} varianten, {pbo['maanden']} maanden). Boven 50% betekent: de in-sample beste is vaker wel dan niet "
      "een slechte keuze voor de periode erna.")
    t = res["voor_na"]["totaal"]
    a(f"- **Voor/na op dezelfde eindtest (vanaf {res['protocol']['eindtest']}):**")
    a(f"  - VOOR (het lab-protocol): {t['voor']['trades']} trades in {t['voor']['markten_met_trades']} markten, netto **{t['voor']['netto_R']:+.1f}R**.")
    a(f"  - NA (de selectiepoort): {t['na_alle']['trades']} trades, **{t['na_alle']['netto_R']:+.1f}R** (\"geen trade\").")
    a("  - Dat \"na\" niet verliest, is geen bewezen verbetering. Het betekent alleen dat er niets wordt gehandeld dat niet bewezen is.\n")
    a("## Voor: wat het lab-protocol koos (alleen data vóór de eindtest) en hoe dat uitpakte\n")
    a("| Markt | Strategie | Variant | WF-ondergrens | Eindtest n | gem. R | netto R | 95%-interval (blokken) |")
    a("|---|---|---|---|---|---|---|---|")
    for k, v in res["voor_na"]["voor"].items():
        if v["strategie"]:
            e = v["eindtest"]
            a(f"| {k} | {v['strategie']} | `{v['variant']}` | {fmt(v['ondergrens_wf'], 3)} | {e.get('n', 0)} | {fmt(e.get('gem_R'), 3)} | {fmt(e.get('netto_R'), 1)} | {e.get('ci95') or '–'} |")
    a("\nDe andere bestaande markten kregen ook in het oude protocol \"geen trade\". ICT is hier buiten beschouwing gelaten; "
      "die wordt apart door `leren.py` gekozen (eerdere toets met zomertijd-correcte data: geen voordeel op NQ/EURUSD in 2026).\n")
    a("## Markten (fase 3)\n")
    a("Bron Yahoo Finance. Dagen = handelsdagen met 1h-data. Sprongen = openingsgaten groter dan 8× de mediane candle "
      "(vaak future-rollovers). Correlatie = weekrendementen sinds nov 2024 (dagrendementen onderschatten de samenhang tussen markten die op verschillende tijden sluiten), hoogste absolute met een bestaande markt.\n")
    a("| Markt | Kandidaat | 1h-dagen | candles/dag | platte candles | sprongen | hoogste correlatie | Besluit |")
    a("|---|---|---|---|---|---|---|---|")
    for k, v in res["markten"].items():
        q = v["data_1h"]
        c = v.get("max_corr_bestaand")
        dec = DECISIONS.get(k, ("bestaand", ""))
        a(f"| {k} ({v['titel']}) | {'ja' if v['kandidaat'] else 'nee'} | {q.get('dagen', '–')} | {q.get('candles_per_dag_mediaan', '–')} | "
          f"{q.get('platte_candles', '–')} | {q.get('sprongen', '–')} | {c[0] + ' ' + fmt(c[1]) if c else '–'} | "
          f"{dec[0]}{': ' + dec[1] if dec[1] else ''} |")
    a("\nGeen enkele kandidaat is toegevoegd. Twee redenen:")
    a("- De instrumentgegevens bij Capital.com (epic, contractgrootte, spread, financiering, uren) zijn nog niet uitgelezen. "
      "Dat doet `capital_instrumenten.py`, met de demo-sleutels in GitHub.")
    a("- Geen strategie haalt op deze markten de poort.\n")
    a("Bestaande markten die sterk samenhangen (NQ–ES 0,95, BTC–ETH 0,82, EUR/USD–GBP/USD 0,82, goud–zilver 0,76, NVDA–NQ 0,71) blijven bestaan. "
      "`risico.py` telt ze voortaan als één groep: max 1 positie per groep en richting.\n")
    a("## Strategieën (fase 4): beste per familie\n")
    a("Per familie de variant met de hoogste validatie-ondergrens. gem. R is netto (kosten, slippage 0,02R en financiering); "
      "×1,5 = met 50% hogere kosten. Interval = block-bootstrap per week, 95%.\n")
    a("| Markt | Strategie | Variant | Train n / gem. R | Validatie n / gem. R / ×1,5 | Val. ondergrens | DSR | Eindtest n / gem. R / interval | Faalt op |")
    a("|---|---|---|---|---|---|---|---|---|")
    fams = {}
    for e in S:
        k = (e["markt"], e["strategie"])
        if k not in fams or (e["validatie"].get("ondergrens95_eenzijdig") or -9) > (fams[k]["validatie"].get("ondergrens95_eenzijdig") or -9):
            fams[k] = e
    best = sorted(fams.values(), key=lambda e: -(e["validatie"].get("ondergrens95_eenzijdig") or -9))
    for e in best[:25] + [x for x in best[25:] if x["strategie"] in ("orb",) or (x["markt"] == "NQ" and x["strategie"] == "lab:trend")]:
        tr, va, ho = e["train"], e["validatie"], e["eindtest"]
        a(f"| {e['markt']} | {e['strategie']} | `{e['variant']}` | {tr.get('n', 0)} / {fmt(tr.get('gem_R'), 3)} | "
          f"{va.get('n', 0)} / {fmt(va.get('gem_R'), 3)} / {fmt(va.get('gem_R_kosten15'), 3)} | {fmt(va.get('ondergrens95_eenzijdig'), 3)} | "
          f"{e['dsr']:.2f} | {ho.get('n', 0)} / {fmt(ho.get('gem_R'), 3)} / {ho.get('ci95') or '–'} | {', '.join(w.split(':')[0] for w in e['redenen'])} |")
    a("\n### Per hypothese\n")
    a("- **Donchian 55/20 en time-series momentum (21/63/252 dagen), dagdata:**")
    a("  - Te weinig trades in de validatie (meestal 6–19 per markt). P1 faalt dus overal.")
    a("  - De resultaten springen per markt alle kanten op.")
    a("  - Er komt financiering per nacht bij.")
    a("  - Deze strategieën houden posities dagen tot weken vast. Dat past niet bij de daytrade-opzet en de prop-regels van de bot.")
    a("  - **Afgewezen voor nu.**")
    a("- **Opening-range-breakout NQ/ES (HistData 1m, zomertijd-correct):**")
    a("  - Alle 10 varianten zijn negatief of rond 0, in train, validatie én eindtest.")
    a("  - **Afgewezen.**")
    a("- **VWAP-pullback:**")
    a("  - Niet getest. Voor forex en CFD's is er geen betrouwbare volumedata, en Yahoo-futures geven maar 60 dagen 5m-data.")
    a("  - **Uitgesteld**, tot er een volumebron is die aansluit op de broker.")
    a("- **Regimefilter op de lab-strategieën** (trendstrategieën alleen in een trendmarkt, mean reversion alleen in een zijwaartse markt):")
    a("  - Haalt ook nergens de poort; meestal te weinig trades.")
    a("  - Behandeld als filter, niet als eigen strategie. **Niet ingevoerd.**")
    a("- **Bestaande lab-strategieën:** geen enkele combinatie slaagt.")
    a("  - Nasdaq 100 trend volgen (op de site: +0,12R, interval −0,08 tot +0,32) was in de validatie (nov 2025 – apr 2026) negatief.")
    a("  - De positieve eindtest daarna heeft maar 24 trades en een interval dat ruim door 0 loopt.\n")
    a("## Beperkingen\n")
    a("- **Data:**")
    a("  - Yahoo 1h gaat ~730 dagen terug, dus de eindtest is maar 6 maanden.")
    a("  - Futures zijn continue contracten met rollovers. Capital.com handelt CFD's met andere uren en prijzen.")
    a("  - Yahoo-futures lopen 10–15 minuten achter.")
    a("- **Kosten:** dit zijn schattingen, niet bij Capital.com geverifieerd.")
    a("  - De spread is per markt vast gekozen.")
    a("  - Financiering is ruim gerekend.")
    a("  - Spreads bij nieuws en 's nachts zijn breder dan hier aangenomen.")
    a("- **Statistiek:**")
    a("  - Voor de DSR is aangenomen dat de proeven onafhankelijk zijn, met N = markt × familie. Varianten hangen samen, dus de echte N ligt lager.")
    a("  - De DSR rekent met de Sharpe per trade.")
    a("  - Het block-bootstrap-interval gebruikt weekblokken.")
    a("  - PBO is berekend op maandsommen.")
    a("- **Overlevingsbias:** de markten zijn vandaag gekozen. Aandelen als NVDA zijn achteraf winnaars, en dat vertekent kopen-en-houden en trendstrategieën.")
    a("- **Eindtest:** die is nu één keer bekeken. Een volgende ronde moet een nieuwe, latere eindtest gebruiken.")
    (OUT / "2_onderzoek.md").write_text("\n".join(L) + "\n")


def main():
    import sys
    if "--rapport" in sys.argv:
        write_report(json.loads((OUT / "onderzoek.json").read_text()))
    else:
        run()


if __name__ == "__main__":
    main()
