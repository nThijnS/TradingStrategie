"""
Capital.com REST-client (https://open-api.capital.com) met strikt gescheiden demo- en live-omgeving.

- De omgeving bepaalt het adres; er is geen per-account demo/live-vlag in de API. Daarom controleert broker.py
  daarnaast het account-ID en de sessievelden hasActiveDemoAccounts / hasActiveLiveAccounts.
- Sessies verlopen na 10 minuten zonder gebruik; bij 401 wordt één keer opnieuw ingelogd.
- Rate limits (documentatie): 10 verzoeken/s, 1 order per 0,1 s, POST /session 1/s. De client wacht zelf.
- Leesverzoeken worden bij netwerkfouten maximaal twee keer herhaald. Orderverzoeken NOOIT: een time-out bij een
  order geeft UnknownOutcome (uitkomst onbekend). broker.py zoekt dan later bij de broker na of de order er is.
- Wachtwoorden, sleutels en tokens komen nooit in foutmeldingen of logs.
"""
import json
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from risico import Instrument

URLS = {
    "demo": "https://demo-api-capital.backend-capital.com/api/v1",
    "live": "https://api-capital.backend-capital.com/api/v1",
}
TIMEOUT_S = 15


class BrokerError(RuntimeError):
    """De broker gaf een fout terug (HTTP-status bekend). Bij een order: niet uitgevoerd."""

    def __init__(self, status, msg):
        super().__init__(f"HTTP {status}: {msg}")
        self.status = status


class UnknownOutcome(RuntimeError):
    """Netwerkfout of time-out tijdens een order: we weten NIET of de order is uitgevoerd."""


class InstrumentError(RuntimeError):
    """Instrumentgegevens ontbreken of zijn niet eenduidig: niet handelen."""


