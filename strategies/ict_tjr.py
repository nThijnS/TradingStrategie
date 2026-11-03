"""De ICT/TJR-strategie: sweep van liquiditeit -> MSS met displacement -> FVG, in de handelssessies.

Zelfde logica als tjr_alerts.pine. De score telt: 4H bias, 1H bias, premium/discount, OTE, HTF FVG, SMT,
Silver Bullet, sterke displacement, IFVG en draw on liquidity >= 2R.

Deze module bevat alleen de detectie. Ze is bij de refactor van november 2026 ongewijzigd overgenomen uit
tradingstrategie.py; tests/test_golden.py bewijst dat de setups exact gelijk zijn aan die van de oude code.
Uitkomsten (stop/TP) worden niet hier, maar in backtesting/engine.py gesimuleerd.
"""
from datetime import timedelta

import pandas as pd

from core.config import CFG
from core.sessions import in_sess, sess_name

BAR = timedelta(minutes=5)


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


def analyse(df, es, cfg=CFG, refusals=None):
    """Loopt alle 5m-candles af en geeft een lijst setups en entry-zone events terug.
    refusals: lijst waar elke sweep die geen trade werd in komt, met de reden (voor het logboek)."""
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

            def refuse(reason, s=s, d=d):
                if refusals is not None:
                    refusals.append(dict(time=t, side=d.upper(), reason=reason, sweep=s.get("sweep_name"),
                                         sweep_t=s.get("sweep_t"), bias_a=aBias, bias_b=bBias))

            if sweep and in_trade and s["state"] <= 1 and not (can_setup and ok_dir) and refusals is not None:
                refusals.append(dict(time=t, side=d.upper(), sweep=sweep[0], sweep_t=t, bias_a=aBias, bias_b=bBias,
                                     reason="max setups per dag" if not can_setup else f"tegen {cfg['htf_b']}-bias"))

            if sweep and can_setup and ok_dir and s["state"] <= 1:
                if s["state"] == 0:
                    s.update(ext=L[i] if up else H[i], leg=H[i] if up else L[i],
                             fT=None, fB=None, smt=False, sweep_name=sweep[0], sweep_t=t, lvl=lv_map[sweep[0]])
                s["state"], s["bar"] = 1, i

            if s["state"] in (1, 2) and cfg["no_close"] and (C[i] < s["lvl"] if up else C[i] > s["lvl"]):
                refuse("candle sloot voorbij het niveau")
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
                    refuse("geen MSS met displacement" if in_trade else "geen MSS voor einde sessie")
                    s["state"] = 0
                elif up and swingH is not None and C[i] > swingH and bullDisp:
                    s.update(state=2, mss=i, strong=strong,
                             ifvg=lastBearFvgTop is not None and C[i] > lastBearFvgTop and i - lastBearFvgBar <= cfg["mss_window"])
                elif not up and swingL is not None and C[i] < swingL and bearDisp:
                    s.update(state=2, mss=i, strong=strong,
                             ifvg=lastBullFvgBot is not None and C[i] < lastBullFvgBot and i - lastBullFvgBar <= cfg["mss_window"])

            if s["state"] == 2:
                if not ok_dir:   # HTF-bias is intussen gedraaid: setup vervalt
                    refuse(f"{cfg['htf_b']}-bias gedraaid na de MSS")
                    s["state"] = 0
                elif s["fT"] is not None and cfg["need_smt"] and not s["smt"]:
                    refuse("geen SMT-divergentie")
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
                        refuse("stop aan de verkeerde kant van de entry")
                        s["state"] = 0
                elif i - s["mss"] > cfg["fvg_window"] or not in_trade:
                    refuse("geen FVG na de MSS")
                    s["state"] = 0

            if s["state"] == 3 and i > s["sig"]:
                st = s["setup"]
                hit = L[i] <= st["entry"] if up else H[i] >= st["entry"]
                if hit:
                    st["entry_hit"] = t
                    entries.append(dict(time=t, setup=st))
                    s["state"] = 0
                elif i - s["sig"] > cfg["entry_win"] or (C[i] < st["stop"] if up else C[i] > st["stop"]):
                    st["missed"] = "entry niet op tijd geraakt" if i - s["sig"] > cfg["entry_win"] else "stop geraakt voor de entry"
                    s["state"] = 0

    return setups, entries


# ------------- Doel en signalen voor de gemeenschappelijke interface -------------
def target_price(s, target, fallback_r=None):
    """TP-prijs van een setup voor een gekozen doel.
    target: getal = vaste R; "DOL" = de liquiditeit, en zonder liquiditeit fallback_r (zoals de app: cfg["tp_r"])."""
    long = s["side"] == "LONG"
    risk = abs(s["entry"] - s["stop"])
    if target == "DOL":
        if s.get("dol") is not None:
            return s["dol"]
        r = CFG["tp_r"] if fallback_r is None else fallback_r
    else:
        r = float(target)
    return s["entry"] + r * risk if long else s["entry"] - r * risk


class ICTStrategy:
    """ICT/TJR via de gemeenschappelijke strategie-interface (strategies.base.Strategy)."""
    name = "ict"

    def __init__(self, cfg=None):
        self.cfg = dict(CFG, **(cfg or {}))

    def setups(self, df, smt, refusals=None):
        return analyse(df, smt, self.cfg, refusals)[0]

    def signals(self, df, smt, target=None):
        from strategies.base import Signal
        out = []
        for s in self.setups(df, smt):
            tp = s["tp"] if target is None else target_price(s, target, self.cfg["tp_r"])
            out.append(Signal(time=s["time"], side=1 if s["side"] == "LONG" else -1, entry=s["entry"], stop=s["stop"],
                              tp=tp, order="LIMIT", fill_from=s["entry_hit"], meta=s))
        return out
