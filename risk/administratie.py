"""
Saldo-administratie: stortingen en opnames (geldstromen) apart van het handelsresultaat.

Alleen rekenwerk, geen netwerk: execution/runner.py geeft de brokergegevens en bewaart de stand.

BEGRIPPEN (alles in accountvaluta)
  startkapitaal      config.json administratie.startkapitaal.bedrag, anders het eerste saldo dat de bot zag
                     (start_saldo in de brokerstatus)
  geldstromen        config.json administratie.geldstromen: [{"t": ISO-tijd met tijdzone, "bedrag": +storting / -opname,
                     "omschrijving": "..."}]. Ze worden met de hand vastgelegd: de bot leidt ze nooit zelf af.
  inleg(t)           startkapitaal + alle geldstromen tot en met t
  handelsresultaat   P = accountwaarde (NAV) - inleg. Een storting verandert P dus niet.
  risicobasis B      config.json demo.risicokapitaal (bijv. 10000) als dat is ingesteld, anders de inleg
  risicovermogen E   min(B + P, NAV): het vermogen waarmee de limieten rekenen, alsof het account B groot is.
                     Positiegrootte rekent met min(E, B), dus nooit met meer dan het risicokapitaal.

Piek en dagstart worden als handelsresultaat bewaard (P_piek, P_dag). Een storting schuift ze dus niet op en
telt niet als winst; de limieten (risk/rules.check_portfolio) blijven ongewijzigd en krijgen B + P_piek, B + P_dag.

ONZEKERHEID
  De bot kent geen geldstromen uit de brokerhistorie. Hij markeert wel een saldowijziging die hij niet kan
  verklaren: zonder open posities, zonder gesloten trades en zonder vastgelegde geldstroom in die periode. Zolang
  zo'n wijziging niet is vastgelegd (als geldstroom of in administratie.geaccepteerd) plaatst hij geen nieuwe
  orders: anders zou een storting als winst meetellen in de limieten.
"""
import json
from datetime import datetime

TOL = 0.01          # afronding van de broker (centen)


def _t(x):
    t = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("tijd zonder tijdzone")
    return t


def load(raw, start_saldo=None):
    """Administratie uit config.json (raw = de hele config). Geeft dict(startkapitaal, bron, geldstromen, problemen,
    geaccepteerd). Een ongeldige regel wordt een probleem, niet stil overgeslagen."""
    a = (raw or {}).get("administratie") or {}
    probs, flows = [], []
    sk = a.get("startkapitaal")
    if isinstance(sk, dict) and sk.get("bedrag") is not None:
        try:
            start, bron = float(sk["bedrag"]), "config.json administratie.startkapitaal"
            if start <= 0:
                raise ValueError
        except (TypeError, ValueError):
            start, bron = None, None
            probs.append("administratie.startkapitaal.bedrag is geen positief getal")
    else:
        start, bron = (float(start_saldo), "eerste saldo dat de bot zag (start_saldo)") if start_saldo else (None, None)
    if start is None:
        start = 0.0                       # alleen om te kunnen rekenen; het probleem blokkeert nieuwe orders
        if not probs:
            probs.append("startkapitaal onbekend: leg administratie.startkapitaal vast in config.json")
    for i, g in enumerate(a.get("geldstromen") or []):
        try:
            b = float(g["bedrag"])
            if abs(b) < TOL:
                raise ValueError("bedrag 0")
            flows.append(dict(t=_t(g["t"]), bedrag=b, omschrijving=str(g.get("omschrijving", "")),
                              soort="storting" if b > 0 else "opname"))
        except (KeyError, TypeError, ValueError) as ex:
            probs.append(f"administratie.geldstromen[{i}] ongeldig ({ex}): verwacht t (ISO-tijd met tijdzone) en bedrag")
    flows.sort(key=lambda f: f["t"])
    return dict(startkapitaal=start, bron=bron, geldstromen=flows, problemen=probs,
                geaccepteerd=set(str(x) for x in a.get("geaccepteerd") or []))


