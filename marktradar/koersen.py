"""Koersen voor Scout en Charts: 1-uurs candles van Yahoo, alleen afgesloten candles tot het peilmoment.

Eigen download omdat core.data alleen OHLC bewaart en de Scout ook volume nodig heeft. Opschonen gebeurt met de
bestaande strategies.lab.clean.
"""
import pandas as pd

from core.markets import LAB_MARKETS
from strategies import lab

UUR = pd.Timedelta(hours=1)
KOLOMMEN = ["Open", "High", "Low", "Close", "Volume"]


def download(markten=LAB_MARKETS, period="730d"):
    import yfinance as yf
    ruw = yf.download([m["symbool"] for m in markten], interval="1h", period=period, group_by="ticker", auto_adjust=False,
                      progress=False, threads=True)
    uit = {}
    for m in markten:
        try:
            uit[m["naam"]] = ruw[m["symbool"]][KOLOMMEN].copy()
        except KeyError:
            uit[m["naam"]] = pd.DataFrame(columns=KOLOMMEN)
    return uit


def afgesloten(df, peil):
    """Een candle telt pas als hij op het peilmoment gesloten is."""
    return df[df.index + UUR <= pd.Timestamp(peil)]


def opschonen(ruw, peil):
    """Geeft {markt: candles in UTC} en een lijst van markten zonder bruikbare data."""
    koersen, fouten = {}, []
    for naam, df in ruw.items():
        df = df.dropna(subset=["Open", "High", "Low", "Close"], how="all")
        if not len(df):
            fouten.append(f"{naam}: geen koersen")
            continue
        df = df.assign(Volume=df["Volume"].fillna(0))
        schoon, _ = lab.clean(df)
        schoon = afgesloten(schoon.tz_convert("UTC"), peil)
        if len(schoon):
            koersen[naam] = schoon
        else:
            fouten.append(f"{naam}: geen afgesloten candles")
    return koersen, fouten


def einde(df):
    """Het moment waarop de laatste candle sloot."""
    return df.index[-1] + UUR


def isotijd(t):
    return pd.Timestamp(t).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def bron(markt, df):
    """Bronverwijzing voor een bevinding op deze koersreeks."""
    symbool = next(m["symbool"] for m in LAB_MARKETS if m["naam"] == markt)
    return dict(naam=f"Yahoo Finance 1h {symbool}", url=f"https://finance.yahoo.com/quote/{symbool}", tijdstip=isotijd(einde(df)))
