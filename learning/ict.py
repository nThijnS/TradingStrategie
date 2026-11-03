"""
Zelflerende laag van TradingStrategie. Draait elke werkdag na de beurs (GitHub Actions, workflow leren.yml).

1. Haalt per markt de laatste 60 dagen 5m-data op en zoekt alle setups met elke combinatie van instellingen:
   displacement (basis/strenger) x doel (1R, 1,5R, 2R, DOL) x sessies (NY AM / + London / alle) x biasfilter (geen / 1H mee).
2. Bewaart de uitkomst van elke setup in het geheugen (leren_geheugen.json). Dat groeit elke dag, ook voorbij 60 dagen.
3. Kiest per markt de variant met de beste voorzichtige score: gemiddelde R min een onzekerheidsmarge,
   recente trades tellen zwaarder (halfwaardetijd 60 dagen). Remmen tegen toeval:
     - minstens MIN_TRADES trades, anders blijft de huidige instelling staan;
     - alleen wisselen als de nieuwe variant minstens SWITCH_MARGIN R per trade beter scoort;
     - een markt waarvan zelfs de beste variant onder 0 scoort, gaat op pauze (geen meldingen, wel loggen en leren).
4. Schrijft de keuze naar learned.json (de app leest dat elke minuut) en het Obsidian-journaal (journaal/).

Gebruik:
  python leren.py              # leren + journaal bijwerken
  python leren.py --geen-data  # alleen opnieuw kiezen en journaal schrijven uit het bestaande geheugen
  python leren.py --histdata   # eenmalig: geheugen ook vullen met de lokale HistData (jan 2025 - okt 2026)
"""
import math
import sys
from datetime import datetime, timedelta


from backtesting import engine
from backtesting.ict import LEARN_EXITS, trade
from core import config, data
from core.markets import ICT_MARKETS
from core.sessions import NY, sess_name
from learning.journal import days_from_logbook, journal_day, svg_chart, write_journal  # noqa: F401
from storage import jsonstore, paths
from strategies.ict_tjr import analyse

MEMORY = paths.LEREN_MEMORY
LEARNED = paths.LEARNED
HISTORY = paths.LEREN_HISTORY
JOURNAL = paths.JOURNAL

COST = {m["name"]: m["cost"] for m in ICT_MARKETS}       # kosten per trade in prijspunten (core/markets.py)
DISP = {"basis": dict(disp_pct=0.6, disp_atr=1.2), "strenger": dict(disp_pct=0.7, disp_atr=1.5)}
TARGETS = ["1.0", "1.5", "2.0", "DOL"]
SESSIONS = {"NY AM": ["NY AM"], "NY AM + London": ["NY AM", "London"], "alle sessies": ["London", "NY AM", "NY PM"]}
BIAS = {"geen": False, "1H mee": True}
MIN_TRADES = 20
SWITCH_MARGIN = 0.05
HALF_LIFE_DAYS = 60
Z = 1.0                 # onzekerheidsmarge: gemiddelde - 1 standaardfout
MAX_HOURS = 5
VALIDATION_DAYS = 60    # controle (rapportage): score op de laatste 60 dagen tegenover de periode ervoor
# Versie van de trade-simulatie waarmee een geheugenrij is berekend. Rijen zonder "sim" zijn met de oude
# leren.simulate5 berekend (DOL-terugval 2R, TP in de vulcandle telde, 5u05m). Zie storage/migrations.py.
SIM_VERSION = 2


# ------------- Uitkomst (backtesting/engine.py) -------------
def outcome_row(df, s, target, cost, fallback_r=None):
    """(netto R, kosten in R) of None; zie simulate5."""
    tr = trade(df, s, target, LEARN_EXITS, engine.Costs(price=cost), fallback_r)
    if tr is None or tr.reason == "open":
        return None
    return tr.net_r, tr.cost_r


def simulate5(df, s, target, cost, fallback_r=None):
    """Netto R van een setup voor een doel (zie backtesting/ict.py), of None als er geen entry was of de trade
    nog loopt (dan morgen opnieuw). fallback_r: TP zonder liquiditeit bij "DOL" (de app gebruikt cfg["tp_r"])."""
    tr = trade(df, s, target, LEARN_EXITS, engine.Costs(price=cost), fallback_r)
    if tr is None or tr.reason == "open":
        return None
    return tr.net_r


# ------------- Geheugen -------------
def load(path, default):
    return jsonstore.load(path, default)


