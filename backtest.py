#!/usr/bin/env python3
"""Doorverwijzing: de ICT-backtest op HistData staat nu in research/histdata_ict.py (zelfde uitvoer, data/trades.pkl).
Deze naam blijft bestaan voor oude aanroepen en de scripts in research/archief/."""
import sys

from research import histdata_ict as _impl

if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
