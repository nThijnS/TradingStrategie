"""Schrijft de live data voor het dashboard (docs/index.html en het artifact).

status.json        botstatus, ICT-setups van vandaag, alle gevolgde markten (koers, conditie, datakwaliteit,
                   signalen van de strategie die het strategielab koos) en fouten.
markt/<NAAM>.json  candles per timeframe (5m, 15m, 1h, 4h, 1d) plus setups en signalen voor op de grafiek.

Plaatst nooit een order: het leest alleen data en de keuzes van de bot. De cloud draait dit elke 3 minuten
en zet het op de branch "live"; dataverwerking (leren.py, strategielab.py) staat daar los van.

    python live_status.py              # schrijft status.json en markt/ naast dit script
    python live_status.py --uit X.json # status naar X.json, markt/ in dezelfde map
"""
import argparse
import json
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import strategielab as lab
import tradingstrategie as ts

HERE = ts.HERE
NL = ts.ZoneInfo("Europe/Amsterdam")
FRESH_MIN = 20                     # ouder dan dit (tijdens een sessie) = "vertraagd"
CLOSED = ("stop", "TP", "dicht 16:00")
CACHE = HERE / ".cache_live"       # zodat 1h- en dagdata niet elke 3 minuten opnieuw worden opgehaald
TTL = {"5m": 0, "1h": 10 * 60, "1d": 60 * 60}
PERIOD = {"5m": "5d", "1h": "60d", "1d": "2y"}
KEEP = 300                         # candles per timeframe in markt/<NAAM>.json
SOURCE = "Yahoo Finance (gratis; futures en aandelen kunnen 10-15 min vertraagd zijn)"

# Versiegeschiedenis van het dashboard en de bot (nieuwste bovenaan)
APP_VERSIONS = [
    dict(versie="3.0", datum="2026-10-31", wat="Zes onderdelen, 15 markten, strategielab met 6 strategieën en walk-forward, candlestick-grafieken, Data Farm en Risk Center."),
    dict(versie="2.0", datum="2026-10-31", wat="Radar-dashboard: signalen van vandaag met positiegrootte voor de prop firm."),
    dict(versie="1.2", datum="2026-10-30", wat="Zelflerend: leren.py kiest elke werkdag per markt de beste ICT-variant."),
    dict(versie="1.1", datum="2026-10-30", wat="Logboek met elke setup en weigering (forward test)."),
    dict(versie="1.0", datum="2026-10-27", wat="ICT-meldingen op je telefoon via ntfy, in de cloud."),
]


# ------------- Bestaand: ICT-markten -------------
def session_now(now):
    """Welke sessie loopt er (of None) en welke komt hierna, in NY-tijd."""
    names = dict(zip([tuple(s) for s in ts.CFG["trade_sess"]],
                     [n for n in ts.SESS_NAMES if ts.SET["sessies"].get(n, True)]))
    if now.weekday() < 5:
        for (a, b), n in names.items():
            if a <= now.strftime("%H:%M") < b:
                return n, None
    for d in range(8):
        day = (now + timedelta(days=d)).date()
        if day.weekday() >= 5:
            continue
        for (a, b), n in sorted(names.items()):
            start = datetime.combine(day, datetime.strptime(a, "%H:%M").time(), ts.NY)
            if start > now:
                return None, dict(naam=n, start=start.isoformat(), start_nl=start.astimezone(NL).strftime("%a %H:%M"))
    return None, None


def setup_status(df, s, now):
    res, r = ts.outcome(df, s)
    if res in CLOSED:
        return "afgerond", res, round(float(r), 2)
    if res == "loopt nog":
        return "actief", "in de trade", 0.0
    if s.get("missed"):
        return "verlopen", s["missed"], 0.0
    return ("nieuw" if now - s["time"] < timedelta(minutes=15) else "wacht op entry"), "wacht op entry", 0.0


