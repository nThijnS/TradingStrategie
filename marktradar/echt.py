"""Echte ronde. Eerst alle bronnen ophalen, daarna pas het peilmoment zetten, zodat niets nieuwer is dan de ronde.

Een bron die faalt, stopt de ronde niet: de bot die ervan afhangt meldt wat ontbreekt.
"""
import os
from datetime import datetime, timezone

from . import instellingen as inst
from . import koersen as kz
from . import llm as llm_laag
from . import opslag
from .bots import charts, chieftekst, news, scout, sentiment, skeptic
from .bronnen import capital, fed, kalender
from .chief import draai_ronde
from .schema import tijd

OPHALERS = dict(koersen=kz.download, fed=fed.haal, kalender=kalender.haal, sentiment=capital.haal)


def _probeer(functie, wat):
    try:
        return functie(), None
    except capital.GeenSleutels:
        return None, f"{wat}: geen sleutels"
    except capital.CapitalFout as e:    # bevat alleen de stap en de HTTP-status
        return None, f"{wat} niet opgehaald ({e})"
    except Exception as e:      # alleen het type: foutteksten kunnen geheimen bevatten
        return None, f"{wat} niet opgehaald ({type(e).__name__})"


def maak_llm(instellingen, datum, map_, stuur):
    if stuur is None and not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    boek = (lambda model, usd: opslag.boek_kosten(map_, datum, model, usd)) if map_ else None
    return llm_laag.Llm(stuur or llm_laag.anthropic_stuur, instellingen["llm_model"], instellingen["llm_max_tokens"],
                        instellingen["max_dagbudget_usd"], opslag.besteed_op(map_, datum) if map_ else 0.0, boek)


def draai(nu=None, ophalen=None, map_=None, stuur=None):
    o = dict(OPHALERS, **(ophalen or {}))
    instellingen = inst.laad()
    ruw, fout_koers = _probeer(o["koersen"], "koersen")
    berichten, fout_fed = _probeer(o["fed"], "Federal Reserve")
    agenda_ruw, fout_agenda = _probeer(o["kalender"], "agenda")
    metingen, fout_sentiment = _probeer(o["sentiment"], "klantsentiment")

    nu = nu or datetime.now(timezone.utc)
    peilmoment, datum = nu.strftime("%Y-%m-%dT%H:%M:%SZ"), nu.strftime("%Y-%m-%d")
    koersen, fouten = kz.opschonen(ruw, peilmoment) if ruw is not None else ({}, [fout_koers])
    agenda = kalender.per_markt(agenda_ruw, tijd(peilmoment)) if agenda_ruw is not None else None
    historie = opslag.lees_historie(map_) if map_ else []
    if map_ and metingen:
        opslag.bewaar_metingen(map_, metingen)
    llm = maak_llm(instellingen, datum, map_, stuur)
    fouten_news = [x for x in (fout_fed, fout_agenda) if x]

    bots = dict(
        scout=lambda c: scout.draai(c, koersen, fouten, instellingen["scout_drempel"], instellingen["max_markten"], agenda),
        charts=lambda c: charts.draai(c, koersen),
        news=lambda c: news.draai(c, berichten or [], agenda, llm, fouten_news),
        sentiment=lambda c: sentiment.draai(c, metingen or [], historie),
        skeptic=lambda c: skeptic.draai(c, llm))
    ronde = draai_ronde(bots, datum, peilmoment, instellingen, meldingen=[fout_sentiment] if fout_sentiment else [],
                        schrijver=chieftekst.maak_schrijver(llm))
    if llm:
        ronde["modellen"] = {wie: sorted(m) for wie, m in llm.modellen.items()}
        ronde["kosten_usd"] = round(llm.deze_ronde, 6)
    return ronde
