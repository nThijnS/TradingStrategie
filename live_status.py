"""Schrijft status.json voor het live dashboard (docs/index.html en het artifact).

Per markt: laatste koers, verandering vandaag, hoe oud de data is, wat leren.py heeft gekozen,
de setups van vandaag met hun status en de forward-test uit het logboek. Plaatst nooit een order:
het leest alleen data en de keuzes van de bot.

    python live_status.py              # schrijft status.json
    python live_status.py --uit X.json # ander bestand
"""
import argparse
import json
from datetime import datetime, timedelta

import tradingstrategie as ts

HERE = ts.HERE
NL = ts.ZoneInfo("Europe/Amsterdam")
FRESH_MIN = 20                     # ouder dan dit (tijdens een sessie) = "vertraagd"
CLOSED = ("stop", "TP", "dicht 16:00")


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


def build():
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
    names = [n for n in ts.SESS_NAMES if ts.SET["sessies"].get(n, True)]
    nl = lambda hm: datetime.combine(now.date(), datetime.strptime(hm, "%H:%M").time(), ts.NY).astimezone(NL).strftime("%H:%M")
    sessions = [dict(naam=n, nl=f"{nl(a)}–{nl(b)}") for n, (a, b) in zip(names, ts.CFG["trade_sess"])]
    return dict(gemaakt=now.isoformat(timespec="seconds"), sessie=sess, volgende=nxt, sessies=sessions,
                meldingen_aan=bool(ts.SET["actief"]),
                vers_min=FRESH_MIN, geleerd_op=learned.get("bijgewerkt"), leren=history, markten=markets,
                logboek_regels=len(book))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--uit", default=str(HERE / "status.json"))
    a = ap.parse_args()
    data = build()
    with open(a.uit, "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{a.uit}: {len(data['markten'])} markten, sessie {data['sessie'] or '-'}, "
          f"{sum(len(m.get('setups', [])) for m in data['markten'])} setups vandaag")
