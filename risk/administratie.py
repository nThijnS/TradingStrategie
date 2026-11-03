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

SALDOCONTROLE (fail closed)
  De bot kent geen geldstromen uit de brokerhistorie. Hij vergelijkt het saldo (zonder open winst/verlies) met de
  vorige meting: verschil = saldowijziging - resultaat van de trades die in die periode sloten (uit de
  gesloten-tradehistorie, herkend aan instrument, tijd en bedrag) - vastgelegde geldstromen. Blijft er iets over,
  dan wordt dat een onopgeloste post. Zolang er zo'n post is, plaatst hij geen nieuwe orders en worden piek en
  dagstart niet bijgewerkt; anders zou een storting als winst meetellen in de limieten.
  - Vergelijkingsmeting: alleen een meting zonder open posities of orders, met beschikbare tradehistorie. Ze wordt
    pas vervangen als het verschil is afgehandeld (verklaard, of vastgelegd als onopgeloste post).
  - Tradehistorie niet beschikbaar en het saldo is veranderd: voorlopige post; de vergelijkingsmeting blijft staan
    tot de historie er weer is.
  - Open posities: geen vergelijking (rente en open resultaat lopen door); de vorige meting blijft staan, zodat een
    storting tijdens een open positie bij de volgende meting zonder posities alsnog opvalt.
  - Rente (swap) over het dagelijkse rollmoment staat niet in de tradehistorie en geeft dus ook een post. Die
    keur je goed met administratie.geaccepteerd (id) of je legt haar vast.
  Een post is opgelost als de vastgelegde geldstromen in die periode haar verklaren of als haar id in
  administratie.geaccepteerd staat.

RAPPORTAGE (report, voor het dashboard)
  Zolang er een onopgeloste of voorlopige post is, kan NAV - inleg een niet-vastgelegde storting bevatten. Het
  handelsresultaat heet dan "voorlopig" en heeft geen definitief getal: het dashboard krijgt het laatst bevestigde
  resultaat (bij de vergelijkingsmeting voor de eerste post), het onverklaarde bedrag apart en NAV - inleg alleen als
  "inclusief onverklaard". De grafiek zonder geldstromen stopt op dat moment; de punten daarna staan apart.