def histdata(m):
    """Eenmalige startvulling: 5m-candles uit de lokale HistData (zomertijd gecorrigeerd)."""
    sym, smt = m["histdata"]
    return data.to5(data.load_histdata(sym)), data.to5(data.load_histdata(smt))


def collect(mem, source="yahoo"):
    """Nieuwe setups in het geheugen zetten (bestaande uitkomsten blijven staan).
    source "yahoo": laatste 60 dagen live data; "histdata": de lokale 1m-data van jan 2025 tot okt 2026."""
    for m in config.CFG["markets"]:
        name = m["name"]
        try:
            df, es = histdata(m) if source == "histdata" else (data.fetch(m["symbol"], "60d"), data.fetch(m["smt"], "60d"))
        except Exception as ex:
            print(f"{name}: geen data ({ex})", flush=True)
            continue
        added = 0
        B = engine.Bars(df)
        for dname, over in DISP.items():
            cfg = {**config.CFG, **m["cfg"], **over, "max_per_day": 6, "need_bias_b": False,
                   "trade_sess": [("02:00", "05:00"), ("09:30", "11:30"), ("13:30", "15:30")]}
            setups, _ = analyse(df, es, cfg)
            for s in setups:
                for target in TARGETS:
                    key = f"{name}|{dname}|{target}|{s['time'].isoformat()}|{s['side']}"
                    if key in mem:
                        continue
                    out = outcome_row(B, s, target, COST.get(name, 0), cfg["tp_r"])
                    if out is None:
                        continue
                    r, cost_r = out
                    mem[key] = dict(markt=name, disp=dname, target=target, t=s["time"].isoformat(),
                                    sess=sess_name(s["time"]), bias_mee=s["bias_b"] == (1 if s["side"] == "LONG" else -1),
                                    R=round(float(r), 3), kosten_r=round(float(cost_r), 4), bron=source, sim=SIM_VERSION)
                    added += 1
        print(f"{name}: {added} nieuwe uitkomsten", flush=True)
    return mem


# ------------- Kiezen -------------
def variants():
    for d in DISP:
        for tg in TARGETS:
            for sn in SESSIONS:
                for b in BIAS:
                    yield dict(disp=d, target=tg, sessies=sn, bias=b)


def vid(v):
    return f"{v['disp']} · TP {v['target']} · {v['sessies']} · bias {v['bias']}"


def score(rows, v, now):
    sel = [r for r in rows if r["disp"] == v["disp"] and r["target"] == v["target"]
           and r["sess"] in SESSIONS[v["sessies"]] and (r["bias_mee"] or not BIAS[v["bias"]])]
    # zoals de app: per dag alleen de eerste trade
    sel.sort(key=lambda r: r["t"])
    seen, trades = set(), []
    for r in sel:
        d = r["t"][:10]
        if d not in seen:
            seen.add(d)
            trades.append(r)
    n = len(trades)
    if n < 2:
        return dict(n=n, gem=0.0, score=-9.0, win=0.0, totaal=0.0)
    w = [0.5 ** ((now - datetime.fromisoformat(r["t"])).days / HALF_LIFE_DAYS) for r in trades]
    R = [r["R"] for r in trades]
    sw = sum(w)
    mean = sum(wi * ri for wi, ri in zip(w, R)) / sw
    var = sum(wi * (ri - mean) ** 2 for wi, ri in zip(w, R)) / sw
    n_eff = sw ** 2 / sum(wi ** 2 for wi in w)
    return dict(n=n, gem=round(mean, 3), score=round(mean - Z * math.sqrt(var / n_eff), 3),
                win=round(sum(r > 0 for r in R) / n, 3), totaal=round(sum(R), 1))


