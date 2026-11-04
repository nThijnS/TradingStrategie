#!/usr/bin/env python3
"""Vooraf vastgelegd tijdframeonderzoek. Plaatst nooit orders en verandert niets aan de actieve handelsconfiguratie.

    python -W ignore -m research.tijdframes nulmeting    # huidige 1h-aanpak op de 15 markten (Yahoo) -> rapport/nulmeting.json
    python -W ignore -m research.tijdframes varianten    # de vier varianten op 6 markten (HistData)  -> rapport/tijdframes.json

Het protocol staat in research/tijdframes_protocol.json en lag vast voordat er resultaten waren. De hash ervan komt in
het rapport, zodat later te zien is of het protocol achteraf is aangepast.

Bewaking tegen vooruitkijken:
- Context van een hogere tijdframe telt pas vanaf het slot van die candle (closed_state).
- Een signaal gebruikt alleen gesloten candles en de instap is de open van de eerstvolgende 5m-candle.
- Parameters en de strategie per markt worden alleen op de ontwikkelperiode gekozen.

Elke trade heeft een sleutel (markt|familie|parameters|setuptijd|kant). Per markt loopt één strategie tegelijk en een
setup kan maar één keer een trade worden; zie tests/test_tijdframes.py.
"""
import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from backtesting import engine
from backtesting.metrics import block_bootstrap
from core import market_hours
from core.data import clean, fetch_all, load_histdata, resample, to5
from core.markets import LAB_MARKETS, fin_rate
from learning import selector
from research import registry
from risk import rules
from storage import paths
from strategies import lab as strat

