#!/usr/bin/env python3
"""
ARCHIEF (bevroren, november 2026): afgerond onderzoek; draait niet in de cloud. Bij de refactor zijn alleen de
imports aangepast. Backtests via backtest.simulate gebruiken nu de centrale engine (kleine verschillen met de
oorspronkelijke cijfers: zie docs/refactor/3_engine_vergelijking.md).

Data farm: legt elk ICT-event vast op meerdere tijdframes, zoals de "LIT Data Farm" uit de TikTok-video (@keyzecom),
en draait daarop de LIT-route: sweep -> MSS met displacement (held) -> order block -> 2m-rejectie = entry.
Elke fire, weigering en uitkomst wordt bewaard. Data: HistData 1m met zomertijd-correctie (tp_videos.load_dst).

Event-soorten (vocabulary):
  liquiditeit   pool_formed (swing / EQH / EQL / sessie-niveau), pool_swept, sweep (geraakt + terug gesloten),
                manip_leg (displacement-candle die een pool pakt), manip_seq (reeks candles die samen pools pakken)
  structuur     zigzag (HH/HL/LH/LL), structure_break (bos/choch, intern/extern; één event per fysieke breuk),
                mss (na een sweep, met displacement, held), mss_failed (geen displacement of niet held)
  imbalance     fvg_formed, fvg_inverted, ifvg_retest
  zones         ob_confirmed, ob_mitigated, ob_invalidated, ob_expired, ob_consumed
  ankers        session_open (middernacht ET en 18:00 Globex)
  beslissingen  rejection_2m, lit_fire, lit_refusal, lit_outcome

Gebruik:
  python datafarm.py                 # NQ en ES, alle data -> data/farm/
  python datafarm.py --report        # alleen het overzicht van de LIT-route
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))   # repo-root (archief)

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import stats
from tp_videos import load_dst
from tradingstrategie import pivots

OUT = _Path(__file__).resolve().parents[2] / "data" / "farm"
MARKETS = {"NQ": dict(sym="NSXUSD", tick=0.25, cost=2.0), "ES": dict(sym="SPXUSD", tick=0.25, cost=0.5)}
TFS = {"2m": "2min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h"}
SETUP_TFS = ("5m", "15m")          # waar de route sweeps/MSS/OB zoekt
CONF_TFS = ("15m", "1h", "4h")     # waar we confluence tellen
SPLIT = pd.Timestamp("2026-01-01", tz="America/New_York")

DISP_BODY, DISP_ATR = 0.6, 1.5     # displacement: body >= 60% van de range en range >= 1,5x ATR
PIV_INT, PIV_EXT = 2, 5            # swing-lengte intern / extern
EQ_TOL = 0.15                      # equal highs/lows: binnen 0,15x ATR
MSS_WIN, HOLD_BARS = 20, 3         # sweep -> MSS binnen 20 bars; MSS moet 3 bars standhouden
OB_EXPIRE = 60                     # OB zonder aanraking na 60 bars verlopen
REJ_WIN_MIN = 180                  # na de OB max 3 uur wachten op een 2m-rejectie
MIN_RR, MAX_FIRES, MAX_HOURS = 1.5, 5, 5


def bars(m1, tf):
    off = "2h" if tf == "4h" else None
    b = m1.resample(TFS[tf], offset=off, label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return b[(b.index.weekday < 5) | ((b.index.weekday == 6) & (b.index.hour >= 18))]


def atr(b, n=14):
    tr = pd.concat([b.High - b.Low, (b.High - b.Close.shift()).abs(), (b.Low - b.Close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean().values


class Farm:
    def __init__(self, mkt):
        self.mkt, self.ev, self.n = mkt, [], 0

    def add(self, kind, tf, t, **kw):
        self.n += 1
        e = dict(id=f"{self.mkt}-{self.n}", kind=kind, tf=tf, t=t, **kw)
        self.ev.append(e)
        return e


def tf_events(F, b, tf, step):
    """Alle events op één tijdframe. t = moment dat het event bekend is (sluiting van de candle)."""
    O, H, L, C = (b[c].values for c in ["Open", "High", "Low", "Close"])
    T = b.index + step
    A = atr(b)
    n = len(b)
    phi, pli = pivots(list(H), list(L), PIV_INT)
    phe, ple = pivots(list(H), list(L), PIV_EXT)
    rng = H - L
    body = np.where(rng > 0, np.abs(C - O) / np.where(rng > 0, rng, 1), 0)
    disp = (body >= DISP_BODY) & (rng >= DISP_ATR * A)

    pools = []                      # dict(level, side 'BSL'/'SSL', scope, id)
    piv = {"int": dict(H=[], L=[], trend=0), "ext": dict(H=[], L=[], trend=0)}
    last_int_h = last_int_l = None
    zz_last = {"H": None, "L": None}
    sweeps = []                     # recente sweeps die op een MSS wachten
    fvgs, obs = [], []
    run_dir, run_start, run_taken = 0, 0, []
    for i in range(n):
        t = T[i]
        # --- pivots, zigzag en pools ---
        for scope, ph, pl in (("int", phi, pli), ("ext", phe, ple)):
            if ph[i] is not None:
                piv[scope]["H"].append(ph[i])
            if pl[i] is not None:
                piv[scope]["L"].append(pl[i])
        if phi[i] is not None:
            last_int_h = (phi[i], i - PIV_INT)
            lab = "HH" if zz_last["H"] is None or phi[i] > zz_last["H"] else "LH"
            zz_last["H"] = phi[i]
            F.add("zigzag", tf, t, price=phi[i], label=lab, at=b.index[i - PIV_INT])
            eq = [p for p in pools if p["side"] == "BSL" and abs(p["level"] - phi[i]) <= EQ_TOL * A[i]]
            e = F.add("pool_formed", tf, t, side="BSL", scope="EQH" if eq else "swing", level=phi[i])
            pools.append(dict(level=phi[i], side="BSL", scope=e["scope"], id=e["id"], i=i))
        if pli[i] is not None:
            last_int_l = (pli[i], i - PIV_INT)
            lab = "LL" if zz_last["L"] is None or pli[i] < zz_last["L"] else "HL"
            zz_last["L"] = pli[i]
            F.add("zigzag", tf, t, price=pli[i], label=lab, at=b.index[i - PIV_INT])
            eq = [p for p in pools if p["side"] == "SSL" and abs(p["level"] - pli[i]) <= EQ_TOL * A[i]]
            e = F.add("pool_formed", tf, t, side="SSL", scope="EQL" if eq else "swing", level=pli[i])
            pools.append(dict(level=pli[i], side="SSL", scope=e["scope"], id=e["id"], i=i))

        # --- pools geraakt: pool_swept, sweep (terug gesloten), manip_leg ---
        if i % 500 == 0:   # oude pools en pivots opruimen (houdt de lus snel)
            pools = [p for p in pools if i - p["i"] < 3000]
            for P in piv.values():
                P["H"], P["L"] = P["H"][-30:], P["L"][-30:]
        taken = [p for p in pools if (H[i] > p["level"] if p["side"] == "BSL" else L[i] < p["level"])]
        if taken:
            ids = {p["id"] for p in taken}
            pools = [p for p in pools if p["id"] not in ids]
            for side in ("BSL", "SSL"):
                tk = [p for p in taken if p["side"] == side]
                if not tk:
                    continue
                lvl = max(p["level"] for p in tk) if side == "BSL" else min(p["level"] for p in tk)
                F.add("pool_swept", tf, t, side=side, level=lvl, n_pools=len(tk), pools=[p["id"] for p in tk])
                closed_back = C[i] < lvl if side == "BSL" else C[i] > lvl
                if closed_back:
                    e = F.add("sweep", tf, t, side=side, level=lvl, ext=H[i] if side == "BSL" else L[i],
                              grade=tk[0]["scope"], vol=round(float(rng[i] / A[i]), 2))
                    sweeps.append(dict(i=i, side=side, ext=e["ext"], id=e["id"], level=lvl))
                if disp[i]:
                    F.add("manip_leg", tf, t, side=side, level=lvl, disp=round(float(rng[i] / A[i]), 2))
        # --- manipulation sequence: reeks candles van dezelfde kleur die samen pools pakken ---
        d = 1 if C[i] > O[i] else -1 if C[i] < O[i] else 0
        if d != run_dir:
            if i - run_start >= 2 and run_taken:
                F.add("manip_seq", tf, t, dir=run_dir, n_candles=i - run_start, n_pools=len(run_taken),
                      start=b.index[run_start])
            run_dir, run_start, run_taken = d, i, []
        run_taken += taken

        # --- structuur: één event per fysieke breuk, bos/choch, intern/extern ---
        emitted = False   # extern gaat voor intern; één event per fysieke breuk
        for scope in ("ext", "int"):
            P = piv[scope]
            for dr, lst in ((1, [h for h in P["H"] if C[i] > h]), (-1, [l for l in P["L"] if C[i] < l])):
                if not lst:
                    continue
                kind = "bos" if P["trend"] == dr else "choch"
                key = "H" if dr == 1 else "L"
                P[key] = [x for x in P[key] if x not in lst]
                P["trend"] = dr
                if not emitted:
                    F.add("structure_break", tf, t, dir=dr, brk=kind, scope=scope, n_pivots=len(lst),
                          level=max(lst) if dr == 1 else min(lst), disp=bool(disp[i]))
                    emitted = True

        # --- MSS na een sweep: met displacement en held, anders mss_failed ---
        sweeps = [s for s in sweeps if i - s["i"] <= MSS_WIN]
        for s in list(sweeps):
            up = s["side"] == "SSL"         # sell-side gepakt -> long
            ref = last_int_h if up else last_int_l
            if ref is None or ref[1] <= s["i"] - 30:
                continue
            if (C[i] > ref[0]) if up else (C[i] < ref[0]):
                sweeps.remove(s)
                if not disp[i]:
                    F.add("mss_failed", tf, t, dir=1 if up else -1, level=ref[0], reason="geen displacement", sweep=s["id"])
                    continue
                later = C[i + 1:i + 1 + HOLD_BARS]
                held = len(later) == HOLD_BARS and ((later > ref[0]).all() if up else (later < ref[0]).all())
                tk = T[min(i + HOLD_BARS, n - 1)]
                if not held:
                    F.add("mss_failed", tf, tk, dir=1 if up else -1, level=ref[0], reason="niet held", sweep=s["id"])
                    continue
                e = F.add("mss", tf, tk, dir=1 if up else -1, level=ref[0], disp=round(float(rng[i] / A[i]), 2),
                          sweep=s["id"], sweep_ext=s["ext"], at=b.index[i])
                # order block: laatste candle van de andere kleur in het been tussen sweep en MSS
                ob = None
                for j in range(i, s["i"] - 1, -1):
                    if (C[j] < O[j]) if up else (C[j] > O[j]):
                        ob = j
                        break
                if ob is not None:
                    z = F.add("ob_confirmed", tf, tk, dir=1 if up else -1, top=float(H[ob]), bot=float(L[ob]),
                              mss=e["id"], sweep=s["id"], sweep_ext=s["ext"], at=b.index[ob])
                    obs.append(dict(ev=z, i=i + HOLD_BARS, touched=False, live=True))

        # --- order blocks bijhouden ---
        for o in obs:
            if not o["live"] or i <= o["i"]:
                continue
            z = o["ev"]
            up = z["dir"] == 1
            if (C[i] < z["bot"]) if up else (C[i] > z["top"]):
                F.add("ob_invalidated", tf, t, ob=z["id"])
                o["live"] = False
            elif L[i] <= z["top"] and H[i] >= z["bot"] and not o["touched"]:
                F.add("ob_mitigated", tf, t, ob=z["id"])
                o["touched"] = True
            elif not o["touched"] and i - o["i"] > OB_EXPIRE:
                F.add("ob_expired", tf, t, ob=z["id"])
                o["live"] = False
        obs = [o for o in obs if o["live"]]

        # --- FVG's: ontstaan, inversie, retest ---
        if i >= 2 and L[i] > H[i - 2] and body[i - 1] >= 0.5:
            e = F.add("fvg_formed", tf, t, dir=1, top=float(L[i]), bot=float(H[i - 2]), at=b.index[i - 1])
            fvgs.append(dict(ev=e, inv=False, i=i))
        if i >= 2 and H[i] < L[i - 2] and body[i - 1] >= 0.5:
            e = F.add("fvg_formed", tf, t, dir=-1, top=float(L[i - 2]), bot=float(H[i]), at=b.index[i - 1])
            fvgs.append(dict(ev=e, inv=False, i=i))
        for f in fvgs:
            if i <= f["i"]:
                continue
            z = f["ev"]
            if not f["inv"] and ((C[i] < z["bot"]) if z["dir"] == 1 else (C[i] > z["top"])):
                F.add("fvg_inverted", tf, t, fvg=z["id"], dir=-z["dir"])
                f["inv"], f["inv_i"] = True, i
            elif f["inv"] and i > f["inv_i"] and L[i] <= z["top"] and H[i] >= z["bot"]:
                ok = (C[i] < z["bot"]) if z["dir"] == 1 else (C[i] > z["top"])
                F.add("ifvg_retest", tf, t, fvg=z["id"], held=bool(ok))
                f["done"] = True
        fvgs = [f for f in fvgs if not f.get("done") and i - f["i"] < 300]
    return A


def session_opens(F, m1):
    for t in m1.index[(m1.index.minute == 0) & ((m1.index.hour == 0) | (m1.index.hour == 18))]:
        F.add("session_open", "2m", t, anchor="middernacht ET" if t.hour == 0 else "18:00 Globex",
              price=float(m1.at[t, "Open"]))


def zones_at(ev, t, kinds=("ob_confirmed", "fvg_formed"), tfs=CONF_TFS):
    """Actieve OB/FVG-zones per tijdframe op moment t (grofweg: gevormd in de laatste 2 dagen)."""
    return [e for e in ev if e["kind"] in kinds and e["tf"] in tfs and t - pd.Timedelta("2D") <= e["t"] <= t]


def lit_route(F, m1, b2, cfg):
    """Per bevestigde OB op 5m/15m: wacht op de eerste 2m-rejectie in de zone; entry op de close daarvan."""
    ev = F.ev
    obs = [e for e in ev if e["kind"] == "ob_confirmed" and e["tf"] in SETUP_TFS]
    inval = {e["ob"]: e["t"] for e in ev if e["kind"] == "ob_invalidated"}
    # pools op 15m/1h met moment van ontstaan en (eventueel) van gepakt worden
    swept_at = {}
    for e in ev:
        if e["kind"] == "pool_swept" and e["tf"] in ("15m", "1h"):
            for pid in e["pools"]:
                swept_at[pid] = e["t"]
    pf = sorted((e for e in ev if e["kind"] == "pool_formed" and e["tf"] in ("15m", "1h")), key=lambda e: e["t"])
    pf_t = np.array([e["t"].value for e in pf])
    pf_lvl = np.array([e["level"] for e in pf])
    pf_bsl = np.array([e["side"] == "BSL" for e in pf])
    far = pd.Timestamp.max.tz_localize("UTC").value
    pf_sw = np.array([swept_at[e["id"]].value if e["id"] in swept_at else far for e in pf])
    zone_ev = sorted((e for e in ev if e["kind"] in ("ob_confirmed", "fvg_formed") and e["tf"] in CONF_TFS),
                     key=lambda e: e["t"])
    zone_t = np.array([e["t"].value for e in zone_ev])
    O2, H2, L2, C2 = (b2[c].values for c in ["Open", "High", "Low", "Close"])
    T2 = b2.index + pd.Timedelta("2min")
    fires_day = {}
    busy_until = T2[0]
    for z in sorted(obs, key=lambda e: e["t"]):
        up = z["dir"] == 1
        k0 = np.searchsorted(T2, z["t"], side="left")
        k1 = np.searchsorted(T2, z["t"] + pd.Timedelta(minutes=REJ_WIN_MIN), side="right")
        dead = inval.get(z["id"])
        hit = None
        for k in range(k0, min(k1, len(T2))):
            if dead is not None and T2[k] > dead:
                break
            inside = L2[k] <= z["top"] and H2[k] >= z["bot"]
            if inside and ((C2[k] > O2[k] and C2[k] > z["bot"]) if up else (C2[k] < O2[k] and C2[k] < z["top"])):
                hit = k
                break
        if hit is None:
            F.add("lit_refusal", z["tf"], z["t"], ob=z["id"], dir=z["dir"],
                  reason="OB ongeldig voor rejectie" if dead is not None and dead < z["t"] + pd.Timedelta(minutes=REJ_WIN_MIN)
                  else "geen 2m-rejectie in de zone")
            continue
        t = T2[hit]
        rej = F.add("rejection_2m", "2m", t, ob=z["id"], dir=z["dir"], close=float(C2[hit]))
        hm = t.strftime("%H:%M")
        day = (t + pd.Timedelta(hours=6)).date()
        entry = float(C2[hit])
        ext = min(z["bot"], z["sweep_ext"]) if up else max(z["top"], z["sweep_ext"])
        stop = ext - 4 * cfg["tick"] if up else ext + 4 * cfg["tick"]
        risk = abs(entry - stop)
        # doel: dichtstbijzijnde nog niet gepakte pool op 15m/1h aan de goede kant
        tp = None
        a0, a1 = np.searchsorted(pf_t, (t - pd.Timedelta("5D")).value), np.searchsorted(pf_t, t.value, side="right")
        live = pf_sw[a0:a1] > t.value
        lv = pf_lvl[a0:a1]
        if up:
            cand = lv[live & pf_bsl[a0:a1] & (lv > entry + MIN_RR * risk)]
            tp = float(cand.min()) if len(cand) else None
        else:
            cand = lv[live & ~pf_bsl[a0:a1] & (lv < entry - MIN_RR * risk)]
            tp = float(cand.max()) if len(cand) else None
        lo, hi = np.searchsorted(zone_t, (t - pd.Timedelta("2D")).value), np.searchsorted(zone_t, t.value, side="right")
        conf = sorted({e["tf"] for e in zone_ev[lo:hi] if e["dir"] == z["dir"] and e["bot"] <= z["top"] and e["top"] >= z["bot"]})
        reason = None
        if "16:00" <= hm < "18:00":
            reason = "markt dicht / onderhoud"
        elif t < busy_until:
            reason = "al in een trade"
        elif fires_day.get(day, 0) >= MAX_FIRES:
            reason = f"max {MAX_FIRES} per dag"
        elif risk <= 0:
            reason = "stop aan de verkeerde kant"
        elif tp is None:
            reason = f"geen pool op >= {MIN_RR}R"
        if reason:
            F.add("lit_refusal", "2m", t, ob=z["id"], dir=z["dir"], reason=reason, rejection=rej["id"])
            continue
        fire = F.add("lit_fire", "2m", t, ob=z["id"], dir=z["dir"], entry=entry, stop=stop, tp=tp,
                     rr=round((tp - entry) / risk if up else (entry - tp) / risk, 2), conf=conf, setup_tf=z["tf"],
                     mss=z["mss"], sweep=z["sweep"], rejection=rej["id"])
        fires_day[day] = fires_day.get(day, 0) + 1
        res, r, t_out = exit_1m(m1, up, entry, stop, tp, t)
        F.add("ob_consumed", z["tf"], t, ob=z["id"])
        F.add("lit_outcome", "2m", t_out, fire=fire["id"], result=res, R=round(r, 2),
              R_net=round(r - cfg["cost"] / risk, 2), dir=z["dir"])
        busy_until = t_out


def exit_1m(m1, up, entry, stop, tp, t):
    after = m1.loc[t:t + pd.Timedelta(hours=MAX_HOURS)]
    risk = abs(entry - stop)
    for ts, h, l in zip(after.index, after.High.values, after.Low.values):
        if (l <= stop) if up else (h >= stop):
            return "stop", -1.0, ts
        if (h >= tp) if up else (l <= tp):
            return "TP", abs(tp - entry) / risk, ts
    c = after.Close.values[-1]
    return f"dicht na {MAX_HOURS}u", ((c - entry) if up else (entry - c)) / risk, after.index[-1]


def run(mkt):
    cfg = MARKETS[mkt]
    print(f"{mkt}: data laden...", flush=True)
    m1 = load_dst(cfg["sym"])
    F = Farm(mkt)
    B = {tf: bars(m1, tf) for tf in TFS}
    for tf, b in B.items():
        print(f"  {tf}: {len(b)} candles", flush=True)
        tf_events(F, b, tf, pd.Timedelta(TFS[tf]))
    session_opens(F, m1)
    print("  LIT-route...", flush=True)
    lit_route(F, m1, B["2m"], cfg)
    ev = pd.DataFrame(F.ev)
    ev["day"] = (ev.t + pd.Timedelta(hours=6)).dt.date
    OUT.mkdir(parents=True, exist_ok=True)
    ev.to_pickle(OUT / f"events_{mkt}.pkl")
    print(f"  {len(ev)} events opgeslagen", flush=True)
    return ev


def chain(ev, f):
    """Lineage van een fire, zoals in de video: sweep -> MSS -> OB -> entry."""
    by = ev.set_index("id")
    s, m, o = by.loc[f["sweep"]], by.loc[f["mss"]], by.loc[f["ob"]]
    side = "long" if f["dir"] == 1 else "short"
    return (f"{f['t']:%H:%M} {f['setup_tf']} ob {side} - sweep {s['side']}@{s['tf']} ({s['grade']}) -> "
            f"MSS@{m['tf']} lvl {m['level']:.2f} disp {m['disp']} held -> OB {o['bot']:.2f}-{o['top']:.2f} "
            f"conf {','.join(f['conf']) or '-'} -> entry {f['entry']:.2f} sl {f['stop']:.2f} tp {f['tp']:.2f} ({f['rr']}R)")


def study(ev, day):
    d = ev[ev.day == day]
    counts = d.kind.value_counts().sort_index()
    out = dict(day=str(day), counts={k: int(v) for k, v in counts.items()}, fires=[], refusals={})
    outc = ev[ev.kind == "lit_outcome"].set_index("fire")
    for _, f in d[d.kind == "lit_fire"].iterrows():
        o = outc.loc[f["id"]] if f["id"] in outc.index else None
        out["fires"].append(dict(chain=chain(ev, f), result=None if o is None else o["result"],
                                 R=None if o is None else float(o["R"]), R_net=None if o is None else float(o["R_net"])))
    out["refusals"] = {k: int(v) for k, v in d[d.kind == "lit_refusal"].reason.value_counts().items()}
    return out


def report(evs):
    for mkt, ev in evs.items():
        o = ev[ev.kind == "lit_outcome"].sort_values("t")
        f = ev[ev.kind == "lit_fire"]
        print(f"\n===== {mkt}: LIT-route (sweep -> MSS -> OB -> 2m-rejectie) =====")
        if not len(o):
            print("geen trades")
            continue
        months = max((o.t.max() - o.t.min()).days / 30.4, 1)
        for lab, col in (("bruto", "R"), ("na kosten", "R_net")):
            a, b, c = stats(o[o.t < SPLIT][col].values), stats(o[o.t >= SPLIT][col].values), stats(o[col].values)
            print(f"{lab:9} {c['n']:4} trades ({c['n'] / months:4.1f}/mnd) | 2025: {a['win']:4.0%} win {a['totR']:+7.1f}R"
                  f" | 2026: {b['win']:4.0%} win {b['totR']:+7.1f}R | maxDD {c['maxDD']:5.1f}R")
        ff = f.set_index("id")
        o2 = o.assign(conf=o.fire.map(ff.conf).map(len), tf=o.fire.map(ff.setup_tf))
        print("per setup-tijdframe:", {k: round(g.R_net.sum(), 1) for k, g in o2.groupby("tf")})
        print("per aantal confluence-TF's:", {k: (len(g), round(g.R_net.sum(), 1)) for k, g in o2.groupby("conf")})
        print("weigeringen:", ev[ev.kind == "lit_refusal"].reason.value_counts().to_dict())
        print("event-tellingen:", ev.kind.value_counts().to_dict())


def main():
    if "--report" in sys.argv:
        evs = {m: pd.read_pickle(OUT / f"events_{m}.pkl") for m in MARKETS if (OUT / f"events_{m}.pkl").exists()}
    else:
        evs = {m: run(m) for m in MARKETS}
        for mkt, ev in evs.items():
            days = sorted(ev.day.unique())
            (OUT / f"studies_{mkt}.json").write_text(json.dumps([study(ev, d) for d in days], default=str, ensure_ascii=False))
    report(evs)


if __name__ == "__main__":
    main()
