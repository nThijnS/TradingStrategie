#!/usr/bin/env python3
"""Haalt marktenlijst en uurcandles op bij Capital.com (demo, ALLEEN LEZEN: geen orders, geen accountwijzigingen).

    python -W ignore -m research.capital_data --dagen 730 --uit capitaldata      (workflow Capitaldata)

Elke candle bevat bid en ask, dus de spread per uur komt van de broker zelf in plaats van uit een aanname.
De marktkeuze volgt een vaste regel op de spread (kies), niet op eerdere resultaten. De uitvoer staat als artifact bij
de run; er gaat niets naar de repo. Sleutels en tokens komen niet in logs of uitvoer.
"""
import argparse
import gzip
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from execution.capital import Capital
from execution.markets import EPICS
from research.feedmeting import ReadOnly, candles, credentials, scrub

GROEPEN = ("crypto", "forex", "indices", "commodities")
# Per soort: hoogste toegestane spread in % en het maximumaantal markten. Vastgelegd vóór de eerste uitslag.
REGEL = {"CRYPTOCURRENCIES": (0.30, 25), "CURRENCIES": (0.03, 20), "INDICES": (0.05, 15), "COMMODITIES": (0.15, 12)}
STAP_DAGEN = 40          # 40 dagen = 960 uurcandles, onder de grens van 1000 per verzoek


def crawl(ro, groepen=GROEPEN, max_verzoeken=120):
    """Loopt door de marktnavigatie van de gevraagde groepen. Geeft {epic: markt}."""
    start = [n for n in ro.get("/marketnavigation").get("nodes", []) if any(g in (n.get("name") or "").lower() for g in groepen)]
    todo, gezien, out, n = [x["id"] for x in start], set(), {}, 0
    while todo and n < max_verzoeken:
        node = todo.pop(0)
        if node in gezien:
            continue
        gezien.add(node)
        n += 1
        d = ro.get(f"/marketnavigation/{quote(str(node), safe='')}?limit=500")
        todo += [x["id"] for x in d.get("nodes") or []]
        for m in d.get("markets") or []:
            out.setdefault(m["epic"], m)
    return out


def spread_pct(m):
    b, o = m.get("bid"), m.get("offer")
    return round((o - b) / ((o + b) / 2) * 100, 5) if b and o and o > b else None


def kies(markten, verplicht=()):
    """Vaste regel: per soort de laagste spreads onder de grens, plus de markten die de bot al kent."""
    uit, per = set(verplicht), {}
    for e, m in markten.items():
        s = spread_pct(m)
        grens = REGEL.get(m.get("instrumentType"))
        if s is not None and grens and s <= grens[0]:
            per.setdefault(m["instrumentType"], []).append((s, e))
    for soort, rijen in per.items():
        uit |= {e for _, e in sorted(rijen)[:REGEL[soort][1]]}
    return sorted(uit)


def vensters(eind, dagen, stap=STAP_DAGEN):
    """Van oud naar nieuw, elk venster onder de 1000 candles en zonder gat."""
    a = eind - timedelta(days=dagen)
    while a < eind:
        b = min(a + timedelta(days=stap), eind)
        yield a, b
        a = b


def uurcandles(ro, epic, eind, dagen):
    delen = []
    for a, b in vensters(eind, dagen):
        q = f"/prices/{quote(epic, safe='')}?resolution=HOUR&max=1000&from={a:%Y-%m-%dT%H:%M:%S}&to={b:%Y-%m-%dT%H:%M:%S}"
        try:
            df = candles(ro.get(q))
        except Exception:           # geen data in dit venster (markt bestond nog niet): overslaan
            continue
        if len(df):
            delen.append(df)
    if not delen:
        return pd.DataFrame()
    df = pd.concat(delen).sort_index()
    return df[~df.index.duplicated(keep="last")]


def details(ro, epic):
    d = ro.get(f"/markets/{quote(epic, safe='')}")
    i, r = d.get("instrument") or {}, d.get("dealingRules") or {}
    return dict(naam=i.get("name"), type=i.get("type"), valuta=i.get("currency"), marge=i.get("marginFactor"), marge_eenheid=i.get("marginFactorUnit"),
                financiering=i.get("overnightFee"), uren=i.get("openingHours"), min_deal=r.get("minDealSize"), min_stop=r.get("minStopOrProfitDistance"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dagen", type=int, default=730)
    ap.add_argument("--uit", default="capitaldata")
    a = ap.parse_args()
    uit = Path(a.uit)
    uit.mkdir(parents=True, exist_ok=True)
    eind = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    ro = ReadOnly(Capital("demo", *credentials()))
    try:
        markten = crawl(ro)
        epics = kies(markten, EPICS.values())
        print(f"{len(markten)} markten gevonden, {len(epics)} gekozen", flush=True)
        rij = {}
        for i, e in enumerate(epics, 1):
            m = markten.get(e, {})
            r = dict(epic=e, naam=m.get("instrumentName"), type=m.get("instrumentType"), spread_nu_pct=spread_pct(m), status=m.get("marketStatus"))
            try:
                df = uurcandles(ro, e, eind, a.dagen)
                r.update(candles=len(df), van=str(df.index[0]) if len(df) else None, details=details(ro, e))
                if len(df):
                    with gzip.open(uit / f"{e}.csv.gz", "wt") as f:
                        df.to_csv(f)
            except Exception as ex:
                r["fout"] = scrub(ex)
            rij[e] = r
            if i % 10 == 0:
                print(f"{i}/{len(epics)}", flush=True)
        (uit / "markten.json").write_text(json.dumps(dict(gemaakt=eind.isoformat(), omgeving="demo (alleen lezen)", regel=REGEL, gevonden=len(markten),
                                                          alle={e: dict(naam=m.get("instrumentName"), type=m.get("instrumentType"), spread_nu_pct=spread_pct(m)) for e, m in markten.items()},
                                                          gekozen=rij), ensure_ascii=False, indent=1))
    except Exception as ex:
        raise SystemExit(f"mislukt: {scrub(ex)}") from None


if __name__ == "__main__":
    main()
