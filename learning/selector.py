"""Strategie-selectie per markt: welke strategie gebruikt de bot, welke onderzoekt hij verder, of pauze.

ICT is hier één strategiefamilie naast trend, momentum, mean reversion, breakout en volatiliteit. Elke familie
gaat door dezelfde, vooraf vastgelegde stappen (dezelfde poort als research/protocol.py):

  1. Splitsen in de tijd: alles vóór `cut` (= laatste VAL_DAYS dagen) is train, daarna validatie.
  2. Variant per familie kiezen op ALLEEN train (beste gemiddelde R, minstens MIN_TRAIN trades).
     Validatie wordt dus niet gebruikt om varianten te kiezen.
  3. Poort op de validatie van die ene variant (alle vijf nodig):
       P1  genoeg data: >= MIN_VAL trades in de validatie en >= MIN_TRAIN in train
       P2  validatie: gemiddelde R > 0 bij 1,5x kosten EN block-bootstrap 95%-ondergrens (eenzijdig) > 0
       P3  train: gemiddelde R > 0 (zelfde richting in beide perioden)
       P4  Deflated Sharpe (train+validatie) >= 0,95, gecorrigeerd voor ALLE varianten die op deze markt
           geprobeerd zijn (ook die van andere families): hoe meer je probeert, hoe strenger
       P5  validatie zonder de 5 beste trades nog > 0
  4. Status per markt:
       actief     een familie haalt de poort -> die strategie wordt gebruikt (bij meerdere: hoogste ondergrens)
       onderzoek  niets haalt de poort, maar een familie is in train én validatie positief: de bot volgt hem
                  (papertrades, geen orders) tot er genoeg data is
       pauze      geen van beide
  5. Nieuwe uitkomsten: een actieve strategie wordt gevolgd vanaf de inschakeldatum. Na FWD_MIN nieuwe trades
     met een negatief gemiddelde gaat hij uit en mag die familie COOLDOWN_DAYS dagen niet terugkomen op die markt.
  6. Rem op wisselen: een actieve strategie die de poort nog haalt, blijft staan tenzij een andere minstens
     MARGIN R per trade (ondergrens) beter is. Haalt de huidige variant de poort nog, dan blijft die variant
     (geen dagelijks wisselen door een verschuivend trainvenster).

Er wordt nooit een strategie ingeschakeld zonder dat hij de poort haalt. Of een strategie ook LIVE mag (echt geld)
blijft een handmatige vrijgave (config.json live.strategieen, zie execution/runner.py).
"""
import hashlib
import math
from datetime import datetime

import numpy as np
import pandas as pd

from backtesting.metrics import block_bootstrap, deflated_sharpe

VAL_DAYS = 180          # validatie = laatste 180 dagen
MIN_TRAIN = 30
MIN_VAL = 30
COST_X = 1.5
DSR_MIN = 0.95
FWD_MIN = 20            # zoveel nieuwe trades voordat de uitkomsten na inschakelen een actieve strategie kunnen stoppen
COOLDOWN_DAYS = 60
MARGIN = 0.05


def _rng(*parts):
    """Vaste, eigen random-generator per markt/variant: de bootstrap is reproduceerbaar en hangt niet af van de
    volgorde waarin markten worden doorgerekend."""
    seed = int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)
    return np.random.default_rng(seed)


def _mean(trades, key="R"):
    return float(np.mean([x[key] for x in trades])) if trades else float("nan")


def summary(trades):
    if not trades:
        return dict(n=0)
    R = np.array([x["R"] for x in trades], float)
    se = float(R.std(ddof=1) / math.sqrt(len(R))) if len(R) > 1 else float("nan")
    return dict(n=len(R), gem=round(float(R.mean()), 3), totaal=round(float(R.sum()), 2), win=round(float((R > 0).mean()), 3),
                se=round(se, 3) if np.isfinite(se) else None)


def gate(train, val, n_trials, rng=None):
    """De poort (P1-P5). Trades: dicts met t, R en R15 (R bij 1,5x kosten). Geeft dict met geslaagd, redenen en maten."""
    why = []
    if len(val) < MIN_VAL or len(train) < MIN_TRAIN:
        why.append(f"P1: te weinig data ({len(train)} train, {len(val)} validatie; minimaal {MIN_TRAIN}/{MIN_VAL})")
    ci = block_bootstrap(val, key="R15", rng=rng) if len(val) >= 5 else None
    m15 = _mean(val, "R15")
    lb = ci[1] if ci else None
    if not (val and m15 > 0 and lb is not None and lb > 0):
        why.append(f"P2: validatie {m15:+.3f}R bij {COST_X}x kosten, ondergrens "
                   f"{'onbekend' if lb is None else f'{lb:+.3f}R'}")
    mt = _mean(train)
    if not train or not mt > 0:
        why.append(f"P3: train {mt:+.3f}R")
    dsr = deflated_sharpe([x["R"] for x in train + val], n_trials)
    if dsr < DSR_MIN:
        why.append(f"P4: Deflated Sharpe {dsr:.2f} (< {DSR_MIN}, {n_trials} varianten geprobeerd)")
    top = sorted((x["R"] for x in val), reverse=True)
    if len(top) <= 10 or np.mean(top[5:]) <= 0:
        why.append("P5: zonder de 5 beste validatietrades niet positief")
    return dict(geslaagd=not why, redenen=why, train=summary(train), validatie=summary(val),
                validatie_kosten15=round(m15, 3) if val else None, ondergrens=round(lb, 3) if lb is not None else None,
                dsr=round(dsr, 3))