def urllib_transport(method, url, headers, body):
    """Standaard HTTP-laag. Geeft (status, json, headers); gooit OSError/socket.timeout bij netwerkproblemen."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method=method, data=data, headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {}), dict(r.headers)
    except urllib.error.HTTPError as ex:
        raw = ex.read().decode(errors="replace")[:300]
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"errorCode": raw}
        return ex.code, payload, dict(ex.headers or {})


class Capital:
    def __init__(self, modus, key, ident, pw, transport=urllib_transport, sleep=time.sleep, clock=time.monotonic):
        if modus not in URLS:
            raise ValueError(f"onbekende modus {modus!r}")
        if not (key and ident and pw):
            raise BrokerError(0, f"inloggegevens voor {modus} ontbreken")
        self.modus, self.base = modus, URLS[modus]
        self._cred = (key, ident, pw)
        self._t, self._sleep, self._clock = transport, sleep, clock
        self._last = 0.0
        self.h = {}
        self.sessie = {}
        self.laatste_ok = None        # tijdstip (UTC) van het laatste geslaagde API-verzoek
        self.login()

    # ---------- transport ----------
    def _throttle(self, gap):
        wait = self._last + gap - self._clock()
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()

    def _send(self, method, path, body, headers, order):
        self._throttle(0.15 if order else 0.11)
        try:
            return self._t(method, self.base + path, headers, body)
        except (socket.timeout, TimeoutError, OSError) as ex:
            if order:
                raise UnknownOutcome(f"{method} {path}: {type(ex).__name__} — uitkomst onbekend") from None
            raise

    def login(self):
        key, ident, pw = self._cred
        self._throttle(1.05)
        status, data, hdr = self._t("POST", self.base + "/session", {"X-CAP-API-KEY": key},
                                    dict(identifier=ident, password=pw, encryptedPassword=False))
        if status != 200:
            raise BrokerError(status, f"inloggen bij Capital.com {self.modus} mislukt ({data.get('errorCode', '')})")
        h = {k.upper(): v for k, v in hdr.items()}
        if not h.get("CST") or not h.get("X-SECURITY-TOKEN"):
            raise BrokerError(status, "sessie zonder tokens ontvangen")
        self.h = {"X-CAP-API-KEY": key, "CST": h["CST"], "X-SECURITY-TOKEN": h["X-SECURITY-TOKEN"]}
        self.sessie = data
        self.laatste_ok = datetime.now(timezone.utc)

    def call(self, method, path, body=None, order=False):
        tries = 1 if order else 3
        relogged = False
        for i in range(tries):
            try:
                status, data, _ = self._send(method, path, body, self.h, order)
            except UnknownOutcome:
                raise
            except (socket.timeout, TimeoutError, OSError) as ex:
                if i == tries - 1:
                    raise BrokerError(0, f"{method} {path}: netwerkfout ({type(ex).__name__})") from None
                self._sleep(1.5 * (i + 1))
                continue
            if status == 401 and not relogged:      # sessie verlopen: opnieuw inloggen (order was niet verwerkt)
                relogged = True
                self.login()
                status, data, _ = self._send(method, path, body, self.h, order)
            if status == 429 and not order and i < tries - 1:
                self._sleep(2.0)
                continue
            if status >= 400:
                raise BrokerError(status, f"{method} {path}: {data.get('errorCode') or data}")
            self.laatste_ok = datetime.now(timezone.utc)
            return data
        raise BrokerError(0, f"{method} {path}: geen antwoord")

    # ---------- account ----------
    def select_account(self, account_id):
        """Zet het actieve account en controleert daarna bij de broker welk account echt actief is."""
        if str(self.sessie.get("currentAccountId")) != str(account_id):
            self.call("PUT", "/session", dict(accountId=account_id))
        active = self.call("GET", "/session").get("accountId")
        return str(active)

    def current_account_id(self):
        return str(self.call("GET", "/session").get("accountId"))

    def account(self, account_id):
        accs = self.call("GET", "/accounts").get("accounts", [])
        a = next((x for x in accs if str(x.get("accountId")) == str(account_id)), None)
        if a is None:
            raise BrokerError(0, "het actieve account staat niet in de accountlijst")
        b = a.get("balance") or {}
        bal, pl = float(b["balance"]), float(b.get("profitLoss") or 0)
        return dict(id=str(a["accountId"]), ccy=a.get("currency"), saldo=bal, open_pl=pl, nav=bal + pl,
                    status=a.get("status"), type=a.get("accountType"))

    # ---------- markten ----------
    def market(self, epic):
        return self.call("GET", f"/markets/{epic}")

    def instrument(self, markt, epic, now=None):
        m = self.market(epic)
        try:
            i, d, s = m["instrument"], m["dealingRules"], m["snapshot"]
            bid, ask = float(s["bid"]), float(s["offer"])
            dec = int(s["decimalPlacesFactor"])
            min_size = float(d["minDealSize"]["value"])
            step = float((d.get("minSizeIncrement") or {}).get("value") or 0)
        except (KeyError, TypeError, ValueError) as ex:
            raise InstrumentError(f"{epic}: veld ontbreekt ({ex})") from None
        if not step:
            raise InstrumentError(f"{epic}: minSizeIncrement ontbreekt")
        mid = (bid + ask) / 2

        def dist(rule):
            """Afstand als prijs. Alleen PERCENTAGE is eenduidig om te rekenen; andere eenheden laat de broker zelf
            controleren (een te korte stop wordt dan geweigerd en er ontstaat geen onbeschermde positie)."""
            if not rule or rule.get("value") is None:
                return None
            if rule.get("unit") == "PERCENTAGE":
                return mid * float(rule["value"]) / 100
            return None

        max_size = (d.get("maxDealSize") or {}).get("value")
        if (s.get("delayTime") or 0) > 0:
            status = "VERTRAAGD"
        else:
            status = s.get("marketStatus") or "ONBEKEND"
        return Instrument(markt=markt, epic=epic, ccy=i.get("currency"), lot_size=float(i.get("lotSize") or 0),
                          scaling=float(s.get("scalingFactor") or 1), min_size=min_size,
                          max_size=float(max_size) if max_size else None, step=step, decimals=dec,
                          min_stop=dist(d.get("minStopOrProfitDistance")) or 0.0,
                          max_stop=dist(d.get("maxStopOrProfitDistance")), bid=bid, ask=ask, status=status,
                          quote_time=_utc(s.get("updateTimeUTC")))

    def fx(self, src, dst):
        """Koers om een bedrag in valuta src om te rekenen naar dst, via het forexpaar bij de broker. None = onbekend."""
        if src == dst:
            return 1.0
        for epic, inv in ((f"{src}{dst}", False), (f"{dst}{src}", True)):
            try:
                s = self.market(epic)["snapshot"]
                mid = (float(s["bid"]) + float(s["offer"])) / 2
            except (BrokerError, KeyError, TypeError, ValueError):
                continue
            if mid > 0:
                return 1 / mid if inv else mid
        return None

    # ---------- posities en orders ----------
    def positions(self):
        out = []
        for x in self.call("GET", "/positions").get("positions", []):
            p, m = x.get("position", {}), x.get("market", {})
            side = 1 if p.get("direction") == "BUY" else -1
            out.append(dict(deal_id=p.get("dealId"), epic=m.get("epic"), side=side, size=float(p.get("size") or 0),
                            level=float(p.get("level") or 0), stop=_num(p.get("stopLevel")), tp=_num(p.get("profitLevel")),
                            stop_dist=_num(p.get("stopDistance")), tp_dist=_num(p.get("profitDistance")),
                            working_order_id=p.get("workingOrderId"), contract_size=_num(p.get("contractSize")),
                            created=_utc(p.get("createdDateUTC")), upl=float(p.get("upl") or 0),
                            bid=_num(m.get("bid")), ask=_num(m.get("offer"))))
        return out

    def working_orders(self):
        out = []
        for w in self.call("GET", "/workingorders").get("workingOrders", []):
            o = w.get("workingOrderData", {})
            out.append(dict(deal_id=o.get("dealId"), epic=o.get("epic"), side=1 if o.get("direction") == "BUY" else -1,
                            size=float(o.get("orderSize") or 0), level=float(o.get("orderLevel") or 0),
                            stop=_num(o.get("stopLevel")), tp=_num(o.get("profitLevel")),
                            stop_dist=_num(o.get("stopDistance")), tp_dist=_num(o.get("profitDistance")),
                            created=_utc(o.get("createdDateUTC")), good_till=o.get("goodTillDateUTC")))
        return out

    def confirm(self, ref, tries=6):
        """Wacht op de bevestiging van een order. Geeft dict(accepted, deal_id, status, reden) of UnknownOutcome."""
        for i in range(tries):
            try:
                c = self.call("GET", f"/confirms/{ref}")
            except BrokerError as ex:
                if ex.status in (0, 404) and i < tries - 1:     # nog niet verwerkt of netwerk: even wachten
                    self._sleep(0.5 * (i + 1))
                    continue
                raise UnknownOutcome(f"bevestiging {ref} niet op te halen: {ex}") from None
            deal = c.get("dealId") or next((a.get("dealId") for a in c.get("affectedDeals") or []), None)
            return dict(accepted=c.get("dealStatus") == "ACCEPTED", deal_id=deal, status=c.get("status"),
                        reden=c.get("reason") or c.get("dealStatus"), level=_num(c.get("level")))
        raise UnknownOutcome(f"bevestiging {ref} kwam niet")

    def _place(self, path, body):
        r = self.call("POST", path, body, order=True)
        ref = r.get("dealReference")
        if not ref:
            raise UnknownOutcome(f"geen dealReference ontvangen ({r})")
        return dict(self.confirm(ref), ref=ref)

    def place_market(self, epic, side, size, stop, tp):
        return self._place("/positions", dict(epic=epic, direction="BUY" if side > 0 else "SELL", size=size,
                                              guaranteedStop=False, stopLevel=stop, profitLevel=tp))

    def place_limit(self, epic, side, size, level, stop, tp, good_till):
        return self._place("/workingorders", dict(epic=epic, direction="BUY" if side > 0 else "SELL", size=size,
                                                  level=level, type="LIMIT", guaranteedStop=False, stopLevel=stop,
                                                  profitLevel=tp, goodTillDate=good_till.strftime("%Y-%m-%dT%H:%M:%S")))

    def close(self, deal_id):
        r = self.call("DELETE", f"/positions/{deal_id}", order=True)
        return self.confirm(r["dealReference"]) if r.get("dealReference") else dict(accepted=True)

    def cancel(self, deal_id):
        r = self.call("DELETE", f"/workingorders/{deal_id}", order=True)
        return self.confirm(r["dealReference"]) if r.get("dealReference") else dict(accepted=True)

    def closed(self, seconds=86400):
        tx = self.call("GET", f"/history/transactions?type=TRADE&lastPeriod={seconds}").get("transactions", [])
        return [dict(instrument=t.get("instrumentName"), dicht=(t.get("dateUtc") or "")[:19] + "+00:00",
                     pl=float(t.get("size") or 0)) for t in tx]


def _num(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _utc(s):
    """Tijd uit een *UTC-veld van de API. Velden zonder UTC in de naam worden bewust niet gebruikt."""
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "")[:26])
    except ValueError:
        return None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
