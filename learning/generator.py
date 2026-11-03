"""Kandidaat-generator: het systeem stelt zelf nieuwe varianten van bestaande strategieën voor en toetst ze.

Hoe een nieuwe kandidaat ontstaat, getoetst wordt en eventueel actief wordt
  1. Maken (dagelijks, per markt en strategiefamilie): uitgaand van de variant die op TRAIN het best is (de ouder),
     stelt de generator buren voor: één instelling één stap omhoog of omlaag in een vast raster (SPACE), bijvoorbeeld
     doel 2R -> 2,5R of stop 1,5 -> 2 x ATR. Hoogstens BUDGET nieuwe per familie per dag, nooit twee keer dezelfde.
  2. Zeven op TRAIN (alleen data vóór de selectiegrens van vandaag): minstens MIN_TRAIN trades, vaak genoeg om
     de validatie te kunnen halen, en gemiddeld positief bij 1,5x kosten. Wie niet slaagt: "afgewezen op train".
     Validatie- en testdata worden hierbij NIET bekeken (getest: andere data na de grens geeft exact dezelfde keuzes).
  3. Wie slaagt komt in de pool (hoogstens POOL_MAX per familie per markt; bij een volle pool valt de zwakste op
     train af, behalve de variant die nu actief of in onderzoek is).
  4. Toetsen: de pool doet mee in de dagelijkse selectie (learning/selector.py) met dezelfde poort als elke andere
     strategie. De poort zelf staat hier niet: de generator kan hem niet veranderen. Elke ooit geprobeerde variant
     telt mee in het aantal proeven voor de Deflated Sharpe (P4); dat getal kan alleen stijgen. Hoe meer de
     generator probeert, hoe strenger de poort dus wordt.
  5. Actief alleen als de selector hem door de poort laat; anders blijft de markt op onderzoek of pauze.
  Achteraf (test): per kandidaat worden de trades NA de aanmaakdatum bijgehouden ("na aanmaak"), data die bij het
  maken nog niet bestond.

Logging: kandidaten.json (pool, afgewezenen, aantal proeven per markt en een gebeurtenissenlog) en een regel per
nieuwe kandidaat in de uitvoer van de workflow. ICT wordt (nog) niet gegenereerd: de ICT-uitkomsten komen uit het
leergeheugen, dat alleen de 48 vaste varianten bevat.
"""
import hashlib
import json

import numpy as np

from learning import selector

# Het raster per familie: alleen bestaande instellingen, in kleine stappen
SPACE = {
    "trend": {"tp": [1.5, 2.0, 2.5, 3.0, 4.0], "sm": [1.5, 2.0, 2.5, 3.0]},
    "momentum": {"er": [0.2, 0.3, 0.4, 0.5, 0.6], "lb": [6, 10, 15, 20], "tp": [1.5, 2.0, 3.0], "sm": [1.0, 1.5, 2.0]},
    "meanrev": {"k": [1.5, 2.0, 2.5, 3.0], "sm": [1.0, 1.5, 2.0]},
    "breakout": {"n": [12, 24, 48, 72, 96], "tp": [1.5, 2.0, 3.0], "sm": [1.0, 1.5, 2.0]},
    "volatiliteit": {"p": [0.05, 0.1, 0.2, 0.3], "tp": [1.5, 2.0, 3.0], "sm": [1.0, 1.5, 2.0]},
}
DEFAULTS = {"trend": dict(sm=2.0), "momentum": dict(lb=10, tp=2.0, sm=1.5), "meanrev": dict(sm=1.5),
            "breakout": dict(tp=2.0, sm=1.5), "volatiliteit": dict(tp=2.0, sm=1.5)}
BUDGET = 2          # nieuwe kandidaten per familie per markt per dag
POOL_MAX = 4        # gegenereerde kandidaten per familie per markt in de pool
LOG_MAX = 2000


def full(sid, v):
    """Variant met alle instellingen ingevuld (zelfde betekenis als strategies.lab.signals met de standaardwaarden)."""
    return {**DEFAULTS.get(sid, {}), **v}


def canon(sid, v):
    return json.dumps(full(sid, v), sort_keys=True)


def neighbors(sid, v):
    """Eén instelling één rasterstap omhoog of omlaag."""
    f = full(sid, v)
    out = []
    for p, grid in SPACE[sid].items():
        cur = f.get(p)
        i = min(range(len(grid)), key=lambda j: abs(grid[j] - cur)) if cur is not None else None
        for j in (i - 1, i + 1) if i is not None else ():
            if 0 <= j < len(grid) and grid[j] != cur:
                out.append((dict(f, **{p: grid[j]}), f"{p} {cur:g} -> {grid[j]:g}"))
    return out


def _order(market, sid, day, key):
    return hashlib.sha256(f"{market}|{sid}|{day}|{key}".encode()).hexdigest()


