"""Gemeenschappelijke strategie-interface.

Een strategie zet marktdata om in signalen. Wat er daarna met een signaal gebeurt (vulling, stop, doel,
tijdsluiting, kosten) bepaalt uitsluitend backtesting/engine.py, voor elke strategie op dezelfde manier.
"""
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd


@dataclass
class Signal:
    time: pd.Timestamp                 # moment waarop het signaal bekend is (sluiting van de signaalcandle)
    side: int                          # +1 long, -1 short
    entry: float                       # limietprijs (LIMIT) of verwachte instapprijs (MARKET: open van de volgende candle)
    stop: float
    tp: Optional[float]                # None = geen vast doel (uitstap via tijd of een uitstapsignaal)
    order: str = "LIMIT"               # "LIMIT" of "MARKET"
    fill_from: Optional[pd.Timestamp] = None   # vanaf deze candle mag de order gevuld worden (standaard: time)
    meta: dict = field(default_factory=dict)


class Strategy:
    """Basis voor strategieën. Een strategie implementeert signals(); de engine doet de rest."""
    name: str = "strategie"

    def signals(self, *data: Any, **params: Any):
        raise NotImplementedError
