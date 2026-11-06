"""Economische agenda: het weekbestand van Forex Factory.

De voorwaarden van dit bestand zijn niet gevonden. Daarom halen we het hooguit één keer per ronde op en bewaren we
alleen tijd, valuta, titel en impact, niet de verwachtingen.
"""
import json
import urllib.request
from datetime import datetime, timedelta, timezone

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
BRON = "https://www.forexfactory.com/calendar"
VENSTER = timedelta(hours=24)
MARKTEN = dict(USD=("NQ", "ES", "EURUSD", "GBPUSD", "USDJPY", "GOUD"), EUR=("EURUSD", "DAX"), GBP=("GBPUSD",), JPY=("USDJPY",))


def haal():
    req = urllib.request.Request(URL, headers={"User-Agent": "MarketPilot-MarktRadar"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def per_markt(gebeurtenissen, peil):
    """{markt: [tekst]} van de zwaarste gebeurtenissen in de 24 uur na het peilmoment."""
    uit = {}
    for g in gebeurtenissen:
        try:
            t = datetime.fromisoformat(g["date"])
            valuta, titel, impact = g["country"], str(g["title"])[:100], g["impact"]
        except (KeyError, TypeError, ValueError):
            continue
        if impact == "High" and t.tzinfo is not None and peil <= t <= peil + VENSTER:
            tekst = f"{valuta} {titel} om {t.astimezone(timezone.utc):%H:%M} UTC"
            for markt in MARKTEN.get(valuta, ()):
                uit.setdefault(markt, []).append(tekst)
    return uit
