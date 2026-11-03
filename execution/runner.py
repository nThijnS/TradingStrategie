#!/usr/bin/env python3
"""
Orderuitvoering bij Capital.com: neemt de signalen uit status.json over op een DEMO-account (standaard) of,
alleen na een bewuste opt-in van de eigenaar, op een LIVE-account.

MODUS
  Demo (standaard)  geheimen CAPITAL_API_KEY, CAPITAL_IDENTIFIER, CAPITAL_PASSWORD; optioneel CAPITAL_DEMO_ACCOUNT_ID.
  Live              ALLES hieronder moet kloppen, anders gebeurt er niets (en staat de reden in demo.json):
                    1. config.json  "broker": {"modus": "live"}
                    2. config.json  "live": {"limieten_gevalideerd": true, "strategieen": ["GOUD:momentum", ...]}
                    3. GitHub-variabele CAPITAL_MODUS = live
                    4. geheim CAPITAL_LIVE_BEVESTIGING = IK-HANDEL-MET-ECHT-GELD
                    5. geheimen CAPITAL_LIVE_API_KEY, CAPITAL_LIVE_IDENTIFIER, CAPITAL_LIVE_PASSWORD
                    6. geheim CAPITAL_LIVE_ACCOUNT_ID; de broker moet bevestigen dat precies dat account actief is
                    7. de live-limieten zijn binnen de veilige grenzen van risico.Limits.problems(live=True)
  Een live-verzoek dat niet aan alles voldoet, valt NIET terug op demo: dan handelt de bot helemaal niet.

NOODSTOP  config.json "noodstop": true, of het bestand NOODSTOP in de repo, of omgevingsvariabele NOODSTOP=1.
  Wel:  geen nieuwe orders; wachtende (nog niet gevulde) limietorders van de bot worden geannuleerd.
  Niet: open posities worden NIET gesloten. Die houden hun stop-loss en take-profit bij de broker; de
        tijdsluiting (daytrade) blijft wel werken. Alles sluiten doe je zelf in Capital.com.

VEILIGHEID PER ORDER
  - Vlak voor elke order: account, posities, wachtende orders en de koers opnieuw ophalen.
  - Eén positie of order per instrument; een tweede signaal op hetzelfde instrument wordt overgeslagen.
  - Instrument en koers controleren, niveaus en grootte berekenen en de portefeuillelimieten toetsen (risico.py).
  - Het signaal wordt in het journaal gezet ("verzenden") en opgeslagen VOORDAT de order verstuurd wordt.
  - Na de order: bevestiging ophalen en controleren dat stop-loss en take-profit op de positie of order staan.
    Kan dat niet worden bevestigd, dan wordt de positie gesloten of de order geannuleerd.
  - Time-out of netwerkfout: status "onbekend". Nooit opnieuw versturen; in de volgende rondes wordt bij de
    broker nagezocht of de order er is.

    python broker.py --status status.json --uit demo.json
"""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from risk import rules as risico
from execution.capital import Capital, BrokerError, UnknownOutcome, InstrumentError
from storage import paths

HERE = paths.ROOT
SETTINGS = paths.CONFIG
NY = ZoneInfo("America/New_York")
LIVE_PHRASE = "IK-HANDEL-MET-ECHT-GELD"
STATE_FILES = dict(paths.BROKER_STATE)

# Capital.com-epics per markt. Bevestigd met capital_instrumenten.py (zie rapport/instrumenten.json);
# een epic die de broker niet kent of waarvan de gegevens niet kloppen, wordt nooit verhandeld.
EPICS = {"GOUD": "GOLD", "ZILVER": "SILVER", "OLIE": "OIL_CRUDE", "NQ": "US100", "ES": "US500", "DAX": "DE40",
         "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY", "BTC": "BTCUSD", "ETH": "ETHUSD", "SOL": "SOLUSD",
         "AAPL": "AAPL", "NVDA": "NVDA", "MSFT": "MSFT"}

