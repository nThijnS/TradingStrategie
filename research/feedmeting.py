#!/usr/bin/env python3
"""Alleen-lezen meting van de Capital.com-feed (demo). Plaatst geen orders en wijzigt niets op het account.

    python -W ignore -m research.feedmeting meet --minuten 20 --uit rapport/feedmeting.json   (workflow Feedmeting)
    python -W ignore -m research.feedmeting vergelijk rapport/feedmeting.json                  (lokaal, met HistData)

Wat er gemeten wordt:
- Historie: hoe ver 15m-, 5m- en 1m-candles teruggaan, en de spread per uur uit de bid/ask van uurcandles.
- Candles: tijdzone, candlegrenzen en prijsverschil met Yahoo (en lokaal met HistData).
- Live: koersleeftijd, status en spread (REST) en, als `websockets` beschikbaar is, updates, gaten, dubbele updates,
  herverbindingen en het sluiten van 1m-candles.

Elke markt krijgt per onderdeel een oordeel. Verouderde of onvolledige data of een verbroken verbinding maakt de feed
"onbruikbaar" (feed_health). Een bruikbare feed rechtvaardigt nooit op zichzelf een order: hij kan hoogstens de koers
leveren voor een signaal dat al door de poort is.

Veiligheid: ReadOnly laat alleen GET door. Sleutels en tokens komen niet in logs of uitvoer (scrub).
"""
import argparse
import asyncio
import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from core import market_hours
from core.markets import LAB_MARKETS
from execution.capital import Capital
from execution.markets import EPICS
from risk.rules import Limits

SOORT = {m["naam"]: m["soort"] for m in LAB_MARKETS}
SYMBOL = {m["naam"]: m["symbool"] for m in LAB_MARKETS}
PROBE_DAYS = (30, 90, 180, 365, 730)
RESOLUTIONS = ("MINUTE_15", "MINUTE_5", "MINUTE")
WS_URLS = ("wss://api-streaming-capital.backend-capital.com/connect", "wss://demo-api-streaming-capital.backend-capital.com/connect")
MAX_AGE_S = Limits().max_koers_leeftijd_s
MAX_GAP_S = 120          # markt open en zo lang geen koers: gat
MAX_MISSING_PCT = 1.0
MAX_BASIS_LAG_MIN = 0    # candletijden moeten zonder verschuiving op de onderzoeksdata aansluiten
SECRET_RE = re.compile(r"(?i)(cst|x-security-token|x-cap-api-key|securitytoken|password|identifier)[\"':= ]+[^\s,\"'}]+")
SCRUB = ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD")


def scrub(text, secrets=()):
    """Foutmelding zonder sleutels of tokens."""
    text = SECRET_RE.sub(lambda m: f"{m.group(1)}=***", str(text))
    for s in list(secrets) + [os.environ.get(k) for k in SCRUB]:
        if s:
            text = text.replace(s, "***")
    return text[:300]


class ReadOnly:
    """Alleen GET. Er is hier bewust geen enkele weg naar orders, posities of accountwijzigingen."""

    def __init__(self, client):
        self._c = client

    def get(self, path):
        return self._c.call("GET", path)

    @property
    def tokens(self):
        return list(self._c.h.values())


# ------------- Oordeel -------------
def feed_health(row, open_):
    """row: dict met metingen van één markt. open_: was de markt volgens de handelsuren open tijdens de meting?
    Geeft dict(oordeel, redenen). Ontbrekende metingen tellen als onbruikbaar: geen bewijs is geen goedkeuring."""
    if not open_:
        return dict(oordeel="niet gemeten", redenen=["markt dicht tijdens de meting"])
    why = []
    if not row.get("rest_metingen"):
        why.append("geen REST-koersen ontvangen")
    if (row.get("vertraging_max") or 0) > 0:
        why.append("broker meldt vertraagde koers")
    if row.get("max_leeftijd_s") is None:
        why.append("koersleeftijd onbekend")
    elif row["max_leeftijd_s"] > MAX_AGE_S:
        why.append(f"koers tot {row['max_leeftijd_s']:.0f} s oud (max {MAX_AGE_S})")
    if row.get("niet_verhandelbaar"):
        why.append(f"{row['niet_verhandelbaar']} metingen niet TRADEABLE")
    ws = row.get("ws")
    if ws is None:
        why.append("geen streamingmeting")
    else:
        if not ws.get("updates"):
            why.append("geen streaming-updates")
        if ws.get("grootste_gat_s", 0) > MAX_GAP_S:
            why.append(f"streaminggat van {ws['grootste_gat_s']:.0f} s")
        if (ws.get("ontbrekende_candles_pct") or 0) > MAX_MISSING_PCT:
            why.append(f"{ws['ontbrekende_candles_pct']:.1f}% 1m-candles ontbreekt")
        if ws.get("verbroken"):
            why.append(f"verbinding {ws['verbroken']} keer verbroken")
    return dict(oordeel="onbruikbaar" if why else "bruikbaar", redenen=why)


