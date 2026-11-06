"""De Chief: regelt de ronde, weegt de uitvoer met vaste regels en legt de voorspellingen vast.

Volgorde: Scout, dan Charts, News en Sentiment los van elkaar, dan de Skeptic, dan het oordeel.
Een bot die uitvalt of ongeldige uitvoer geeft, maakt de ronde niet stuk: de Chief meldt het en verlaagt de zekerheid.

Oordeel per markt (bij twijfel altijd GEEN_ACTIE):
  GEEN_ACTIE   veto, geen Skeptic, tegenspraak, geen signaal of te weinig zekerheid
  VOLGEN       minstens twee bots met dezelfde richting en zekerheid >= drempel_volgen
  ONDERZOEKEN  dezelfde richting en zekerheid >= drempel_onderzoeken, maar nog niet genoeg voor VOLGEN
Alleen bevindingen met een bron en met de horizon uit de instellingen tellen mee.

De LLM schrijft hooguit de toelichting. De oordelen hierboven liggen dan al vast en komen alleen uit deze code.
"""
import copy

from . import instellingen as inst
from .schema import OngeldigeUitvoer, SPECIALISTEN, controleer, tijd


def _roep(naam, bots, context, ronde, peil, instellingen):
    """Draait één bot. Geeft geldige uitvoer terug, of None met de reden in ronde["ontbreekt"]."""
    bot = bots.get(naam)
    if bot is None:
        ronde["ontbreekt"].append(f"{naam}: niet beschikbaar")
        return None
    try:
        uitvoer = bot(copy.deepcopy(context))
        ronde["ruw"][naam] = uitvoer
        controleer(uitvoer, naam, ronde["ronde_id"], peil, instellingen["max_markten"])
    except OngeldigeUitvoer as e:
        ronde["ontbreekt"].append(f"{naam}: uitvoer geweigerd ({e})")
        return None
    except Exception as e:      # ook een kapotte bot mag de ronde niet stoppen
        ronde["ontbreekt"].append(f"{naam}: uitgevallen ({type(e).__name__})")
        return None
    ronde["ontbreekt"].extend(f"{naam}: {x}" for x in uitvoer["ontbreekt"])
    return uitvoer


def _telt_mee(bevinding, bot, instellingen, ronde):
    if not bevinding["bronnen"]:
        ronde["niet_meegeteld"].append(dict(bot=bot, markt=bevinding["markt"], reden="geen bron"))
        return False
    if bevinding["horizon"] != instellingen["horizon"]:
        ronde["niet_meegeteld"].append(dict(bot=bot, markt=bevinding["markt"], reden=f"horizon {bevinding['horizon']}"))
        return False
    return True


def _stemmen(markt, geldig):
    """Per specialist de richting op deze markt: {bot: {richting: hoogste zekerheid}}."""
    uit = {}
    for bot in SPECIALISTEN:
        for b in geldig.get(bot, ()):
            if b["markt"] == markt and b["richting"] != "geen":
                r = uit.setdefault(bot, {})
                r[b["richting"]] = max(r.get(b["richting"], 0), b["zekerheid"])
    return uit


def beoordeel(markt, geldig, vetos, skeptic_aanwezig, aantal_ontbrekend, instellingen):
    def oordeel(tekst, reden, richting="geen", zekerheid=None, steun=()):
        return dict(markt=markt, oordeel=tekst, richting=richting, zekerheid=zekerheid, steun=list(steun), reden=reden)

    if markt in vetos:
        return oordeel("GEEN_ACTIE", f"Veto van de Skeptic: {vetos[markt]}")
    if not skeptic_aanwezig:
        return oordeel("GEEN_ACTIE", "De Skeptic ontbreekt, dus er is geen tegentoets gedaan.")
    stemmen = _stemmen(markt, geldig)
    if not stemmen:
        return oordeel("GEEN_ACTIE", "Geen richting met bron gevonden.")
    richtingen = {r for s in stemmen.values() for r in s}
    if len(richtingen) > 1:
        return oordeel("GEEN_ACTIE", "De bots spreken elkaar tegen.")
    richting = richtingen.pop()
    steun = sorted(stemmen)
    gemiddeld = sum(stemmen[b][richting] for b in steun) / len(steun)
    zekerheid = round(gemiddeld * (1 - instellingen["straf_per_ontbrekende_bot"] * aantal_ontbrekend), 4)
    if len(steun) >= 2 and zekerheid >= instellingen["drempel_volgen"]:
        return oordeel("VOLGEN", f"{len(steun)} bots wijzen dezelfde kant op.", richting, zekerheid, steun)
    if zekerheid >= instellingen["drempel_onderzoeken"]:
        return oordeel("ONDERZOEKEN", "Eén aanwijzing of beperkte zekerheid; nog geen bevestiging.", richting, zekerheid, steun)
    return oordeel("GEEN_ACTIE", "Te weinig zekerheid.")


