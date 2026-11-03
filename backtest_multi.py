#!/usr/bin/env python3
"""Doorverwijzing: de backtest op meerdere markten staat nu in research/histdata_ict.py (multi, data/trades_multi.pkl).
Deze naam blijft bestaan voor oude aanroepen en de scripts in research/archief/."""
import sys

from research import histdata_ict as _impl

if __name__ == "__main__":
    _impl.multi()
else:
    sys.modules[__name__] = _impl