"""
import json
from collections import Counter
from datetime import datetime, timedelta

TOL = 0.01          # afronding van de broker (centen)
HISTORY_H = 24      # execution/capital.closed() vraagt de gesloten trades van de laatste 24 uur op


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


def _cut(st, adm):
    """Begin van de eerste onopgeloste saldowijziging (None als er geen is). Daarna kan de reeks een niet-vastgelegde
    storting bevatten."""
    return min((_t(x["van_t"]) for x in unresolved(st, adm)), default=None)


def _peak_from_series(st, adm):
    """Hoogste handelsresultaat in de ruwe equityreeks, alleen tot de eerste onverklaarde saldowijziging."""
    cut = _cut(st, adm)
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


def _trade_key(c):
    return f"{c.get('instrument')}|{c.get('dicht')}|{c.get('pl')}"


def _post(prev, now, a, bruto, adm, reden, trades=None, voorlopig=False, suffix=None):
    t0 = _t(prev["t"])
    return dict(id=f"{prev['t']}|{suffix or round(bruto, 2)}", van_t=prev["t"], tot_t=now.isoformat(timespec="seconds"),
                van=prev["saldo"], naar=a["saldo"], bruto=round(bruto, 2), trades=trades,
                verschil=round(bruto - flows_between(adm, t0, now), 2), reden=reden, voorlopig=voorlopig)


def check_balance(s, adm, a, now, positions_open, closed_now):
    """De saldocontrole (zie boven). closed_now = gesloten trades van de laatste 24 uur, of None als de
    tradehistorie niet op te halen was. Werkt s["vorige"] en s["onverklaard"] bij."""
    posts = [x for x in s.get("onverklaard", []) if not x.get("voorlopig")]     # voorlopige post: elke ronde opnieuw
    prev = s.get("vorige")
    keys = None if closed_now is None else [_trade_key(c) for c in closed_now]
    me = dict(t=now.isoformat(timespec="seconds"), saldo=a["saldo"], gezien=keys)
    if positions_open:
        pass                                       # geen vergelijking; de vorige meting blijft staan
    elif prev is None:
        if keys is not None:
            s["vorige"] = me
    elif keys is None:                             # historie weg: niets afleiden, vorige meting houden
        bruto = a["saldo"] - prev["saldo"]
        if abs(bruto - flows_between(adm, _t(prev["t"]), now)) >= TOL:
            posts.append(_post(prev, now, a, bruto, adm, "gesloten-tradehistorie niet beschikbaar: saldowijziging niet te "
                                                         "verklaren", voorlopig=True, suffix="historie"))
    else:
        new = Counter(keys) - Counter(prev.get("gezien") or [])
        amount = {}
        for c in closed_now:
            try:
                amount.setdefault(_trade_key(c), float(c.get("pl") or 0.0))
            except (TypeError, ValueError):
                amount.setdefault(_trade_key(c), 0.0)     # onleesbaar bedrag: niet als verklaring meetellen
        pl = sum(amount[k] * n for k, n in new.items())
        bruto = a["saldo"] - prev["saldo"] - pl
        too_long = now - _t(prev["t"]) > timedelta(hours=HISTORY_H - 1)
        if too_long or abs(bruto - flows_between(adm, _t(prev["t"]), now)) >= TOL:
            n = sum(new.values())
            reden = (f"periode langer dan de opgevraagde tradehistorie ({HISTORY_H} uur): niet volledig te verklaren"
                     if too_long else f"saldowijziging na aftrek van {n} gesloten trade(s) ({pl:+,.2f}) en vastgelegde "
                                      f"geldstromen" if n else "saldowijziging zonder gesloten trade of vastgelegde geldstroom")
            posts.append(_post(prev, now, a, bruto, adm, reden, trades=round(pl, 2)))
        s["vorige"] = me                           # afgehandeld: verklaard, of als post bewaard
    s["onverklaard"] = posts[-50:]


def update(st, adm, a, now, day, day_start_t, positions_open, closed_now):
    """Elke ronde: saldocontrole, daarna piek en dagstart (als handelsresultaat) bijwerken. a = account (nav, saldo);
    closed_now = gesloten trades (lijst) of None als die niet op te halen waren. Geeft de administratie in st."""
    s = st["administratie"]
    p = a["nav"] - inleg(adm, now)
    check_balance(s, adm, a, now, positions_open, closed_now)
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
        explained = abs(flows_between(adm, _t(x["van_t"]), _t(x["tot_t"])) - x.get("bruto", x["verschil"])) < TOL
        if explained and not x.get("voorlopig") and not x.get("reden", "").startswith("periode langer"):
            continue
        out.append(dict(x, verschil=round(x.get("bruto", x["verschil"]) - flows_between(adm, _t(x["van_t"]), _t(x["tot_t"])), 2)))
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


def report(nav, adm, st, now):
    """Handelsresultaat en grafiek voor het dashboard (zie RAPPORTAGE boven). status "definitief": handelsresultaat =
    NAV - inleg. status "voorlopig": handelsresultaat None, met bevestigd (+ bevestigd_t), onverklaard_bedrag en
    handelsresultaat_incl_onverklaard; equity_zonder_geldstromen loopt dan tot bevestigd_t en equity_voorlopig bevat de
    punten daarna (inclusief het onverklaarde bedrag)."""
    p = round(nav - inleg(adm, now), 2)
    curve = trading_curve(st.get("equity") or [], adm)
    open_jumps = unresolved(st, adm)
    if not open_jumps:
        return dict(status="definitief", handelsresultaat=p, bevestigd=p, bevestigd_t=now.isoformat(timespec="seconds"),
                    onverklaard_bedrag=0.0, handelsresultaat_incl_onverklaard=p,
                    equity_zonder_geldstromen=curve, equity_voorlopig=[])
    first = min(open_jumps, key=lambda x: _t(x["van_t"]))
    cut = _t(first["van_t"])
    # de vergelijkingsmeting is gedaan zonder open posities: saldo = accountwaarde, dus een bevestigd resultaat
    return dict(status="voorlopig", handelsresultaat=None, bevestigd=round(first["van"] - inleg(adm, cut), 2),
                bevestigd_t=first["van_t"], onverklaard_bedrag=round(sum(x["verschil"] for x in open_jumps), 2),
                handelsresultaat_incl_onverklaard=p,
                equity_zonder_geldstromen=[x for x in curve if _t(x[0]) <= cut],
                equity_voorlopig=[x for x in curve if _t(x[0]) > cut])
