"""Rekent vastgelegde voorspellingen af en maakt de scorekaart. Oude rondes blijven onaangeraakt.

Instap: de open van de eerste candle die start op of na het moment van vastleggen. Uitstap: de open van de eerste
candle na de horizon. Zo telt niets mee dat op het moment van vastleggen al bekend kon zijn.

"goed" betekent dat de richting bruto klopte; daarop rusten trefkans en Brier-score, omdat zekerheid over de richting
gaat. "netto" is na spread en financiering. Een voorspelling zonder uitkomst blijft wachten tot er koersen zijn.

Voorspellingen op dezelfde dag hangen samen. Daarom telt de onzekerheidsmarge dagen en geen losse voorspellingen.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd

from core.markets import LAB_MARKETS, fin_rate

from . import koersen as kz
from . import opslag
from .schema import tijd

MIN_VOORSPELLINGEN = 100
MIN_DAGEN = 30
MARKT = {m["naam"]: m for m in LAB_MARKETS}
DAG = pd.Timedelta(hours=24)


def _horizon(tekst):
    return pd.Timedelta(hours=int(tekst[:-1]) * (24 if tekst[-1] == "d" else 1))


def _iso(t):
    return kz.isotijd(t)


def reken(v, df):
    """Eén uitkomst, of None zolang de horizon nog niet voorbij is."""
    start = df.index.searchsorted(pd.Timestamp(tijd(v["vastgelegd_op"])))
    if start >= len(df):
        return None
    instap_t = df.index[start]
    eind = df.index.searchsorted(instap_t + _horizon(v["horizon"]))
    if eind >= len(df):
        return None
    uitstap_t, instap, uitstap = df.index[eind], float(df["Open"].iloc[start]), float(df["Open"].iloc[eind])
    teken = 1 if v["richting"] == "omhoog" else -1
    m = MARKT[v["markt"]]
    kosten = m["kosten"] + fin_rate(m) * (uitstap_t - instap_t).total_seconds() / (365 * 86400)
    beweging = uitstap / instap - 1
    uit = dict(id=v["id"], bron=v["bron"], markt=v["markt"], datum=v["id"][:10], richting=v["richting"], zekerheid=v["zekerheid"],
               horizon=v["horizon"], instap_t=_iso(instap_t), uitstap_t=_iso(uitstap_t), instap=instap, uitstap=uitstap,
               bruto=round(teken * beweging, 6), kosten=round(kosten, 6), netto=round(teken * beweging - kosten, 6), goed=teken * beweging > 0,
               netto_gisteren=None)
    if start >= 1:      # basislijn: de richting van de 24 uur vóór de instap
        c = df["Close"].iloc[:start]
        eerder = c.asof(instap_t - DAG)
        if pd.notna(eerder) and c.iloc[-1] != eerder:
            uit["netto_gisteren"] = round((1 if c.iloc[-1] > eerder else -1) * beweging - kosten, 6)
    return uit


def voorspellingen(map_):
    for pad in sorted((Path(map_) / "rondes").glob("*.json")):
        if not pad.name.endswith("-droog.json"):
            yield from json.loads(pad.read_text(encoding="utf-8")).get("voorspellingen", ())


def reken_af(map_, koersen):
    """Voegt nieuwe uitkomsten toe en geeft het aantal terug."""
    klaar = {u["id"] for u in opslag.lees_uitkomsten(map_)}
    nieuw = []
    for v in voorspellingen(map_):
        if v["id"] not in klaar and v["markt"] in koersen:
            u = reken(v, koersen[v["markt"]])
            if u:
                nieuw.append(u)
    opslag.bewaar_uitkomsten(map_, nieuw)
    return len(nieuw)


def wilson(goed, n, z=1.96):
    """95%-interval voor een kans."""
    if n == 0:
        return None
    p = goed / n
    noemer = 1 + z * z / n
    midden = (p + z * z / (2 * n)) / noemer
    marge = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / noemer
    return [round(max(0.0, midden - marge), 3), round(min(1.0, midden + marge), 3)]


def _gem(x):
    x = [i for i in x if i is not None]
    return round(sum(x) / len(x), 6) if x else None


def score(uitkomsten):
    per_dag = defaultdict(list)
    for u in uitkomsten:
        per_dag[u["datum"]].append(u["goed"])
    dagen = len(per_dag)
    daggem = sum(sum(g) / len(g) for g in per_dag.values())
    n = len(uitkomsten)
    genoeg = n >= MIN_VOORSPELLINGEN and dagen >= MIN_DAGEN
    return dict(n=n, dagen=dagen, trefkans=round(daggem / dagen, 3), interval=wilson(daggem, dagen),
                brier=round(sum((u["zekerheid"] - u["goed"]) ** 2 for u in uitkomsten) / n, 4), brier_geen_voorsprong=0.25,
                netto=_gem([u["netto"] for u in uitkomsten]),
                basislijn=dict(geen_actie=0.0, willekeurig=_gem([-u["kosten"] for u in uitkomsten]), gisteren=_gem([u["netto_gisteren"] for u in uitkomsten])),
                conclusie="vergelijking mogelijk" if genoeg else "te weinig data")


def scorekaart(uitkomsten):
    per_bron = defaultdict(list)
    for u in uitkomsten:
        per_bron[u["bron"]].append(u)
    return {bron: score(x) for bron, x in sorted(per_bron.items())}
