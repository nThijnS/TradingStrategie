#!/usr/bin/env python3
"""
Instrumentgegevens controleren bij Capital.com (ALLEEN LEZEN: inloggen en GET-verzoeken, nooit orders).

Voor elke huidige markt (broker.EPICS) en elke kandidaat uit onderzoek.py:
- zoekt de epic op (GET /markets?searchTerm=...) en bewaart de zoekresultaten;
- leest de details (GET /markets/{epic}): valuta, lotSize, scalingFactor, min/max ordergrootte, stapgrootte,
  minimale stopafstand, marge, financiering (overnightFee), handelsuren, status en de actuele spread;
- telt hoeveel 1-uurscandles de broker zelf heeft (GET /prices, max 1000) om de data-aansluiting te controleren.

Een kandidaat krijgt alleen een epic als de zoekresultaten een exacte, eenduidige match geven; anders blijft die
leeg en moet de epic bewust worden gekozen. Schrijft rapport/instrumenten.json.

Dat rapport is ook de vrijgave per instrument: execution/runner.py plaatst alleen een demo-order op een markt
waarvan het rapport het instrument bevestigt (verified()). Zonder rapport, of met een fout of probleem in het
rapport, wordt de markt veilig geweigerd met de reden erbij. Per order controleert de runner de gegevens
daarnaast opnieuw bij de broker (contractgrootte, ordergrootte, decimalen, valuta, status en koers).

Draait met de DEMO-geheimen (workflow "Instrumenten controleren", handmatig te starten):
    python capital_instrumenten.py
"""
import json
import os
from datetime import datetime, timezone

from execution.capital import Capital, BrokerError
from core.markets import LAB_MARKETS
from execution.markets import EPICS, INSTRUMENT_TYPES
from storage import paths

HERE = paths.ROOT
OUT = paths.INSTRUMENTS

# Kandidaten: zoekterm en de epics die als exacte match gelden (geen gok: alleen gebruikt als de broker ze teruggeeft)
CANDIDATES = {
    "AUDUSD": ("AUD/USD", ["AUDUSD"]), "USDCAD": ("USD/CAD", ["USDCAD"]), "USDCHF": ("USD/CHF", ["USDCHF"]),
    "NZDUSD": ("NZD/USD", ["NZDUSD"]), "EURGBP": ("EUR/GBP", ["EURGBP"]), "EURJPY": ("EUR/JPY", ["EURJPY"]),
    "US30": ("Wall Street", []), "FTSE": ("UK 100", []), "NIKKEI": ("Japan 225", []), "CAC": ("France 40", []),
    "BRENT": ("Brent", []), "KOPER": ("Copper", []), "GAS": ("Natural Gas", []),
}


def details(b, epic):
    m = b.market(epic)
    i, d, s = m.get("instrument", {}), m.get("dealingRules", {}), m.get("snapshot", {})
    bid, ask = s.get("bid"), s.get("offer")
    mid = (bid + ask) / 2 if bid and ask else None
    out = dict(epic=epic, naam=i.get("name"), type=i.get("type"), valuta=i.get("currency"), lotSize=i.get("lotSize"),
               scalingFactor=s.get("scalingFactor"), decimalen=s.get("decimalPlacesFactor"),
               minDealSize=d.get("minDealSize"), maxDealSize=d.get("maxDealSize"), minSizeIncrement=d.get("minSizeIncrement"),
               minStopOrProfitDistance=d.get("minStopOrProfitDistance"), maxStopOrProfitDistance=d.get("maxStopOrProfitDistance"),
               marge=dict(factor=i.get("marginFactor"), eenheid=i.get("marginFactorUnit")), financiering=i.get("overnightFee"),
               handelsuren=i.get("openingHours"), status=s.get("marketStatus"), vertraging=s.get("delayTime"),
               bid=bid, ask=ask, spread=round(ask - bid, 8) if mid else None,
               spread_pct=round((ask - bid) / mid * 100, 5) if mid else None)
    try:
        p = b.call("GET", f"/prices/{epic}?resolution=HOUR&max=1000").get("prices", [])
        out["uurcandles_bij_broker"] = dict(aantal=len(p), van=p[0]["snapshotTimeUTC"] if p else None,
                                            tot=p[-1]["snapshotTimeUTC"] if p else None)
    except BrokerError as ex:
        out["uurcandles_bij_broker"] = dict(fout=str(ex))
    problems = []
    for k, label in (("minDealSize", "minimale ordergrootte"), ("minSizeIncrement", "stapgrootte"),
                     ("decimalen", "prijsdecimalen"), ("valuta", "valuta")):
        if out[k] is None or (isinstance(out[k], dict) and out[k].get("value") is None):
            problems.append(f"{label} ontbreekt")
    if not out["naam"]:
        problems.append("instrumentnaam ontbreekt")
    if out["lotSize"] != 1:
        problems.append(f"lotSize {out['lotSize']} (broker.py handelt alleen bij 1)")
    if (out["scalingFactor"] or 1) != 1:
        problems.append(f"scalingFactor {out['scalingFactor']}")
    if (out["vertraging"] or 0) > 0:
        problems.append("koers met vertraging")
    out["bruikbaar_voor_broker_py"] = not problems
    out["problemen"] = problems
    return out


