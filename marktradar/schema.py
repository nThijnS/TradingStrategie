"""Het gezamenlijke formaat van alle deelbots. Ongeldige uitvoer wordt geweigerd en telt dan niet mee.

Een bevinding zonder bron is geldig formaat maar telt niet mee in het oordeel; dat beslist de Chief.
"""
import re
from datetime import datetime

from core.markets import LAB_MARKETS

BOTS = ("scout", "charts", "news", "sentiment", "skeptic")
SPECIALISTEN = ("charts", "news", "sentiment")
RICHTINGEN = ("omhoog", "omlaag", "geen")
OORDELEN = ("GEEN_ACTIE", "VOLGEN", "ONDERZOEKEN")
MARKTEN = tuple(m["naam"] for m in LAB_MARKETS)
ZONDER_RICHTING = ("scout", "skeptic")      # Scout voorspelt geen richting en de Skeptic draagt geen ideeën aan
MAX_TEKST = 500

VELDEN = {"bot", "ronde_id", "gemaakt_op", "data_tot", "bevindingen", "ontbreekt"}
VELDEN_BEVINDING = {"markt", "richting", "horizon", "zekerheid", "bewering", "bronnen"}
VELDEN_BRON = {"naam", "url", "tijdstip"}
VELDEN_VETO = {"markt", "reden"}


class OngeldigeUitvoer(ValueError):
    pass


def _eis(ok, tekst):
    if not ok:
        raise OngeldigeUitvoer(tekst)


def _velden(obj, verplicht, wat):
    _eis(isinstance(obj, dict), f"{wat} is geen object")
    _eis(set(obj) == verplicht, f"{wat} heeft verkeerde velden: {sorted(set(obj) ^ verplicht)}")


def _tekst(x, wat):
    _eis(isinstance(x, str) and x.strip() and len(x) <= MAX_TEKST, f"{wat} moet tekst van 1 tot {MAX_TEKST} tekens zijn")


def tijd(tekst):
    """ISO-tijd met tijdzone. Een tijd zonder zone is onduidelijk en dus ongeldig."""
    _eis(isinstance(tekst, str), f"tijdstip is geen tekst: {tekst!r}")
    try:
        t = datetime.fromisoformat(tekst.replace("Z", "+00:00"))
    except ValueError:
        raise OngeldigeUitvoer(f"ongeldig tijdstip: {tekst!r}") from None
    _eis(t.utcoffset() is not None, f"tijdstip zonder tijdzone: {tekst!r}")
    return t


def _bevinding(b, bot, data_tot):
    _velden(b, VELDEN_BEVINDING, "bevinding")
    _eis(b["markt"] in MARKTEN, f"onbekende markt: {b['markt']!r}")
    _eis(b["richting"] in RICHTINGEN, f"onbekende richting: {b['richting']!r}")
    _eis(bot not in ZONDER_RICHTING or b["richting"] == "geen", f"{bot} mag geen richting geven")
    _eis(isinstance(b["horizon"], str) and re.fullmatch(r"[1-9]\d*[hd]", b["horizon"]), f"ongeldige horizon: {b['horizon']!r}")
    z = b["zekerheid"]
    _eis(isinstance(z, (int, float)) and not isinstance(z, bool) and 0 <= z <= 1, f"zekerheid buiten 0-1: {z!r}")
    _tekst(b["bewering"], "bewering")
    _eis(isinstance(b["bronnen"], list), "bronnen is geen lijst")
    for bron in b["bronnen"]:
        _velden(bron, VELDEN_BRON, "bron")
        _tekst(bron["naam"], "bronnaam")
        _eis(isinstance(bron["url"], str), "bron-url is geen tekst")
        _eis(tijd(bron["tijdstip"]) <= data_tot, f"bron is nieuwer dan data_tot: {bron['tijdstip']}")


def controleer(uitvoer, bot, ronde_id, peil, max_markten):
    """Weigert uitvoer met een verkeerd formaat of met gegevens van na het peilmoment van de ronde."""
    verplicht = VELDEN | {"veto"} if bot == "skeptic" else VELDEN
    _velden(uitvoer, verplicht, "uitvoer")
    _eis(uitvoer["bot"] == bot, f"uitvoer van {uitvoer['bot']!r} waar {bot!r} werd verwacht")
    _eis(uitvoer["ronde_id"] == ronde_id, f"verkeerde ronde: {uitvoer['ronde_id']!r}")
    data_tot = tijd(uitvoer["data_tot"])
    _eis(data_tot <= peil, "data_tot ligt na het peilmoment")
    _eis(data_tot <= tijd(uitvoer["gemaakt_op"]), "data_tot ligt na gemaakt_op")
    _eis(isinstance(uitvoer["bevindingen"], list), "bevindingen is geen lijst")
    for b in uitvoer["bevindingen"]:
        _bevinding(b, bot, data_tot)
    _eis(isinstance(uitvoer["ontbreekt"], list), "ontbreekt is geen lijst")
    for x in uitvoer["ontbreekt"]:
        _tekst(x, "ontbreekt")
    if bot == "scout":
        _eis(len({b["markt"] for b in uitvoer["bevindingen"]}) <= max_markten, f"Scout koos meer dan {max_markten} markten")
    if bot == "skeptic":
        _eis(isinstance(uitvoer["veto"], list), "veto is geen lijst")
        for v in uitvoer["veto"]:
            _velden(v, VELDEN_VETO, "veto")
            _eis(v["markt"] in MARKTEN, f"onbekende markt in veto: {v['markt']!r}")
            _tekst(v["reden"], "vetoreden")