ICT_ENTRY_MIN = 45        # ICT-limietorder alleen binnen 45 min na de setup, 60 min geldig
LAB_SIGNAL_MIN = 20       # lab-signaal (afgesloten uurcandle) alleen binnen 20 min na het sluiten van die candle
STATUS_MAX_MIN = 8        # status.json ouder dan dit = verouderd: geen orders
RECONCILE_MIN = 15        # zo lang zoeken we een "onbekende" order na
DEFAULT_LIMITS = dict(risico_pct=0.5, max_open_risico_pct=1.5, dagverlies_pct=3.0, totaalverlies_pct=5.0, trailing=True,
                      max_open=3, max_per_groep=1, hefboom=30, min_rr=0.0)
DEFAULTS = dict(aan=True, dag_reset="Europe/Amsterdam", max_uren=12, limieten=DEFAULT_LIMITS)


# ------------- Instellingen en modus -------------
def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def save(path, data):
    """Atomair wegschrijven: eerst een tijdelijk bestand, dan vervangen (nooit een half journaal)."""
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.replace(tmp, path)


def settings(cfg_file=SETTINGS):
    """Instellingen uit config.json. "demo" blijft werken als oude naam voor de demo-instellingen."""
    raw = load(cfg_file, {})
    s = dict(DEFAULTS)
    old = raw.get("demo", {})
    s.update({k: v for k, v in old.items() if k in ("aan", "dag_reset", "max_uren")})
    lim = dict(DEFAULT_LIMITS)
    lim.update({k: v for k, v in old.items() if k in risico.Limits.__dataclass_fields__})   # oude platte demo-instellingen
    lim.update(old.get("limieten", {}))
    s["limieten"] = lim
    s["broker"] = raw.get("broker", {})
    s["live"] = raw.get("live", {})
    s["noodstop"] = bool(raw.get("noodstop", False))
    return s


def emergency_stop(cfg, env):
    if cfg.get("noodstop"):
        return "noodstop aan in config.json"
    if (HERE / "NOODSTOP").exists():
        return "bestand NOODSTOP staat in de repo"
    if str(env.get("NOODSTOP", "")).strip().lower() in ("1", "true", "ja", "aan"):
        return "omgevingsvariabele NOODSTOP staat aan"
    return None