def forward_test(book, name):
    rows = [x for x in book.values() if x["markt"] == name and x["type"] == "setup"]
    done = [x for x in rows if x["uitkomst"] in CLOSED]
    good = [x for x in done if x["kans"]]
    refs = [x for x in book.values() if x["markt"] == name and x["type"] == "weigering"]
    recent = sorted(rows, key=lambda x: x["tijd"], reverse=True)[:8]
    return dict(setups=len(rows), afgerond=len(done), win=sum(x["R"] > 0 for x in done), R=round(sum(x["R"] for x in done), 2),
                kans_afgerond=len(good), kans_R=round(sum(x["R"] for x in good), 2), weigeringen=len(refs),
                sinds=min((x["tijd"] for x in rows), default=None),
                laatste=[dict(tijd=x["tijd"], kant=x["kant"], kans=x["kans"], uitkomst=x["uitkomst"], R=x["R"],
                              entry=x["entry"], stop=x["stop"], tp=x["tp"]) for x in recent])


def market_status(m, book, learned, now):
    out = dict(naam=m["name"], symbool=m["symbol"], dec=m["dec"], actief=bool(m.get("actief", True)),
               variant=m.get("variant"), keuze=learned.get(m["name"]), fout=None)
    refs = []
    try:
        df, setups, _ = ts.analyse_market(m, refusals=refs)
    except Exception as ex:   # geen data: tonen als fout, nooit als signaal
        out["fout"] = f"geen data: {ex}"
        out["forward"] = forward_test(book, m["name"])
        return out
    last_t = df.index[-1]
    prev = df[df.index.date < now.date()]
    close, ref = float(df["Close"].iloc[-1]), float(prev["Close"].iloc[-1]) if len(prev) else None
    age = (now - (last_t + ts.BAR)).total_seconds() / 60
    off = ts.alt_offset(m, df)
    out.update(koers=round(close, m["dec"]), verandering=round((close / ref - 1) * 100, 2) if ref else None,
               laatste_candle=last_t.isoformat(), data_min_oud=round(age), candles=len(df),
               alt=dict(label=m["alt"]["label"], verschil=round(off, m["dec"])) if off is not None else None,
               chart=[[t.isoformat(), round(float(c), m["dec"])] for t, c in df["Close"].iloc[-120:].items()])
    today = []
    for s in setups:
        if s["time"].date() != now.date():
            continue
        st, uitleg, r = setup_status(df, s, now)
        today.append(dict(tijd=s["time"].isoformat(), sessie=ts.sess_name(s["time"]), kant=s["side"], grade=s["grade"],
                          score=int(s["score"]), kans=bool(s["good"]), tegen_bias=bool(ts.against_bias(s)),
                          entry=round(float(s["entry"]), m["dec"]), stop=round(float(s["stop"]), m["dec"]),
                          tp=round(float(s["tp"]), m["dec"]), rr=round(float(s["rr"]), 2), sweep=s["sweep"],
                          redenen=[k for k, v in s["checks"].items() if v], missend=[k for k, v in s["checks"].items() if not v],
                          status=st, uitleg=uitleg, R=r, telt=bool(s["good"] and out["actief"])))
    out["setups"] = today
    out["weigeringen_vandaag"] = [dict(tijd=f["time"].isoformat(), kant=f["side"], reden=f["reason"])
                                  for f in refs if f["time"].date() == now.date()][-6:]
    out["forward"] = forward_test(book, m["name"])
    return out