PROTOCOL = Path(__file__).with_name("tijdframes_protocol.json")
BARS = {"1min": pd.Timedelta(minutes=1), "5min": pd.Timedelta(minutes=5), "15min": pd.Timedelta(minutes=15),
        "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4)}
MARKET = {m["naam"]: m for m in LAB_MARKETS}
EVAL_DAYS = selector.VAL_DAYS
FAMILIES = [k for k in strat.STRATS if k != "ict"]


def load_protocol(path=PROTOCOL):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def spread_frac(name, report):
    """Gemeten spread als deel van de prijs (momentopname uit rapport/instrumenten.json). None = onbekend."""
    x = ((report or {}).get("huidig") or {}).get(name) or {}
    return x["spread_pct"] / 100 if x.get("spread_pct") is not None else None


def cost_frac(name, report):
    """Kosten per rondgang als deel van de prijs: max(model, gemeten spread) plus de helft daarvan aan slippage."""
    return 1.5 * max(MARKET[name]["kosten"], spread_frac(name, report) or 0.0)


# ------------- Tijdframes zonder vooruitkijken -------------
def frames(m1):
    return {"1min": m1, "5min": to5(m1), "15min": resample(m1, "15min"), "1h": resample(m1, "1h"), "4h": resample(m1, "4h")}


def closed_state(X_ctx, index, bar, ctx_bar):
    """+1/-1/0 per candle van `index`: e20 tegenover e50 op de laatste contextcandle die bij het slot van die candle
    gesloten is. De contextcandle wordt dus pas bekend op start + lengte."""
    state = pd.Series(np.sign((X_ctx["e20"] - X_ctx["e50"]).to_numpy()), index=X_ctx.index + ctx_bar)
    state = state[~state.index.duplicated(keep="last")]
    out = state.reindex(index + bar, method="ffill")
    return pd.Series(out.to_numpy(), index=index).fillna(0.0)


def find_setups(spec, fam, params, X):
    """Setups van één strategie: dicts met t (slot signaalcandle), side, stopd, target, mid."""
    tf = spec["signaal"]
    x = X[tf]
    up, dn, stopd, target = strat.signals(fam, x, params)
    up, dn = up.fillna(False).astype(bool), dn.fillna(False).astype(bool)
    for c in spec["context"]:
        st = closed_state(X[c], x.index, BARS[tf], BARS[c])
        up, dn = up & (st > 0), dn & (st < 0)
    sd, mid, close = stopd.to_numpy(), x["mid"].to_numpy(), x.index + BARS[tf]
    upa, dna = up.to_numpy(), dn.to_numpy()
    return [dict(t=close[i], setup=close[i], side=1 if upa[i] else -1, stopd=float(sd[i]), target=target, mid=float(mid[i]))
            for i in np.flatnonzero(upa | dna) if np.isfinite(sd[i]) and sd[i] > 0]


def apply_trigger(setups, B5, window):
    """5m-instaptrigger. Het signaalmoment wordt het slot van de triggercandle; setups zonder trigger vervallen."""
    out = []
    for s in setups:
        j0 = int(B5.t.searchsorted(s["t"], side="left"))
        for j in range(max(j0, 1), min(j0 + window, B5.n)):
            if B5.t[j] >= s["t"] + window * BARS["5min"]:
                break
            hit = B5.c[j] > B5.h[j - 1] if s["side"] > 0 else B5.c[j] < B5.l[j - 1]
            if hit:
                out.append(dict(s, t=B5.t[j] + BARS["5min"]))
                break
    return out


# ------------- Uitvoerbaarheid en simulatie -------------
def reject_reason(name, soort, t, entry, risk, spread, proto):
    """Waarom de orderlogica dit signaal zou weigeren (None = uitvoerbaar). Dezelfde grenzen als risk/rules.py."""
    u = proto["uitvoerbaarheid"]
    t = t.to_pydatetime()
    if not market_hours.is_open(soort, name, t):
        return "markt dicht"
    end = market_hours.session_end(soort, name, t)
    if end is not None and (end - t).total_seconds() <= proto["instap_en_uitstap"]["sluitbuffer_min"] * 60:
        return "vlak voor het slot"
    if spread is not None and spread > u["max_spread_r"] * risk:
        return "spread groter dan 0,25R"
    if risk / entry * 100 < u["min_stop_pct"]:
        return "stop kleiner dan brokerminimum"
    if u["risico_pct"] / (risk / entry * 100) > u["hefboom"]:
        return "hefboom boven 1:30"
    return None


def execute(name, soort, setups, B, cost, fin, spread_f, proto, max_delay, key=""):
    """Setups door de uitvoerbaarheidscontrole en de engine. Eén trade tegelijk per strategie op deze markt.
    Geeft (trades, tellers per reden)."""
    ex = proto["instap_en_uitstap"]
    exits = engine.Exits(max_hours=ex["max_uren"], gap_hours=ex["gap_uren"])
    costs = engine.Costs(frac=cost, financing=fin)
    counts, trades, busy, used = Counter(ruw=len(setups)), [], None, set()
    delay = pd.Timedelta(minutes=max_delay)
    for s in setups:
        k = int(B.t.searchsorted(s["t"], side="left"))
        if k >= B.n:
            counts["data op"] += 1
            continue
        t_in = B.t[k]
        if t_in - s["t"] > delay:
            counts["markt dicht"] += 1
            continue
        if busy is not None and t_in <= busy:
            counts["strategie heeft al een positie"] += 1
            continue
        id_ = f"{name}|{key}|{s['setup'].isoformat()}|{s['side']}"
        if id_ in used:                # één setup is nooit twee trades
            counts["dubbel"] += 1
            continue
        side, e, risk = s["side"], float(B.o[k]), s["stopd"]
        target = s["target"]
        tp = None if target is None else (e + side * target[1] * risk if target[0] == "R" else s["mid"])
        if tp is None or (tp - e) * side <= ex["min_ruimte_r"] * risk:
            counts["te weinig ruimte tot doel"] += 1
            continue
        why = reject_reason(name, soort, t_in, e, risk, None if spread_f is None else spread_f * e, proto)
        if why:
            counts[why] += 1
            continue
        tr = engine.simulate(B, side, e, e - side * risk, tp, k, "MARKET", exits, costs)
        if tr is None:
            continue
        if tr.reason == "open":
            counts["loopt nog"] += 1
            continue
        used.add(id_)
        busy = tr.exit_time
        counts["uitgevoerd"] += 1
        trades.append(dict(id=id_, markt=name, key=key, t=tr.entry_time.tz_convert("UTC"), t_uit=(tr.exit_time + B.bar).tz_convert("UTC"),
                           kant=side, entry=e, risk=risk, rr=abs(tp - e) / risk, stop_pct=risk / e * 100,
                           stop_x_spread=risk / (spread_f * e) if spread_f else None, reden=tr.reason, bruto=tr.gross_r, R=tr.net_r,
                           R15=tr.net_r - (selector.COST_X - 1) * cost * e / risk))
    return trades, counts


# ------------- Portefeuille met de echte risicoregels -------------
def portfolio(trades, lim=None, start=10000.0, risk_pct=0.5):
    """Trades één voor één langs risk.rules.check_portfolio (ongewijzigde limieten). Risico per trade: risk_pct van de
    accountwaarde; winst en verlies tellen bij het sluiten. Geeft de geaccepteerde trades en de afwijzingen."""
    lim = lim or rules.Limits()
    # Bij gelijke tijd eerst sluiten (dat maakt ruimte); de eigen uitstap komt altijd na de eigen instap.
    tick = pd.Timedelta(1, "ns")
    events = sorted([(x["t"], 1, i) for i, x in enumerate(trades)] + [(max(x["t_uit"], x["t"] + tick), 0, i) for i, x in enumerate(trades)],
                    key=lambda e: (e[0], e[1]))
    eq, peak, day_start, day = start, start, start, None
    book, accepted, rejected, seen = {}, [], Counter(), set()
    breach = Counter()
    max_open, max_group, min_dd, worst_day = 0, 0, 0.0, 0.0
    for t, is_entry, i in events:
        if t.date() != day:
            day, day_start = t.date(), eq
        x = trades[i]
        if not is_entry:
            if i in book:
                eq += x["R"] * book.pop(i)["risico"]
                peak = max(peak, eq)
                min_dd = min(min_dd, eq / peak - 1)
                worst_day = min(worst_day, eq / day_start - 1)
                if eq <= day_start * (1 - lim.dagverlies_pct / 100):
                    breach["dag"] += 1
                if eq <= peak * (1 - lim.totaalverlies_pct / 100):
                    breach["trailing"] += 1
            continue
        if x["id"] in seen:
            rejected["dubbel signaal"] += 1
            continue
        seen.add(x["id"])
        risico = eq * risk_pct / 100
        p = rules.Plan(side=x["kant"], soort="MARKET", entry=x["entry"], stop=x["entry"] - x["kant"] * x["risk"],
                       tp=x["entry"] + x["kant"] * x["risk"])
        p.risico_acc, p.notional_acc = risico, risico / (x["risk"] / x["entry"])
        b = rules.Book(equity=eq, day_start=day_start, peak=peak, start=start, open_risks=[o["risico"] for o in book.values()],
                       exposures=[(o["markt"], o["kant"]) for o in book.values()], used_notional=sum(o["notional"] for o in book.values()))
        why = rules.check_portfolio(b, lim, p, x["markt"])
        if why:
            rejected[why.split(" (")[0].split(":")[0][:44]] += 1
            continue
        book[i] = dict(markt=x["markt"], kant=x["kant"], risico=risico, notional=p.notional_acc)
        accepted.append(x)
        max_open = max(max_open, len(book))
        groups = Counter(rules.group_of(o["markt"]) for o in book.values())
        max_group = max(max_group, max(groups.values()))
    return dict(trades=accepted, afgewezen=dict(rejected), eind=round(eq, 2), rendement_pct=round((eq / start - 1) * 100, 2),
                max_dd_pct=round(-min_dd * 100, 2), slechtste_dag_pct=round(-worst_day * 100, 2), grensbreuken=dict(breach),
                max_open=max_open, max_in_groep=max_group)


def effective_bets(trades):
    """Onafhankelijke weddenschappen: trades op dezelfde dag, in dezelfde gecorreleerde groep en dezelfde richting
    tellen als één."""
    return len({(rules.group_of(x["markt"]), x["t"].date(), rules.direction_in_group(x["markt"], x["kant"])) for x in trades})


def loss_streak(R):
    best = cur = 0
    for r in R:
        cur = cur + 1 if r <= 0 else 0
        best = max(best, cur)
    return best


def stats(trades, days, label=""):
    """Samenvatting van een trade-lijst over een periode van `days` dagen. Gemiddelden per trade; lb = eenzijdige
    95%-ondergrens van de gemiddelde R bij 1,5x kosten (block bootstrap met weekblokken)."""
    trades = sorted(trades, key=lambda x: x["t"])
    n = len(trades)
    if not n:
        return dict(n=0, per_week=0.0)
    R = np.array([x["R"] for x in trades], float)
    eq = np.cumsum(R)
    dd = float((np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq).max())
    wins, losses = R[R > 0], R[R <= 0]
    ci = block_bootstrap(trades, key="R15", rng=selector._rng("tijdframes", label)) if n >= 5 else None
    gross = [x["bruto"] for x in trades if x.get("bruto") is not None]
    return dict(n=n, per_week=round(n / days * 7, 2), gem=round(float(R.mean()), 3), bruto=round(float(np.mean(gross)), 3) if gross else None, gem15=round(float(np.mean([x["R15"] for x in trades])), 3),
                totaal=round(float(R.sum()), 1), win=round(float((R > 0).mean()), 3), gem_winst=round(float(wins.mean()), 2) if len(wins) else 0.0,
                gem_verlies=round(float(losses.mean()), 2) if len(losses) else 0.0, max_dd_r=round(dd, 1), verliesreeks=loss_streak(R),
                onder=round(ci[1], 3) if ci else None, ci95=[round(ci[0], 3), round(ci[2], 3)] if ci else None,
                weddenschappen=effective_bets(trades), gem_rr=round(float(np.mean([x["rr"] for x in trades])), 2))


def mean_pair_corr(trades):
    """Gemiddelde correlatie van dag-R tussen markten: hoe sterk bewegen de uitkomsten samen?"""
    if not trades:
        return None
    d = pd.DataFrame([dict(m=x["markt"], d=x["t"].date(), R=x["R"]) for x in trades]).pivot_table(index="d", columns="m", values="R", aggfunc="sum").fillna(0.0)
    if d.shape[1] < 2 or len(d) < 20:
        return None
    c = d.corr().to_numpy()
    return round(float(np.nanmean(c[np.triu_indices_from(c, 1)])), 3)


# ------------- Datakwaliteit 1m -------------
def quality_1m(name, m1):
    """Datakwaliteit: alleen om te beoordelen of 1m bruikbaar is. Forex, futures en grondstoffen volgen dezelfde handelsuren."""
    a, b = m1.index[0], m1.index[-1]
    want = pd.date_range(a, b, freq="1min")
    ny = want.tz_convert(market_hours.NY)
    wd, hm = ny.weekday, ny.hour * 100 + ny.minute
    open_ = ~((wd == 5) | ((wd == 6) & (hm < 1800)) | ((wd == 4) & (hm >= 1700)) | ((hm >= 1700) & (hm < 1800)))
    expected = want[open_]
    have = expected.isin(m1.index)
    missing = expected[~have]
    runs = pd.Series(missing).diff().ne(pd.Timedelta(minutes=1)).cumsum().value_counts() if len(missing) else pd.Series(dtype=int)
    flat = (m1["High"] == m1["Low"]).mean()
    return dict(markt=name, candles=len(m1), verwacht=len(expected), ontbreekt_pct=round(float((~have).mean() * 100), 2),
                gaten_boven_30min=int((runs > 30).sum()), langste_gat_min=int(runs.max()) if len(runs) else 0,
                platte_candles_pct=round(float(flat * 100), 2), dubbel=int(m1.index.duplicated().sum()))


# ------------- De vier varianten -------------
def base_params():
    return [(fam, json.dumps(v)) for fam in FAMILIES for v in strat.STRATS[fam]["varianten"]]


def run_variant(name, soort, vspec, fr, X, B5, cost, fin, spread_f, proto, exec_bars=None, only=None):
    """Alle tien de strategieën van één variant op één markt. Geeft {familie: {params: trades}} en de tellers."""
    B = exec_bars or B5
    by, counts = {}, Counter()
    ex = proto["instap_en_uitstap"]["max_instapvertraging_min"]
    for fam, key in base_params():
        if only and (fam, key) not in only:
            continue
        s = find_setups(vspec, fam, json.loads(key), X)
        if vspec["trigger"]:
            s = apply_trigger(s, B5, proto["trigger_regel"]["venster_5m_candles"])
        tr, c = execute(name, soort, s, B, cost, fin, spread_f, proto, ex[vspec["signaal"]], f"{fam}|{key}")
        for x in tr:
            x["familie"] = fam
        by.setdefault(fam, {})[key] = tr
        counts.update(c)
    return by, counts


def verdict(rule, b, base, e1, e2, pf):
    """De vooraf vastgelegde besluitregel op portefeuille B in de evaluatie."""
    out = dict(meer_kansen=bool(base.get("per_week")) and b.get("per_week", 0) >= 1.5 * base["per_week"],
               na_kosten=b.get("n", 0) > 0 and b.get("gem15", -1) > 0 and (b.get("onder") or -1) > 0,
               meerdere_perioden=e1.get("gem", -1) > 0 and e2.get("gem", -1) > 0,
               risico=not pf["grensbreuken"])
    out["interessant"] = all(out.values())
    return out


def varianten():
    proto, sha = load_protocol()
    report = json.loads(paths.INSTRUMENTS.read_text())
    data, q, fingerprints = {}, {}, {}
    for name, spec in proto["markten"].items():
        m1, _ = clean(load_histdata(spec["histdata"]))
        print(f"{name}: {len(m1)} 1m-candles", flush=True)
        fr = frames(m1)
        data[name] = fr
        q[name] = quality_1m(name, m1)
        fingerprints[name] = registry.fingerprint(m1)
    end = min(fr["5min"].index[-1] for fr in data.values()).tz_convert("UTC")
    start = max(fr["5min"].index[0] for fr in data.values()).tz_convert("UTC") + pd.Timedelta(days=60)      # opwarmen indicatoren
    cut = end - pd.Timedelta(days=EVAL_DAYS)
    mid = cut + pd.Timedelta(days=90)
    dev_days, eval_days = (cut - start).days, EVAL_DAYS
    n_trials = proto["poort"]["proeven_per_markt"]
    out = dict(protocol=proto["naam"], protocol_sha256=sha, periode=dict(ontwikkeling=[start.date().isoformat(), cut.date().isoformat()],
               evaluatie=[cut.date().isoformat(), end.date().isoformat()], splitsing_e1_e2=mid.date().isoformat()),
               kosten_frac={m: round(cost_frac(m, report), 6) for m in proto["markten"]}, kwaliteit_1m=q, varianten={})
    picks = {}
    for vid, vspec in proto["varianten"].items():
        print(f"== {vid}", flush=True)
        allt, counts, gate_rows, B_trades, A_trades, per_market = [], Counter(), [], [], [], {}
        picks[vid] = {}
        for name, spec in proto["markten"].items():
            fr = data[name]
            X = {tf: strat.indicators(fr[tf]) for tf in ("15min", "1h", "4h") if tf == vspec["signaal"] or tf in vspec["context"]}
            B5 = engine.Bars(fr["5min"])
            by, c = run_variant(name, spec["soort"], vspec, fr, X, B5, cost_frac(name, report), fin_rate(MARKET[name]),
                                spread_frac(name, report), proto)
            counts.update(c)
            for fam in by:
                for key in by[fam]:
                    by[fam][key] = [x for x in by[fam][key] if x["t"] >= start]
                    allt += by[fam][key]
            fams = [selector.evaluate_family(name, fam, by[fam], cut, n_trials) for fam in by]
            d = selector.decide(name, fams, None, end, lambda s, k: by.get(s, {}).get(k, []))
            for f in fams:
                g = f["poort"]
                gate_rows.append(dict(markt=name, familie=f["id"], variant=f["variant"], geslaagd=g["geslaagd"], train=g["train"], validatie=g["validatie"],
                                      ondergrens=g["ondergrens"], dsr=g["dsr"], redenen=[r[:2] for r in g["redenen"]]))
            if d["status"] == "actief":
                A_trades += [x for x in by[d["strategie"]][d["variant_key"]] if x["t"] >= cut]
            flat = {f"{fam}|{k}": v for fam in by for k, v in by[fam].items()}
            best = selector.pick_variant(flat, cut)
            dev = [x for x in flat[best] if x["t"] < cut] if best else []
            use = best is not None and np.mean([x["R"] for x in dev]) > 0
            ev = [x for x in flat[best] if x["t"] >= cut] if use else []
            B_trades += ev
            picks[vid][name] = best if use else None
            per_market[name] = dict(status=d["status"], keuze=best if use else None, ontwikkeling=stats(dev, dev_days, f"{vid}{name}d"),
                                    evaluatie=stats(ev, eval_days, f"{vid}{name}e"),
                                    uitgevoerd_per_week=round(sum(len(v) for v in flat.values()) / 10 / ((end - start).days / 7), 2))
        pool_e = [x for x in allt if x["t"] >= cut]
        pf_b, pf_a = portfolio(B_trades), portfolio(A_trades)
        b = pf_b.pop("trades")
        a = pf_a.pop("trades")
        fam_tab = {fam: stats([x for x in pool_e if x["familie"] == fam], eval_days, f"{vid}{fam}") for fam in FAMILIES}
        e1 = stats([x for x in b if x["t"] < mid], 90, f"{vid}e1")
        e2 = stats([x for x in b if x["t"] >= mid], eval_days - 90, f"{vid}e2")
        out["varianten"][vid] = dict(
            titel=vspec["titel"], tellers=dict(counts), per_markt=per_market, poort=gate_rows,
            poort_geslaagd=sum(r["geslaagd"] for r in gate_rows), poort_afwijzingen=dict(Counter(t for r in gate_rows for t in r["redenen"])),
            aanbod_evaluatie=stats(pool_e, eval_days, f"{vid}pool"), per_familie=fam_tab,
            portefeuille_A=dict(pf_a, stats=stats(a, eval_days, f"{vid}A")), portefeuille_B=dict(pf_b, stats=stats(b, eval_days, f"{vid}B"), e1=e1, e2=e2,
                                                                                               correlatie=mean_pair_corr(b)),
            # Na afloop toegevoegd, telt niet mee in het oordeel: de grenzen blokkeren de portefeuilles al in E1, dus zonder
            # deze regel is E2 leeg. Dit is een meting van de gekozen strategieën, geen voorstel om limieten te verruimen.
            B_zonder_limieten=dict(na_afloop=True, stats=stats(B_trades, eval_days, f"{vid}Bvrij"), e1=stats([x for x in B_trades if x["t"] < mid], 90, f"{vid}Bvrij1"),
                                   e2=stats([x for x in B_trades if x["t"] >= mid], eval_days - 90, f"{vid}Bvrij2")),
            stopafstand=dict(mediaan_pct=round(float(np.median([x["stop_pct"] for x in allt])), 3) if allt else None,
                             mediaan_x_spread=round(float(np.median([x["stop_x_spread"] for x in allt if x["stop_x_spread"]])), 1) if allt else None))
    base = out["varianten"]["V1_1h"]["portefeuille_B"]["stats"]
    for vid, v in out["varianten"].items():
        p = v["portefeuille_B"]
        v["oordeel"] = dict(verdict(proto["besluitregel"], p["stats"], base, p["e1"], p["e2"], p), is_baseline=vid == "V1_1h")
    out["gevoeligheid_1m"] = sensitivity(proto, report, data, picks, start)
    target = paths.REPORTS / "tijdframes.json"
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    registry.record("tijdframes", dict(protocol_sha256=sha), {k: v["oordeel"] for k, v in out["varianten"].items()}, fingerprints)
    print("geschreven:", target, flush=True)


def sensitivity(proto, report, data, picks, start):
    """Zelfde strategieën, uitstap op 1m in plaats van 5m: hoeveel hangt af van wat er binnen een 5m-candle gebeurt?"""
    res = {}
    for vid in ("V1_1h", "V3_15m"):
        vspec = proto["varianten"][vid]
        rows = []
        for name, best in picks[vid].items():
            if not best:
                continue
            fam, key = best.split("|", 1)
            fr = data[name]
            X = {tf: strat.indicators(fr[tf]) for tf in ("15min", "1h", "4h") if tf == vspec["signaal"] or tf in vspec["context"]}
            B5 = engine.Bars(fr["5min"])
            args = (name, proto["markten"][name]["soort"], vspec, fr, X, B5, cost_frac(name, report), fin_rate(MARKET[name]), spread_frac(name, report), proto)
            a, _ = run_variant(*args, only={(fam, key)})
            b, _ = run_variant(*args, exec_bars=engine.Bars(fr["1min"]), only={(fam, key)})
            aa = {x["id"]: x for x in a[fam][key] if x["t"] >= start}
            bb = {x["id"]: x for x in b[fam][key] if x["t"] >= start}
            both = aa.keys() & bb.keys()
            if both:
                rows.append(dict(markt=name, n=len(both), gem_5m=round(float(np.mean([aa[k]["R"] for k in both])), 3),
                                 gem_1m=round(float(np.mean([bb[k]["R"] for k in both])), 3),
                                 uitkomst_anders_pct=round(float(np.mean([aa[k]["reden"] != bb[k]["reden"] for k in both]) * 100), 1)))
        res[vid] = rows
    return res


# ------------- Nulmeting -------------
def nulmeting():
    """De huidige 1h-aanpak op alle 15 markten met de strategieën uit lab.json. Alleen 1h, dus los van de varianten."""
    import re
    proto, sha = load_protocol()
    report = json.loads(paths.INSTRUMENTS.read_text())
    lab = json.loads(paths.LAB.read_text())
    data = fetch_all(LAB_MARKETS)
    rows, picked, tagged = [], [], Counter()
    for res in lab["markten"]:
        name = res["naam"]
        m = MARKET[name]
        df, q = clean(data.get(name, pd.DataFrame()))
        X = strat.indicators(df)
        end = X.index[-1]
        cut = end - pd.Timedelta(days=EVAL_DAYS)
        cost, sp = cost_frac(name, report), spread_frac(name, report)
        k = res.get("keuze") or {}
        follow = (k.get("onderzoek") or {}).get("strategie")
        row = dict(markt=name, status=k.get("status"), gevolgd=follow, spread_pct=None if sp is None else round(sp * 100, 4),
                   model_pct=round(m["kosten"] * 100, 4), families={})
        for s in res.get("strategieen", []):
            p = s.get("poort") or {}
            tags = sorted(set(re.findall(r"P\d", " ".join(p.get("redenen", [])))))
            tagged.update(tags)
            info = dict(poort_redenen=tags, variant=s.get("variant_txt"))
            if s["id"] != "ict":
                up, dn, stopd, target = strat.signals(s["id"], X, s["variant"])
                exits = engine.Exits(max_bars=strat.MAX_BARS, gap_hours=strat.GAP_HOURS)
                trades, rejected = [], Counter()
                for i, tr in strat.run_signals(X, up, dn, stopd, target, engine.Costs(frac=cost, financing=fin_rate(m)), exits):
                    if tr.reason == "open":
                        continue
                    why = reject_reason(name, m["soort"], tr.entry_time, tr.entry, tr.risk, None if sp is None else sp * tr.entry, proto)
                    if why:
                        rejected[why] += 1
                        continue
                    trades.append(dict(id=f"{name}|{s['id']}|{tr.entry_time.isoformat()}", markt=name, kant=tr.side, entry=tr.entry, risk=tr.risk,
                                       t=tr.entry_time.tz_convert("UTC"), t_uit=(tr.exit_time + BARS["1h"]).tz_convert("UTC"), rr=abs(tr.tp - tr.entry) / tr.risk,
                                       bruto=tr.gross_r, R=tr.net_r, R15=tr.net_r - (selector.COST_X - 1) * cost * tr.entry / tr.risk))
                va = [x for x in trades if x["t"] >= cut.tz_convert("UTC")]
                info.update(evaluatie=stats(va, EVAL_DAYS, f"nul{name}{s['id']}"), afgewezen=dict(rejected))
                if s["id"] == follow:
                    picked += va
            row["families"][s["id"]] = info
        rows.append(row)
    pf = portfolio(picked)
    acc = pf.pop("trades")
    out = dict(protocol_sha256=sha, gemaakt=pd.Timestamp.now("UTC").isoformat(timespec="minutes"), lab_van=lab["gemaakt"], markten=rows,
               poort_afwijzingen_per_familie=dict(tagged), gevolgd_ongefilterd=stats(picked, EVAL_DAYS, "nulgevolgd"), gevolgd_portefeuille=dict(pf, stats=stats(acc, EVAL_DAYS, "nulpf")),
               correlatie=mean_pair_corr(picked),
               echte_demo="Eén demo-order: GOUD long op 2026-11-02 (accountresultaat -4,95 euro); op 2026-11-03 0 open trades. Te weinig om iets uit af te leiden.")
    target = paths.REPORTS / "nulmeting.json"
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print("geschreven:", target, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stap", choices=("nulmeting", "varianten"))
    a = ap.parse_args()
    {"nulmeting": nulmeting, "varianten": varianten}[a.stap]()


if __name__ == "__main__":
    main()