def pick_variant(by_variant, cut):
    """Beste variant op ALLEEN train (voor `cut`), met minstens MIN_TRAIN trades."""
    best, best_m = None, None
    for k, trades in by_variant.items():
        tr = [x for x in trades if x["t"] < cut]
        if len(tr) >= MIN_TRAIN and (best_m is None or _mean(tr) > best_m):
            best, best_m = k, _mean(tr)
    return best


def evaluate_family(market, sid, by_variant, cut, n_trials, keep=None):
    """Variant kiezen op train en door de poort halen. keep: huidige variant, die blijft als hij de poort nog haalt."""
    out = dict(id=sid, varianten=len(by_variant))
    cands = []
    if keep is not None and keep in by_variant:
        cands.append(keep)
    k = pick_variant(by_variant, cut)
    if k is not None and k not in cands:
        cands.append(k)
    if not cands:
        out.update(variant=None, poort=dict(geslaagd=False, redenen=[f"P1: geen variant met {MIN_TRAIN} trades in train"]))
        return out
    for key in cands:
        trades = by_variant[key]
        tr = [x for x in trades if x["t"] < cut]
        va = [x for x in trades if x["t"] >= cut]
        g = gate(tr, va, n_trials, _rng(market, sid, key))
        out.update(variant=key, poort=g)
        if g["geslaagd"]:
            break
    return out


def decide(market, families, prev, now, trades_of):
    """Status voor één markt. families: uitkomsten van evaluate_family. prev: vorige keuze (of None).
    trades_of(sid, key) -> trades van die variant (voor de uitkomsten na inschakelen)."""
    today = now.date().isoformat()
    blocked = dict((prev or {}).get("geblokkeerd", {}))
    blocked = {k: v for k, v in blocked.items() if v > today}
    passing = [f for f in families if f["poort"]["geslaagd"] and f["id"] not in blocked]
    passing.sort(key=lambda f: -(f["poort"]["ondergrens"] or -9))
    why = None
    cur = prev if prev and prev.get("status") == "actief" else None
    # uitkomsten na inschakelen (echt nieuwe data)
    if cur:
        fwd = [x for x in trades_of(cur["strategie"], cur["variant_key"]) if x["t"].date().isoformat() >= cur["sinds"]]
        if len(fwd) >= FWD_MIN and _mean(fwd) < 0:
            until = (now + pd.Timedelta(days=COOLDOWN_DAYS)).date().isoformat()
            blocked[cur["strategie"]] = until
            passing = [f for f in passing if f["id"] != cur["strategie"]]
            why = (f"{cur['titel']} uitgeschakeld: {len(fwd)} nieuwe trades sinds {cur['sinds']} gemiddeld "
                   f"{_mean(fwd):+.3f}R; {COOLDOWN_DAYS} dagen geblokkeerd")
            cur = None
    pick = None
    if cur:
        same = next((f for f in passing if f["id"] == cur["strategie"]), None)
        if same is not None:
            best = passing[0]
            if best["id"] != same["id"] and (best["poort"]["ondergrens"] or 0) >= (same["poort"]["ondergrens"] or 0) + MARGIN:
                pick, why = best, f"gewisseld: {best['id']} haalt de poort met een duidelijk hogere ondergrens"
            else:
                pick, why = same, "huidige strategie haalt de poort nog"
        else:
            why = why or "huidige strategie haalt de poort niet meer"
    if pick is None and passing:
        pick = passing[0]
        why = (why + "; " if why else "") + f"{pick['id']} haalt de poort (ondergrens {pick['poort']['ondergrens']:+.3f}R)"
    if pick is not None:
        status = "actief"
        sinds = cur["sinds"] if cur and cur["strategie"] == pick["id"] and cur["variant_key"] == pick["variant"] else today
        research = None
    else:
        promising = [f for f in families if f["variant"] is not None and f["id"] not in blocked
                     and f["poort"]["train"].get("n", 0) and (f["poort"]["train"].get("gem") or 0) > 0
                     and (f["poort"]["validatie"].get("gem") or 0) > 0]
        promising.sort(key=lambda f: -(f["poort"]["validatie"].get("gem") or 0))
        research = promising[0] if promising else None
        status = "onderzoek" if research else "pauze"
        why = (why + "; " if why else "") + (
            f"geen strategie haalt de poort; {research['id']} is in train en validatie positief en wordt gevolgd "
            f"zonder orders" if research else "geen strategie haalt de poort en geen is in beide perioden positief: pauze")
        sinds = prev["sinds"] if prev and prev.get("status") == status and (
            (prev.get("onderzoek") or {}).get("strategie") == (research or {}).get("id")) else today
    return dict(status=status, strategie=pick["id"] if pick else None, variant_key=pick["variant"] if pick else None,
                poort=pick["poort"] if pick else None, sinds=sinds, reden=why, geblokkeerd=blocked,
                onderzoek=dict(strategie=research["id"], variant_key=research["variant"], poort=research["poort"]) if research else None)


def n_trials(families):
    return max(2, sum(f.get("varianten", 1) for f in families))


def now_ny():
    from core.sessions import NY
    return datetime.now(NY)
