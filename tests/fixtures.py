"""Vaste, synthetische marktdata voor de tests (geen netwerk, geen HistData nodig).

RandomState in plaats van default_rng: de getallenreeks van RandomState is in NumPy bevroren, dus de data
is op elke machine en elke NumPy-versie gelijk. Daardoor kunnen de golden-tests exacte uitkomsten vergelijken.
"""
import numpy as np
import pandas as pd

NY = "America/New_York"


def minute_bars(days=45, seed=7, start="2026-03-02", price=20000.0, vol=0.00045, corr=0.85):
    """1m-candles voor een markt en een gecorreleerde partner (voor SMT), CME-uren: 18:00 tot 17:00 NY.
    Volatiliteit wisselt per dag en is hoger rond de open van London en New York, zodat er sweeps en
    displacement-candles ontstaan."""
    rs = np.random.RandomState(seed)
    sessions = []
    day = pd.Timestamp(start)
    while len(sessions) < days:
        if day.weekday() < 5:
            sessions.append(pd.date_range(day - pd.Timedelta(hours=6), day + pd.Timedelta(hours=17), freq="1min",
                                          inclusive="left", tz=None))
        day += pd.Timedelta(days=1)
    idx = pd.DatetimeIndex(np.concatenate([s.values for s in sessions])).tz_localize(NY, ambiguous="NaT",
                                                                                    nonexistent="NaT")
    idx = idx[idx.notna()]
    idx = idx[~idx.duplicated()]
    n = len(idx)
    hm = idx.hour + idx.minute / 60
    boost = 1 + 1.5 * ((hm >= 9.5) & (hm < 11.5)) + 0.8 * ((hm >= 2) & (hm < 5))
    day_vol = pd.Series(rs.lognormal(0, 0.35, size=2 * len(sessions) + 10))
    dv = day_vol.iloc[pd.factorize(pd.Series(idx.date))[0]].to_numpy()
    z1, z2 = rs.standard_normal(n), rs.standard_normal(n)
    jumps = rs.binomial(1, 0.004, n) * rs.standard_normal(n) * 6
    r1 = vol * dv * boost * (z1 + jumps)
    r2 = vol * dv * boost * (corr * z1 + np.sqrt(1 - corr ** 2) * z2 + jumps * corr)
    out = []
    for r, p0 in ((r1, price), (r2, price / 3.6)):
        close = p0 * np.exp(np.cumsum(r))
        open_ = np.concatenate([[p0], close[:-1]])
        wick = np.abs(rs.standard_normal((2, n))) * vol * 0.6 * dv * boost * close
        high = np.maximum(open_, close) + wick[0]
        low = np.minimum(open_, close) - wick[1]
        out.append(pd.DataFrame(dict(Open=open_, High=high, Low=low, Close=close), index=idx))
    return out[0], out[1]


def to5(m1):
    return m1.resample("5min", label="left", closed="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()


def hourly_bars(n=4000, seed=11, start="2024-01-01", price=100.0):
    """1h-candles (UTC) met afwisselend trend- en zijwaartse stukken, voor de lab-strategieën."""
    rs = np.random.RandomState(seed)
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    regime = np.repeat(rs.choice([-1.0, 0.0, 1.0], size=n // 200 + 1), 200)[:n]
    r = 0.004 * rs.standard_normal(n) + 0.0006 * regime
    close = price * np.exp(np.cumsum(r))
    open_ = np.concatenate([[price], close[:-1]]) * (1 + 0.0005 * rs.standard_normal(n))
    wick = np.abs(rs.standard_normal((2, n))) * 0.002 * close
    return pd.DataFrame(dict(Open=open_, High=np.maximum(open_, close) + wick[0],
                             Low=np.minimum(open_, close) - wick[1], Close=close), index=idx)
