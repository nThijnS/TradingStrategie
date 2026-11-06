"""Korte ntfy-melding met de kern van de briefing. Een mislukte melding stopt niets."""
import re
import urllib.request

MAX_TEKENS = 3000


def kern(ronde):
    regels = [ronde["toelichting"]["samenvatting"]] if (ronde.get("toelichting") or {}).get("samenvatting") else []
    actie = [o for o in ronde["oordelen"] if o["oordeel"] != "GEEN_ACTIE"]
    for o in actie:
        regels.append(f"{o['markt']}: {o['oordeel']} ({o['richting']}, zekerheid {o['zekerheid']:.2f}). {o['reden']}")
    rust = len(ronde["oordelen"]) - len(actie)
    regels.append(f"Geen actie op {rust} van {len(ronde['oordelen'])} markten." if ronde["oordelen"] else "Geen markten bekeken.")
    if ronde["ontbreekt"]:
        regels.append(f"Ontbreekt: {len(ronde['ontbreekt'])} punten, zie het dashboard.")
    regels.append(f"Kosten vandaag: ${ronde['kosten_usd']:.2f}.")
    regels.append("Geen financieel advies.")
    return "\n".join(regels)[:MAX_TEKENS]


def _post(url, tekst, kop):
    req = urllib.request.Request(url, data=tekst.encode(), method="POST", headers=kop)
    urllib.request.urlopen(req, timeout=10).close()


def stuur(ronde, onderwerp, post=None):
    """Geeft True als de melding is verstuurd. Een droge ronde gaat nooit naar de telefoon."""
    if ronde["droog"] or not onderwerp or not re.fullmatch(r"[\w-]{1,64}", onderwerp):
        return False
    try:
        (post or _post)(f"https://ntfy.sh/{onderwerp}", kern(ronde), {"Title": f"MarktRadar {ronde['ronde_id']}", "Tags": "radar"})
        return True
    except Exception:       # alleen niet verstuurd: het onderwerp is geheim en mag niet in een foutmelding komen
        return False