# ------------- Candles -------------
def candles(payload):
    """Capital /prices -> DataFrame (UTC) met mid-OHLC en spread. Tijd = snapshotTimeUTC: de start van de candle."""
    rows = []
    for p in payload.get("prices", []):
        try:
            o, h, l, c = (p[k] for k in ("openPrice", "highPrice", "lowPrice", "closePrice"))
            rows.append(dict(t=pd.Timestamp(p["snapshotTimeUTC"], tz="UTC"), Open=(o["bid"] + o["ask"]) / 2, High=(h["bid"] + h["ask"]) / 2,
                             Low=(l["bid"] + l["ask"]) / 2, Close=(c["bid"] + c["ask"]) / 2, spread=c["ask"] - c["bid"]))
        except (KeyError, TypeError):
            continue
    df = pd.DataFrame(rows)
    return df.set_index("t").sort_index() if len(df) else df


def spread_by_hour(df):
    """Mediane spread in procent per UTC-uur."""
    if not len(df):
        return {}
    pct = df["spread"] / df["Close"] * 100
    return {int(k): round(float(v), 5) for k, v in pct.groupby(pct.index.hour).median().items()}


def compare(a, b, lags=(-120, -60, 0, 60, 120)):
    """Twee candlereeksen vergelijken: welke tijdverschuiving past het best en hoe groot is het prijsverschil?
    Beste verschuiving = de laagste mediane afwijking van het rendement. Bij 0 sluiten de candletijden aan."""
    if not len(a) or not len(b):
        return dict(gedeeld=0)
    best, out = None, None
    for lag in lags:
        x = a.copy()
        x.index = x.index + pd.Timedelta(minutes=lag)
        idx = x.index.intersection(b.index)
        if len(idx) < 10:
            continue
        ra, rb = x["Close"].reindex(idx).pct_change(), b["Close"].reindex(idx).pct_change()
        err = float((ra - rb).abs().median())
        if best is None or err < best:
            basis = (x["Close"].reindex(idx) / b["Close"].reindex(idx) - 1) * 100
            best, out = err, dict(gedeeld=len(idx), beste_verschuiving_min=lag, mediaan_rendementsverschil_pct=round(err * 100, 5),
                                  basis_mediaan_pct=round(float(basis.median()), 4), basis_spreiding_pct=round(float(basis.std()), 4))
    return out or dict(gedeeld=0)


def boundaries_ok(df, minutes):
    """Beginnen alle candles precies op een veelvoud van de candlelengte?"""
    if not len(df):
        return None
    seconds = (df.index - pd.Timestamp("1970-01-01", tz="UTC")).total_seconds()
    return bool((seconds % (minutes * 60) == 0).all())


def history(ro, epic, now):
    """Hoe ver gaat elke resolutie terug? Vraagt een klein venster op vaste afstanden in het verleden."""
    out = {}
    for res in RESOLUTIONS:
        depth = 0
        for d in PROBE_DAYS:
            start = now - timedelta(days=d)
            q = f"/prices/{epic}?resolution={res}&max=20&from={start:%Y-%m-%dT%H:%M:%S}&to={start + timedelta(days=3):%Y-%m-%dT%H:%M:%S}"
            try:
                if ro.get(q).get("prices"):
                    depth = d
            except Exception:       # geen data op die afstand of geweigerd: telt als niet beschikbaar
                pass
        out[res] = depth
    return out