def resolve_mode(cfg, env):
    """Welke modus mag er draaien? Geeft dict(modus, problemen, limieten, creds, account_id)."""
    asked = str((cfg.get("broker") or {}).get("modus", "demo")).lower()
    if asked not in ("demo", "live"):
        return dict(modus="geblokkeerd", gevraagd=asked, problemen=[f"onbekende modus {asked!r} in config.json"])
    if asked == "demo":
        lim = risico.Limits.from_config(cfg["limieten"])
        creds = tuple(env.get(k, "").strip() for k in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
        probs = [f"demo-limiet: {p}" for p in lim.problems(live=False)]
        if not all(creds):
            probs.append("demo-geheimen ontbreken (CAPITAL_API_KEY, CAPITAL_IDENTIFIER, CAPITAL_PASSWORD)")
        return dict(modus="demo", gevraagd=asked, problemen=probs, limieten=lim, creds=creds,
                    account_id=env.get("CAPITAL_DEMO_ACCOUNT_ID", "").strip() or None)
    live = cfg.get("live") or {}
    lim = risico.Limits.from_config(dict(DEFAULT_LIMITS, **(live.get("limieten") or {})))
    creds = tuple(env.get(k, "").strip() for k in ("CAPITAL_LIVE_API_KEY", "CAPITAL_LIVE_IDENTIFIER", "CAPITAL_LIVE_PASSWORD"))
    probs = []
    if env.get("CAPITAL_MODUS", "").strip().lower() != "live":
        probs.append("GitHub-variabele CAPITAL_MODUS is niet 'live'")
    if env.get("CAPITAL_LIVE_BEVESTIGING", "").strip() != LIVE_PHRASE:
        probs.append("geheim CAPITAL_LIVE_BEVESTIGING ontbreekt of klopt niet")
    if not all(creds):
        probs.append("live-geheimen ontbreken (CAPITAL_LIVE_API_KEY, CAPITAL_LIVE_IDENTIFIER, CAPITAL_LIVE_PASSWORD)")
    acc = env.get("CAPITAL_LIVE_ACCOUNT_ID", "").strip()
    if not acc:
        probs.append("geheim CAPITAL_LIVE_ACCOUNT_ID ontbreekt (welk live-account precies)")
    if live.get("limieten_gevalideerd") is not True:
        probs.append("config.json live.limieten_gevalideerd staat niet op true")
    probs += [f"live-limiet: {p}" for p in lim.problems(live=True)]
    if not live.get("strategieen"):
        probs.append("config.json live.strategieen is leeg: geen enkele strategie is voor live vrijgegeven")
    return dict(modus="live" if not probs else "geblokkeerd", gevraagd=asked, problemen=probs, limieten=lim,
                creds=creds, account_id=acc or None, toegestaan=set(live.get("strategieen") or []),
                demo_account_id=env.get("CAPITAL_DEMO_ACCOUNT_ID", "").strip() or None)


def verify_account(b, mode):
    """Bevestig bij de broker welk account actief is. Geeft (account_id, reden-als-het-niet-klopt)."""
    s = b.sessie
    if mode["modus"] == "live":
        if s.get("hasActiveLiveAccounts") is False:
            return None, "de broker meldt geen actief live-account"
        active = b.select_account(mode["account_id"])
        if active != str(mode["account_id"]):
            return None, f"actief account {mask(active)} is niet het opgegeven live-account {mask(mode['account_id'])}"
        if mode.get("demo_account_id") and active == mode["demo_account_id"]:
            return None, "het live-account is gelijk aan het demo-account: modus niet eenduidig"
        return active, None
    if s.get("hasActiveDemoAccounts") is False:
        return None, "de demo-omgeving meldt geen actief demo-account"
    if mode.get("account_id"):
        active = b.select_account(mode["account_id"])
        if active != str(mode["account_id"]):
            return None, f"actief account {mask(active)} is niet het opgegeven demo-account"
        return active, None
    return b.current_account_id(), None


def mask(x):
    x = str(x or "")
    return x[:3] + "…" + x[-3:] if len(x) > 6 else "…"


# ------------- Signalen -------------
def signals(status, now):
    """Signalen die meetellen en nu nog genomen kunnen worden, met de strategie erbij (voor de live-vrijgave)."""
    out = []
    for m in status.get("markten", []):             # ICT: limietorder op de entry
        if (m.get("data_min_oud") or 999) > 20:     # ICT-data verouderd: niet handelen
            continue
        for s in m.get("setups", []):
            t = datetime.fromisoformat(s["tijd"])
            if s.get("telt") and s["status"] in ("nieuw", "wacht op entry") and timedelta(0) <= now - t < timedelta(minutes=ICT_ENTRY_MIN):
                out.append(dict(markt=m["naam"], strategie="ict", bron="ICT", key=f"ICT|{m['naam']}|{s['tijd']}|{s['kant']}",
                                kant=s["kant"], entry=s["entry"], stop=s["stop"], tp=s["tp"], soort="LIMIT", ref=m.get("koers")))
    for m in status.get("alle_markten", []):        # strategielab: marktorder na een afgesloten uurcandle
        if not m.get("open") or m.get("status") != "live":
            continue
        k = m.get("keuze") or {}
        for s in m.get("signalen", []):
            t = datetime.fromisoformat(s["t"])      # sluittijd van de signaalcandle (ligt in het verleden)
            if s["status"] == "nieuw" and timedelta(0) <= now - t < timedelta(minutes=LAB_SIGNAL_MIN):
                out.append(dict(markt=m["naam"], strategie=k.get("strategie") or "lab", bron=k.get("titel") or "lab",
                                key=f"LAB|{m['naam']}|{s['t']}|{s['kant']}", kant=s["kant"], entry=s["entry"],
                                stop=s["stop"], tp=s["tp"], soort="MARKET", ref=m.get("koers")))
    return out


# ------------- Hoofdlogica -------------
class Run:
    def __init__(self, b, mode, cfg, st, now):
        self.b, self.mode, self.cfg, self.st, self.now = b, mode, cfg, st, now
        self.lim = mode["limieten"]
        self.log = st.setdefault("log", [])
        self.orders = st.setdefault("orders", {})
        self.state_file = None

    def note(self, actie, markt="", detail=""):
        self.log.append(dict(t=self.now.isoformat(timespec="seconds"), actie=actie, markt=markt, detail=detail))

    def persist(self):
        if self.state_file:
            save(self.state_file, self.st)

    def fresh(self):
        a = self.b.account(self.acc_id)
        return a, self.b.positions(), self.b.working_orders()

    def ours(self):
        return {v["deal_id"]: k for k, v in self.orders.items() if v.get("deal_id")}

    def reconcile(self, positions, wos):
        """Orders met onbekende uitkomst nazoeken bij de broker; gevulde limietorders aan hun positie koppelen."""
        known = self.ours()
        for k, v in self.orders.items():
            if v.get("status") != "onbekend":
                continue
            sent = datetime.fromisoformat(v["t"])
            hit = next((x for x in positions + wos if x["deal_id"] not in known and x["epic"] == v["epic"]
                        and x["side"] == v["side"] and abs(x["size"] - v["size"]) < 1e-9
                        and (x["created"] is None or x["created"] >= sent - timedelta(minutes=1))), None)
            if hit:
                v.update(status="geplaatst", deal_id=hit["deal_id"], detail=v.get("detail", "") + " — gevonden bij controle")
                known[hit["deal_id"]] = k
                self.note("order teruggevonden", v["markt"], f"onbekende uitkomst: staat wél bij de broker ({mask(hit['deal_id'])})")
            elif self.now - sent > timedelta(minutes=RECONCILE_MIN):
                v["status"] = "niet gevonden"
                self.note("order niet gevonden", v["markt"], "onbekende uitkomst: na controle niet bij de broker; niet opnieuw verstuurd")
        for p in positions:                       # gevulde limietorder: de positie krijgt een eigen deal-ID
            if p["deal_id"] in known or any(v.get("positie_id") == p["deal_id"] for v in self.orders.values()):
                continue
            if p.get("working_order_id") and p["working_order_id"] in known:      # exacte koppeling via de API
                self.orders[known[p["working_order_id"]]]["positie_id"] = p["deal_id"]
                continue
            src = next((v for v in reversed(list(self.orders.values())) if v.get("soort") == "LIMIT" and v.get("status") == "geplaatst"
                        and v.get("epic") == p["epic"] and v.get("side") == p["side"] and not v.get("positie_id")
                        and (p["created"] is None or p["created"] >= datetime.fromisoformat(v["t"]) - timedelta(minutes=1))), None)
            if src:
                src["positie_id"] = p["deal_id"]

    def time_exits(self, positions):
        """Daytrade: posities van de bot na hun sluittijd sluiten (ook tijdens een noodstop)."""
        by_id = {}
        for v in self.orders.values():
            for pid in (v.get("deal_id"), v.get("positie_id")):
                if pid:
                    by_id[pid] = v
        for p in positions:
            v = by_id.get(p["deal_id"])
            if v and v.get("sluit_voor") and self.now >= datetime.fromisoformat(v["sluit_voor"]):
                try:
                    self.b.close(p["deal_id"])
                    self.note("gesloten (tijd)", v["markt"], f"positie {mask(p['deal_id'])}")
                except (BrokerError, UnknownOutcome) as ex:
                    self.note("sluiten mislukt", v["markt"], str(ex))

    def cancel_ours(self, wos, why):
        known = self.ours()
        for w in wos:
            if w["deal_id"] in known:
                try:
                    self.b.cancel(w["deal_id"])
                    self.orders[known[w["deal_id"]]]["status"] = "geannuleerd"
                    self.note("order geannuleerd", self.orders[known[w["deal_id"]]]["markt"], why)
                except (BrokerError, UnknownOutcome) as ex:
                    self.note("annuleren mislukt", "", str(ex))

    def book(self, a, positions, wos, fxc):
        """Portefeuille uit verse brokerdata: risico vanaf de huidige prijs tot de stop, in accountvaluta."""
        risks, expo, notional = [], [], 0.0
        rev = {v: k for k, v in EPICS.items()}
        sent = {}                                  # stops die de bot zelf meestuurde en de broker accepteerde
        for v in self.orders.values():
            for pid in (v.get("deal_id"), v.get("positie_id")):
                if pid and v.get("stop") is not None and v.get("status") == "geplaatst":
                    sent[pid] = v["stop"]
        for p in positions:
            f = fxc(p["epic"])
            stop = p["stop"] if p["stop"] is not None else (sent.get(p["deal_id"]) if p.get("stop_dist") or p.get("stop") else None)
            p = dict(p, stop=stop)
            if p["stop"] is None or f is None or (p.get("contract_size") not in (None, 1, 1.0)):
                risks.append(None)                 # risico onbekend: blokkeert nieuwe orders
            else:
                cur = (p["bid"] if p["side"] > 0 else p["ask"]) or p["level"]
                risks.append(max(0.0, (cur - p["stop"]) * p["side"] * p["size"] * f))
                notional += abs(p["size"] * cur * f)
            expo.append((rev.get(p["epic"], p["epic"]), p["side"]))
        for w in wos:
            f = fxc(w["epic"])
            wstop = w["stop"] if w["stop"] is not None else (sent.get(w["deal_id"]) if w.get("stop_dist") else None)
            risks.append(None if (wstop is None or f is None) else abs(w["level"] - wstop) * w["size"] * f)
            expo.append((rev.get(w["epic"], w["epic"]), w["side"]))
            if f:
                notional += abs(w["size"] * w["level"] * f)
        return risico.Book(equity=a["nav"], day_start=self.st["dag_start"], peak=self.st["piek"], start=self.st["start_saldo"],
                           open_risks=risks, exposures=expo, used_notional=notional)

    def handle(self, s):
        o = dict(markt=s["markt"], strategie=s["strategie"], bron=s["bron"], soort=s["soort"], t=self.now.isoformat())

        def skip(why):
            self.orders[s["key"]] = dict(o, status="overgeslagen", reden=why)
            self.note("overgeslagen", s["markt"], f"{s['bron']}: {why}")

        if self.mode["modus"] == "live" and f"{s['markt']}:{s['strategie']}" not in self.mode["toegestaan"]:
            return skip(f"{s['markt']}:{s['strategie']} is niet vrijgegeven voor live (config.json live.strategieen)")
        epic = EPICS.get(s["markt"])
        if not epic:
            return skip("geen geverifieerd Capital.com-instrument voor deze markt")
        # 1. alles vers ophalen
        a, positions, wos = self.fresh()
        if any(x["epic"] == epic for x in positions + wos):
            return skip("er staat al een positie of order op dit instrument")
        try:
            inst = self.b.instrument(s["markt"], epic)
        except (InstrumentError, BrokerError) as ex:
            return skip(f"instrumentgegevens niet bruikbaar: {ex}")
        why = risico.check_instrument(inst) or risico.check_quote(inst, self.now, self.lim.max_koers_leeftijd_s)
        if why:
            return skip(why)
        # 2. niveaus en grootte
        basis = (inst.bid + inst.ask) / 2 - s["ref"] if s.get("ref") else 0.0
        plan, why = risico.plan_levels(s, inst, self.lim, basis)
        if why:
            return skip(why)
        fx_cache = {}

        def fxc(e):
            if e not in fx_cache:
                ccy = inst.ccy if e == epic else self._ccy(e)
                fx_cache[e] = self.b.fx(ccy, a["ccy"]) if ccy else None
            return fx_cache[e]

        why = risico.size_plan(plan, inst, self.lim, a["nav"], fxc(epic))
        if why:
            return skip(why)
        # 3. limieten met de verse portefeuille
        why = risico.check_portfolio(self.book(a, positions, wos, fxc), self.lim, plan, s["markt"])
        if why:
            return skip(why)
        # 4. journaal vóór verzenden
        until = (datetime.now(NY).replace(hour=16, minute=0, second=0, microsecond=0) if s["strategie"] == "ict"
                 else self.now + timedelta(hours=self.cfg["max_uren"]))
        detail = (f"{s['kant']} {plan.size:g} {epic} @ {plan.entry}, stop {plan.stop}, doel {plan.tp}, "
                  f"risico {plan.risico_acc:,.2f} {a['ccy']}")
        rec = dict(o, status="verzenden", epic=epic, side=plan.side, size=plan.size, entry=plan.entry, stop=plan.stop,
                   tp=plan.tp, risico=round(plan.risico_acc, 2), detail=detail, sluit_voor=until.astimezone(timezone.utc).isoformat())
        self.orders[s["key"]] = rec
        self.persist()
        # 5. versturen en bevestigen
        try:
            if plan.soort == "MARKET":
                r = self.b.place_market(epic, plan.side, plan.size, plan.stop, plan.tp)
            else:
                r = self.b.place_limit(epic, plan.side, plan.size, plan.entry, plan.stop, plan.tp,
                                       (self.now + timedelta(minutes=60)).astimezone(timezone.utc))
        except UnknownOutcome as ex:
            rec.update(status="onbekend", reden=str(ex))
            self.note("uitkomst onbekend", s["markt"], f"{detail} — {ex}; wordt nagezocht, niet opnieuw verstuurd")
            return self.persist()
        except BrokerError as ex:
            rec.update(status="geweigerd", reden=str(ex))
            self.note("geweigerd", s["markt"], f"{detail} — {ex}")
            return self.persist()
        rec["ref"] = r.get("ref")
        if not r["accepted"]:
            rec.update(status="geweigerd", reden=r.get("reden"))
            self.note("geweigerd door broker", s["markt"], f"{detail} — {r.get('reden')}")
            return self.persist()
        rec.update(status="geplaatst", deal_id=r.get("deal_id"))
        self.verify_protection(rec, plan, inst)
        self.persist()

    def _ccy(self, epic):
        try:
            return self.b.market(epic)["instrument"]["currency"]
        except (BrokerError, KeyError, TypeError):
            return None

    def verify_protection(self, rec, plan, inst):
        """Staan stop-loss en take-profit echt bij de broker? Zo niet: positie sluiten of order annuleren."""
        tick = 10 ** -inst.decimals
        try:
            pool = self.b.positions() if plan.soort == "MARKET" else self.b.working_orders()
        except (BrokerError, OSError) as ex:
            pool, rec["controle"] = None, f"controle niet mogelijk: {ex}"
        x = next((p for p in pool or [] if p["deal_id"] == rec.get("deal_id")), None)
        tol = max(1.5 * tick, 0.1 * abs(plan.entry - plan.stop))
        if x is None:
            ok = False
        elif x["stop"] is not None:            # absolute stop: aan de goede kant en dicht bij wat we stuurden
            ok = (x["level"] - x["stop"]) * plan.side > 0 and abs(x["stop"] - plan.stop) <= tol and (x["tp"] is not None or bool(x.get("tp_dist")))
        else:                                  # alleen afstanden (zo toont de API wachtende orders): moeten er zijn en > 0
            ok = bool(x.get("stop_dist")) and x["stop_dist"] > 0 and (x["tp"] is not None or bool(x.get("tp_dist")))
        if ok:
            self.note("order " + plan.soort.lower(), rec["markt"], f"{rec['bron']}: {rec['detail']} — stop en doel bevestigd")
            return
        rec["status"] = "zonder bevestigde bescherming"
        try:
            if plan.soort == "MARKET" and rec.get("deal_id"):
                self.b.close(rec["deal_id"])
            elif rec.get("deal_id"):
                self.b.cancel(rec["deal_id"])
            rec["status"] = "teruggedraaid"
            self.note("teruggedraaid", rec["markt"], f"stop/doel niet bevestigd bij de broker: {'positie gesloten' if plan.soort == 'MARKET' else 'order geannuleerd'}")
        except (BrokerError, UnknownOutcome) as ex:
            self.note("LET OP", rec["markt"], f"stop/doel niet bevestigd en terugdraaien mislukt ({ex}): controleer Capital.com")


def run(status, cfg, env, st_by_mode, connect=None, now=None):
    """Eén ronde. Geeft de stand voor het dashboard (demo.json). Plaatst alleen orders als alles klopt."""
    now = now or datetime.now(timezone.utc)
    mode = resolve_mode(cfg, env)
    base = dict(modus=mode["modus"], gevraagde_modus=mode["gevraagd"], omgeving=label(mode["modus"]))
    stop = emergency_stop(cfg, env)
    base["noodstop"] = stop
    if mode["modus"] == "geblokkeerd":
        return dict(base, gekoppeld=False, blokkade="live gevraagd maar niet vrijgegeven: " + "; ".join(mode["problemen"]),
                    problemen=mode["problemen"])
    if mode["problemen"]:
        return dict(base, gekoppeld=False, melding="Nog niet gekoppeld: " + "; ".join(mode["problemen"]), problemen=mode["problemen"])
    if not cfg["aan"]:
        return dict(base, gekoppeld=True, uit=True, melding="Orderuitvoering staat uit (config.json: demo.aan = false).")
    st = st_by_mode
    b = (connect or (lambda m: Capital(m["modus"], *m["creds"])))(mode)
    acc_id, why = verify_account(b, mode)
    base.update(broker=f"Capital.com {mode['modus']}", laatste_api_controle=b.laatste_ok.isoformat(timespec="seconds") if b.laatste_ok else None,
                limieten=mode["limieten"].__dict__)
    if why:
        return dict(base, gekoppeld=True, blokkade=f"account niet bevestigd: {why}. Geen orders.")
    r = Run(b, mode, cfg, st, now)
    r.acc_id = acc_id
    r.state_file = STATE_FILES[mode["modus"]]
    a, positions, wos = r.fresh()
    if st.get("account") and st["account"] != acc_id:          # ander account dan vorige keer: tellers opnieuw
        for k in ("start_saldo", "piek", "dag", "dag_start", "equity"):
            st.pop(k, None)
    st["account"] = acc_id
    day = datetime.now(ZoneInfo(cfg["dag_reset"])).date().isoformat()
    st.setdefault("start_saldo", a["nav"])
    st["piek"] = max(st.get("piek", a["nav"]), a["nav"])
    if st.get("dag") != day:
        st["dag"], st["dag_start"] = day, max(a["nav"], a["saldo"])   # zoals prop firms: hoogste van saldo en waarde
    r.reconcile(positions, wos)
    r.time_exits(positions)
    blok = None
    made = datetime.fromisoformat(status["gemaakt"]) if status.get("gemaakt") else None
    if stop:
        blok = f"NOODSTOP: {stop}. Geen nieuwe orders; open posities houden hun stop en doel."
        r.cancel_ours(wos, "noodstop")
    elif made is None or now - made > timedelta(minutes=STATUS_MAX_MIN):
        blok = "status.json ontbreekt of is verouderd: geen nieuwe orders"
    if not blok:
        for s in signals(status, now):
            if s["key"] in r.orders:
                continue
            try:
                r.handle(s)
            except (BrokerError, InstrumentError) as ex:      # één signaal mag de rest niet tegenhouden
                r.orders.setdefault(s["key"], dict(markt=s["markt"], status="fout", reden=str(ex), t=now.isoformat()))
                r.note("fout", s["markt"], str(ex))
    a, positions, wos = r.fresh()
    eq = st.setdefault("equity", [])
    if not eq or now - datetime.fromisoformat(eq[-1][0]) >= timedelta(minutes=15):
        eq.append([now.isoformat(timespec="minutes"), round(a["nav"], 2)])
        del eq[:-3000]
    lim = mode["limieten"]
    floor = (st["piek"] if lim.trailing else st["start_saldo"]) * (1 - lim.totaalverlies_pct / 100)
    rev = {v: k for k, v in EPICS.items()}
    try:
        closed = b.closed()
    except BrokerError:
        closed = []
    return dict(base, gekoppeld=True, account=mask(acc_id), valuta=a["ccy"], saldo=a["saldo"], nav=a["nav"], open_pl=a["open_pl"],
                start_saldo=st["start_saldo"], dag_start=st["dag_start"], piek=st["piek"], grens=round(floor, 2),
                daggrens=round(st["dag_start"] * (1 - lim.dagverlies_pct / 100), 2), blokkade=blok,
                laatste_api_controle=b.laatste_ok.isoformat(timespec="seconds") if b.laatste_ok else None,
                regels=dict(lim.__dict__, max_uren=cfg["max_uren"], risico_pct=lim.risico_pct),
                open_trades=[dict(instrument=p["epic"], markt=rev.get(p["epic"]), units=p["size"] * p["side"], prijs=p["level"],
                                  open=p["created"].isoformat() if p["created"] else None, pl=p["upl"], stop=p["stop"], doel=p["tp"])
                             for p in positions],
                orders=[dict(instrument=w["epic"], units=w["size"] * w["side"], prijs=w["level"], geldig_tot=w["good_till"]) for w in wos],
                gesloten=closed, equity=eq,
                onbekend=[k for k, v in r.orders.items() if v.get("status") == "onbekend"])


def label(modus):
    return {"demo": "DEMO-account (nepgeld)", "live": "LIVE-account (ECHT GELD)",
            "geblokkeerd": "live gevraagd, maar geblokkeerd: geen orders"}.get(modus, modus)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", default=str(HERE / "status.json"))
    ap.add_argument("--uit", default=str(HERE / "demo.json"))
    a = ap.parse_args()
    cfg = settings()
    env = dict(os.environ)
    asked = str((cfg.get("broker") or {}).get("modus", "demo")).lower()
    sf = STATE_FILES.get(asked, STATE_FILES["demo"])
    st = load(sf, {})
    try:
        out = run(load(a.status, {}), cfg, env, st)
    except Exception as ex:   # problemen met de broker mogen de meldingen niet raken
        out = dict(gekoppeld=True, modus=asked, omgeving=label(asked), fout=f"{type(ex).__name__}: {ex}", blokkade="fout: geen orders")
    log = st.setdefault("log", [])
    del log[:-60]
    st["orders"] = dict(list(st.get("orders", {}).items())[-400:])
    out.update(gemaakt=datetime.now(NY).isoformat(timespec="seconds"), log=log[-30:][::-1])
    if st:
        save(sf, st)
    Path(a.uit).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":"), default=str))
    print(f"broker ({out.get('modus')}): {out.get('blokkade') or out.get('melding') or out.get('fout') or 'NAV ' + str(out.get('nav'))}")


if __name__ == "__main__":
    main()