SOORT = {m["naam"]: m["soort"] for m in LAB_MARKETS}


def load_report(path=None):
    """rapport/instrumenten.json, of None als het er niet is of niet te lezen is."""
    try:
        return json.loads((path or OUT).read_text())
    except (OSError, ValueError):
        return None


def verified(markt, epic, report):
    """Is dit instrument voor deze markt bevestigd door het leesrapport? Geeft None (in orde) of de reden."""
    if not report:
        return ("instrument niet geverifieerd: rapport/instrumenten.json ontbreekt "
                "(draai de workflow 'Instrumenten controleren', alleen lezen)")
    if not isinstance(report, dict) or not isinstance(report.get("huidig"), dict):
        return "instrument niet geverifieerd: rapport/instrumenten.json heeft niet de verwachte vorm"
    if str(report.get("omgeving") or "").split(" ")[0] != "demo":
        return f"instrumentrapport komt niet uit de demo-omgeving ({report.get('omgeving')!r})"
    x = report["huidig"].get(markt)
    if not isinstance(x, dict) or not x:
        return f"instrument niet geverifieerd: {markt} staat niet in rapport/instrumenten.json"
    if x.get("epic") != epic:
        return f"instrument niet geverifieerd: rapport heeft epic {x.get('epic')!r}, de bot gebruikt {epic!r}"
    if x.get("fout"):
        return f"instrument niet geverifieerd: de broker gaf een fout ({x['fout']})"
    if not x.get("bruikbaar_voor_broker_py"):
        return "instrument niet bruikbaar: " + ("; ".join(x.get("problemen") or []) or "reden onbekend")
    want = INSTRUMENT_TYPES.get(SOORT.get(markt))
    if want and x.get("type") != want:
        return f"instrument niet geverifieerd: type {x.get('type')!r} past niet bij een {SOORT.get(markt)}-markt (verwacht {want})"
    return None


def status_per_market(report):
    """{markt: None of reden} voor alle markten met een epic (voor het dashboard en het rapport)."""
    return {m: verified(m, e, report) for m, e in EPICS.items()}


def main():
    b = Capital("demo", os.environ.get("CAPITAL_API_KEY", "").strip(), os.environ.get("CAPITAL_IDENTIFIER", "").strip(),
                os.environ.get("CAPITAL_PASSWORD", "").strip())
    res = dict(gemaakt=datetime.now(timezone.utc).isoformat(timespec="seconds"), omgeving="demo (alleen lezen)",
               huidig={}, kandidaten={})
    for markt, epic in EPICS.items():
        try:
            res["huidig"][markt] = details(b, epic)
        except BrokerError as ex:
            res["huidig"][markt] = dict(epic=epic, fout=str(ex), bruikbaar_voor_broker_py=False)
    for markt, (term, exact) in CANDIDATES.items():
        try:
            found = b.call("GET", f"/markets?searchTerm={term.replace(' ', '%20').replace('/', '%2F')}").get("markets", [])
        except BrokerError as ex:
            res["kandidaten"][markt] = dict(zoekterm=term, fout=str(ex))
            continue
        hits = [dict(epic=f.get("epic"), naam=f.get("instrumentName"), type=f.get("instrumentType")) for f in found[:8]]
        match = [h["epic"] for h in hits if h["epic"] in exact]
        entry = dict(zoekterm=term, zoekresultaten=hits, epic=match[0] if len(match) == 1 else None)
        if entry["epic"]:
            try:
                entry["details"] = details(b, entry["epic"])
            except BrokerError as ex:
                entry["fout"] = str(ex)
        else:
            entry["opmerking"] = "geen eenduidige match: epic bewust kiezen uit de zoekresultaten"
        res["kandidaten"][markt] = entry
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    ok = sum(1 for x in res["huidig"].values() if x.get("bruikbaar_voor_broker_py"))
    print(f"{OUT}: {ok}/{len(res['huidig'])} huidige markten bruikbaar; kandidaten met epic: "
          f"{[k for k, v in res['kandidaten'].items() if v.get('epic')]}")


if __name__ == "__main__":
    main()