# ------------- Alle markten (Data Farm) -------------
def fetch_cached(tf):
    """Alle markten in één keer ophalen per timeframe, met een korte cache. Geeft (data, tijdstip, fout)."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{tf}.pkl"
    if f.exists() and time.time() - f.stat().st_mtime < TTL[tf]:
        try:
            return pickle.loads(f.read_bytes())
        except Exception:
            pass
    try:
        data = lab.fetch_all(lab.MARKETS, interval=tf, period=PERIOD[tf])
        res = (data, datetime.now(ts.NY).isoformat(timespec="seconds"), None)
    except Exception as ex:
        if f.exists():   # oude data tonen, maar met de fout erbij
            old = pickle.loads(f.read_bytes())
            return old[0], old[1], f"{type(ex).__name__}: {ex}"
        return {}, None, f"{type(ex).__name__}: {ex}"
    f.write_bytes(pickle.dumps(res))
    return res


def is_open(soort, naam, now):
    """Is de markt nu open (NY-tijd)? Feestdagen worden niet herkend."""
    wd, hm = now.weekday(), now.strftime("%H:%M")
    if soort == "crypto":
        return True
    if soort == "aandeel":
        return wd < 5 and "09:30" <= hm < "16:00"
    if naam == "DAX":
        return wd < 5 and "03:00" <= hm < "11:30"
    # futures en forex: zondag 18:00 t/m vrijdag 17:00, dagelijks een uur pauze
    if wd == 5 or (wd == 6 and hm < "18:00") or (wd == 4 and hm >= "17:00"):
        return False
    return not ("17:00" <= hm < "18:00")


def resample(df, rule):
    offset = "2h" if rule == "4h" else None
    return df.resample(rule, offset=offset, label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()


def candles(df, dec):
    return [[int(t.timestamp()), round(float(r.Open), dec), round(float(r.High), dec), round(float(r.Low), dec),
             round(float(r.Close), dec)] for t, r in df.iloc[-KEEP:].iterrows()]


def decimals(price):
    return 5 if price < 5 else 3 if price < 200 else 2


def lab_signals(m, df1h, choice, market_open=True):
    """Signalen van de strategie die het lab koos, op de nieuwste 1-uurs candles (papertrades)."""
    sid = (choice or {}).get("strategie")
    if not sid or sid == "ict" or len(df1h) < 300:
        return []
    X = lab.indicators(df1h)
    up, dn, stopd, target = lab.signals(sid, X, choice["variant"])
    out = []
    for x in lab.simulate(X, up, dn, stopd, target, m["kosten"]):
        if x["t"] < X.index[-1] - pd.Timedelta(hours=36):
            continue
        out.append(dict(t=x["t"].isoformat(), kant=x["kant"], entry=x["entry"], stop=x["stop"], tp=x["tp"], rr=round(x["rr"], 2),
                        status=("actief" if market_open else "markt dicht") if x["open"] else "afgerond",
                        R=None if x["open"] else round(x["R"], 2)))
    # signaal op de laatst gesloten candle: instap bij de open van de volgende
    for arr, side in ((up, 1), (dn, -1)) if market_open else ():
        if bool(arr.fillna(False).iloc[-1]) and float(stopd.iloc[-1]) > 0:
            e, r = float(X["c"].iloc[-1]), float(stopd.iloc[-1])
            tp = e + side * target[1] * r if target[0] == "R" else float(X["mid"].iloc[-1])
            out.append(dict(t=(X.index[-1] + pd.Timedelta(hours=1)).isoformat(), kant="LONG" if side > 0 else "SHORT",
                            entry=e, stop=e - side * r, tp=tp, rr=round(abs(tp - e) / r, 2), status="nieuw", R=None))
    return out[-4:]


def all_markets(now, outdir, ict):
    labdata = lab.load(lab.LAB, {})
    by_lab = {m["naam"]: m for m in labdata.get("markten", [])}
    frames = {tf: fetch_cached(tf) for tf in ("5m", "1h", "1d")}
    errors = [f"{tf}: {e}" for tf, (_, _, e) in frames.items() if e]
    (outdir / "markt").mkdir(exist_ok=True)
    rows = []
    for m in lab.MARKETS:
        row = dict(naam=m["naam"], titel=m["titel"], soort=m["soort"], symbool=m["symbool"], bron=SOURCE,
                   open=is_open(m["soort"], m["naam"], now), timeframes={}, fout=None)
        clean = {}
        for tf, (data, fetched, err) in frames.items():
            df, q = lab.clean(data.get(m["naam"], pd.DataFrame(columns=["Open", "High", "Low", "Close"])))
            clean[tf] = df
            row["timeframes"][tf] = dict(q, opgehaald=fetched, fout=err)
        d5 = clean["5m"]
        if not len(d5):
            row["fout"] = "geen 5m-data ontvangen"
            row["status"] = "storing"
            rows.append(row)
            continue
        last = d5.index[-1]
        age = (now - (last.tz_convert(ts.NY) + timedelta(minutes=5))).total_seconds() / 60
        price = float(d5["Close"].iloc[-1])
        dec = decimals(price)
        d1 = clean["1d"]
        prevc = float(d1["Close"].iloc[-2]) if len(d1) >= 2 else None
        row.update(koers=round(price, dec), dec=dec, laatste_candle=last.isoformat(), data_min_oud=max(0, round(age)),
                   verandering=round((price / prevc - 1) * 100, 2) if prevc else None,
                   status="dicht" if not row["open"] else "vertraagd" if age > 25 else "live" if age <= 25 else "storing")
        if row["open"] and age > 120:
            row["status"] = "storing"
        lm = by_lab.get(m["naam"], {})
        choice = lm.get("keuze")
        row["regime"] = lm.get("regime")
        row["keuze"] = dict(strategie=choice.get("strategie"), titel=choice.get("titel"), variant_txt=choice.get("variant_txt"),
                            sinds=choice.get("sinds"), reden=choice.get("reden_vandaag")) if choice else None
        sig = []
        try:
            sig = lab_signals(m, clean["1h"], choice, row["open"]) if row["status"] != "storing" else []
        except Exception as ex:
            row["fout"] = f"signalen: {ex}"
        row["signalen"] = sig
        row["ict"] = m["naam"] in ict
        # grafiekdata in een eigen bestand
        charts = {"5m": d5, "15m": resample(d5, "15min"), "1h": clean["1h"], "4h": resample(clean["1h"], "4h"), "1d": d1}
        (outdir / "markt" / f"{m['naam']}.json").write_text(json.dumps(dict(
            naam=m["naam"], gemaakt=now.isoformat(timespec="seconds"), dec=dec,
            candles={tf: candles(df, dec) for tf, df in charts.items() if len(df)},
            signalen=sig, ict_setups=ict.get(m["naam"], {}).get("setups", []),
            lab_laatste=lm.get("laatste_signalen", [])), separators=(",", ":")))
        rows.append(row)
    return rows, errors, labdata.get("gemaakt")


def build(outdir=HERE):
    ts.apply_settings()
    now = datetime.now(ts.NY)
    try:
        learned = json.loads(ts.LEARNED_FILE.read_text())
    except (OSError, ValueError):
        learned = {}
    try:
        history = json.loads((HERE / "leren_geschiedenis.json").read_text())[-10:]
    except (OSError, ValueError):
        history = []
    book = ts.load_logbook()
    sess, nxt = session_now(now)
    markets = [market_status(m, book, learned.get("markten", {}), now) for m in ts.CFG["markets"]]
    ict = {m["naam"]: m for m in markets}
    names = [n for n in ts.SESS_NAMES if ts.SET["sessies"].get(n, True)]
    nl = lambda hm: datetime.combine(now.date(), datetime.strptime(hm, "%H:%M").time(), ts.NY).astimezone(NL).strftime("%H:%M")
    sessions = [dict(naam=n, nl=f"{nl(a)}–{nl(b)}") for n, (a, b) in zip(names, ts.CFG["trade_sess"])]
    try:
        alle, errors, lab_made = all_markets(now, Path(outdir), ict)
    except Exception as ex:   # de ICT-status moet blijven werken, ook als dit deel faalt
        alle, errors, lab_made = [], [f"alle markten: {type(ex).__name__}: {ex}"], None
    errors += [f"{m['naam']}: {m['fout']}" for m in markets if m.get("fout")]
    return dict(gemaakt=now.isoformat(timespec="seconds"), sessie=sess, volgende=nxt, sessies=sessions,
                meldingen_aan=bool(ts.SET["actief"]), vers_min=FRESH_MIN, geleerd_op=learned.get("bijgewerkt"),
                lab_gemaakt=lab_made, leren=history, markten=markets, alle_markten=alle, fouten=errors,
                logboek_regels=len(book), versies=APP_VERSIONS, modus="alleen analyse en papertrades: er worden nooit orders geplaatst")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uit", default=str(HERE / "status.json"))
    a = ap.parse_args()
    out = Path(a.uit)
    data = build(out.parent)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"{out}: {len(data['markten'])} ICT-markten, {len(data['alle_markten'])} markten, sessie {data['sessie'] or '-'}, "
          f"{sum(len(m.get('setups', [])) for m in data['markten'])} setups vandaag, {len(data['fouten'])} fouten")
