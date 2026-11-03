"""Handelsuren per marktsoort: één definitie voor het dashboard (is de markt open?) en de orderuitvoering
(wanneer moet een lab-trade uiterlijk dicht?).

De regels zijn die van het dashboard (dashboard/status.py, sinds versie 3.0). Ze gaan over de beurs of de
bron van de data (Yahoo), niet over de CFD bij Capital.com. Of de broker de markt echt open heeft, controleert
execution/runner.py per order (marketStatus = TRADEABLE). Feestdagen staan hier niet in; dan meldt de broker de
markt als dicht en komt er geen order.

  crypto            altijd open
  aandeel           ma-vr 09:30-16:00 New York
  DAX               ma-vr 09:00-17:30 Frankfurt (eerder als 03:00-11:30 New York; dat klopte niet in de weken
                    dat de zomertijd in Europa en de VS op een andere datum wisselt)
  futures en forex  zondag 18:00 t/m vrijdag 17:00 New York, dagelijks dicht 17:00-18:00
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
FRANKFURT = ZoneInfo("Europe/Berlin")


def _day_session(soort, naam):
    """(tijdzone, open, dicht) voor markten die elke werkdag sluiten; None voor de andere."""
    if soort == "aandeel":
        return NY, time(9, 30), time(16, 0)
    if naam == "DAX":
        return FRANKFURT, time(9, 0), time(17, 30)
    return None


def is_open(soort, naam, now):
    if soort == "crypto":
        return True
    day = _day_session(soort, naam)
    if day:
        tz, a, b = day
        t = now.astimezone(tz)
        return t.weekday() < 5 and a <= t.time() < b
    t = now.astimezone(NY)
    wd, hm = t.weekday(), t.strftime("%H:%M")
    if wd == 5 or (wd == 6 and hm < "18:00") or (wd == 4 and hm >= "17:00"):
        return False
    return not ("17:00" <= hm < "18:00")


def session_end(soort, naam, now):
    """Wanneer sluit de markt die nu open is voor langer dan een paar uur (beursslot of weekend)? Daar sluit de
    backtest een lab-trade (strategies/lab.GAP_HOURS), dus daar moet de demo-positie ook dicht. None = sluit niet
    (crypto) of de markt is nu dicht. De dagelijkse pauze van een uur bij futures en forex telt niet mee."""
    if soort == "crypto" or not is_open(soort, naam, now):
        return None
    day = _day_session(soort, naam)
    if day:
        tz, _, b = day
        t = now.astimezone(tz)
        return datetime.combine(t.date(), b, tz)
    t = now.astimezone(NY)
    friday = t.date() + timedelta(days=(4 - t.weekday()) % 7)
    return datetime.combine(friday, time(17, 0), NY)
