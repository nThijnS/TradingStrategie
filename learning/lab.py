"""
Strategielab: vergelijkt per markt verschillende soorten strategieën en kiest er voorzichtig één.

Draait elke dag na de beurs (workflow leren.yml, na leren.py). Plaatst zelf geen orders; de signalen van de gekozen
strategie gaan via live_status.py naar broker.py, dat ze op het DEMO-account neemt (live alleen na opt-in en alleen
voor strategieën die de eigenaar in config.json live.strategieen vrijgeeft).

LET OP (zie rapport/2_onderzoek.md): de keuze hieronder gebruikt de walk-forward-testtrades ook om tussen strategieën
te kiezen. Dat geeft selectiebias; het resultaat "op nieuwe data" is daardoor te rooskleurig. Geschikt voor de
demo-forward-test, niet als bewijs. onderzoek.py toetst met een onaangeroerde eindtest.

1. Haalt per markt ~2 jaar 1-uurs candles op (Yahoo Finance) en controleert de datakwaliteit.
2. Test zes soorten strategieën: ICT (uit het geheugen van leren.py), trend volgen, momentum, mean reversion,
   breakout en volatiliteit (squeeze). Elke soort heeft maar twee varianten, zodat er weinig te "fitten" valt.
3. Walk-forward: kies de beste variant op 240 dagen trainingsdata, test die op de 60 dagen erna (die hij nog
   niet kende), schuif 60 dagen op, enzovoort. Alleen die testtrades tellen als "op nieuwe data".
4. Kiest per markt de strategie met de beste ondergrens (gemiddelde R min 1 standaardfout) op nieuwe data,
   met minstens MIN_OOS trades. Wisselt alleen bij een duidelijk betere (MARGIN), en kiest "geen trade" als
   niets boven 0 komt. Elke keuze komt als versie in lab_versies.json (terugdraaien = vorige versie).
5. Schrijft lab.json (voor het dashboard) en een dagregel in lab_geschiedenis.json.

    python strategielab.py   (= learning/lab.py)
    python strategielab.py --markt BTC   # alleen deze markt (test)
"""
import argparse
import json
from datetime import datetime

import numpy as np
import pandas as pd

from backtesting.metrics import Z, lab_stats as stats  # noqa: F401
from core.data import clean, fetch_all  # noqa: F401
from core.markets import LAB_MARKETS as MARKETS
from core.markets import fin_rate  # noqa: F401
from core.sessions import NY
from research.validation import MIN_OOS, MIN_TRAIN, TEST_D, TRAIN_D, current_variant, walk_forward  # noqa: F401
from storage import jsonstore, paths
from strategies.lab import MAX_BARS, STRATS, indicators, nights, regime_now, signals, simulate, vtxt  # noqa: F401

LAB = paths.LAB
VERSIONS = paths.LAB_VERSIONS
HISTORY = paths.LAB_HISTORY
MEMORY = paths.LEREN_MEMORY     # ICT-uitkomsten van het leren (learning/ict.py)
ICT_MARKETS = ("NQ", "EURUSD", "GOUD")   # alleen daar heeft het leren een geheugen
MARGIN = 0.05       # alleen wisselen als de nieuwe minstens zoveel R per trade beter scoort


def ict_trades(name, X):
    """ICT-trades per variant uit het geheugen van leren.py (R is daar al na kosten)."""
    try:
        from learning import ict as leren
        mem = json.loads(MEMORY.read_text())
    except Exception:
        return {}
    rows = [r for r in mem.values() if r["markt"] == name]
    out = {}
    for v in leren.variants():
        sel = sorted((r for r in rows if r["disp"] == v["disp"] and r["target"] == v["target"]
                      and r["sess"] in leren.SESSIONS[v["sessies"]] and (r["bias_mee"] or not leren.BIAS[v["bias"]])),
                     key=lambda r: r["t"])
        seen, trades = set(), []
        for r in sel:
            if r["t"][:10] in seen:
                continue
            seen.add(r["t"][:10])
            t = pd.Timestamp(r["t"]).tz_convert("UTC")
            k = X.index.searchsorted(t) - 1
            rr = 2.0 if v["target"] == "DOL" else float(v["target"])
            trades.append(dict(t=t, R=r["R"], bruto=None, rr=rr, kant=None,
                               trend=X["trend"].iloc[k] if 0 <= k < len(X) else "onbekend",
                               vol=X["vol"].iloc[k] if 0 <= k < len(X) else "onbekend"))
        out[leren.vid(v)] = trades
    return out



def load(path, default):
    return jsonstore.load(path, default)