def flows_between(adm, a, b):
    """Som van de geldstromen met a < t <= b (a = None: vanaf het begin)."""
    return sum(f["bedrag"] for f in adm["geldstromen"] if (a is None or f["t"] > a) and f["t"] <= b)


def inleg(adm, t):
    return adm["startkapitaal"] + flows_between(adm, None, t)


def trading_curve(equity, adm):
    """Accountwaarde zonder geldstromen: [[t, NAV - geldstromen tot t]]. Uit de ruwe reeks af te leiden, dus niets
    van de ruwe reeks gaat verloren."""
    return [[t, round(v - flows_between(adm, None, _t(t)), 2)] for t, v in equity]


def confirm_in_series(equity, adm):
    """Per geldstroom: zit er in de ruwe equityreeks een sprong van ongeveer dat bedrag rond dat tijdstip?
    Alleen een controle voor het dashboard; de berekening gebruikt dit niet."""
    out = []
    pts = [(_t(t), v) for t, v in equity]
    for f in adm["geldstromen"]:
        hit = None
        for (t1, v1), (t2, v2) in zip(pts, pts[1:]):
            if t1 < f["t"] <= t2:
                hit = dict(van=v1, naar=v2, sprong=round(v2 - v1, 2))
                break
        ok = hit is not None and abs(hit["sprong"] - f["bedrag"]) <= max(1.0, 0.01 * abs(f["bedrag"]))
        out.append(dict(t=f["t"].isoformat(), bedrag=f["bedrag"], omschrijving=f["omschrijving"],
                        in_equityreeks="ja" if ok else ("andere sprong" if hit else "geen meetpunten rond dit tijdstip"),
                        sprong=hit and hit["sprong"]))
    return out


def fingerprint(adm):
    """Verandert als startkapitaal of geldstromen in config.json veranderen."""
    return json.dumps([adm["startkapitaal"], [(f["t"].isoformat(), f["bedrag"]) for f in adm["geldstromen"]]])


def _peak_from_series(st, adm):
    """Hoogste handelsresultaat in de ruwe equityreeks, alleen tot de eerste onverklaarde saldowijziging (daarna kan
    de reeks een niet-vastgelegde storting bevatten)."""
    open_jumps = unresolved(st, adm)
    cut = min((_t(x["van_t"]) for x in open_jumps), default=None)
    pts = [v - adm["startkapitaal"] for t, v in trading_curve(st.get("equity") or [], adm) if cut is None or _t(t) <= cut]
    return max(pts) if pts else None


def rebase(st, adm, now, day_start_t):
    """Startkapitaal of geldstromen zijn veranderd (bijvoorbeeld een storting achteraf vastgelegd): piek en dagstart
    opnieuw afleiden uit de ruwe gegevens, zodat een eerder als winst meegetelde storting de grenzen niet blijft
    vertekenen. Een kortere piek tussen twee meetpunten van de reeks kan daarbij wegvallen."""
    s = st["administratie"]
    old = dict(resultaat_piek=s.get("resultaat_piek"), resultaat_dag_start=s.get("resultaat_dag_start"))
    s["resultaat_piek"] = _peak_from_series(st, adm)
    if st.get("dag_start") is not None and st.get("dag") == s.get("resultaat_dag"):
        s["resultaat_dag_start"] = st["dag_start"] - inleg(adm, day_start_t)
    s.setdefault("herberekend", []).append(dict(t=now.isoformat(timespec="seconds"), oud=old,
                                                nieuw=dict(resultaat_piek=s["resultaat_piek"],
                                                           resultaat_dag_start=s["resultaat_dag_start"])))
    del s["herberekend"][:-20]
    s["vingerafdruk"] = fingerprint(adm)
    return s


