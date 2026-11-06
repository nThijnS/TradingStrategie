"""Scout: welke markten verdienen vandaag aandacht? Vaste rekenregels, geen LLM en geen richting.

Per markt drie maten, elk als percentiel tegen de eigen historie van maximaal HISTORIE candles:
  beweging      absolute koersverandering over 24 uur
  volatiliteit  ATR(14) als deel van de prijs
  volume        volume van de laatste 24 uur (niet bij markten zonder volume, zoals forex bij Yahoo)
Een markt is opvallend als een maat het percentiel scout_drempel haalt. De hoogste maat bepaalt de volgorde.
Een markt met zwaar agendapunt in de komende 24 uur telt ook, maar achter markten die al uit de cijfers opvallen.
"""
import pandas as pd

from core import market_hours
from core.markets import LAB_MARKETS
from strategies import lab

from .. import koersen as kz

HISTORIE = 2000
MIN_CANDLES = 300
MAX_OUDERDOM = pd.Timedelta(hours=3)     # open markt met oudere koers: data niet betrouwbaar (of feestdag)
DAG = pd.Timedelta(hours=24)
SOORT = {m["naam"]: m["soort"] for m in LAB_MARKETS}


def percentiel(reeks):
    """Welk deel van de historie is lager dan de laatste waarde? None zonder bruikbare data."""
    r = reeks.dropna().iloc[-HISTORIE:]
    return round(float((r < r.iloc[-1]).mean()), 3) if len(r) >= MIN_CANDLES else None


def maten(df):
    c = df["Close"]
    eerder = pd.Series(c.reindex(df.index - DAG, method="ffill").values, index=df.index)
    verandering = c / eerder - 1
    atr = lab.indicators(df)["atr"] / c
    uit = dict(verandering=round(float(verandering.iloc[-1]), 5), beweging=percentiel(verandering.abs()), volatiliteit=percentiel(atr))
    volume = df["Volume"].rolling(24).sum()
    uit["volume"] = percentiel(volume) if df["Volume"].iloc[-HISTORIE:].gt(0).mean() > 0.9 else None
    return uit


def _tekst(m):
    delen = [f"24 uur {m['verandering']:+.2%} (beweging hoger dan {m['beweging']:.0%} van de historie)"]
    delen.append(f"volatiliteit {m['volatiliteit']:.0%}")
    delen.append(f"volume {m['volume']:.0%}" if m["volume"] is not None else "volume onbekend")
    if "agenda" in m:
        delen.append(f"agenda: {m['agenda']}")
    return "Opvallend: " + ", ".join(delen) + "."


def draai(context, koersen, fouten=(), drempel=0.90, max_markten=5, agenda=None):
    peil = pd.Timestamp(context["peilmoment"])
    ontbreekt = list(fouten) + ([] if agenda is not None else ["agenda niet beschikbaar"])
    kandidaten = []
    for naam, df in koersen.items():
        if market_hours.is_open(SOORT[naam], naam, peil.to_pydatetime()) and peil - kz.einde(df) > MAX_OUDERDOM:
            ontbreekt.append(f"{naam}: koers te oud voor een open markt")
            continue
        m = maten(df) if len(df) >= MIN_CANDLES else None
        if not m or m["beweging"] is None or m["volatiliteit"] is None:
            ontbreekt.append(f"{naam}: te weinig historie")
            continue
        score = max(x for x in (m["beweging"], m["volatiliteit"], m["volume"]) if x is not None)
        punten = (agenda or {}).get(naam)
        if punten:
            m["agenda"] = punten[0]
        if score >= drempel or punten:
            kandidaten.append((max(score, drempel), naam, m, df))
    kandidaten.sort(key=lambda k: (-k[0], k[1]))
    gekozen = kandidaten[:max_markten]
    bevindingen = [dict(markt=naam, richting="geen", horizon=context["horizon"], zekerheid=score, bewering=_tekst(m),
                        bronnen=[kz.bron(naam, df)]) for score, naam, m, df in gekozen]
    tot = max((kz.einde(df) for df in koersen.values()), default=peil)
    return dict(bot="scout", ronde_id=context["ronde_id"], gemaakt_op=context["peilmoment"], data_tot=kz.isotijd(tot),
                bevindingen=bevindingen, ontbreekt=ontbreekt)
