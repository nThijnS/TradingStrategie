"""Klassieke strategieën uit het onderzoek (research/protocol.py): Donchian-breakout en time-series momentum
op dagdata, opening-range-breakout (ORB) op 5m. Alleen signalen; de uitkomst komt uit backtesting/engine.py.
Geen van deze strategieën haalde de selectiepoort (rapport/2_onderzoek.md); ze draaien niet live."""
import numpy as np
import pandas as pd

from strategies.base import Signal


def daily_X(d):
    X = pd.DataFrame(dict(o=d["Open"], h=d["High"], l=d["Low"], c=d["Close"]))
    tr = pd.concat([X.h - X.l, (X.h - X.c.shift()).abs(), (X.l - X.c.shift()).abs()], axis=1).max(axis=1)
    X["atr"] = tr.rolling(20).mean()
    return X


def donchian_signals(X, n_in=55, n_out=20, k=2.0):
    """Turtle-achtige breakout: slot boven de hoogste high van n_in dagen = long (onder de laagste = short),
    stop k x ATR20, uitstap bij een slot voorbij het tegenoverliggende n_out-kanaal."""
    hi, lo = X.h.rolling(n_in).max().shift(), X.l.rolling(n_in).min().shift()
    up, dn = (X.c > hi) & (X.c.shift() <= hi.shift()), (X.c < lo) & (X.c.shift() >= lo.shift())
    ex_l, ex_s = X.c < X.l.rolling(n_out).min().shift(), X.c > X.h.rolling(n_out).max().shift()
    return up, dn, k * X.atr, ex_l, ex_s


def tsmom_signals(X, horizons=(21, 63, 252), k=3.0):
    """Time-series momentum: elke maand de richting van de meerderheid van de rendementen over 1, 3 en 12 maanden.
    Stop k x ATR20; uitstap als de richting bij de volgende maandwissel omdraait."""
    vote = sum(np.sign(X.c / X.c.shift(hz) - 1) for hz in horizons)
    month_start = pd.Series(X.index.to_period("M"), index=X.index) != pd.Series(X.index.to_period("M"), index=X.index).shift()
    up, dn = month_start & (vote > 0), month_start & (vote < 0)
    ex_l, ex_s = month_start & (vote <= 0), month_start & (vote >= 0)
    return up, dn, k * X.atr, ex_l, ex_s


def orb_signals(d5, minutes=30, tp=2.0, last_entry="11:30"):
    """Opening-range-breakout op 5m-candles (NY-tijd). Range 09:30 + `minutes`; signaal bij het eerste slot buiten
    de range (uiterlijk last_entry), instap op de open van de candle erna, stop aan de overkant van de range,
    doel tp x R. Geen trade als de range < 0,1% of > 1,5% van de prijs."""
    out = []
    for _, g in d5.groupby(d5.index.date):
        hm = g.index.strftime("%H:%M")
        rng = g[(hm >= "09:30") & (hm < (pd.Timestamp("09:30") + pd.Timedelta(minutes=minutes)).strftime("%H:%M"))]
        if len(rng) < minutes // 5:
            continue
        hi, lo = rng.High.max(), rng.Low.min()
        mid = (hi + lo) / 2
        if not (0.001 <= (hi - lo) / mid <= 0.015):
            continue
        after = g[(hm >= rng.index[-1].strftime("%H:%M")) & (hm < "15:55")].iloc[1:]
        sig = None
        for k, (t, row) in enumerate(after.iterrows()):
            if t.strftime("%H:%M") > last_entry:
                break
            if row.Close > hi or row.Close < lo:
                sig = k
                break
        if sig is None or sig + 1 >= len(after):
            continue
        side = 1 if after.Close.iloc[sig] > hi else -1
        e = after.Open.iloc[sig + 1]
        stop = lo if side > 0 else hi
        risk = (e - stop) * side
        if risk <= 0:
            continue
        out.append(Signal(time=after.index[sig], side=side, entry=float(e), stop=float(stop), tp=float(e + side * tp * risk),
                          order="MARKET", fill_from=after.index[sig + 1]))
    return out