def train_check(trades, cut, days):
    """Zeef op ALLEEN train: (geslaagd, reden, maten)."""
    tr = [x for x in trades if x["t"] < cut]
    m15 = float(np.mean([x["R15"] for x in tr])) if tr else float("nan")
    stats = dict(n=len(tr), gem15=round(m15, 3) if tr else None)
    if len(tr) < selector.MIN_TRAIN:
        return False, f"te weinig trades in train ({len(tr)} < {selector.MIN_TRAIN})", stats
    if len(tr) / max(days, 1.0) * selector.VAL_DAYS < selector.MIN_VAL:
        return False, "handelt te weinig om de validatie te kunnen halen", stats
    if not m15 > 0:
        return False, f"train {m15:+.3f}R bij {selector.COST_X}x kosten", stats
    return True, f"train {m15:+.3f}R bij {selector.COST_X}x kosten over {len(tr)} trades", stats


def market_entry(reg, market):
    return reg.setdefault("markten", {}).setdefault(market, dict(proeven=0, families={}))


def pool(reg, market, sid):
    """Kandidaten in de pool: {sleutel: params}."""
    fam = market_entry(reg, market)["families"].get(sid, {})
    return {k: c["params"] for k, c in fam.items() if c["status"] == "in pool"}


def log(reg, event):
    reg.setdefault("log", []).append(event)
    reg["log"] = reg["log"][-LOG_MAX:]


def generate(reg, market, sid, base_variants, by_variant, cut, day, simulate_fn, protected=(), days=None):
    """Stel nieuwe varianten voor, zeef ze op train en werk de pool bij. by_variant wordt aangevuld met wie slaagt.
    base_variants: de vaste varianten (dicts). simulate_fn(params) -> trades met t, R, R15.
    protected: sleutels die niet uit de pool mogen vallen (huidige keuze). Geeft de lijst gebeurtenissen."""
    me = market_entry(reg, market)
    fam = me["families"].setdefault(sid, {})
    tried = {canon(sid, v) for v in base_variants} | set(fam)
    if days is None:
        starts = [x["t"] for t in by_variant.values() for x in t if x["t"] < cut]
        days = max(1.0, (cut - min(starts)).total_seconds() / 86400) if starts else 1.0
    parent_key = selector.pick_variant(by_variant, cut) or json.dumps(base_variants[0])
    parent = json.loads(parent_key)
    props = [(n, rule) for n, rule in neighbors(sid, parent) if canon(sid, n) not in tried]
    props.sort(key=lambda p: _order(market, sid, day, canon(sid, p[0])))
    made_today = sum(1 for c in fam.values() if c["gemaakt"] == day)     # budget per dag, ook als de run herhaald wordt
    events = []
    for params, rule in props[:max(0, BUDGET - made_today)]:
        key = canon(sid, params)
        trades = simulate_fn(params)
        ok, why, st = train_check(trades, cut, days)
        me["proeven"] += 1                           # telt altijd mee, ook als hij afvalt
        fam[key] = dict(params=params, ouder=canon(sid, parent), regel=rule, gemaakt=day, status="in pool" if ok else
                        "afgewezen op train", reden=why, train=st)
        if ok:
            by_variant[key] = trades
        ev = dict(t=day, markt=market, familie=sid, variant=key, regel=rule, uitkomst=fam[key]["status"], reden=why)
        events.append(ev)
        log(reg, ev)
    # pool begrenzen: zwakste op train eruit (huidige keuze niet)
    members = [k for k, c in fam.items() if c["status"] == "in pool"]
    while len(members) > POOL_MAX:
        def tmean(k):
            tr = [x["R15"] for x in by_variant.get(k, []) if x["t"] < cut]
            return float(np.mean(tr)) if tr else -9.0
        out = min((k for k in members if k not in protected), key=tmean, default=None)
        if out is None:
            break
        fam[out]["status"] = "verdrongen"
        fam[out]["reden"] = f"pool vol; zwakste op train ({tmean(out):+.3f}R)"
        by_variant.pop(out, None)
        members.remove(out)
        ev = dict(t=day, markt=market, familie=sid, variant=out, regel="", uitkomst="verdrongen", reden=fam[out]["reden"])
        events.append(ev)
        log(reg, ev)
    return events


def after_creation(reg, market, sid, by_variant):
    """Test achteraf: trades NA de aanmaakdatum per kandidaat in de pool (data die bij het maken niet bestond)."""
    for k, c in market_entry(reg, market)["families"].get(sid, {}).items():
        if c["status"] != "in pool":
            continue
        after = [x["R"] for x in by_variant.get(k, []) if x["t"].date().isoformat() > c["gemaakt"]]
        c["na_aanmaak"] = dict(n=len(after), gem=round(float(np.mean(after)), 3) if after else None,
                               totaal=round(float(np.sum(after)), 2))


def trials(reg, market, base_count):
    """Aantal proeven voor P4: alle vaste varianten + elke ooit gegenereerde kandidaat op deze markt."""
    return max(2, base_count + market_entry(reg, market)["proeven"])
