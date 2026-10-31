#!/usr/bin/env python3
"""
Demo-trading: neemt de signalen van de bot automatisch op een OANDA-oefenaccount (nepgeld).

VEILIGHEID
- Het adres van de oefenomgeving staat vast in de code (api-fxpractice.oanda.com). Een echte sleutel werkt daar
  niet, dus met echt geld handelen kan dit script niet, ook niet per ongeluk.
- Zonder OANDA_TOKEN doet het niets (en zegt dat in demo.json).
- Prop-firm-regels: risico per trade, max aantal open trades, daglimiet en totaallimiet. Wordt een limiet geraakt,
  dan opent hij die dag (of helemaal) niets meer.
- Uit te zetten met config.json: "demo": {"aan": false}.

Draait in de cloud-keten na live_status.py (elke 3 minuten):
    python demo_broker.py --status status.json --uit demo.json
Geheimen (GitHub > Settings > Secrets and variables > Actions): OANDA_TOKEN, en optioneel OANDA_ACCOUNT.
"""
import argparse
import json
import math
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
STATE = HERE / "demo_staat.json"          # bewaard via de actions-cache, net als verstuurd.json
SETTINGS = HERE / "config.json"
NY = ZoneInfo("America/New_York")
API = "https://api-fxpractice.oanda.com/v3"   # ALLEEN de oefenomgeving. Niet veranderen.

# onze marktnaam -> OANDA-instrument (alleen instrumenten met dollar als tweede valuta: 1 unit = $1 per 1,0 beweging)
INSTRUMENTS = {"EURUSD": "EUR_USD", "GBPUSD": "GBP_USD", "GOUD": "XAU_USD", "ZILVER": "XAG_USD",
               "OLIE": "WTICO_USD", "NQ": "NAS100_USD", "ES": "SPX500_USD"}
DEFAULTS = dict(aan=True, risico_pct=0.5, max_open=3, dagverlies_pct=5.0, totaalverlies_pct=10.0, max_uren=12)
ICT_ENTRY_MIN = 45     # een ICT-limietorder alleen plaatsen binnen 45 min na de setup, en 60 min geldig


class Oanda:
    def __init__(self, token, account=None):
        self.token, self.account = token, account

    def call(self, method, path, body=None):
        req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                                              "Accept-Datetime-Format": "RFC3339"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as ex:
            msg = ex.read().decode(errors="replace")[:300]
            raise RuntimeError(f"OANDA {ex.code}: {msg}") from None

    def acc(self, path=""):
        return f"/accounts/{self.account}{path}"


def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def settings():
    s = dict(DEFAULTS)
    s.update(load(SETTINGS, {}).get("demo", {}))
    return s


def ts(t):
    """OANDA-tijd (met nanoseconden) naar datetime."""
    t = t.rstrip("Z").split(".")[0]
    return datetime.fromisoformat(t).replace(tzinfo=timezone.utc)


def fmt(x, prec):
    return f"{x:.{prec}f}"


def signals(status):
    """Signalen die meetellen en nu nog genomen kunnen worden."""
    now = datetime.now(timezone.utc)
    out = []
    for m in status.get("markten", []):             # ICT: limietorder op de entry
        for s in m.get("setups", []):
            t = datetime.fromisoformat(s["tijd"])
            if s.get("telt") and s["status"] in ("nieuw", "wacht op entry") and now - t < timedelta(minutes=ICT_ENTRY_MIN):
                out.append(dict(markt=m["naam"], bron="ICT", key=f"ICT|{m['naam']}|{s['tijd']}|{s['kant']}", kant=s["kant"],
                                entry=s["entry"], stop=s["stop"], tp=s["tp"], soort="LIMIT", ref=m.get("koers")))
    for m in status.get("alle_markten", []):        # strategielab: market order bij de volgende candle
        for s in m.get("signalen", []):
            t = datetime.fromisoformat(s["t"])
            if s["status"] == "nieuw" and now - t < timedelta(minutes=20) and m.get("open"):
                out.append(dict(markt=m["naam"], bron=(m.get("keuze") or {}).get("titel", "lab"), key=f"LAB|{m['naam']}|{s['t']}|{s['kant']}",
                                kant=s["kant"], entry=s["entry"], stop=s["stop"], tp=s["tp"], soort="MARKET", ref=m.get("koers")))
    return out


