"""python -m marktradar [--droog] [--uit MAP] [--melden].

Met --uit: een bestaande ronde van vandaag wordt niet opnieuw gedraaid (dat kost niets), oude voorspellingen worden
afgerekend en dashboard.json wordt bijgewerkt. Met --melden gaat de kern naar ntfy (onderwerp in NTFY_TOPIC).
"""
import argparse
import os
import sys
from datetime import datetime, timezone

from . import melding, opslag


def _dashboard(ronde, map_):
    from . import afrekening
    velden = ("ronde_id", "peilmoment", "status", "oordelen", "ontbreekt", "briefing", "kosten_usd", "modellen", "toelichting")
    return dict(laatste={k: ronde.get(k) for k in velden}, scorekaart=afrekening.scorekaart(opslag.lees_uitkomsten(map_)),
                kosten_per_maand=opslag.kosten_per_maand(map_), min_voorspellingen=afrekening.MIN_VOORSPELLINGEN, min_dagen=afrekening.MIN_DAGEN)


def _na_afloop(ronde, map_, ophalen):
    from . import afrekening, koersen as kz
    try:
        koersen, _ = kz.opschonen(ophalen(), ronde["peilmoment"])
        print(f"Afgerekend: {afrekening.reken_af(map_, koersen)} voorspellingen")
    except Exception as e:      # de ronde staat al veilig; afrekenen lukt de volgende keer
        print(f"Afrekenen mislukt ({type(e).__name__})", file=sys.stderr)
    opslag.bewaar_dashboard(map_, _dashboard(ronde, map_))


def main(argv=None, env=os.environ):
    p = argparse.ArgumentParser(prog="marktradar", description="MarktRadar. Alleen advies, geen financieel advies.")
    p.add_argument("--droog", action="store_true", help="draai met testdata, zonder netwerk en sleutels")
    p.add_argument("--uit", help="map voor rondes, kosten, metingen en uitkomsten")
    p.add_argument("--melden", action="store_true", help="stuur de kern naar ntfy")
    a = p.parse_args(argv)
    if a.droog:
        from . import droog
        ronde = droog.draai()
    else:
        vandaag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if a.uit and opslag.rondepad(a.uit, vandaag).exists():
            print(f"Ronde {vandaag} bestaat al; niets gedraaid.")
            return 0
        from . import echt      # laadt pandas en yfinance; de droge ronde heeft die niet nodig
        ronde = echt.draai(map_=a.uit)
    print(ronde["briefing"])
    if a.uit:
        try:
            print(f"Opgeslagen: {opslag.bewaar(ronde, a.uit)}")
        except FileExistsError as e:
            print(f"Niet opgeslagen, ronde bestaat al: {e.filename}", file=sys.stderr)
            return 1
        if not ronde["droog"]:
            from . import koersen as kz
            _na_afloop(ronde, a.uit, kz.download)
    if a.melden:
        print("Melding verstuurd." if melding.stuur(ronde, env.get("NTFY_TOPIC")) else "Geen melding verstuurd.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
