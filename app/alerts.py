"""Meldingen-app van MarketPilot (was tradingstrategie.py; dat commando blijft werken): TJR / ICT confluence-meldingen op je Mac, zonder TradingView-abonnement.

Zelfde logica als tjr_alerts.pine:
  kern:   sweep van liquiditeit -> MSS met displacement -> FVG, in het NY-window
  score:  4H bias, 1H bias, premium/discount, OTE, HTF FVG, SMT met ES,
          Silver Bullet, sterke displacement, IFVG, draw on liquidity >= 2R
"Kans" = setup in NY AM (backtest 2025-2026: alleen die sessie was in beide jaren winstgevend).
London en NY PM worden nog wel gemeld, maar als "lage kans". TP = vaste 1R (zie backtest.py).
Markten: NQ (TP 1R) en EURUSD (TP op de DOL), zie "markets" en backtest_multi.py.
Sessies: London 02:00-05:00, NY AM 09:30-11:30 en NY PM 13:30-15:30 (NY-tijd).
Alleen meldingen, er worden geen orders geplaatst.

Gebruik:
  python tradingstrategie.py               live: elke minuut checken en melden
  python tradingstrategie.py --scan        alle setups van de afgelopen 30 dagen tonen
  python tradingstrategie.py --test-notify testmelding sturen
  python tradingstrategie.py --logboek     overzicht van alle gelogde setups, uitkomsten en weigeringen
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from backtesting.ict import outcome
from core.config import CFG, DEFAULT_SETTINGS, SESS_NAMES, SET, apply_learned, apply_settings, load_settings  # noqa: F401
from core.data import fetch
from core.sessions import NY, in_sess, sess_name
from storage import jsonstore, paths
from strategies.ict_tjr import BAR, align_htf, analyse, htf_state, nearest, pivots  # noqa: F401

warnings.filterwarnings("ignore")

HERE = paths.ROOT
STATE_FILE = paths.SENT
LOG_FILE = paths.SETUPS_LOG
LOGBOOK_FILE = paths.LOGBOOK     # elke setup en weigering met uitkomst (forward test)
SETTINGS_FILE = paths.CONFIG
LEARNED_FILE = paths.LEARNED     # instellingen die het leren zelf kiest (per markt)

# ------------- Uitvoer -------------
def bias_txt(b):
    return "bullish" if b == 1 else "bearish" if b == -1 else "neutraal"


def kans(s):
    return "kans" if s["good"] else "LAGE KANS"


def against_bias(s):
    return s["bias_b"] != (1 if s["side"] == "LONG" else -1)


def px(s, v):
    return f"{v:.{s.get('dec', 2)}f}"


def setup_text(s):
    return (f"{s.get('mkt', '')} [{sess_name(s['time'])}] {s['side']} {s['grade']} ({s['score']}/10, {kans(s)}{', tegen ' + CFG['htf_b'] + '-bias' if against_bias(s) else ''}) | entry {px(s, s['entry'])} | stop {px(s, s['stop'])} | "
            f"TP {px(s, s['tp'])} ({s['rr']:.1f}R) | sweep {s['sweep']} | "
            f"{CFG['htf_b']} {bias_txt(s['bias_b'])}, {CFG['htf_a']} {bias_txt(s['bias_a'])}")


def checklist(s):
    return "  ".join(("[x] " if v else "[ ] ") + k for k, v in s["checks"].items())


def notify(title, msg, sound="Glass"):
    if sys.platform == "darwin":
        script = f"display notification {json.dumps(msg)} with title {json.dumps(title)} sound name {json.dumps(sound)}"
        subprocess.run(["osascript", "-e", script], check=False)
    push_phone(title, msg, high=sound == "Glass" or sound == "Hero")


def push_phone(title, msg, high=False):
    """Stuurt dezelfde melding naar je telefoon via ntfy.sh."""
    if not CFG["ntfy_topic"] or not SET["telefoon"]:
        return
    req = urllib.request.Request(f"https://ntfy.sh/{CFG['ntfy_topic']}", data=msg.encode(), method="POST",
                                 headers={"Title": title, "Priority": "high" if high else "default",
                                          "Tags": "chart_with_upwards_trend"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as ex:  # geen internet: Mac-melding is al verstuurd
        print("Telefoonmelding mislukt:", ex, flush=True)


def log(line):
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def analyse_market(m, period="30d", refusals=None):
    """Data ophalen en analyseren voor één markt uit CFG["markets"]; setups krijgen de marktnaam mee."""
    df, es = fetch(m["symbol"], period), fetch(m["smt"], period)
    setups, entries = analyse(df, es, dict(CFG, **m["cfg"]), refusals)
    for s in setups:
        s.update(mkt=m["name"], dec=m["dec"])
    return df, setups, entries


# ------------- Logboek -------------
FINAL = ("stop", "TP", "dicht 16:00", "entry niet op tijd geraakt", "stop geraakt voor de entry")


def load_logbook():
    return jsonstore.load(LOGBOOK_FILE, {})


def update_logbook(book, m, df, setups, refusals):
    """Setups en weigeringen van één markt in het logboek zetten; uitkomsten bijwerken tot ze vaststaan."""
    now = datetime.now(NY).isoformat(timespec="minutes")
    for s in setups:
        key = f"setup|{m['name']}|{s['time'].isoformat()}|{s['side']}"
        if book.get(key, {}).get("uitkomst") in FINAL:
            continue
        res, r = outcome(df, s)
        if res == "geen entry":
            res = s.get("missed", "wacht op entry")
        book[key] = dict(type="setup", markt=m["name"], tijd=s["time"].isoformat(), sessie=sess_name(s["time"]),
                         kant=s["side"], grade=s["grade"], score=int(s["score"]), kans=bool(s["good"]),
                         entry=round(float(s["entry"]), 6), stop=round(float(s["stop"]), 6), tp=round(float(s["tp"]), 6),
                         rr=round(float(s["rr"]), 2), sweep=s["sweep"], bias_1h=int(s["bias_b"]), bias_4h=int(s["bias_a"]),
                         checks=[k for k, v in s["checks"].items() if v], uitkomst=res, R=round(float(r), 2), bijgewerkt=now)
    for f in refusals:
        key = f"weigering|{m['name']}|{f['time'].isoformat()}|{f['side']}|{f['reason']}"
        if key not in book:
            book[key] = dict(type="weigering", markt=m["name"], tijd=f["time"].isoformat(), sessie=sess_name(f["time"]),
                             kant=f["side"], reden=f["reason"], sweep=f["sweep"],
                             sweep_tijd=f["sweep_t"].isoformat() if f["sweep_t"] is not None else None,
                             bias_1h=int(f["bias_b"]), bias_4h=int(f["bias_a"]), bijgewerkt=now)


def logbook_report(path=None):
    if path and not Path(path).exists():
        print(f"{path} bestaat nog niet. Download het logboek uit GitHub (Actions > een run > Artifacts > logboek),\n"
              f"pak de zip uit in deze map en draai dit commando opnieuw.")
        return
    book = json.loads(Path(path).read_text()) if path else load_logbook()
    if not book:
        print("Logboek is nog leeg.")
        return
    rows = sorted(book.values(), key=lambda x: x["tijd"])
    print(f"Logboek: {len(rows)} regels, {rows[0]['tijd'][:10]} t/m {rows[-1]['tijd'][:10]} (R zonder kosten)")
    for mkt in sorted({x["markt"] for x in rows}):
        mine = [x for x in rows if x["markt"] == mkt]
        print(f"\n===== {mkt} =====")
        for label, flt in (("kans", True), ("lage kans", False)):
            st = [x for x in mine if x["type"] == "setup" and x["kans"] == flt]
            done = [x for x in st if x["uitkomst"] in ("stop", "TP", "dicht 16:00")]
            wins = sum(x["R"] > 0 for x in done)
            print(f"Setups {label:9}: {len(st):3} | met entry en klaar: {len(done):3} | "
                  f"win {wins / len(done) if done else 0:4.0%} | {sum(x['R'] for x in done):+6.1f}R")
            for res in sorted({x["uitkomst"] for x in st}):
                print(f"    {res:28} {sum(x['uitkomst'] == res for x in st)}")
        refs = [x for x in mine if x["type"] == "weigering"]
        print(f"Weigeringen: {len(refs)}")
        for reason in sorted({x["reden"] for x in refs}, key=lambda r: -sum(x["reden"] == r for x in refs)):
            print(f"    {reason:34} {sum(x['reden'] == reason for x in refs)}")


def alt_offset(m, df):
    """Verschil future - indexprijs op de laatste gezamenlijke candle (None als er geen alt is)."""
    if not m.get("alt"):
        return None
    try:
        alt = fetch(m["alt"]["symbol"], "5d")
    except Exception as ex:
        print(f"{m['alt']['label']}: geen data ({ex})", flush=True)
        return None
    common = df.index.intersection(alt.index)
    if not len(common):
        return None
    return float(df.loc[common[-1], "Close"] - alt.loc[common[-1], "Close"])


def levels(s, m, off, keys=("entry", "stop", "tp")):
    """Prijzen voor in de melding: eerst in US100 (als bekend), daarna de originele."""
    names = {"entry": "Entry", "stop": "Stop", "tp": "TP"}
    own = " | ".join(f"{names[k]} {px(s, s[k])}" for k in keys)
    if off is None:
        return own
    alt = " | ".join(f"{names[k]} {s[k] - off:.{s.get('dec', 2)}f}" for k in keys)
    return f"{m['alt']['label']}: {alt}\n({m['name']}: {own})"


def scan():
    for m in CFG["markets"]:
        print(f"\n===== {m['name']} ({m['symbol']}) =====")
        scan_market(m)


def scan_market(m):
    df, setups, _ = analyse_market(m)
    trade_days = sorted({t.date() for t in df.index if t.weekday() < 5 and in_sess(t, CFG["trade_sess"])})
    weeks = max(len(trade_days) / 5, 1)
    good = [s for s in setups if s["good"]]
    print(f"Data: {df.index[0]:%d-%m %H:%M} t/m {df.index[-1]:%d-%m %H:%M} NY-tijd ({len(df)} candles)")
    print(f"Setups: {len(setups)} totaal (~{len(setups) / weeks:.1f} per week): "
          f"{len(good)} kans ({'/'.join(CFG['kans_sess'])}), {len(setups) - len(good)} lage kans\n")
    totals = {True: [0.0, 0], False: [0.0, 0]}
    per_sess = {}
    by_day = {}
    for s in setups:
        by_day.setdefault(s["time"].date(), []).append(s)
    for d in trade_days:
        day = by_day.get(d, [])
        if not day:
            print(f"{d:%a %d-%m}  geen setup")
            continue
        for s in day:
            res, r = outcome(df, s)
            ps = per_sess.setdefault(sess_name(s["time"]), [0, 0, 0.0, 0])
            ps[0] += 1
            ps[1] += s["good"]
            if res != "geen entry":
                totals[s["good"]][0] += r
                totals[s["good"]][1] += 1
                if s["good"]:
                    ps[2] += r
                    ps[3] += 1
            print(f"{s['time']:%a %d-%m %H:%M}  {setup_text(s)}  -> uitkomst: {res} ({r:+.1f}R)")
            print(f"    {checklist(s)}")
    days_with = sum(1 for d in trade_days if by_day.get(d))
    print(f"\nDagen met minstens 1 setup: {days_with} van {len(trade_days)}")
    for g, label in ((True, "kans"), (False, "lage kans")):
        r, n = totals[g]
        print(f"Resultaat {label}: {r:+.1f}R over {n} trades met entry (zonder kosten/slippage)")
    for name in ("London", "NY AM", "NY PM"):
        n, g, r, e = per_sess.get(name, [0, 0, 0.0, 0])
        print(f"  {name:6}: {n} setups, {g} kans | kans-trades met entry: {e}, {r:+.1f}R")
    print("Let op: veel te weinig trades om iets over de strategie te zeggen.")


def check(sent):
    """Eén keer data ophalen, analyseren en nieuwe meldingen versturen."""
    if not SET["actief"]:
        return
    now = datetime.now(NY)
    recent = now - timedelta(minutes=45)
    setups, last = [], []
    book = load_logbook()
    for m in CFG["markets"]:
        refs = []
        try:
            df, m_setups, entries = analyse_market(m, refusals=refs)
        except Exception as ex:  # één markt zonder data mag de andere niet blokkeren
            print(f"{m['name']}: fout: {ex}", flush=True)
            continue
        update_logbook(book, m, df, m_setups, refs)
        quiet = not m.get("actief", True)   # leren.py heeft deze markt op pauze gezet: wel loggen, niet melden
        setups += m_setups
        last.append(f"{m['name']} {df.index[-1]:%H:%M}")
        new = [s for s in m_setups if s["time"] >= recent] or [e["setup"] for e in entries if e["time"] >= recent]
        off = alt_offset(m, df) if new else None   # alleen ophalen als er iets te melden is
        for s in m_setups:
            # NQ houdt de oude sleutel zodat eerder verstuurde meldingen niet opnieuw komen
            key = f"setup|{s['time'].isoformat()}|{s['side']}" + ("" if m["name"] == "NQ" else f"|{m['name']}")
            if quiet:
                sent.add(key)
                continue
            if s["time"] >= recent and key not in sent and SET["alleen_kans"] and not s["good"]:
                sent.add(key)   # lage kans staat uit: wel onthouden, niet melden
            if s["time"] >= recent and key not in sent:
                extra = f" | tegen {CFG['htf_b']}-bias" if against_bias(s) else ""
                title = (f"{m['name']} {s['side']} {s['grade']} ({s['score']}/10)" if s["good"]
                         else f"LAGE KANS: {m['name']} {s['side']} ({s['score']}/10)")
                notify(title, f"{levels(s, m, off)} ({s['rr']:.1f}R){extra}",
                       sound="Glass" if s["good"] else "Pop")
                log(f"{s['time']:%Y-%m-%d %H:%M} {setup_text(s)}\n    {checklist(s)}")
                sent.add(key)
        for e in entries:
            key = f"entry|{e['time'].isoformat()}|{e['setup']['side']}" + ("" if m["name"] == "NQ" else f"|{m['name']}")
            if quiet:
                sent.add(key)
                continue
            if e["time"] >= recent and key not in sent and (
                    not SET["entry_meldingen"] or (SET["alleen_kans"] and not e["setup"]["good"])):
                sent.add(key)
            if e["time"] >= recent and key not in sent:
                st = e["setup"]
                pre = "" if st["good"] else "LAGE KANS: "
                notify(f"{pre}{m['name']} {st['side']}: prijs in entry-zone", levels(st, m, off, ("entry", "stop")), sound="Hero")
                log(f"{e['time']:%Y-%m-%d %H:%M} {m['name']} {st['side']} prijs in entry-zone ({px(st, st['entry'])})")
                sent.add(key)
    # Einde van de dag zonder setup: dat ook laten weten
    today = [s for s in setups if s["time"].date() == now.date()]
    key = f"summary|{now.date().isoformat()}"
    if (SET["dagmelding"] and CFG["trade_sess"] and now.weekday() < 5 and now.strftime("%H:%M") >= CFG["day_end"]
            and not today and key not in sent):
        notify("MarketPilot", "Vandaag geen TJR-setup. Geen trade is ook een goede trade.", sound="Pop")
        sent.add(key)
    STATE_FILE.write_text(json.dumps(sorted(sent)))
    LOGBOOK_FILE.write_text(json.dumps(book, indent=1, ensure_ascii=False))
    print(f"{now:%H:%M:%S} NY | laatste candle {', '.join(last)} | "
          f"vandaag {sum(s['good'] for s in today)} kans, {sum(not s['good'] for s in today)} lage kans", flush=True)


def load_sent():
    return set(json.loads(STATE_FILE.read_text())) if STATE_FILE.exists() else set()


def live(interval=60):
    sent = load_sent()
    nl = ZoneInfo("Europe/Amsterdam")
    def nl_time(hm):
        h, m = map(int, hm.split(":"))
        return datetime.now(NY).replace(hour=h, minute=m).astimezone(nl).strftime("%H:%M")
    windows = " en ".join(f"{nl_time(a)}-{nl_time(b)}" for a, b in CFG["trade_sess"])
    print(f"MarketPilot draait, zoekt setups van {windows} Nederlandse tijd | stoppen: Ctrl+C")
    notify("MarketPilot", "Gestart, ik meld TJR-setups op " + " en ".join(m["name"] for m in CFG["markets"]))
    while True:
        try:
            check(sent)
        except Exception as ex:  # netwerk of data even weg: gewoon opnieuw proberen
            print("Fout:", ex, flush=True)
        time.sleep(interval)


def near_window(margin_min=20):
    """True als we in een sessie zitten (of net erna, voor late entries en de dagmelding)."""
    now = datetime.now(NY)
    if now.weekday() >= 5:
        return False
    for a, b in CFG["trade_sess"]:
        end = datetime.strptime(b, "%H:%M") + timedelta(minutes=margin_min)
        if a <= now.strftime("%H:%M") <= end.strftime("%H:%M"):
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", action="store_true", help="setups van de afgelopen 30 dagen tonen")
    ap.add_argument("--test-notify", action="store_true", help="testmelding sturen")
    ap.add_argument("--once", action="store_true", help="één keer checken (voor de cloud)")
    ap.add_argument("--logboek", nargs="?", const="", metavar="BESTAND",
                    help="overzicht van het logboek (setups, uitkomsten, weigeringen); standaard logboek.json")
    args = ap.parse_args()
    apply_settings()   # leest ook NTFY_TOPIC uit de omgeving (cloud)
    if args.once:
        if not SET["actief"]:
            print("Meldingen staan uit (config.json: actief = false).")
        elif not CFG["markets"] or not CFG["trade_sess"]:
            print("Geen markt of sessie aan in config.json, niets te doen.")
        elif near_window():
            check(load_sent())
        else:
            print("Buiten de sessies, niets te doen.")
    elif args.logboek is not None:
        logbook_report(args.logboek or None)
    elif args.test_notify:
        notify("TJR LONG A (6/10)", "Testmelding | Entry 29800.00 | Stop 29770.00 | TP 29870.00 (2.3R)")
    elif args.scan:
        scan()
    else:
        live()


if __name__ == "__main__":
    main()