def choose(mem, learned):
    now = datetime.now(NY)
    out, report = {}, {}
    for m in config.CFG["markets"]:
        name = m["name"]
        rows = [r for r in mem.values() if r["markt"] == name]
        ranked = sorted(((score(rows, v, now), v) for v in variants()), key=lambda x: -x[0]["score"])
        ranked_ok = [x for x in ranked if x[0]["n"] >= MIN_TRADES]
        old = learned.get(name)
        old_score = None
        if old:
            old_score = score(rows, old["variant"], now)
        best = ranked_ok[0] if ranked_ok else None
        if best is None:
            pick, why = old, f"nog geen variant met {MIN_TRADES} trades: niets veranderd"
        elif old is None:
            pick, why = dict(variant=best[1]), "eerste keuze"
        elif best[1] == old["variant"]:
            pick, why = old, "huidige variant is nog steeds de beste"
        elif old_score["n"] >= MIN_TRADES and best[0]["score"] < old_score["score"] + SWITCH_MARGIN:
            pick, why = old, f"nieuwe beste is minder dan {SWITCH_MARGIN}R per trade beter: blijven"
        else:
            pick, why = dict(variant=best[1]), "gewisseld naar een duidelijk betere variant"
        if pick is not None:
            sc = score(rows, pick["variant"], now)
            pick = dict(variant=pick["variant"], score=sc, actief=sc["n"] >= MIN_TRADES and sc["score"] > 0,
                        sinds=pick.get("sinds") if old and pick["variant"] == old["variant"] else now.date().isoformat())
            if not pick["actief"]:
                why += "; score <= 0 of te weinig trades: markt op pauze"
            out[name] = pick
        report[name] = dict(waarom=why, top=[dict(variant=vid(v), **s) for s, v in ranked[:8]], n_data=len(rows),
                            validatie=validate(rows, pick["variant"], now) if pick else None)
    return out, report


def to_app(choice):
    """learned.json in het formaat dat tradingstrategie.py leest."""
    app = {"bijgewerkt": datetime.now(NY).isoformat(timespec="minutes"), "markten": {}}
    for name, c in choice.items():
        v = c["variant"]
        cfg = dict(DISP[v["disp"]])
        if v["target"] == "DOL":
            cfg["tp_mode"] = "DOL"
        else:
            cfg.update(tp_mode="R", tp_r=float(v["target"]))
        app["markten"][name] = dict(actief=c["actief"], cfg=cfg, kans_sess=SESSIONS[v["sessies"]],
                                    need_bias_b=BIAS[v["bias"]], variant=vid(v), score=c["score"], sinds=c["sinds"])
    return app

def validate(rows, v, now, days=VALIDATION_DAYS):
    """Chronologische controle van een variant: score op alles vóór de laatste `days` dagen (train) tegenover
    alleen de laatste `days` dagen (nieuw). Alleen rapportage: de keuze zelf verandert hierdoor niet."""
    cut = (now - timedelta(days=days)).isoformat()
    old = [r for r in rows if r["t"] < cut]
    new = [r for r in rows if r["t"] >= cut]
    return dict(dagen=days, train=score(old, v, now), nieuw=score(new, v, now))


def main():
    mem = load(MEMORY, {})
    old_rows = sum(1 for r in mem.values() if r.get("sim") != SIM_VERSION)
    if old_rows:
        print(f"Let op: {old_rows} van {len(mem)} geheugenrijen zijn met de oude simulatie berekend "
              f"(zie python -m storage.migrations).", flush=True)
    if "--histdata" in sys.argv:
        mem = collect(mem, "histdata")
    if "--geen-data" not in sys.argv:
        mem = collect(mem)
        jsonstore.save(MEMORY, mem, compact=True)
    # Ranking van de ICT-varianten voor het journaal. De keuze welke strategie een markt gebruikt (ICT of een andere)
    # maakt het strategielab (learning/lab.py + learning/selector.py); dat schrijft learned.json.
    learned_prev = load(LEARNED, {}).get("markten", {})
    prev = {k: dict(variant=_parse(v["variant"]), sinds=v.get("sinds")) for k, v in learned_prev.items() if "variant" in v}
    choice, report = choose(mem, prev)
    write_journal(choice, report, mem)
    frames = {}
    if "--geen-data" not in sys.argv:
        for m in config.CFG["markets"]:
            try:
                frames[m["name"]] = data.fetch(m["symbol"], "30d")
            except Exception as ex:
                print(f"{m['name']}: geen chartdata ({ex})", flush=True)
    days_from_logbook(frames)
    for name, r in report.items():
        c = choice.get(name)
        best = r["top"][0] if r["top"] else None
        print(f"{name:7} beste ICT-variant {best['variant'] if best else '-'} | score {best['score'] if best else 0:+.3f} "
              f"({best['n'] if best else 0} trades) | keuze per markt: strategielab" if c or best else f"{name:7} geen data")


def _parse(s):
    """Variant-tekst uit learned.json terug naar een dict."""
    disp, tp, sess, bias = [x.strip() for x in s.split("·")]
    return dict(disp=disp, target=tp.replace("TP ", ""), sessies=sess, bias=bias.replace("bias ", ""))


if __name__ == "__main__":
    main()
