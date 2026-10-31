#!/usr/bin/env python3
"""
Demo-trading: neemt de signalen van de bot automatisch op een DEMO-account bij een broker (nepgeld).

Brokers (de eerste waarvan de geheimen er zijn, wordt gebruikt):
  Capital.com demo  CAPITAL_API_KEY, CAPITAL_IDENTIFIER (je login-e-mail), CAPITAL_PASSWORD (het eigen wachtwoord
                    van de API-sleutel, niet je account-wachtwoord). Werkt in Nederland.
  OANDA fxTrade     OANDA_TOKEN (en optioneel OANDA_ACCOUNT). Alleen fxTrade, niet TMS OANDA.

VEILIGHEID
- De adressen van de demo-omgevingen staan vast in de code. Een echte (live) sleutel werkt daar niet, dus met
  echt geld handelen kan dit script niet, ook niet per ongeluk.
- Zonder geheimen doet het niets (en zegt dat in demo.json).
- Prop-firm-regels van Alpha Capital "Alpha Direct": hefboom max 1:30, max dagverlies 3% en een meeschuivend
  (trailing) max verlies van 5% onder de hoogste accountwaarde. Geen winstdoel. Daarnaast: risico per trade en max
  aantal open trades. Een trade die bij verlies de daglimiet zou kunnen breken, wordt niet geopend.
- Uit te zetten met config.json: "demo": {"aan": false}.

Draait in de cloud-keten na live_status.py (elke 3 minuten):
    python demo_broker.py --status status.json --uit demo.json
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
OANDA_API = "https://api-fxpractice.oanda.com/v3"                   # ALLEEN demo. Niet veranderen.
CAPITAL_API = "https://demo-api-capital.backend-capital.com/api/v1"  # ALLEEN demo. Niet veranderen.

# Alpha Capital "Alpha Direct": hefboom 1:30, trailing max verlies 5%, max dagverlies 3%, geen winstdoel
DEFAULTS = dict(aan=True, risico_pct=0.5, max_open=3, dagverlies_pct=3.0, totaalverlies_pct=5.0, trailing=True,
                hefboom=30, dag_reset="Europe/Amsterdam", max_uren=12)
ICT_ENTRY_MIN = 45     # een ICT-limietorder alleen plaatsen binnen 45 min na de setup, en 60 min geldig


def units(x, step):
    """Getal als tekst met zoveel decimalen als de kleinste stap (nooit 1e+06-notatie)."""
    return f"{x:.{max(0, -math.floor(math.log10(step) + 1e-9))}f}"


def http(method, url, headers, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read() or b"{}"), r.headers
    except urllib.error.HTTPError as ex:
        raise RuntimeError(f"{ex.code}: {ex.read().decode(errors='replace')[:300]}") from None


# ------------- Brokers -------------
# Elke broker levert: account(), instrument(markt), market(...), limit(...), positions(), pending(), close(id), closed()
# Instrument: dict(code, bid, ask, prec, step, min_size, ccy) waarbij 1 unit = 1 (ccy) per 1,0 prijsbeweging.

class Oanda:
    naam = "OANDA fxTrade demo"
    CODES = {"EURUSD": "EUR_USD", "GBPUSD": "GBP_USD", "GOUD": "XAU_USD", "ZILVER": "XAG_USD",
             "OLIE": "WTICO_USD", "NQ": "NAS100_USD", "ES": "SPX500_USD"}

    def __init__(self, token, account=None):
        self.h = {"Authorization": f"Bearer {token}", "Accept-Datetime-Format": "RFC3339"}
        self.account = account or self.call("GET", "/accounts")[0]["accounts"][0]["id"]

    def call(self, method, path, body=None):
        return http(method, OANDA_API + path, self.h, body)

    def acc(self, path=""):
        return self.call("GET", f"/accounts/{self.account}{path}")[0]

    def account_info(self):
        a = self.acc("/summary")["account"]
        return dict(id=self.account, ccy=a["currency"], nav=float(a["NAV"]), saldo=float(a["balance"]), open_pl=float(a["unrealizedPL"]))

    def instrument(self, markt):
        code = self.CODES.get(markt)
        if not code:
            return None
        i = self.acc(f"/instruments?instruments={code}")["instruments"][0]
        p = self.acc(f"/pricing?instruments={code}")["prices"][0]
        up = int(i.get("tradeUnitsPrecision", 0))
        return dict(code=code, bid=float(p["closeoutBid"]), ask=float(p["closeoutAsk"]), prec=int(i["displayPrecision"]),
                    step=10 ** -up, min_size=float(i.get("minimumTradeSize", 1)), ccy=code.split("_")[1])

    def _order(self, o):
        res = self.call("POST", f"/accounts/{self.account}/orders", dict(order=o))[0]
        bad = res.get("orderCancelTransaction") or res.get("orderRejectTransaction")
        return (False, bad.get("reason")) if bad else (True, "")

    def market(self, inst, side, size, sl, tp, tag):
        return self._order(dict(type="MARKET", instrument=inst["code"], units=units(side * size, inst["step"]), timeInForce="FOK",
                                stopLossOnFill=dict(price=f"{sl:.{inst['prec']}f}"), takeProfitOnFill=dict(price=f"{tp:.{inst['prec']}f}"),
                                tradeClientExtensions=dict(id=tag, tag="radar")))

    def limit(self, inst, side, size, price, sl, tp, until, tag):
        return self._order(dict(type="LIMIT", instrument=inst["code"], units=units(side * size, inst["step"]), price=f"{price:.{inst['prec']}f}",
                                timeInForce="GTD", gtdTime=until.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
                                stopLossOnFill=dict(price=f"{sl:.{inst['prec']}f}"), takeProfitOnFill=dict(price=f"{tp:.{inst['prec']}f}"),
                                tradeClientExtensions=dict(id=tag, tag="radar")))

    def positions(self):
        return [dict(id=t["id"], tag=t.get("clientExtensions", {}).get("id"), instrument=t["instrument"], units=float(t["currentUnits"]),
                     prijs=float(t["price"]), open=t["openTime"][:19] + "+00:00", pl=float(t.get("unrealizedPL") or 0),
                     stop=float(t["stopLossOrder"]["price"]) if t.get("stopLossOrder") else None,
                     doel=float(t["takeProfitOrder"]["price"]) if t.get("takeProfitOrder") else None) for t in self.acc("/openTrades")["trades"]]

    def pending(self):
        return [dict(instrument=o.get("instrument"), units=o.get("units"), prijs=o.get("price"), geldig_tot=o.get("gtdTime"))
                for o in self.acc("/pendingOrders")["orders"] if o["type"] == "LIMIT"]

    def close(self, pid):
        self.call("PUT", f"/accounts/{self.account}/trades/{pid}/close")

    def closed(self):
        return [dict(instrument=t["instrument"], units=float(t["initialUnits"]), prijs=float(t["price"]), dicht=t["closeTime"][:19] + "+00:00",
                     pl=float(t.get("realizedPL") or 0)) for t in self.acc("/trades?state=CLOSED&count=40")["trades"]]


class Capital:
    naam = "Capital.com demo"
    CODES = {"GOUD": "GOLD", "ZILVER": "SILVER", "OLIE": "OIL_CRUDE", "NQ": "US100", "ES": "US500", "DAX": "DE40",
             "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY", "BTC": "BTCUSD", "ETH": "ETHUSD", "SOL": "SOLUSD",
             "AAPL": "AAPL", "NVDA": "NVDA", "MSFT": "MSFT"}

    def __init__(self, key, ident, pw):
        _, hdr = http("POST", CAPITAL_API + "/session", {"X-CAP-API-KEY": key}, dict(identifier=ident, password=pw, encryptedPassword=False))
        self.h = {"X-CAP-API-KEY": key, "CST": hdr["CST"], "X-SECURITY-TOKEN": hdr["X-SECURITY-TOKEN"]}
        self.cache = {}

    def call(self, method, path, body=None):
        return http(method, CAPITAL_API + path, self.h, body)[0]

    def account_info(self):
        accs = self.call("GET", "/accounts")["accounts"]
        a = next((x for x in accs if x.get("preferred")), accs[0])
        b = a["balance"]
        return dict(id=a["accountId"], ccy=a["currency"], nav=float(b["balance"]) + float(b["profitLoss"]),
                    saldo=float(b["balance"]), open_pl=float(b["profitLoss"]))

    def instrument(self, markt):
        epic = self.CODES.get(markt)
        if not epic:
            return None
        if epic not in self.cache:
            try:
                self.cache[epic] = self.call("GET", f"/markets/{epic}")
            except RuntimeError:
                self.cache[epic] = None
        m = self.cache[epic]
        if not m:
            return None
        d, s = m["dealingRules"], m["snapshot"]
        if s.get("marketStatus") != "TRADEABLE":
            return dict(code=epic, dicht=True)
        return dict(code=epic, bid=float(s["bid"]), ask=float(s["offer"]), prec=int(s.get("decimalPlacesFactor", 2)),
                    step=float((d.get("minSizeIncrement") or {}).get("value", 0.01)), min_size=float(d["minDealSize"]["value"]),
                    ccy=m["instrument"]["currency"])

    def _confirm(self, ref):
        c = self.call("GET", f"/confirms/{ref}")
        return (c.get("dealStatus") == "ACCEPTED", c.get("reason") or c.get("dealStatus") or "")

    def market(self, inst, side, size, sl, tp, tag):
        r = self.call("POST", "/positions", dict(epic=inst["code"], direction="BUY" if side > 0 else "SELL", size=size,
                                                 stopLevel=round(sl, inst["prec"]), profitLevel=round(tp, inst["prec"]), guaranteedStop=False))
        return self._confirm(r["dealReference"])

    def limit(self, inst, side, size, price, sl, tp, until, tag):
        r = self.call("POST", "/workingorders", dict(epic=inst["code"], direction="BUY" if side > 0 else "SELL", size=size,
                                                     level=round(price, inst["prec"]), type="LIMIT", goodTillDate=until.strftime("%Y-%m-%dT%H:%M:%S"),
                                                     stopLevel=round(sl, inst["prec"]), profitLevel=round(tp, inst["prec"]), guaranteedStop=False))
        return self._confirm(r["dealReference"])

    def positions(self):
        out = []
        for x in self.call("GET", "/positions")["positions"]:
            p, m = x["position"], x["market"]
            out.append(dict(id=p["dealId"], tag=p["dealId"], instrument=m["epic"], units=float(p["size"]) * (1 if p["direction"] == "BUY" else -1),
                            prijs=float(p["level"]), open=p["createdDateUTC"][:19] + "+00:00", pl=float(p.get("upl") or 0),
                            stop=p.get("stopLevel"), doel=p.get("profitLevel")))
        return out

    def pending(self):
        return [dict(instrument=w["workingOrderData"]["epic"], units=w["workingOrderData"]["orderSize"], prijs=w["workingOrderData"]["orderLevel"],
                     geldig_tot=w["workingOrderData"].get("goodTillDateUTC")) for w in self.call("GET", "/workingorders")["workingOrders"]]

    def close(self, pid):
        self.call("DELETE", f"/positions/{pid}")

    def closed(self):
        tx = self.call("GET", "/history/transactions?type=TRADE&lastPeriod=86400").get("transactions", [])
        return [dict(instrument=t.get("instrumentName"), units=None, prijs=None, dicht=t["dateUtc"][:19] + "+00:00",
                     pl=float(t.get("size") or 0)) for t in tx]


def connect():
    if os.environ.get("CAPITAL_API_KEY"):
        return Capital(os.environ["CAPITAL_API_KEY"].strip(), os.environ.get("CAPITAL_IDENTIFIER", "").strip(),
                       os.environ.get("CAPITAL_PASSWORD", "").strip())
    if os.environ.get("OANDA_TOKEN"):
        return Oanda(os.environ["OANDA_TOKEN"].strip(), os.environ.get("OANDA_ACCOUNT", "").strip() or None)
    return None


# ------------- Logica -------------
def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def settings():
    s = dict(DEFAULTS)
    s.update(load(SETTINGS, {}).get("demo", {}))
    return s


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


def run(status, cfg, st, log, broker=None):
    b = broker or connect()
    if b is None:
        return dict(gekoppeld=False, melding="Nog niet gekoppeld: zet de sleutel van je demo-account als geheim in GitHub.")
    if not cfg["aan"]:
        return dict(gekoppeld=True, uit=True, broker=b.naam, melding="Demo-trading staat uit (config.json: demo.aan = false).")
    now = datetime.now(timezone.utc)
    a = b.account_info()
    nav, ccy = a["nav"], a["ccy"]
    day = datetime.now(ZoneInfo(cfg["dag_reset"])).date().isoformat()   # nieuwe handelsdag om middernacht
    st.setdefault("start_saldo", nav)
    st["piek"] = max(st.get("piek", nav), nav)
    if st.get("dag") != day:
        st["dag"], st["dag_start"] = day, max(nav, a["saldo"])   # zoals prop firms: hoogste van saldo en waarde
    st.setdefault("orders", {})
    eur = b.instrument("EURUSD")
    eurusd = (eur["bid"] + eur["ask"]) / 2 if eur and not eur.get("dicht") else 1.1
    acc_to_usd = {"USD": 1.0, "EUR": eurusd}.get(ccy)

    # 1. daytrade: posities te lang open sluiten (ICT uiterlijk 16:00 NY, lab na max_uren)
    for p in b.positions():
        info = st["orders"].get(f"pos|{p['tag']}") or st["orders"].get(f"pos|{p['id']}") or {}
        if info.get("sluit_voor") and now >= datetime.fromisoformat(info["sluit_voor"]):
            b.close(p["id"])
            log.append(dict(t=now.isoformat(), actie="gesloten (tijd)", markt=info.get("markt"), detail=f"positie {p['id']}"))
    # 2. limieten
    day_loss = (st["dag_start"] - nav) / st["dag_start"] * 100
    base = st["piek"] if cfg["trailing"] else st["start_saldo"]
    floor = base * (1 - cfg["totaalverlies_pct"] / 100)          # onder deze waarde = account kwijt
    tot_loss = (base - nav) / st["start_saldo"] * 100
    block = None
    if nav <= floor:
        block = f"max verlies geraakt (waarde {nav:,.0f} onder de grens {floor:,.0f}): demo-account gezakt, geen nieuwe trades"
    elif day_loss >= cfg["dagverlies_pct"]:
        block = f"daglimiet geraakt ({day_loss:.1f}% verlies vandaag): vandaag geen nieuwe trades"
    if acc_to_usd is None:
        block = f"accountvaluta {ccy} wordt niet ondersteund (kies USD of EUR)"
    # 3. nieuwe signalen
    open_n = len(b.positions()) + len(b.pending())
    for s in signals(status):
        if s["key"] in st["orders"]:
            continue

        def skip(why):
            st["orders"][s["key"]] = dict(markt=s["markt"], status="overgeslagen", reden=why, t=now.isoformat())
            log.append(dict(t=now.isoformat(), actie="overgeslagen", markt=s["markt"], detail=why))

        # als alles wat open staat plus deze trade de stop raakt: blijft de dag- en totaalgrens heel?
        worst = (open_n + 1) * cfg["risico_pct"]
        if not block and day_loss + worst > cfg["dagverlies_pct"]:
            block_here = f"bij verlies van alle open trades plus deze zou de daglimiet ({cfg['dagverlies_pct']:g}%) breken"
        elif not block and nav * (1 - worst / 100) <= floor:
            block_here = f"bij verlies van alle open trades plus deze zou de max-verliesgrens ({floor:,.0f}) breken"
        else:
            block_here = None
        if block or block_here or open_n >= cfg["max_open"]:
            skip(block or block_here or f"al {open_n} posities/orders open (max {cfg['max_open']})")
            continue
        inst = b.instrument(s["markt"])
        if not inst or inst.get("dicht"):
            skip("markt niet beschikbaar bij de broker" if not inst else "markt bij de broker gesloten")
            continue
        side = 1 if s["kant"] == "LONG" else -1
        mid = (inst["bid"] + inst["ask"]) / 2
        basis = mid - s["ref"] if s.get("ref") else 0.0       # brokerprijs wijkt af van Yahoo (bv. goud-future vs spot)
        dist_stop, dist_tp = abs(s["entry"] - s["stop"]), abs(s["tp"] - s["entry"])
        entry = s["entry"] + basis if s["soort"] == "LIMIT" else (inst["ask"] if side > 0 else inst["bid"])
        sl, tp = entry - side * dist_stop, entry + side * dist_tp
        # risico in de valuta van het instrument: account -> USD -> instrumentvaluta
        to_inst = {"USD": 1.0, "EUR": 1 / eurusd}.get(inst["ccy"])
        if to_inst is None:
            skip(f"instrument in {inst['ccy']} wordt (nog) niet ondersteund")
            continue
        risk = nav * cfg["risico_pct"] / 100 * acc_to_usd * to_inst
        size = math.floor(risk / dist_stop / inst["step"] + 1e-6) * inst["step"]
        # hefboom: de waarde van alle posities samen mag niet boven hefboom x accountwaarde komen
        to_acc = 1 / to_inst / acc_to_usd                            # instrumentvaluta -> accountvaluta
        used = sum(abs(p["units"]) * p["prijs"] for p in b.positions()) / acc_to_usd   # benadering (in USD gerekend)
        room = cfg["hefboom"] * nav - used
        if size * entry * to_acc > room:
            size = math.floor(max(room, 0) / (entry * to_acc) / inst["step"]) * inst["step"]
        size = float(units(size, inst["step"]))
        if size < inst["min_size"]:
            skip(f"positie te klein ({size:g}, minimum {inst['min_size']:g})")
            continue
        tag = f"radar-{int(now.timestamp())}-{s['markt']}"
        until = (datetime.now(NY).replace(hour=16, minute=0, second=0, microsecond=0) if s["bron"] == "ICT"
                 else now + timedelta(hours=cfg["max_uren"]))
        try:
            if s["soort"] == "MARKET":
                ok, why = b.market(inst, side, size, sl, tp, tag)
            else:
                ok, why = b.limit(inst, side, size, entry, sl, tp, (now + timedelta(minutes=60)).astimezone(timezone.utc), tag)
        except RuntimeError as ex:
            ok, why = False, str(ex)
        detail = (f"{s['kant']} {size:g} {inst['code']} @ {entry:.{inst['prec']}f}, stop {sl:.{inst['prec']}f}, doel {tp:.{inst['prec']}f}"
                  + ("" if ok else f" — geweigerd: {why}"))
        st["orders"][s["key"]] = dict(markt=s["markt"], status="geplaatst" if ok else "mislukt", t=now.isoformat(), detail=detail,
                                      code=inst["code"], sluit_voor=until.astimezone(timezone.utc).isoformat())
        log.append(dict(t=now.isoformat(), actie=("order " + s["soort"].lower()) if ok else "mislukt", markt=s["markt"], detail=f"{s['bron']}: {detail}"))
        if ok:
            open_n += 1
    # posities koppelen aan hun signaal (voor de sluittijd): nieuwe positie op hetzelfde instrument
    for p in b.positions():
        if f"pos|{p['id']}" not in st["orders"]:
            src = next((v for k, v in reversed(list(st["orders"].items())) if not k.startswith("pos|")
                        and v.get("code") == p["instrument"] and v.get("status") == "geplaatst"), None)
            if src:
                st["orders"][f"pos|{p['id']}"] = dict(markt=src["markt"], sluit_voor=src["sluit_voor"])

    # 4. stand voor het dashboard
    a = b.account_info()
    eq = st.setdefault("equity", [])
    if not eq or now - datetime.fromisoformat(eq[-1][0]) >= timedelta(minutes=15):
        eq.append([now.isoformat(timespec="minutes"), round(a["nav"], 2)])
        del eq[:-3000]
    return dict(gekoppeld=True, broker=b.naam, account=str(a["id"])[:4] + "…" + str(a["id"])[-4:], valuta=a["ccy"], saldo=a["saldo"],
                nav=a["nav"], open_pl=a["open_pl"], start_saldo=st["start_saldo"], dag_start=st["dag_start"], piek=st["piek"],
                grens=round(floor, 2), daggrens=round(st["dag_start"] * (1 - cfg["dagverlies_pct"] / 100), 2), blokkade=block, regels=cfg,
                open_trades=b.positions(), gesloten=b.closed(), orders=b.pending(), equity=eq)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", default=str(HERE / "status.json"))
    ap.add_argument("--uit", default=str(HERE / "demo.json"))
    a = ap.parse_args()
    st = load(STATE, {})
    log = st.setdefault("log", [])
    try:
        out = run(load(a.status, {}), settings(), st, log)
    except Exception as ex:   # demo-problemen mogen de meldingen niet raken
        out = dict(gekoppeld=True, fout=f"{type(ex).__name__}: {ex}")
    del log[:-60]
    st["orders"] = dict(list(st.get("orders", {}).items())[-400:])
    out.update(gemaakt=datetime.now(NY).isoformat(timespec="seconds"), log=log[-30:][::-1], omgeving="demo-account (nepgeld)")
    STATE.write_text(json.dumps(st, indent=1))
    Path(a.uit).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"demo: {out.get('melding') or out.get('fout') or 'NAV ' + str(out.get('nav'))}")


if __name__ == "__main__":
    main()
