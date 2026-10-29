#!/usr/bin/env python3
"""TradingStrategie: TJR / ICT confluence-meldingen op je Mac, zonder TradingView-abonnement.

Zelfde logica als tjr_alerts.pine:
  kern:   sweep van liquiditeit -> MSS met displacement -> FVG, in het NY-window
  score:  4H bias, 1H bias, premium/discount, OTE, HTF FVG, SMT met ES,
          Silver Bullet, sterke displacement, IFVG, draw on liquidity >= 2R
"Kans" = setup in NY AM (backtest 2025-2026: alleen die sessie was in beide jaren winstgevend).
London en NY PM worden nog wel gemeld, maar als "lage kans". TP = vaste 1R (zie backtest.py).
Markten: NQ (TP 1R) en EURUSD (TP op de DOL), zie "markets" en backtest_multi.py.
Sessies: London 02:00-05:00, NY AM 09:30-11:30 en NY PM 13:30-15:30 (NY-tijd).
Alleen meldingen, er worden geen orders geplaatst.

Gebruik:
  python tradingstrategie.py               live: elke minuut checken en melden
  python tradingstrategie.py --scan        alle setups van de afgelopen 30 dagen tonen
  python tradingstrategie.py --test-notify testmelding sturen
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

NY = ZoneInfo("America/New_York")
HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "verstuurd.json"
LOG_FILE = HERE / "setups.log"

CFG = {
    "symbol": "NQ=F",          # Nasdaq futures (Yahoo); voor ES: "ES=F"
    "smt_symbol": "ES=F",      # gecorreleerd symbool voor SMT
    # Markten die gecheckt worden; "cfg" overschrijft per markt de instellingen hieronder.
    # EURUSD-instellingen komen uit backtest_multi.py (NY AM, basis-displacement, TP op de DOL).
    "markets": [
        # alt: de prijs bij je broker/prop firm (US100 volgt de Nasdaq-100 index, niet de future)
        dict(name="NQ", symbol="NQ=F", smt="ES=F", dec=2, cfg={}, alt=dict(symbol="^NDX", label="US100")),
        dict(name="EURUSD", symbol="EURUSD=X", smt="GBPUSD=X", dec=5,
             cfg=dict(tick=0.00002, disp_pct=0.6, disp_atr=1.2, tp_mode="DOL")),
    ],
    "trade_sess": [("02:00", "05:00"), ("09:30", "11:30"), ("13:30", "15:30")],   # London, NY AM, NY PM
    "sb_sess": [("03:00", "04:00"), ("10:00", "11:00"), ("14:00", "15:00")],      # Silver Bullet per sessie
    "asia_sess": ("20:00", "23:59"),
    "lond_sess": ("02:00", "05:00"),
    "htf_a": "4h",             # context
    "htf_b": "1h",             # bias ("30min" kan ook)
    "htf_piv": 3,
    "need_bias_b": False,      # False: tegen de bias mag, maar telt als lagere kans
    "piv_len": 3,
    "disp_pct": 0.7,           # strenger dan 0.6/1.2: beter in de backtest
    "disp_atr": 1.5,
    "mss_window": 20,
    "fvg_window": 3,
    "smt_len": 20,
    "entry_mode": "50%",       # of "Rand"
    "entry_win": 12,
    "min_rr": 2.0,             # alleen voor het DOL-vinkje in de score
    "tp_r": 1.0,               # winst nemen op 1R (backtest: beter dan de DOL als doel)
    "tp_mode": "R",            # "R" = vaste tp_r, "DOL" = op de liquiditeit (valt terug op tp_r)
    "kans_sess": ["NY AM"],    # alleen setups in deze sessie(s) zijn "kans"
    "buf_ticks": 4,
    "tick": 0.25,
    "max_per_day": 6,          # alle setups samen, zodat je niet wordt overspoeld
    "min_score": 0,            # extra eis voor "kans" (backtest: de score hielp niet, dus uit)
    "no_close": False,         # TradingPool: na de sweep mag geen candle buiten het niveau sluiten
    "need_smt": False,         # TradingPool: divergentie (SMT) verplicht bij de sweep
    "day_end": "15:30",        # na dit tijdstip: melding als er vandaag niks was
    # Pushmelding op je telefoon via de gratis app "ntfy". Het onderwerp staat in ntfy_topic.txt
    # (niet in de code, zodat het geheim blijft). Bestand weg = geen telefoonmeldingen.
    "ntfy_topic": (HERE / "ntfy_topic.txt").read_text().strip() if (HERE / "ntfy_topic.txt").exists() else "",
}

# Aan/uit-schakelaars uit het dashboard. Staan in config.json; ontbreekt iets, dan geldt de standaard.
SETTINGS_FILE = HERE / "config.json"
DEFAULT_SETTINGS = {
    "actief": True,                                        # hoofdschakelaar voor alle meldingen
    "markten": {"NQ": True, "EURUSD": True},
    "sessies": {"London": True, "NY AM": True, "NY PM": True},
    "alleen_kans": False,                                  # True: geen "LAGE KANS"-meldingen
    "entry_meldingen": True,                               # "prijs in entry-zone"
    "dagmelding": True,                                    # "vandaag geen setup" na day_end
    "telefoon": True,                                      # ntfy-pushmeldingen
    "max_per_day": 6,
}
SESS_NAMES = ["London", "NY AM", "NY PM"]                  # zelfde volgorde als trade_sess en sb_sess


def load_settings():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        own = json.loads(SETTINGS_FILE.read_text())
    except (OSError, ValueError):
        return s
    for k, v in own.items():
        if isinstance(s.get(k), dict) and isinstance(v, dict):
            s[k].update(v)
        elif k in s:
            s[k] = v
    return s


SET = DEFAULT_SETTINGS


def apply_settings():
    """config.json toepassen op CFG (markten en sessies) en SET (meldingen)."""
    global SET
    SET = load_settings()
    CFG["markets"] = [m for m in CFG["markets"] if SET["markten"].get(m["name"], True)]
    keep = [i for i, n in enumerate(SESS_NAMES) if SET["sessies"].get(n, True)]
    CFG["trade_sess"] = [CFG["trade_sess"][i] for i in keep]
    CFG["sb_sess"] = [CFG["sb_sess"][i] for i in keep]
    CFG["max_per_day"] = int(SET["max_per_day"])


BAR = timedelta(minutes=5)


# ------------- Data -------------
def fetch(symbol, period="30d"):
    df = yf.download(symbol, interval="5m", period=period, progress=False, auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"Geen data voor {symbol}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    df.index = df.index.tz_convert(NY)
    # Laatste candle weglaten als die nog niet gesloten is
    if df.index[-1] + BAR > datetime.now(timezone.utc):
        df = df.iloc[:-1]
    return df


def in_sess(ts, sess):
    """sess is een (start, eind) of een lijst daarvan."""
    if isinstance(sess, list):
        return any(in_sess(ts, s) for s in sess)
    start, end = sess
    hm = ts.strftime("%H:%M")
    return start <= hm < end if end != "23:59" else start <= hm <= end


# ------------- Hogere timeframes -------------
def pivots(highs, lows, n):
    """Bevestigde swing high/low op index i (de pivot zelf ligt op i - n)."""
    ph = [None] * len(highs)
    pl = [None] * len(lows)
    for i in range(2 * n, len(highs)):
        j = i - n
        win_h = highs[j - n:i + 1]
        win_l = lows[j - n:i + 1]
        if highs[j] == max(win_h) and list(win_h).count(highs[j]) == 1:
            ph[i] = highs[j]
        if lows[j] == min(win_l) and list(win_l).count(lows[j]) == 1:
            pl[i] = lows[j]
    return ph, pl


def htf_state(df5, rule, piv):
    """Bias, laatste FVG en swing-range per HTF-candle; geldig vanaf de sluiting van die candle."""
    offset = "2h" if rule == "4h" else None   # 4H-candles van CME starten om 18:00 NY
    h = df5.resample(rule, offset=offset, label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    H, L, C = h["High"].tolist(), h["Low"].tolist(), h["Close"].tolist()
    ph, pl = pivots(H, L, piv)
    b, sh, sl, rH, rL, fT, fB, fD = 0, None, None, None, None, None, None, 0
    rows = []
    for i in range(len(h)):
        if ph[i] is not None:
            sh = rH = ph[i]
        if pl[i] is not None:
            sl = rL = pl[i]
        if sh is not None and C[i] > sh:
            b, sh = 1, None
        elif sl is not None and C[i] < sl:
            b, sl = -1, None
        if i >= 2 and L[i] > H[i - 2]:
            fT, fB, fD = L[i], H[i - 2], 1
        elif i >= 2 and H[i] < L[i - 2]:
            fT, fB, fD = L[i - 2], H[i], -1
        if fD == 1 and L[i] < fB:
            fD = 0
        if fD == -1 and H[i] > fT:
            fD = 0
        rows.append((b, fT, fB, fD, rH, rL))
    out = pd.DataFrame(rows, columns=["bias", "fT", "fB", "fD", "rH", "rL"], index=h.index)
    out["avail"] = out.index + pd.Timedelta(rule)
    return out


def align_htf(df5, st):
    """Per 5m-candle de HTF-state van de laatst gesloten HTF-candle."""
    left = pd.DataFrame({"close_t": df5.index + BAR}, index=df5.index)
    m = pd.merge_asof(left.sort_values("close_t"), st.sort_values("avail"),
                      left_on="close_t", right_on="avail", direction="backward")
    m.index = df5.index
    return m


# ------------- Analyse -------------
def nearest(p, levels, above):
    vals = [v for v in levels if v is not None and not pd.isna(v) and (v > p if above else v < p)]
    if not vals:
        return None
    return min(vals) if above else max(vals)


def analyse(df, es, cfg=CFG):
    """Loopt alle 5m-candles af en geeft een lijst setups en entry-zone events terug."""
    n = len(df)
    idx = df.index
    O, H, L, C = (df[c].tolist() for c in ["Open", "High", "Low", "Close"])

    A = align_htf(df, htf_state(df, cfg["htf_a"], cfg["htf_piv"]))
    B = align_htf(df, htf_state(df, cfg["htf_b"], cfg["htf_piv"]))

    # Vorige-dag high/low (CME-dag begint om 18:00 NY)
    tday = [(t + timedelta(hours=6)).date() for t in idx]
    daily = df.assign(td=tday).groupby("td").agg(H=("High", "max"), L=("Low", "min"))
    prev = daily.shift(1)
    pdh = [prev["H"].get(d) for d in tday]
    pdl = [prev["L"].get(d) for d in tday]

    # ATR (RMA, zoals Pine)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - df["Close"].shift()).abs(),
                    (df["Low"] - df["Close"].shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean().tolist()

    # SMT
    es = es.reindex(idx).ffill()
    sl_ = cfg["smt_len"]
    my_lo_prev = df["Low"].rolling(sl_).min().shift(1).tolist()
    my_hi_prev = df["High"].rolling(sl_).max().shift(1).tolist()
    o_lo_prev = es["Low"].rolling(sl_).min().shift(1).tolist()
    o_hi_prev = es["High"].rolling(sl_).max().shift(1).tolist()
    oL, oH = es["Low"].tolist(), es["High"].tolist()

    ph, pl = pivots(H, L, cfg["piv_len"])
    tick = cfg["tick"]

    setups, entries = [], []
    swingH = swingL = None
    asiaH = asiaL = londH = londL = None
    lastBullFvgBot = lastBearFvgTop = None
    lastBullFvgBar = lastBearFvgBar = -10**9
    lastTouchBull = lastTouchBear = -10**9
    setups_today = 0
    today = None
    S = {d: dict(state=0) for d in ("long", "short")}

    for i in range(n):
        t = idx[i]
        in_trade = in_sess(t, cfg["trade_sess"])
        in_trade_prev = i > 0 and in_sess(idx[i - 1], cfg["trade_sess"])
        in_asia = in_sess(t, cfg["asia_sess"])
        in_lond = in_sess(t, cfg["lond_sess"])
        in_asia_prev = i > 0 and in_sess(idx[i - 1], cfg["asia_sess"])
        in_lond_prev = i > 0 and in_sess(idx[i - 1], cfg["lond_sess"])

        if in_asia and not in_asia_prev:
            asiaH, asiaL = H[i], L[i]
        elif in_asia:
            asiaH, asiaL = max(asiaH, H[i]), min(asiaL, L[i])
        if in_lond and not in_lond_prev:
            londH, londL = H[i], L[i]
        elif in_lond:
            londH, londL = max(londH, H[i]), min(londL, L[i])

        if ph[i] is not None:
            swingH = ph[i]
        if pl[i] is not None:
            swingL = pl[i]

        a, b = A.iloc[i], B.iloc[i]
        aBias = 0 if pd.isna(a["bias"]) else int(a["bias"])
        bBias = 0 if pd.isna(b["bias"]) else int(b["bias"])
        bRH, bRL = b["rH"], b["rL"]

        def touch(row, d):
            return row["fD"] == d and L[i] <= row["fT"] and H[i] >= row["fB"]
        if touch(b, 1) or touch(a, 1):
            lastTouchBull = i
        if touch(b, -1) or touch(a, -1):
            lastTouchBear = i

        rng = H[i] - L[i]
        body = abs(C[i] - O[i]) / rng if rng > 0 else 0
        bullDisp = C[i] > O[i] and body >= cfg["disp_pct"]
        bearDisp = C[i] < O[i] and body >= cfg["disp_pct"]
        strong = rng >= cfg["disp_atr"] * atr[i]
        bullFvg = i >= 2 and L[i] > H[i - 2]
        bearFvg = i >= 2 and H[i] < L[i - 2]
        if bullFvg:
            lastBullFvgBot, lastBullFvgBar = H[i - 2], i
        if bearFvg:
            lastBearFvgTop, lastBearFvgBar = L[i - 2], i

        def poke(lvl, up):
            if lvl is None or pd.isna(lvl) or i == 0:
                return False
            return (H[i] > lvl and H[i - 1] <= lvl) if up else (L[i] < lvl and L[i - 1] >= lvl)

        lv_map = {"PDH": pdh[i], "Asia H": asiaH, "London H": londH, "PDL": pdl[i], "Asia L": asiaL, "London L": londL}
        hi_hits = [nm for nm in ("PDH", "Asia H", "London H") if poke(lv_map[nm], True)]
        lo_hits = [nm for nm in ("PDL", "Asia L", "London L") if poke(lv_map[nm], False)]

        smtBull = not pd.isna(my_lo_prev[i]) and L[i] < my_lo_prev[i] and oL[i] >= o_lo_prev[i]
        smtBear = not pd.isna(my_hi_prev[i]) and H[i] > my_hi_prev[i] and oH[i] <= o_hi_prev[i]

        if in_trade and not in_trade_prev:
            if t.date() != today:
                today, setups_today = t.date(), 0
            S["long"]["state"] = S["short"]["state"] = 0
        can_setup = in_trade and setups_today < cfg["max_per_day"]

        for d in ("long", "short"):
            s = S[d]
            up = d == "long"
            ok_dir = (not cfg["need_bias_b"]) or bBias == (1 if up else -1)
            sweep = lo_hits if up else hi_hits

            if sweep and can_setup and ok_dir and s["state"] <= 1:
                if s["state"] == 0:
                    s.update(ext=L[i] if up else H[i], leg=H[i] if up else L[i],
                             fT=None, fB=None, smt=False, sweep_name=sweep[0], sweep_t=t, lvl=lv_map[sweep[0]])
                s["state"], s["bar"] = 1, i

            if s["state"] in (1, 2) and cfg["no_close"] and (C[i] < s["lvl"] if up else C[i] > s["lvl"]):
                s["state"] = 0   # candle sloot buiten het geveegde niveau: geen sweep maar een uitbraak

            if s["state"] in (1, 2):
                s["leg"] = max(s["leg"], H[i]) if up else min(s["leg"], L[i])
                if (smtBull if up else smtBear):
                    s["smt"] = True
                if up and bullFvg:
                    s["fT"], s["fB"] = L[i], H[i - 2]
                if not up and bearFvg:
                    s["fT"], s["fB"] = L[i - 2], H[i]

            if s["state"] == 1:
                s["ext"] = min(s["ext"], L[i]) if up else max(s["ext"], H[i])
                if i - s["bar"] > cfg["mss_window"] or not in_trade:
                    s["state"] = 0
                elif up and swingH is not None and C[i] > swingH and bullDisp:
                    s.update(state=2, mss=i, strong=strong,
                             ifvg=lastBearFvgTop is not None and C[i] > lastBearFvgTop and i - lastBearFvgBar <= cfg["mss_window"])
                elif not up and swingL is not None and C[i] < swingL and bearDisp:
                    s.update(state=2, mss=i, strong=strong,
                             ifvg=lastBullFvgBot is not None and C[i] < lastBullFvgBot and i - lastBullFvgBar <= cfg["mss_window"])

            if s["state"] == 2:
                if not ok_dir:   # HTF-bias is intussen gedraaid: setup vervalt
                    s["state"] = 0
                elif s["fT"] is not None and cfg["need_smt"] and not s["smt"]:
                    s["state"] = 0   # geen divergentie: overslaan
                elif s["fT"] is not None and setups_today < cfg["max_per_day"]:
                    fT, fB = s["fT"], s["fB"]
                    if up:
                        entry = fT if cfg["entry_mode"] == "Rand" else (fT + fB) / 2
                        stop = s["ext"] - cfg["buf_ticks"] * tick
                        risk = entry - stop
                    else:
                        entry = fB if cfg["entry_mode"] == "Rand" else (fT + fB) / 2
                        stop = s["ext"] + cfg["buf_ticks"] * tick
                        risk = stop - entry
                    if risk > 0:
                        if up:
                            dol = nearest(entry + risk, [pdh[i], asiaH, londH, bRH], True)
                            dol_rr = (dol - entry) / risk if dol is not None else 0
                            tp, rr = entry + cfg["tp_r"] * risk, cfg["tp_r"]
                            span = s["leg"] - s["ext"]
                            retr = (s["leg"] - entry) / span if span > 0 else 0
                        else:
                            dol = nearest(entry - risk, [pdl[i], asiaL, londL, bRL], False)
                            dol_rr = (entry - dol) / risk if dol is not None else 0
                            tp, rr = entry - cfg["tp_r"] * risk, cfg["tp_r"]
                            span = s["ext"] - s["leg"]
                            retr = (entry - s["leg"]) / span if span > 0 else 0
                        if cfg["tp_mode"] == "DOL" and dol is not None:
                            tp, rr = dol, dol_rr
                        eq = None if pd.isna(bRH) or pd.isna(bRL) else (bRH + bRL) / 2
                        sign = 1 if up else -1
                        checks = {
                            f"{cfg['htf_a']} bias": aBias == sign,
                            f"{cfg['htf_b']} bias": bBias == sign,
                            "Discount" if up else "Premium": eq is not None and (entry < eq if up else entry > eq),
                            "OTE 62-79%": 0.62 <= retr <= 0.79,
                            "HTF FVG (POI)": i - (lastTouchBull if up else lastTouchBear) <= cfg["mss_window"] + cfg["fvg_window"],
                            "SMT": s["smt"],
                            "Silver Bullet": in_sess(t, cfg["sb_sess"]),
                            "Sterke displacement": s["strong"],
                            "IFVG": s["ifvg"],
                            f"DOL >= {cfg['min_rr']}R": dol is not None and dol_rr >= cfg["min_rr"],
                        }
                        score = sum(checks.values())
                        grade = "A+" if score >= 7 else "A" if score >= 5 else "B" if score >= 3 else "C"
                        # Tegen de HTF-bias in is altijd "lage kans", hoe hoog de score ook is
                        good = score >= cfg["min_score"] and sess_name(t) in cfg["kans_sess"]
                        setups_today += 1
                        setup = dict(time=t, side=d.upper(), grade=grade, score=score, good=good,
                                     entry=entry, stop=stop, tp=tp, rr=rr, dol=dol, sweep=s["sweep_name"], sweep_t=s["sweep_t"], mss_t=idx[s["mss"]],
                                     bias_a=aBias, bias_b=bBias, checks=checks, entry_hit=None)
                        setups.append(setup)
                        s.update(state=3, sig=i, setup=setup)
                    else:
                        s["state"] = 0
                elif i - s["mss"] > cfg["fvg_window"] or not in_trade:
                    s["state"] = 0

            if s["state"] == 3 and i > s["sig"]:
                st = s["setup"]
                hit = L[i] <= st["entry"] if up else H[i] >= st["entry"]
                if hit:
                    st["entry_hit"] = t
                    entries.append(dict(time=t, setup=st))
                    s["state"] = 0
                elif i - s["sig"] > cfg["entry_win"] or (C[i] < st["stop"] if up else C[i] > st["stop"]):
                    s["state"] = 0

    return setups, entries


# ------------- Uitvoer -------------
def bias_txt(b):
    return "bullish" if b == 1 else "bearish" if b == -1 else "neutraal"


def sess_name(t):
    hm = t.strftime("%H:%M")
    return "London" if hm < "09:00" else "NY AM" if hm < "12:00" else "NY PM"


def kans(s):
    return "kans" if s["good"] else "LAGE KANS"


def against_bias(s):
    return s["bias_b"] != (1 if s["side"] == "LONG" else -1)


def px(s, v):
    return f"{v:.{s.get('dec', 2)}f}"


def setup_text(s):
    return (f"{s.get('mkt', '')} [{sess_name(s['time'])}] {s['side']} {s['grade']} ({s['score']}/10, {kans(s)}{', tegen ' + CFG['htf_b'] + '-bias' if against_bias(s) else ''}) | entry {px(s, s['entry'])} | stop {px(s, s['stop'])} | "
            f"TP {px(s, s['tp'])} ({s['rr']:.1f}R) | sweep {s['sweep']} | "
            f"{CFG['htf_b']} {bias_txt(s['bias_b'])}, {CFG['htf_a']} {bias_txt(s['bias_a'])}")


def checklist(s):
    return "  ".join(("[x] " if v else "[ ] ") + k for k, v in s["checks"].items())


def notify(title, msg, sound="Glass"):
    if sys.platform == "darwin":
        script = f"display notification {json.dumps(msg)} with title {json.dumps(title)} sound name {json.dumps(sound)}"
        subprocess.run(["osascript", "-e", script], check=False)
    push_phone(title, msg, high=sound == "Glass" or sound == "Hero")


def push_phone(title, msg, high=False):
    """Stuurt dezelfde melding naar je telefoon via ntfy.sh."""
    if not CFG["ntfy_topic"] or not SET["telefoon"]:
        return
    req = urllib.request.Request(f"https://ntfy.sh/{CFG['ntfy_topic']}", data=msg.encode(), method="POST",
                                 headers={"Title": title, "Priority": "high" if high else "default",
                                          "Tags": "chart_with_upwards_trend"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as ex:  # geen internet: Mac-melding is al verstuurd
        print("Telefoonmelding mislukt:", ex, flush=True)


def log(line):
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def outcome(df, s):
    """Na de entry: wat werd eerst geraakt, stop of TP? Uiterlijk 16:00 NY gesloten."""
    if s["entry_hit"] is None:
        return "geen entry", 0.0
    risk = abs(s["entry"] - s["stop"])
    after = df[df.index >= s["entry_hit"]]
    for t, row in after.iterrows():
        long = s["side"] == "LONG"
        if (row["Low"] <= s["stop"]) if long else (row["High"] >= s["stop"]):
            return "stop", -1.0
        if (row["High"] >= s["tp"]) if long else (row["Low"] <= s["tp"]):
            return "TP", s["rr"]
        if t.strftime("%H:%M") >= "16:00" or t.date() != s["entry_hit"].date():
            r = ((row["Close"] - s["entry"]) if long else (s["entry"] - row["Close"])) / risk
            return "dicht 16:00", r
    return "loopt nog", 0.0


def analyse_market(m, period="30d"):
    """Data ophalen en analyseren voor één markt uit CFG["markets"]; setups krijgen de marktnaam mee."""
    df, es = fetch(m["symbol"], period), fetch(m["smt"], period)
    setups, entries = analyse(df, es, dict(CFG, **m["cfg"]))
    for s in setups:
        s.update(mkt=m["name"], dec=m["dec"])
    return df, setups, entries


def alt_offset(m, df):
    """Verschil future - indexprijs op de laatste gezamenlijke candle (None als er geen alt is)."""
    if not m.get("alt"):
        return None
    try:
        alt = fetch(m["alt"]["symbol"], "5d")
    except Exception as ex:
        print(f"{m['alt']['label']}: geen data ({ex})", flush=True)
        return None
    common = df.index.intersection(alt.index)
    if not len(common):
        return None
    return float(df.loc[common[-1], "Close"] - alt.loc[common[-1], "Close"])


def levels(s, m, off, keys=("entry", "stop", "tp")):
    """Prijzen voor in de melding: eerst in US100 (als bekend), daarna de originele."""
    names = {"entry": "Entry", "stop": "Stop", "tp": "TP"}
    own = " | ".join(f"{names[k]} {px(s, s[k])}" for k in keys)
    if off is None:
        return own
    alt = " | ".join(f"{names[k]} {s[k] - off:.{s.get('dec', 2)}f}" for k in keys)
    return f"{m['alt']['label']}: {alt}\n({m['name']}: {own})"


def scan():
    for m in CFG["markets"]:
        print(f"\n===== {m['name']} ({m['symbol']}) =====")
        scan_market(m)


def scan_market(m):
    df, setups, _ = analyse_market(m)
    trade_days = sorted({t.date() for t in df.index if t.weekday() < 5 and in_sess(t, CFG["trade_sess"])})
    weeks = max(len(trade_days) / 5, 1)
    good = [s for s in setups if s["good"]]
    print(f"Data: {df.index[0]:%d-%m %H:%M} t/m {df.index[-1]:%d-%m %H:%M} NY-tijd ({len(df)} candles)")
    print(f"Setups: {len(setups)} totaal (~{len(setups) / weeks:.1f} per week): "
          f"{len(good)} kans ({'/'.join(CFG['kans_sess'])}), {len(setups) - len(good)} lage kans\n")
    totals = {True: [0.0, 0], False: [0.0, 0]}
    per_sess = {}
    by_day = {}
    for s in setups:
        by_day.setdefault(s["time"].date(), []).append(s)
    for d in trade_days:
        day = by_day.get(d, [])
        if not day:
            print(f"{d:%a %d-%m}  geen setup")
            continue
        for s in day:
            res, r = outcome(df, s)
            ps = per_sess.setdefault(sess_name(s["time"]), [0, 0, 0.0, 0])
            ps[0] += 1
            ps[1] += s["good"]
            if res != "geen entry":
                totals[s["good"]][0] += r
                totals[s["good"]][1] += 1
                if s["good"]:
                    ps[2] += r
                    ps[3] += 1
            print(f"{s['time']:%a %d-%m %H:%M}  {setup_text(s)}  -> uitkomst: {res} ({r:+.1f}R)")
            print(f"    {checklist(s)}")
    days_with = sum(1 for d in trade_days if by_day.get(d))
    print(f"\nDagen met minstens 1 setup: {days_with} van {len(trade_days)}")
    for g, label in ((True, "kans"), (False, "lage kans")):
        r, n = totals[g]
        print(f"Resultaat {label}: {r:+.1f}R over {n} trades met entry (zonder kosten/slippage)")
    for name in ("London", "NY AM", "NY PM"):
        n, g, r, e = per_sess.get(name, [0, 0, 0.0, 0])
        print(f"  {name:6}: {n} setups, {g} kans | kans-trades met entry: {e}, {r:+.1f}R")
    print("Let op: veel te weinig trades om iets over de strategie te zeggen.")


def check(sent):
    """Eén keer data ophalen, analyseren en nieuwe meldingen versturen."""
    if not SET["actief"]:
        return
    now = datetime.now(NY)
    recent = now - timedelta(minutes=45)
    setups, last = [], []
    for m in CFG["markets"]:
        try:
            df, m_setups, entries = analyse_market(m)
        except Exception as ex:  # één markt zonder data mag de andere niet blokkeren
            print(f"{m['name']}: fout: {ex}", flush=True)
            continue
        setups += m_setups
        last.append(f"{m['name']} {df.index[-1]:%H:%M}")
        new = [s for s in m_setups if s["time"] >= recent] or [e["setup"] for e in entries if e["time"] >= recent]
        off = alt_offset(m, df) if new else None   # alleen ophalen als er iets te melden is
        for s in m_setups:
            # NQ houdt de oude sleutel zodat eerder verstuurde meldingen niet opnieuw komen
            key = f"setup|{s['time'].isoformat()}|{s['side']}" + ("" if m["name"] == "NQ" else f"|{m['name']}")
            if s["time"] >= recent and key not in sent and SET["alleen_kans"] and not s["good"]:
                sent.add(key)   # lage kans staat uit: wel onthouden, niet melden
            if s["time"] >= recent and key not in sent:
                extra = f" | tegen {CFG['htf_b']}-bias" if against_bias(s) else ""
                title = (f"{m['name']} {s['side']} {s['grade']} ({s['score']}/10)" if s["good"]
                         else f"LAGE KANS: {m['name']} {s['side']} ({s['score']}/10)")
                notify(title, f"{levels(s, m, off)} ({s['rr']:.1f}R){extra}",
                       sound="Glass" if s["good"] else "Pop")
                log(f"{s['time']:%Y-%m-%d %H:%M} {setup_text(s)}\n    {checklist(s)}")
                sent.add(key)
        for e in entries:
            key = f"entry|{e['time'].isoformat()}|{e['setup']['side']}" + ("" if m["name"] == "NQ" else f"|{m['name']}")
            if e["time"] >= recent and key not in sent and (
                    not SET["entry_meldingen"] or (SET["alleen_kans"] and not e["setup"]["good"])):
                sent.add(key)
            if e["time"] >= recent and key not in sent:
                st = e["setup"]
                pre = "" if st["good"] else "LAGE KANS: "
                notify(f"{pre}{m['name']} {st['side']}: prijs in entry-zone", levels(st, m, off, ("entry", "stop")), sound="Hero")
                log(f"{e['time']:%Y-%m-%d %H:%M} {m['name']} {st['side']} prijs in entry-zone ({px(st, st['entry'])})")
                sent.add(key)
    # Einde van de dag zonder setup: dat ook laten weten
    today = [s for s in setups if s["time"].date() == now.date()]
    key = f"summary|{now.date().isoformat()}"
    if (SET["dagmelding"] and CFG["trade_sess"] and now.weekday() < 5 and now.strftime("%H:%M") >= CFG["day_end"]
            and not today and key not in sent):
        notify("TradingStrategie", "Vandaag geen TJR-setup. Geen trade is ook een goede trade.", sound="Pop")
        sent.add(key)
    STATE_FILE.write_text(json.dumps(sorted(sent)))
    print(f"{now:%H:%M:%S} NY | laatste candle {', '.join(last)} | "
          f"vandaag {sum(s['good'] for s in today)} kans, {sum(not s['good'] for s in today)} lage kans", flush=True)


def load_sent():
    return set(json.loads(STATE_FILE.read_text())) if STATE_FILE.exists() else set()


def live(interval=60):
    sent = load_sent()
    nl = ZoneInfo("Europe/Amsterdam")
    def nl_time(hm):
        h, m = map(int, hm.split(":"))
        return datetime.now(NY).replace(hour=h, minute=m).astimezone(nl).strftime("%H:%M")
    windows = " en ".join(f"{nl_time(a)}-{nl_time(b)}" for a, b in CFG["trade_sess"])
    print(f"TradingStrategie draait, zoekt setups van {windows} Nederlandse tijd | stoppen: Ctrl+C")
    notify("TradingStrategie", "Gestart, ik meld TJR-setups op " + " en ".join(m["name"] for m in CFG["markets"]))
    while True:
        try:
            check(sent)
        except Exception as ex:  # netwerk of data even weg: gewoon opnieuw proberen
            print("Fout:", ex, flush=True)
        time.sleep(interval)


def near_window(margin_min=20):
    """True als we in een sessie zitten (of net erna, voor late entries en de dagmelding)."""
    now = datetime.now(NY)
    if now.weekday() >= 5:
        return False
    for a, b in CFG["trade_sess"]:
        end = datetime.strptime(b, "%H:%M") + timedelta(minutes=margin_min)
        if a <= now.strftime("%H:%M") <= end.strftime("%H:%M"):
            return True
    return False


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", action="store_true", help="setups van de afgelopen 30 dagen tonen")
    ap.add_argument("--test-notify", action="store_true", help="testmelding sturen")
    ap.add_argument("--once", action="store_true", help="één keer checken (voor de cloud)")
    args = ap.parse_args()
    if os.environ.get("NTFY_TOPIC"):   # in de cloud komt het onderwerp uit een geheim
        CFG["ntfy_topic"] = os.environ["NTFY_TOPIC"]
    apply_settings()
    if args.once:
        if not SET["actief"]:
            print("Meldingen staan uit (config.json: actief = false).")
        elif not CFG["markets"] or not CFG["trade_sess"]:
            print("Geen markt of sessie aan in config.json, niets te doen.")
        elif near_window():
            check(load_sent())
        else:
            print("Buiten de sessies, niets te doen.")
    elif args.test_notify:
        notify("TJR LONG A (6/10)", "Testmelding | Entry 29800.00 | Stop 29770.00 | TP 29870.00 (2.3R)")
    elif args.scan:
        scan()
    else:
        live()