def _voorspellingen(ronde, geldig, instellingen):
    """Alles met een richting wordt nu vastgelegd, vóór de uitkomst bekend is. Afrekenen gebeurt later."""
    uit = []

    def voeg_toe(bron, markt, richting, zekerheid):
        uit.append(dict(id=f"{ronde['ronde_id']}:{bron}:{markt}:{len(uit)}", bron=bron, markt=markt, richting=richting,
                        horizon=instellingen["horizon"], zekerheid=zekerheid, vastgelegd_op=ronde["peilmoment"]))

    for o in ronde["oordelen"]:
        if o["oordeel"] != "GEEN_ACTIE":
            voeg_toe("chief", o["markt"], o["richting"], o["zekerheid"])
    for bot in SPECIALISTEN:
        for b in geldig.get(bot, ()):
            if b["richting"] != "geen":
                voeg_toe(bot, b["markt"], b["richting"], b["zekerheid"])
    return uit


def briefing(ronde):
    tekst = ronde.get("toelichting") or {}
    regels = [f"MarktRadar {ronde['ronde_id']}"]
    if ronde["droog"]:
        regels.append("DROGE RONDE: testdata, geen echte marktinformatie.")
    if tekst.get("samenvatting"):
        regels.append(tekst["samenvatting"])
    if not ronde["oordelen"]:
        regels.append("Geen markten bekeken.")
    for o in ronde["oordelen"]:
        kop = f"{o['markt']}: {o['oordeel']}"
        if o["richting"] != "geen":
            kop += f" ({o['richting']}, zekerheid {o['zekerheid']:.2f})"
        regels.append(f"{kop}. {o['reden']}")
        if tekst.get("markten", {}).get(o["markt"]):
            regels.append(tekst["markten"][o["markt"]])
    if ronde["ontbreekt"]:
        regels.append("Ontbreekt: " + "; ".join(ronde["ontbreekt"]))
    regels.append("Geen financieel advies.")
    return "\n".join(regels)


def draai_ronde(bots, ronde_id, peilmoment, instellingen=None, droog=False, meldingen=(), schrijver=None):
    """bots: {naam: functie(context) -> uitvoer}. peilmoment: niets in de ronde mag nieuwer zijn dan dit tijdstip.
    meldingen: wat vóór de ronde al misging en in de briefing hoort.
    schrijver: functie(ronde) -> toelichting. Komt ná de oordelen en ziet alleen een kopie, dus verandert ze niet."""
    instellingen = instellingen or inst.laad()
    peil = tijd(peilmoment)
    ronde = dict(versie=1, ronde_id=ronde_id, peilmoment=peilmoment, droog=droog, markten=[], oordelen=[], voorspellingen=[],
                 ontbreekt=list(meldingen), niet_meegeteld=[], ruw={}, modellen={}, kosten_usd=0.0)
    basis = dict(ronde_id=ronde_id, peilmoment=peilmoment, horizon=instellingen["horizon"])

    scout = _roep("scout", bots, basis, ronde, peil, instellingen)
    uitvoer = {}
    geldig = {}
    if scout:
        uitvoer["scout"] = scout
        for b in scout["bevindingen"]:
            if _telt_mee(b, "scout", instellingen, ronde) and b["markt"] not in ronde["markten"]:
                ronde["markten"].append(b["markt"])

    skeptic = None
    if ronde["markten"]:
        context = dict(basis, markten=ronde["markten"])
        for naam in SPECIALISTEN:       # los van elkaar: elke bot krijgt alleen de marktlijst
            u = _roep(naam, bots, context, ronde, peil, instellingen)
            if u:
                uitvoer[naam] = u
                geldig[naam] = [b for b in u["bevindingen"] if _telt_mee(b, naam, instellingen, ronde)]
        skeptic = _roep("skeptic", bots, dict(context, uitvoer=uitvoer), ronde, peil, instellingen)

    vetos = {v["markt"]: v["reden"] for v in skeptic["veto"]} if skeptic else {}
    ontbrekend = sum(n not in uitvoer for n in SPECIALISTEN)
    ronde["oordelen"] = [beoordeel(m, geldig, vetos, skeptic is not None, ontbrekend, instellingen) for m in ronde["markten"]]
    ronde["voorspellingen"] = _voorspellingen(ronde, geldig, instellingen)
    ronde["status"] = "onvolledig" if ronde["ontbreekt"] else "volledig"
    if schrijver:
        try:
            ronde["toelichting"] = schrijver(copy.deepcopy(ronde))
        except Exception as e:      # zonder tekst blijft de vaste briefing staan
            ronde["ontbreekt"].append(f"chief-tekst: uitgevallen ({type(e).__name__})")
            ronde["status"] = "onvolledig"
    ronde["briefing"] = briefing(ronde)
    return ronde