# ------------- Per markt -------------
def analyse_market(m, df, versions):
    df, q = clean(df)
    res = dict(naam=m["naam"], titel=m["titel"], soort=m["soort"], symbool=m["symbool"], kosten=m["kosten"], data=q)
    if len(df) < 1500:
        res["fout"] = f"te weinig data ({len(df)} candles)"
        return res, None
    X = indicators(df)
    start, end = X.index[0], X.index[-1]
    res["regime"] = regime_now(df)
    strategies, oos_by = [], {}
    for sid, info in STRATS.items():
        if sid == "ict":
            if m["naam"] not in ICT_MARKETS:
                continue
            by_variant = ict_trades(m["naam"], X)
            if not by_variant:
                continue
        else:
            by_variant = {}
            for v in info["varianten"]:
                up, dn, stopd, target = signals(sid, X, v)
                by_variant[json.dumps(v)] = simulate(X, up, dn, stopd, target, m["kosten"], fin_rate(m))
        hist_key = max(by_variant, key=lambda k: np.mean([x["R"] for x in by_variant[k]]) if len(by_variant[k]) >= MIN_TRAIN else -9)
        oos, picks = walk_forward(by_variant, start, end)
        now_key = current_variant(by_variant, end) or hist_key
        variant = json.loads(now_key) if sid != "ict" else dict(variant=now_key)
        oos_by[sid] = dict(oos=oos, all=by_variant, key=now_key)
        strategies.append(dict(id=sid, titel=info["titel"], uitleg=info["uitleg"], variant=variant, variant_txt=vtxt(sid, variant),
                               varianten_getest=len(by_variant), historisch=stats(by_variant[hist_key], full=False),
                               historisch_variant=vtxt(sid, json.loads(hist_key) if sid != "ict" else dict(variant=hist_key)),
                               nieuw=stats(oos), keuzes_per_periode=picks))
    res["strategieen"] = strategies
    # benchmark: kopen en vasthouden over de testperiode
    t0 = start + pd.Timedelta(days=TRAIN_D)
    c0 = df["Close"][df.index >= t0]
    res["benchmark"] = dict(kopen_houden_pct=round(float((c0.iloc[-1] / c0.iloc[0] - 1) * 100), 1) if len(c0) else None,
                            geen_trade_R=0.0, testperiode=[t0.date().isoformat(), end.date().isoformat()])
    return res, dict(X=X, oos_by=oos_by)