def migrate(st, adm, now, day_start_t):
    """Eenmalig: de administratie in de brokerstatus zetten. De oude velden blijven staan (en worden in
    administratie.migratie bewaard); er wordt niets overschreven. P_piek komt uit de ruwe equityreeks min de
    geldstromen; P_dag uit de dagstart min de inleg op het begin van de dag."""
    dag_p = None
    if st.get("dag_start") is not None:
        dag_p = st["dag_start"] - inleg(adm, day_start_t)
    st["administratie"] = dict(
        versie=1, resultaat_piek=_peak_from_series(st, adm), resultaat_dag=st.get("dag"), resultaat_dag_start=dag_p,
        onverklaard=[], vorige=None, vingerafdruk=fingerprint(adm),
        migratie=dict(t=now.isoformat(timespec="seconds"),
                      oud={k: st.get(k) for k in ("start_saldo", "piek", "dag", "dag_start")},
                      toelichting="piek en dagstart opnieuw bepaald als handelsresultaat, zonder geldstromen; "
                                  "de oude waarden (inclusief storting) staan hier en in de oude velden"))
    return st["administratie"]


def update(st, adm, a, now, day, day_start_t, positions_open, closed_since_prev):
    """Elke ronde: piek en dagstart (als handelsresultaat) bijwerken en onverklaarde saldowijzigingen markeren.
    a = account (nav, saldo). Geeft de bijgewerkte administratie in st."""
    s = st["administratie"]
    p = a["nav"] - inleg(adm, now)
    prev = s.get("vorige")
    if prev and not prev["open"] and not positions_open and not closed_since_prev:
        t0 = _t(prev["t"])
        diff = a["saldo"] - prev["saldo"] - flows_between(adm, t0, now)
        if abs(diff) >= TOL:
            s.setdefault("onverklaard", []).append(dict(id=f"{prev['t']}|{round(diff, 2)}", van_t=prev["t"],
                                                       tot_t=now.isoformat(timespec="seconds"), van=prev["saldo"],
                                                       naar=a["saldo"], verschil=round(diff, 2)))
            del s["onverklaard"][:-50]
    s["vorige"] = dict(t=now.isoformat(timespec="seconds"), saldo=a["saldo"], open=bool(positions_open))
    if unresolved(st, adm):
        # zolang een saldowijziging niet verklaard is, kan P een storting bevatten: piek en dagstart niet bijwerken
        return s
    if s.get("resultaat_dag") != day or s.get("resultaat_dag_start") is None:
        # zoals de dagstart: hoogste van saldo en waarde, min de inleg
        s["resultaat_dag"], s["resultaat_dag_start"] = day, max(a["nav"], a["saldo"]) - inleg(adm, now)
    s["resultaat_piek"] = p if s.get("resultaat_piek") is None else max(s["resultaat_piek"], p)
    return s


def unresolved(st, adm):
    """Onverklaarde saldowijzigingen die nog niet zijn vastgelegd (als geldstroom in hun periode of geaccepteerd)."""
    out = []
    for x in (st.get("administratie") or {}).get("onverklaard", []):
        if x["id"] in adm["geaccepteerd"]:
            continue
        if abs(flows_between(adm, _t(x["van_t"]), _t(x["tot_t"])) - x["verschil"]) < TOL:
            continue
        out.append(x)
    return out


def risk_view(nav, adm, st, risicokapitaal, now):
    """Getallen voor de limieten en de positiegrootte. Geeft dict met P, B, E, piek/dagstart (E-termen) en de
    omrekening naar accountwaarde (voor het dashboard)."""
    s = st["administratie"]
    lay = inleg(adm, now)
    p = nav - lay
    b = float(risicokapitaal) if risicokapitaal else lay
    e = min(b + p, nav)
    pk = b + max(s["resultaat_piek"] if s.get("resultaat_piek") is not None else p, p)
    dg = b + (s["resultaat_dag_start"] if s.get("resultaat_dag_start") is not None else p)
    return dict(handelsresultaat=round(p, 2), inleg=round(lay, 2), risicobasis=b,
                risicobasis_bron="config.json demo.risicokapitaal" if risicokapitaal else "inleg (startkapitaal + geldstromen)",
                risicovermogen=round(e, 2), sizing_vermogen=min(e, b), piek=pk, dag_start=dg, start=b,
                naar_nav=nav - e)          # optellen bij een grens in E-termen = dezelfde grens als accountwaarde