def run(status, cfg, st, log):
    token = os.environ.get("OANDA_TOKEN", "").strip()
    if not token:
        return dict(gekoppeld=False, melding="Nog niet gekoppeld: zet OANDA_TOKEN als geheim in GitHub.")
    if not cfg["aan"]:
        return dict(gekoppeld=True, uit=True, melding="Demo-trading staat uit (config.json: demo.aan = false).")
    o = Oanda(token, os.environ.get("OANDA_ACCOUNT", "").strip() or None)
    if not o.account:
        accs = o.call("GET", "/accounts").get("accounts", [])
        if not accs:
            raise RuntimeError("geen oefenaccount gevonden bij deze sleutel")
        o.account = accs[0]["id"]
    a = o.call("GET", o.acc("/summary"))["account"]
    nav, ccy = float(a["NAV"]), a["currency"]
    now = datetime.now(timezone.utc)
    day = datetime.now(NY).date().isoformat()
    st.setdefault("start_saldo", nav)
    if st.get("dag") != day:
        st["dag"], st["dag_start"] = day, nav
    st.setdefault("orders", {})
    names = sorted(set(INSTRUMENTS.values()))
    meta = {i["name"]: i for i in o.call("GET", o.acc(f"/instruments?instruments={','.join(names)}"))["instruments"]}
    prices = {p["instrument"]: p for p in o.call("GET", o.acc(f"/pricing?instruments={','.join(names)}"))["prices"]}
    eurusd = float(prices["EUR_USD"]["closeoutAsk"]) if "EUR_USD" in prices else 1.1
    to_usd = 1.0 if ccy == "USD" else eurusd if ccy == "EUR" else None
    trades = o.call("GET", o.acc("/openTrades"))["trades"]

    # 1. daytrade: posities te lang open sluiten (ICT uiterlijk 16:00 NY, lab na max_uren)
    for t in trades:
        info = st["orders"].get(t.get("clientExtensions", {}).get("id", ""), {})
        until = info.get("sluit_voor")
        if until and now >= datetime.fromisoformat(until):
            o.call("PUT", o.acc(f"/trades/{t['id']}/close"))
            log.append(dict(t=now.isoformat(), actie="gesloten (tijd)", markt=info.get("markt"), detail=f"trade {t['id']}"))
    # 2. limieten
    day_loss = (st["dag_start"] - nav) / st["dag_start"] * 100
    tot_loss = (st["start_saldo"] - nav) / st["start_saldo"] * 100
    block = None
    if tot_loss >= cfg["totaalverlies_pct"]:
        block = f"totaallimiet geraakt ({tot_loss:.1f}% verlies): demo-challenge gezakt, geen nieuwe trades"
    elif day_loss >= cfg["dagverlies_pct"]:
        block = f"daglimiet geraakt ({day_loss:.1f}% verlies vandaag): vandaag geen nieuwe trades"
    if to_usd is None:
        block = f"accountvaluta {ccy} wordt niet ondersteund (kies USD of EUR)"
    # 3. nieuwe signalen
    open_n = len(o.call("GET", o.acc("/openTrades"))["trades"]) + len(o.call("GET", o.acc("/pendingOrders"))["orders"])
    for s in signals(status):
        if s["key"] in st["orders"]:
            continue
        inst = INSTRUMENTS.get(s["markt"])
        why = ("geen OANDA-instrument" if not inst else block or
               (f"al {open_n} posities open (max {cfg['max_open']})" if open_n >= cfg["max_open"] else None))
        if why:
            st["orders"][s["key"]] = dict(markt=s["markt"], status="overgeslagen", reden=why, t=now.isoformat())
            log.append(dict(t=now.isoformat(), actie="overgeslagen", markt=s["markt"], detail=why))
            continue
        p, mi = prices[inst], meta[inst]
        prec, uprec = int(mi["displayPrecision"]), int(mi.get("tradeUnitsPrecision", 0))
        long = s["kant"] == "LONG"
        mid = (float(p["closeoutBid"]) + float(p["closeoutAsk"])) / 2
        basis = mid - s["ref"] if s.get("ref") else 0.0       # OANDA-prijs wijkt af van Yahoo (bv. goud-future vs spot)
        dist_stop, dist_tp = abs(s["entry"] - s["stop"]), abs(s["tp"] - s["entry"])
        entry = s["entry"] + basis if s["soort"] == "LIMIT" else float(p["closeoutAsk"] if long else p["closeoutBid"])
        sl = entry - dist_stop if long else entry + dist_stop
        tp = entry + dist_tp if long else entry - dist_tp
        risk_usd = nav * cfg["risico_pct"] / 100 * to_usd
        units = math.floor(risk_usd / dist_stop * 10 ** uprec + 1e-6) / 10 ** uprec
        if units < float(mi.get("minimumTradeSize", 1)):
            why = f"positie te klein ({units} units)"
            st["orders"][s["key"]] = dict(markt=s["markt"], status="overgeslagen", reden=why, t=now.isoformat())
            log.append(dict(t=now.isoformat(), actie="overgeslagen", markt=s["markt"], detail=why))
            continue
        cid = f"radar-{int(now.timestamp())}-{s['markt']}"
        until = (datetime.now(NY).replace(hour=16, minute=0, second=0, microsecond=0) if s["bron"] == "ICT"
                 else now + timedelta(hours=cfg["max_uren"]))
        order = dict(type=s["soort"], instrument=inst, units=fmt(units if long else -units, uprec), positionFill="DEFAULT",
                     stopLossOnFill=dict(price=fmt(sl, prec)), takeProfitOnFill=dict(price=fmt(tp, prec)),
                     clientExtensions=dict(id=cid, tag="radar", comment=s["bron"][:100]),
                     tradeClientExtensions=dict(id=cid, tag="radar", comment=s["bron"][:100]))
        if s["soort"] == "MARKET":
            order["timeInForce"] = "FOK"
        else:
            order.update(price=fmt(entry, prec), timeInForce="GTD",
                         gtdTime=(now + timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S.000000000Z"))
        try:
            res = o.call("POST", o.acc("/orders"), dict(order=order))
            cancel = res.get("orderCancelTransaction") or res.get("orderRejectTransaction")
            ok = not cancel
            detail = (f"{s['kant']} {units:g} {inst} @ {fmt(entry, prec)}, stop {fmt(sl, prec)}, doel {fmt(tp, prec)}"
                      + ("" if ok else f" — geweigerd: {cancel.get('reason')}"))
        except RuntimeError as ex:
            ok, detail = False, str(ex)
        st["orders"][cid] = dict(markt=s["markt"], sluit_voor=until.astimezone(timezone.utc).isoformat())
        st["orders"][s["key"]] = dict(markt=s["markt"], status="geplaatst" if ok else "mislukt", id=cid, t=now.isoformat(), detail=detail)
        log.append(dict(t=now.isoformat(), actie=("order " + s["soort"].lower()) if ok else "mislukt", markt=s["markt"], detail=f"{s['bron']}: {detail}"))
        if ok:
            open_n += 1

    # 4. stand voor het dashboard
    a = o.call("GET", o.acc("/summary"))["account"]
    nav = float(a["NAV"])
    eq = st.setdefault("equity", [])
    if not eq or now - datetime.fromisoformat(eq[-1][0]) >= timedelta(minutes=15):
        eq.append([now.isoformat(timespec="minutes"), round(nav, 2)])
        del eq[:-3000]
    opn = o.call("GET", o.acc("/openTrades"))["trades"]
    closed = o.call("GET", o.acc("/trades?state=CLOSED&count=40"))["trades"]
    pend = o.call("GET", o.acc("/pendingOrders"))["orders"]
    trade = lambda t: dict(id=t["id"], instrument=t["instrument"], units=float(t["initialUnits"]), prijs=float(t["price"]),
                           open=ts(t["openTime"]).isoformat(), stop=float(t["stopLossOrder"]["price"]) if t.get("stopLossOrder") else None,
                           doel=float(t["takeProfitOrder"]["price"]) if t.get("takeProfitOrder") else None,
                           pl=float(t.get("unrealizedPL") or t.get("realizedPL") or 0),
                           slot=float(t["averageClosePrice"]) if t.get("averageClosePrice") else None,
                           dicht=ts(t["closeTime"]).isoformat() if t.get("closeTime") else None,
                           bron=t.get("clientExtensions", {}).get("comment", "handmatig"))
    return dict(gekoppeld=True, account=o.account[:4] + "…" + o.account[-4:], valuta=ccy, saldo=float(a["balance"]), nav=nav,
                open_pl=float(a["unrealizedPL"]), totaal_pl=float(a["pl"]), marge=float(a["marginUsed"]),
                start_saldo=st["start_saldo"], dag_start=st["dag_start"], blokkade=block, regels=cfg,
                open_trades=[trade(t) for t in opn], gesloten=[trade(t) for t in closed],
                orders=[dict(instrument=x.get("instrument"), soort=x["type"], units=x.get("units"), prijs=x.get("price"),
                             geldig_tot=x.get("gtdTime")) for x in pend if x["type"] in ("LIMIT", "STOP", "MARKET_IF_TOUCHED")],
                equity=eq)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", default=str(HERE / "status.json"))
    ap.add_argument("--uit", default=str(HERE / "demo.json"))
    a = ap.parse_args()
    st = load(STATE, {})
    log = st.setdefault("log", [])
    cfg = settings()
    try:
        out = run(load(a.status, {}), cfg, st, log)
    except Exception as ex:   # demo-problemen mogen de meldingen niet raken
        out = dict(gekoppeld=bool(os.environ.get("OANDA_TOKEN")), fout=f"{type(ex).__name__}: {ex}")
    del log[:-60]
    st["orders"] = dict(list(st.get("orders", {}).items())[-400:])
    out.update(gemaakt=datetime.now(NY).isoformat(timespec="seconds"), log=log[-30:][::-1], omgeving="OANDA oefenaccount (nepgeld)")
    STATE.write_text(json.dumps(st, indent=1))
    Path(a.uit).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"demo: {out.get('melding') or out.get('fout') or 'NAV ' + str(out.get('nav'))}")


if __name__ == "__main__":
    main()
