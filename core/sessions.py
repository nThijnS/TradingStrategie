"""Tijdzones en handelssessies (NY-tijd)."""
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
NL = ZoneInfo("Europe/Amsterdam")
SESS_NAMES = ["London", "NY AM", "NY PM"]     # zelfde volgorde als CFG["trade_sess"] en CFG["sb_sess"]


def in_sess(ts, sess):
    """sess is een (start, eind) of een lijst daarvan."""
    if isinstance(sess, list):
        return any(in_sess(ts, s) for s in sess)
    start, end = sess
    hm = ts.strftime("%H:%M")
    return start <= hm < end if end != "23:59" else start <= hm <= end


def sess_name(t):
    hm = t.strftime("%H:%M")
    return "London" if hm < "09:00" else "NY AM" if hm < "12:00" else "NY PM"