# ------------- Live -------------
class Stream:
    """Verwerkt streamingberichten per epic. Bewaart alleen tellers en tijden, nooit ruwe berichten."""

    def __init__(self, epics):
        self.q = {e: dict(n=0, dubbel=0, terug=0, last=None, last_ts=None, gap=0.0, onbekend=0) for e in epics}
        self.bars = defaultdict(set)
        self.bar_seen = {}
        self.shapes = Counter()
        self.verbroken = 0

    def handle(self, msg, now_s):
        dest = msg.get("destination")
        self.shapes[dest] += 1
        p = msg.get("payload") or {}
        e = p.get("epic")
        if e not in self.q:
            return
        if dest == "quote":
            s = self.q[e]
            bid, ask, ts = p.get("bid"), p.get("ofr", p.get("ask")), p.get("timestamp")
            key = (bid, ask, ts)
            if s["last_ts"] is not None and ts is not None and ts < s["last_ts"]:
                s["terug"] += 1
            if s["last"] == key:
                s["dubbel"] += 1
            if s.get("seen") is not None:
                s["gap"] = max(s["gap"], now_s - s["seen"])
            s.update(n=s["n"] + 1, last=key, last_ts=ts, seen=now_s)
        elif dest == "ohlc.event" and p.get("resolution") == "MINUTE" and p.get("t") is not None:
            t = int(p["t"] // 1000)
            self.bars[e].add(t)
            self.bar_seen.setdefault((e, t), now_s)

    def summary(self, epic, minutes):
        s = self.q[epic]
        bars = sorted(self.bars[epic])
        missing = None
        if len(bars) >= 2:
            want = (bars[-1] - bars[0]) // 60 + 1
            missing = round((1 - len(bars) / want) * 100, 2)
        return dict(updates=s["n"], per_minuut=round(s["n"] / max(minutes, 1), 1), dubbel=s["dubbel"], terug_in_tijd=s["terug"],
                    grootste_gat_s=round(s["gap"], 1), candles_1m=len(bars), ontbrekende_candles_pct=missing, verbroken=self.verbroken)


async def stream_once(url, tokens, epics, st, seconds):
    import websockets
    corr = 0

    def msg(dest, payload=None):
        nonlocal corr
        corr += 1
        return json.dumps(dict(destination=dest, correlationId=str(corr), cst=tokens["CST"], securityToken=tokens["X-SECURITY-TOKEN"], payload=payload or {}))

    async with websockets.connect(url, open_timeout=15, ping_interval=None) as ws:
        await ws.send(msg("marketData.subscribe", dict(epics=epics)))
        await ws.send(msg("OHLCMarketData.subscribe", dict(epics=epics, resolutions=["MINUTE"], type="classic")))
        end, ping = time.monotonic() + seconds, time.monotonic() + 300
        while time.monotonic() < end:
            if time.monotonic() > ping:
                await ws.send(msg("ping"))
                ping = time.monotonic() + 300
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                continue
            st.handle(json.loads(raw), time.monotonic())


async def stream(tokens, epics, st, seconds):
    """Probeert de streamingadressen op volgorde en verbindt opnieuw tot de meettijd op is. Geeft het gebruikte adres."""
    end, used, err = time.monotonic() + seconds, None, None
    while time.monotonic() < end:
        for url in WS_URLS if used is None else (used,):
            try:
                await stream_once(url, tokens, epics, st, end - time.monotonic())
                used = url
                break
            except Exception as ex:
                err = type(ex).__name__
                if sum(st.shapes.values()):
                    used = url
                    st.verbroken += 1
                    break
        else:
            return None, err
    return used, err


def poll(ro, epics, seconds, every=30):
    """REST: koersleeftijd, status, spread en vertraging per markt, elke `every` seconden."""
    rows = defaultdict(list)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        t0 = time.monotonic()
        for name, epic in epics.items():
            try:
                s = ro.get(f"/markets/{epic}").get("snapshot", {})
                now = datetime.now(timezone.utc)
                up = s.get("updateTimeUTC") or s.get("updateTime")
                age = (now - pd.Timestamp(up, tz="UTC").to_pydatetime()).total_seconds() if up and len(str(up)) > 8 else None
                bid, ask = s.get("bid"), s.get("offer")
                rows[name].append(dict(age=age, status=s.get("marketStatus"), delay=s.get("delayTime") or 0,
                                       spread_pct=(ask - bid) / ((ask + bid) / 2) * 100 if bid and ask else None))
            except Exception:
                rows[name].append(dict(age=None, status="FOUT", delay=0, spread_pct=None))
        await_s = every - (time.monotonic() - t0)
        if await_s > 0:
            time.sleep(await_s)
    return rows


def poll_summary(rows):
    ages = [r["age"] for r in rows if r["age"] is not None]
    sp = [r["spread_pct"] for r in rows if r["spread_pct"] is not None]
    return dict(rest_metingen=len(rows), max_leeftijd_s=round(max(ages), 1) if ages else None, mediaan_leeftijd_s=round(float(np.median(ages)), 1) if ages else None,
                niet_verhandelbaar=sum(r["status"] != "TRADEABLE" for r in rows), vertraging_max=max((r["delay"] for r in rows), default=0),
                spread_mediaan_pct=round(float(np.median(sp)), 5) if sp else None, spread_max_pct=round(max(sp), 5) if sp else None)


def measure(minutes, path):
    key, ident, pw = (os.environ.get(k) for k in SCRUB)
    client = Capital("demo", key, ident, pw)
    ro = ReadOnly(client)
    now = datetime.now(timezone.utc)
    out = dict(gemaakt=now.isoformat(timespec="seconds"), omgeving="demo (alleen lezen)", minuten=minutes, markten={})
    overlap = {}
    import yfinance as yf
    for name, epic in EPICS.items():
        row = dict(epic=epic)
        try:
            row["historie_dagen"] = history(ro, epic, now)
            h = candles(ro.get(f"/prices/{epic}?resolution=HOUR&max=1000"))
            row["spread_per_uur_pct"] = spread_by_hour(h)
            row["uurcandles"] = len(h)
            row["grenzen_ok"] = boundaries_ok(h, 60)
            y = yf.download(SYMBOL[name], interval="1h", period="60d", progress=False, auto_adjust=False)
            if len(y):
                y.columns = y.columns.get_level_values(0)
                y.index = y.index.tz_convert("UTC")
                row["tegen_yahoo_1h"] = compare(h, y)
            w = ro.get(f"/prices/{epic}?resolution=MINUTE_15&max=1000&from=2026-10-12T00:00:00&to=2026-10-23T20:00:00")
            overlap[name] = [[p["snapshotTimeUTC"], p["closePrice"]["bid"], p["closePrice"]["ask"]] for p in w.get("prices", [])]
        except Exception as ex:
            row["fout"] = scrub(f"{type(ex).__name__}: {ex}", ro.tokens)
        out["markten"][name] = row
    seconds = minutes * 60
    tokens = client.h
    st = Stream(list(EPICS.values()))
    url, err = None, None
    try:
        import websockets  # noqa: F401
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(1) as pool:
            fut = pool.submit(lambda: asyncio.run(stream(tokens, list(EPICS.values()), st, seconds)))
            rows = poll(ro, EPICS, seconds)
            url, err = fut.result()
    except ImportError:
        err, rows = "websockets niet geïnstalleerd", poll(ro, EPICS, seconds)
    out["stream"] = dict(adres=url, fout=scrub(err, ro.tokens) if err else None, soorten_berichten=dict(st.shapes), verbroken=st.verbroken)
    end = datetime.now(timezone.utc)
    for name, epic in EPICS.items():
        row = out["markten"][name]
        row.update(poll_summary(rows[name]))
        if url:
            row["ws"] = st.summary(epic, minutes)
        open_ = market_hours.is_open(SOORT[name], name, now) and market_hours.is_open(SOORT[name], name, end)
        row["markt_open"] = open_
        row["feed"] = feed_health(row, open_)
    out["overlap_15m"] = overlap
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print("Oordelen:", dict(Counter(r["feed"]["oordeel"] for r in out["markten"].values())), flush=True)


def compare_histdata(path):
    """Lokaal: de Capital-candles uit de meting tegen HistData op dezelfde dagen."""
    from core.data import load_histdata, resample
    from research.tijdframes import load_protocol
    proto, _ = load_protocol()
    res = {}
    overlap = json.load(open(path))["overlap_15m"]
    for name, spec in proto["markten"].items():
        rows = overlap.get(name) or []
        if not rows:
            res[name] = dict(gedeeld=0)
            continue
        a = pd.DataFrame([dict(t=pd.Timestamp(t, tz="UTC"), Close=(b + o) / 2) for t, b, o in rows]).set_index("t")
        h = resample(load_histdata(spec["histdata"]), "15min").tz_convert("UTC")
        res[name] = compare(a, h)
    print(json.dumps(res, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="stap", required=True)
    m = sub.add_parser("meet")
    m.add_argument("--minuten", type=int, default=20)
    m.add_argument("--uit", default="feedmeting.json")
    v = sub.add_parser("vergelijk")
    v.add_argument("bestand")
    a = ap.parse_args()
    if a.stap == "meet":
        try:
            measure(a.minuten, a.uit)
        except Exception as ex:
            raise SystemExit(f"Feedmeting mislukt: {scrub(f'{type(ex).__name__}: {ex}')}") from None
    else:
        compare_histdata(a.bestand)


if __name__ == "__main__":
    main()
