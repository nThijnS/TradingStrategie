"""
Strategielab + strategie-selectie: kiest per markt ZELF welke strategie de bot gebruikt, verder onderzoekt of niet.

Draait elke dag na de beurs (workflow leren.yml, na leren.py, dat de ICT-uitkomsten verzamelt). Plaatst zelf geen
orders; de signalen van een ACTIEVE strategie gaan via live_status.py naar broker.py (demo; live alleen na opt-in en
alleen voor strategieën die de eigenaar in config.json live.strategieen vrijgeeft).

1. Haalt per markt ~2 jaar 1-uurs candles op (Yahoo Finance) en controleert de datakwaliteit.
2. Kandidaten per markt: ICT (alle 48 varianten, uitkomsten uit het leergeheugen; alleen NQ, EURUSD, GOUD), trend
   volgen, momentum, mean reversion, breakout en volatiliteit (elk 2 varianten). ICT is één familie, geen standaard.
3. Selectie (learning/selector.py): variant per familie gekozen op train, poort P1-P5 op de laatste 180 dagen
   (genoeg data, kosten 1,5x, bootstrap-ondergrens, Deflated Sharpe voor alle geprobeerde varianten, niet afhankelijk
   van uitschieters), uitschakelen na slechte nieuwe uitkomsten, rem op wisselen.
   Status per markt: actief / onderzoek (gevolgd zonder orders) / pauze.
4. Schrijft lab.json (dashboard), lab_versies.json (elke wissel), lab_geschiedenis.json (dagregel), learned.json
   (ICT staat alleen aan op een markt waar ICT de actieve keuze is) en journaal/Huidige strategie.md.

    python strategielab.py   (= learning/lab.py)
    python strategielab.py --markt BTC   # alleen deze markt (test, schrijft alleen lab_test.json)
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
from learning import selector
from storage import jsonstore, paths
from strategies.lab import MAX_BARS, STRATS, indicators, nights, regime_now, signals, simulate, vtxt  # noqa: F401

LAB = paths.LAB
VERSIONS = paths.LAB_VERSIONS
HISTORY = paths.LAB_HISTORY
MEMORY = paths.LEREN_MEMORY     # ICT-uitkomsten van het leren (learning/ict.py)
ICT_MARKETS = ("NQ", "EURUSD", "GOUD")   # alleen daar heeft het leren een geheugen
MARGIN = selector.MARGIN
COST_X = selector.COST_X


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
            c = r.get("kosten_r")
            trades.append(dict(t=t, R=r["R"], R15=r["R"] - (COST_X - 1) * c if c is not None else r["R"], kosten_bekend=c is not None,
                               bruto=None, rr=rr, kant=None,
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
    strategies, by_family = [], {}
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
                trades = simulate(X, up, dn, stopd, target, m["kosten"], fin_rate(m))
                for x in trades:   # R bij 1,5x spread/commissie (voor de poort)
                    x["R15"] = x["R"] - (COST_X - 1) * m["kosten"] * x["entry"] / abs(x["entry"] - x["stop"])
                by_variant[json.dumps(v)] = trades
        by_family[sid] = by_variant
    cut = end - pd.Timedelta(days=selector.VAL_DAYS)
    trials = max(2, sum(len(v) for v in by_family.values()))
    for sid, by_variant in by_family.items():
        info = STRATS[sid]
        hist_key = max(by_variant, key=lambda k: np.mean([x["R"] for x in by_variant[k]]) if len(by_variant[k]) >= MIN_TRAIN else -9)
        _, picks = walk_forward(by_variant, start, end)
        key = selector.pick_variant(by_variant, cut) or hist_key
        variant = json.loads(key) if sid != "ict" else dict(variant=key)
        tr = [x for x in by_variant[key] if x["t"] < cut]
        va = [x for x in by_variant[key] if x["t"] >= cut]
        strategies.append(dict(id=sid, titel=info["titel"], uitleg=info["uitleg"], variant=variant, variant_txt=vtxt(sid, variant),
                               varianten_getest=len(by_variant), historisch=stats(by_variant[hist_key], full=False),
                               historisch_variant=vtxt(sid, json.loads(hist_key) if sid != "ict" else dict(variant=hist_key)),
                               train=stats(tr, full=False), nieuw=stats(va), keuzes_per_periode=picks))
    res["strategieen"] = strategies
    # benchmark: kopen en vasthouden over de testperiode
    t0 = start + pd.Timedelta(days=TRAIN_D)
    c0 = df["Close"][df.index >= t0]
    res["benchmark"] = dict(kopen_houden_pct=round(float((c0.iloc[-1] / c0.iloc[0] - 1) * 100), 1) if len(c0) else None,
                            geen_trade_R=0.0, testperiode=[t0.date().isoformat(), end.date().isoformat()])
    res["selectie_periode"] = dict(train_tot=cut.isoformat(), validatie_van=cut.isoformat(), validatie_dagen=selector.VAL_DAYS,
                                   varianten_geprobeerd=trials)
    return res, dict(X=X, by=by_family, cut=cut, trials=trials)


def _variant_key(sid, variant):
    if sid is None or variant is None:
        return None
    return variant["variant"] if sid == "ict" else json.dumps(variant)


def _prev(entry):
    """Vorige keuze in het formaat van de selector (ook voor versies van vóór de selector)."""
    if not entry:
        return None
    p = dict(entry)
    p.setdefault("status", "actief" if entry.get("strategie") else "pauze")
    p.setdefault("variant_key", _variant_key(entry.get("strategie"), entry.get("variant")))
    return p


def choose(res, ctx, versions, now=None):
    """Per markt zelf kiezen tussen alle strategiefamilies (ICT is er één van): actief, onderzoek of pauze.
    Zie learning/selector.py voor de poort en de regels."""
    now = now or selector.now_ny()
    name = res["naam"]
    hist = versions.setdefault(name, [])
    prev = _prev(hist[-1] if hist else None)
    by = ctx["by"]
    fams = [selector.evaluate_family(name, sid, by[sid], ctx["cut"], ctx["trials"],
                                     keep=prev["variant_key"] if prev and prev.get("strategie") == sid else None)
            for sid in by]
    d = selector.decide(name, fams, prev, now, lambda sid, key: by.get(sid, {}).get(key, []))
    by_id = {s["id"]: s for s in res["strategieen"]}
    for f in fams:
        if f["id"] in by_id:
            by_id[f["id"]]["poort"] = f["poort"]
            by_id[f["id"]]["poort_variant"] = vtxt(f["id"], json.loads(f["variant"]) if f["id"] != "ict" else dict(variant=f["variant"])) \
                if f["variant"] else None
    sid, key = d["strategie"], d["variant_key"]
    variant = (json.loads(key) if sid != "ict" else dict(variant=key)) if sid else None
    rs = d["onderzoek"]
    if d["status"] == "actief":
        titel = STRATS[sid]["titel"]
    elif d["status"] == "onderzoek":
        titel = f"Onderzoek: {STRATS[rs['strategie']]['titel']} (geen orders)"
    else:
        titel = "Geen trade"
    entry = dict(sinds=d["sinds"], status=d["status"], strategie=sid, titel=titel, variant=variant, variant_key=key,
                 variant_txt=vtxt(sid, variant) if sid else "", ondergrens=d["poort"]["ondergrens"] if d["poort"] else None,
                 n=d["poort"]["validatie"]["n"] if d["poort"] else 0, reden=d["reden"], geblokkeerd=d["geblokkeerd"],
                 onderzoek=dict(strategie=rs["strategie"], titel=STRATS[rs["strategie"]]["titel"],
                                variant_txt=vtxt(rs["strategie"], json.loads(rs["variant_key"]) if rs["strategie"] != "ict"
                                                 else dict(variant=rs["variant_key"])),
                                redenen=rs["poort"]["redenen"]) if rs else None)
    changed = not prev or any(prev.get(k) != entry.get(k) for k in ("status", "strategie", "variant_key", "geblokkeerd")) or \
        ((prev.get("onderzoek") or {}).get("strategie") != (entry["onderzoek"] or {}).get("strategie"))
    if changed:
        hist.append(entry)
    else:
        hist[-1] = dict(hist[-1], **{k: entry[k] for k in ("ondergrens", "n", "reden")})
    cur = hist[-1]
    since = [x for x in by.get(sid, {}).get(key, []) if x["t"].date().isoformat() >= cur["sinds"]] if sid else []
    rejected = [dict(strategie=STRATS[f["id"]]["titel"], reden="; ".join(f["poort"]["redenen"]))
                for f in fams if not f["poort"]["geslaagd"]]
    res["keuze"] = dict(cur, reden_vandaag=d["reden"], gewisseld=bool(prev) and changed, eerste=not prev)
    res["vorige"] = hist[-2] if len(hist) > 1 else None
    res["sinds_keuze"] = stats(since) if since else dict(n=0)
    res["afgewezen"] = rejected
    res["versies"] = hist[-10:]
    res["laatste_signalen"] = []
    if sid and sid != "ict":
        for x in by[sid].get(key, [])[-5:]:
            res["laatste_signalen"].append(dict(t=x["t"].isoformat(), kant=x["kant"], entry=round(x["entry"], 6),
                                                stop=round(x["stop"], 6), tp=round(x["tp"], 6), R=round(x["R"], 2)))
    return entry, d["reden"], rejected


def write_learned(results, now=None):
    """learned.json (de ICT-app leest dit elke minuut) uit de keuze per markt: ICT staat alleen aan op een markt
    waar de selector ICT als actieve strategie koos. Anders logt de app de ICT-setups wel, maar meldt en handelt niet."""
    from learning import ict as leren
    now = now or selector.now_ny()
    old = (load(paths.LEARNED, {}) or {}).get("markten", {})
    choice = {}
    for res in results:
        name = res.get("naam")
        if name not in ICT_MARKETS or "keuze" not in res:
            if name in old:
                choice[name] = None
            continue
        k = res["keuze"]
        ict = next((s for s in res.get("strategieen", []) if s["id"] == "ict"), None)
        on = k.get("status") == "actief" and k.get("strategie") == "ict"
        vtext = k["variant_key"] if on else (ict["variant"]["variant"] if ict else old.get(name, {}).get("variant"))
        if not vtext:
            continue
        g = (ict or {}).get("poort") or {}
        sc = dict(n=g.get("validatie", {}).get("n", 0), gem=g.get("validatie", {}).get("gem", 0.0),
                  score=g.get("ondergrens") if g.get("ondergrens") is not None else -9.0,
                  win=g.get("validatie", {}).get("win", 0.0), totaal=g.get("validatie", {}).get("totaal", 0.0))
        choice[name] = dict(variant=leren._parse(vtext), actief=on, score=sc,
                            sinds=k["sinds"] if on else (old.get(name, {}).get("sinds") or now.date().isoformat()))
    app = leren.to_app({n: c for n, c in choice.items() if c})
    for name, c in old.items():          # markten die het lab vandaag niet kon doorrekenen: vorige keuze, maar uit
        if name not in app["markten"] and choice.get(name, 0) is not None:
            app["markten"][name] = dict(c, actief=False)
    for name, res in ((r.get("naam"), r) for r in results):
        if name in app["markten"] and "keuze" in res:
            app["markten"][name]["selectie"] = dict(status=res["keuze"]["status"], strategie=res["keuze"]["strategie"],
                                                    reden=res["keuze"]["reden_vandaag"])
    jsonstore.save(paths.LEARNED, app)
    hist = load(paths.LEREN_HISTORY, [])
    hist.append(dict(t=now.isoformat(timespec="minutes"), keuze={n: dict(variant=c["variant"], actief=c["actief"], score=c["score"])
                                                               for n, c in app["markten"].items()}))
    jsonstore.save(paths.LEREN_HISTORY, hist[-400:])
    return app


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
               instellingen=dict(train_dagen=TRAIN_D, test_dagen=TEST_D, min_trades_nieuw=selector.MIN_VAL, wissel_marge=selector.MARGIN,
                                 validatie_dagen=selector.VAL_DAYS, min_train=selector.MIN_TRAIN, dsr_min=selector.DSR_MIN,
                                 kosten_x=selector.COST_X, nieuwe_trades_min=selector.FWD_MIN, afkoeldagen=selector.COOLDOWN_DAYS,
                                 max_uren_per_trade=MAX_BARS, bron="Yahoo Finance, 1-uurs candles (~2 jaar)"),
               strategieen={k: dict(titel=v["titel"], uitleg=v["uitleg"]) for k, v in STRATS.items()}, markten=out)
    if a.markt:
        jsonstore.save(paths.LAB_TEST, lab, compact=True)
        return
    jsonstore.save(LAB, lab, compact=True)
    jsonstore.save(VERSIONS, versions)
    write_learned(out)
    from learning.journal import write_selection
    write_selection(out)
    hist = load(HISTORY, [])
    hist = [h for h in hist if h["t"][:10] != day["t"][:10]] + [day]   # één regel per dag
    jsonstore.save(HISTORY, hist[-180:])


if __name__ == "__main__":
    main()
