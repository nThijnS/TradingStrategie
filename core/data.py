"""Marktdata: Yahoo Finance (live), HistData.com (backtests), opschonen en resamplen.

HistData-tijden zijn NY-lokale tijd MET zomertijd (gecontroleerd op 29 oktober 2026: het nieuws van 08:30 ET staat
in juni/augustus ook op 08:30). De oude lader las ze als EST zonder zomertijd (Etc/GMT+5), waardoor alles van half
maart tot begin november 1 uur verschoof. load_histdata() is de correcte lader; load_histdata_est() bestaat alleen
om oude onderzoeksresultaten te kunnen reproduceren.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd

from core.sessions import NY
from storage import paths

OHLC = ["Open", "High", "Low", "Close"]
AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
BAR5 = timedelta(minutes=5)


# ------------- Yahoo Finance -------------
def fetch(symbol, period="30d", interval="5m"):
    """Eén symbool, NY-tijd, zonder de laatste candle als die nog niet gesloten is (geen repaint/look-ahead)."""
    import yfinance as yf
    df = yf.download(symbol, interval=interval, period=period, progress=False, auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"Geen data voor {symbol}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[OHLC].dropna()
    df.index = df.index.tz_convert(NY)
    bar = pd.Timedelta(interval.replace("m", "min")) if interval.endswith("m") else pd.Timedelta(interval)
    if df.index[-1] + bar > datetime.now(timezone.utc):
        df = df.iloc[:-1]
    return df


def fetch_all(markets, interval="1h", period="730d"):
    """Meerdere markten in één verzoek (lab/onderzoek). markets: dicts met "naam" en "symbool"."""
    import yfinance as yf
    syms = [m["symbool"] for m in markets]
    raw = yf.download(syms, interval=interval, period=period, group_by="ticker", auto_adjust=False,
                      progress=False, threads=True)
    out = {}
    for m in markets:
        try:
            df = raw[m["symbool"]] if isinstance(raw.columns, pd.MultiIndex) else raw
            out[m["naam"]] = df[OHLC].copy()
        except KeyError:
            out[m["naam"]] = pd.DataFrame(columns=OHLC)
    return out


# ------------- Datakwaliteit -------------
def clean(df):
    """Datakwaliteit: dubbele, lege en onmogelijke candles eruit, en tellen wat er mis was."""
    df = df.dropna(how="all")    # lege rijen ontstaan doordat markten met verschillende uren samen worden opgehaald
    q = dict(ruw=len(df))
    if len(df) and df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    dup = df.index.duplicated(keep="last")
    df = df[~dup]
    nan = df.isna().any(axis=1)
    df = df[~nan]
    bad = (df[OHLC] <= 0).any(axis=1) | (df["High"] < df["Low"]) | \
          (df["High"] < df[["Open", "Close"]].max(axis=1) - 1e-12) | (df["Low"] > df[["Open", "Close"]].min(axis=1) + 1e-12)
    df = df[~bad].sort_index()
    q.update(dubbel=int(dup.sum()), leeg=int(nan.sum()), ongeldig=int(bad.sum()), candles=len(df),
             van=df.index[0].isoformat() if len(df) else None, tot=df.index[-1].isoformat() if len(df) else None)
    return df, q


def check_ohlc(df):
    """Lijst met problemen in een OHLC-reeks (leeg = in orde). Gebruikt door tests en de data-lader."""
    probs = []
    if not df.index.is_monotonic_increasing:
        probs.append("tijden niet oplopend")
    if df.index.duplicated().any():
        probs.append(f"{int(df.index.duplicated().sum())} dubbele tijden")
    if df.index.tz is None:
        probs.append("tijden zonder tijdzone")
    if df[OHLC].isna().any().any():
        probs.append("lege waarden")
    if ((df["High"] < df[["Open", "Close"]].max(axis=1) - 1e-12) | (df["Low"] > df[["Open", "Close"]].min(axis=1) + 1e-12)).any():
        probs.append("high/low niet om open/close heen")
    return probs


# ------------- Resamplen -------------
def resample(df, rule):
    """Candles samenvoegen. 4H-candles van CME starten om 18:00 NY (offset 2 uur)."""
    offset = "2h" if rule == "4h" else None
    return df.resample(rule, offset=offset, label="left", closed="left").agg(AGG).dropna()


def to5(m1):
    return m1.resample("5min", label="left", closed="left").agg(AGG).dropna()


# ------------- HistData.com (lokaal, data/raw, git-ignored) -------------
def _read_raw(sym):
    files = sorted(paths.HISTDATA_RAW.glob(f"DAT_ASCII_{sym}_M1_*.csv"))
    if not files:
        raise FileNotFoundError(f"geen HistData voor {sym} in {paths.HISTDATA_RAW}")
    d = pd.concat(pd.read_csv(f, sep=";", header=None, names=["t", "Open", "High", "Low", "Close", "V"]) for f in files)
    d.index = pd.to_datetime(d["t"], format="%Y%m%d %H%M%S")
    return d[OHLC]


def load_histdata_est(sym):
    """OUDE lader (tijden als EST zonder zomertijd). Alleen voor het reproduceren van oude resultaten."""
    pq = paths.DATA / f"{sym}_m1.pkl"
    if pq.exists():
        return pd.read_pickle(pq)
    d = _read_raw(sym)
    d.index = d.index.tz_localize("Etc/GMT+5").tz_convert(NY)
    d = d.sort_index()
    d = d[~d.index.duplicated()]
    d.to_pickle(pq)
    return d


def load_histdata(sym):
    """1m-candles van HistData in NY-tijd, zomertijd-correct. Cache: data/<sym>_m1_dst.pkl
    (zelfde bestand en zelfde uitkomst als de eerdere tp_videos.load_dst)."""
    pq = paths.DATA / f"{sym}_m1_dst.pkl"
    if pq.exists():
        return pd.read_pickle(pq)
    d = load_histdata_est(sym)
    raw = d.index.tz_convert("Etc/GMT+5").tz_localize(None)     # terug naar de tijden uit het bestand
    idx = raw.tz_localize(NY, ambiguous="NaT", nonexistent="NaT")
    d = d.set_axis(idx)
    d = d[d.index.notna()]
    d = d[~d.index.duplicated()].sort_index()
    d.to_pickle(pq)
    return d
