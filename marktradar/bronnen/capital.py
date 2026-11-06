"""Klantsentiment van Capital.com, alleen lezen, alleen op de demo-host.

Deze client kan precies twee dingen: inloggen en sentiment opvragen. Hij hergebruikt de brokerclient bewust niet,
omdat MarktRadar niets uit execution/ mag laden. EPICS moet gelijk blijven aan execution/markets.py (getest).
De API geeft alleen de huidige stand, dus historie ontstaat alleen door zelf op te slaan.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

BASIS = "https://demo-api-capital.backend-capital.com/api/v1"
EPICS = {"GOUD": "GOLD", "ZILVER": "SILVER", "OLIE": "OIL_CRUDE", "NQ": "US100", "ES": "US500", "DAX": "DE40",
         "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY", "BTC": "BTCUSD", "ETH": "ETHUSD", "SOL": "SOLUSD",
         "AAPL": "AAPL", "NVDA": "NVDA", "MSFT": "MSFT"}


class GeenSleutels(RuntimeError):
    pass


def _urllib(methode, url, kop, inhoud):
    data = None if inhoud is None else json.dumps(inhoud).encode()
    req = urllib.request.Request(url, data=data, headers=dict(kop, **{"Content-Type": "application/json"}), method=methode)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r), dict(r.headers)


def lees(antwoord, t):
    """Zet het antwoord om in rijen. Waarden buiten 0-100 of onbekende markten vallen af."""
    terug = {e: m for m, e in EPICS.items()}
    rijen = []
    for x in antwoord.get("clientSentiments", ()):
        markt, long = terug.get(x.get("marketId")), x.get("longPositionPercentage")
        if markt and isinstance(long, (int, float)) and not isinstance(long, bool) and 0 <= long <= 100:
            rijen.append(dict(t=t, markt=markt, long=float(long)))
    return rijen


def haal(env=os.environ, stuur=_urllib):
    sleutel, wie, wachtwoord = (env.get(k) for k in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    if not (sleutel and wie and wachtwoord):
        raise GeenSleutels("geen Capital-sleutels")
    _, kop = stuur("POST", f"{BASIS}/session", {"X-CAP-API-KEY": sleutel}, dict(identifier=wie, password=wachtwoord))
    kop = {k.upper(): v for k, v in kop.items()}
    toegang = {"CST": kop["CST"], "X-SECURITY-TOKEN": kop["X-SECURITY-TOKEN"]}
    antwoord, _ = stuur("GET", f"{BASIS}/clientsentiment?marketIds={','.join(EPICS.values())}", toegang, None)
    return lees(antwoord, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
