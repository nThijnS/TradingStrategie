"""Sentiment: klantposities bij Capital.com, vergeleken met de eigen opgeslagen historie.

Zonder MIN_METINGEN eerdere metingen doet deze bot geen uitspraak over extreem of niet. Richting is altijd "geen":
dat een extreme klantpositie de andere kant op wijst, is een idee en geen bewijs. Toetsen kan later met de
opgeslagen reeks, via het normale protocol.
"""
from ..schema import tijd

MIN_METINGEN = 60
EXTREEM = 0.90
BRON = dict(naam="Capital.com klantsentiment", url="https://open-api.capital.com/")


class GeenKlantsentiment(RuntimeError):
    pass


def duiding(long, eerder):
    if len(eerder) < MIN_METINGEN:
        return f"Klanten {long:.0f}% long. Nog geen vergelijking: {len(eerder)} van {MIN_METINGEN} metingen."
    p = sum(x < long for x in eerder) / len(eerder)
    if p >= EXTREEM:
        return f"Klanten {long:.0f}% long, extreem hoog: meer dan {p:.0%} van de eerdere metingen."
    if p <= 1 - EXTREEM:
        return f"Klanten {long:.0f}% long, extreem laag: meer dan slechts {p:.0%} van de eerdere metingen."
    return f"Klanten {long:.0f}% long, normaal: meer dan {p:.0%} van de eerdere metingen."


def draai(context, rijen, historie):
    if not rijen:
        raise GeenKlantsentiment("geen metingen")
    peil = tijd(context["peilmoment"])
    nu = {r["markt"]: r for r in rijen if tijd(r["t"]) <= peil}
    bevindingen, ontbreekt = [], []
    for markt in context["markten"]:
        r = nu.get(markt)
        if r is None:
            ontbreekt.append(f"{markt}: geen klantsentiment")
            continue
        eerder = [h["long"] for h in historie if h["markt"] == markt and tijd(h["t"]) < tijd(r["t"])]
        bevindingen.append(dict(markt=markt, richting="geen", horizon=context["horizon"], zekerheid=0.5,
                                bewering=duiding(r["long"], eerder), bronnen=[dict(BRON, tijdstip=r["t"])]))
    tot = max((r["t"] for r in nu.values()), key=tijd, default=context["peilmoment"])
    return dict(bot="sentiment", ronde_id=context["ronde_id"], gemaakt_op=context["peilmoment"], data_tot=tot,
                bevindingen=bevindingen, ontbreekt=ontbreekt)
