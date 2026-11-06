"""Berichten van de Federal Reserve via RSS. Alleen titel, korte omschrijving, link en publicatietijd."""
import hashlib
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

FEEDS = ("https://www.federalreserve.gov/feeds/press_monetary.xml", "https://www.federalreserve.gov/feeds/speeches_and_testimony.xml")
HOST = "https://www.federalreserve.gov/"
MAX_TEKST = 1500


def _schoon(tekst):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", tekst or "")).strip()


def lees(xml):
    """Zet een RSS-feed om in berichten. Berichten zonder geldige tijd of met een vreemde link vallen af."""
    uit = []
    for item in ET.fromstring(xml).iter("item"):
        titel, link = _schoon(item.findtext("title")), (item.findtext("link") or "").strip()
        try:
            t = parsedate_to_datetime(item.findtext("pubDate") or "").astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        if titel and link.startswith(HOST):
            uit.append(dict(id=hashlib.sha1(link.encode()).hexdigest()[:10], naam="Federal Reserve", titel=titel[:300],
                            tekst=_schoon(item.findtext("description"))[:MAX_TEKST], url=link,
                            tijdstip=t.strftime("%Y-%m-%dT%H:%M:%SZ")))
    return uit


def haal():
    uit = {}
    for url in FEEDS:
        req = urllib.request.Request(url, headers={"User-Agent": "MarketPilot-MarktRadar"})
        with urllib.request.urlopen(req, timeout=20) as r:
            uit.update({b["id"]: b for b in lees(r.read())})
    return list(uit.values())