def choose(res, ctx, versions):
    """Kies voorzichtig: beste ondergrens op nieuwe data, met rem op wisselen en 'geen trade' als niets goed is."""
    name, today = res["naam"], datetime.now(NY).date().isoformat()
    hist = versions.setdefault(name, [])
    prev = hist[-1] if hist else None
    ok = [s for s in res["strategieen"] if s["nieuw"].get("n", 0) >= MIN_OOS and s["nieuw"].get("ondergrens") is not None]
    ok.sort(key=lambda s: -s["nieuw"]["ondergrens"])
    best = ok[0] if ok else None
    by_id = {s["id"]: s for s in res["strategieen"]}
    prev_s = by_id.get(prev["strategie"]) if prev and prev.get("strategie") else None
    prev_score = prev_s["nieuw"].get("ondergrens") if prev_s and prev_s["nieuw"].get("n", 0) >= MIN_OOS else None
    rejected = []
    for s in res["strategieen"]:
        if best and s["id"] == best["id"]:
            continue
        h, nw = s["historisch"], s["nieuw"]
        if h.get("n", 0) >= MIN_TRAIN and h.get("expectancy", 0) > 0 and (nw.get("ondergrens") or -1) <= 0:
            rejected.append(dict(strategie=s["titel"], reden=f"op oude data {h['expectancy']:+.2f}R per trade, op nieuwe data {nw.get('expectancy', 0):+.2f}R: houdt geen stand"))
        elif nw.get("n", 0) < MIN_OOS:
            rejected.append(dict(strategie=s["titel"], reden=f"te weinig trades op nieuwe data ({nw.get('n', 0)} < {MIN_OOS})"))
    if best is None or best["nieuw"]["ondergrens"] <= 0:
        pick, why = None, ("geen enkele strategie heeft op nieuwe data een ondergrens boven 0: geen trade"
                           if best else f"nog geen strategie met {MIN_OOS} trades op nieuwe data: geen trade")
    elif prev_s and prev_s["id"] == best["id"]:
        pick, why = best, "de huidige strategie is nog steeds de beste op nieuwe data"
    elif prev_score is not None and prev_score > 0 and best["nieuw"]["ondergrens"] < prev_score + MARGIN:
        pick, why = prev_s, f"{best['titel']} scoort iets beter, maar minder dan {MARGIN}R per trade: niet wisselen"
        rejected.append(dict(strategie=best["titel"], reden=why))
    else:
        pick, why = best, (f"beste ondergrens op nieuwe data ({best['nieuw']['ondergrens']:+.3f}R over {best['nieuw']['n']} trades)"
                           + (f", duidelijk beter dan {prev_s['titel']}" if prev_s else ""))
    entry = dict(sinds=today, strategie=pick["id"] if pick else None, titel=pick["titel"] if pick else "Geen trade",
                 variant=pick["variant"] if pick else None, variant_txt=pick["variant_txt"] if pick else "",
                 ondergrens=pick["nieuw"]["ondergrens"] if pick else None, n=pick["nieuw"]["n"] if pick else 0, reden=why)
    changed = not prev or prev.get("strategie") != entry["strategie"] or prev.get("variant") != entry["variant"]
    if changed:
        hist.append(entry)
    cur = hist[-1]
    # hoe doet de gekozen strategie het sinds de keuze (alleen trades na de keuzedatum: echt nieuwe data)
    since = []
    if cur["strategie"] and cur["strategie"] in ctx["oos_by"]:
        key = json.dumps(cur["variant"]) if cur["strategie"] != "ict" else cur["variant"]["variant"]
        trades = ctx["oos_by"][cur["strategie"]]["all"].get(key, [])
        since = [x for x in trades if x["t"].date().isoformat() >= cur["sinds"]]
    res["keuze"] = dict(cur, reden_vandaag=why, gewisseld=bool(prev) and changed, eerste=not prev)
    res["vorige"] = hist[-2] if len(hist) > 1 else None
    res["sinds_keuze"] = stats(since) if since else dict(n=0)
    res["afgewezen"] = rejected
    res["versies"] = hist[-10:]
    # laatste signalen van de gekozen strategie (papertrades, voor het dashboard)
    res["laatste_signalen"] = []
    if cur["strategie"] and cur["strategie"] != "ict" and cur["strategie"] in ctx["oos_by"]:
        key = json.dumps(cur["variant"])
        for x in ctx["oos_by"][cur["strategie"]]["all"].get(key, [])[-5:]:
            res["laatste_signalen"].append(dict(t=x["t"].isoformat(), kant=x["kant"], entry=round(x["entry"], 6),
                                                stop=round(x["stop"], 6), tp=round(x["tp"], 6), R=round(x["R"], 2)))
    return entry, why, rejected


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--markt", help="alleen deze markt")
    a = ap.parse_args()
    markets = [m for m in MARKETS if not a.markt or m["naam"] == a.markt]
    versions = load(VERSIONS, {})
    data = fetch_all(markets)
    out, day = [], dict(t=datetime.now(NY).isoformat(timespec="minutes"), markten={})
    for m in markets:
        try:
            res, ctx = analyse_market(m, data.get(m["naam"], pd.DataFrame()), versions)
            if ctx:
                entry, why, rejected = choose(res, ctx, versions)
                top = sorted((s for s in res["strategieen"] if s["nieuw"].get("n")), key=lambda s: -(s["nieuw"].get("ondergrens") or -9))
                day["markten"][m["naam"]] = dict(
                    regime=f"{res['regime']['trend']}, {res['regime']['vol'].lower()}", keuze=entry["titel"], variant=entry["variant_txt"],
                    gewisseld=res["keuze"]["gewisseld"], reden=why, afgewezen=rejected,
                    getest=[dict(strategie=s["titel"], varianten=s["varianten_getest"], n=s["nieuw"]["n"],
                                 nieuw=s["nieuw"].get("expectancy"), ondergrens=s["nieuw"].get("ondergrens"),
                                 historisch=s["historisch"].get("expectancy")) for s in top])
        except Exception as ex:   # één markt mag de rest niet tegenhouden
            res = dict(naam=m["naam"], titel=m["titel"], soort=m["soort"], symbool=m["symbool"], fout=f"{type(ex).__name__}: {ex}")
        out.append(res)
        k = res.get("keuze", {})
        print(f"{m['naam']:7} {res.get('fout') or (res['regime']['trend'] + ' / ' + res['regime']['vol']):40} -> {k.get('titel', '-')}: {k.get('reden_vandaag', '')}")
    lab = dict(gemaakt=datetime.now(NY).isoformat(timespec="minutes"), versie=2,
               instellingen=dict(train_dagen=TRAIN_D, test_dagen=TEST_D, min_trades_nieuw=MIN_OOS, wissel_marge=MARGIN,
                                 max_uren_per_trade=MAX_BARS, bron="Yahoo Finance, 1-uurs candles (~2 jaar)"),
               strategieen={k: dict(titel=v["titel"], uitleg=v["uitleg"]) for k, v in STRATS.items()}, markten=out)
    if a.markt:
        jsonstore.save(paths.LAB_TEST, lab, compact=True)
        return
    jsonstore.save(LAB, lab, compact=True)
    jsonstore.save(VERSIONS, versions)
    hist = load(HISTORY, [])
    hist = [h for h in hist if h["t"][:10] != day["t"][:10]] + [day]   # één regel per dag
    jsonstore.save(HISTORY, hist[-180:])


if __name__ == "__main__":
    main()
