#!/usr/bin/env python3
"""
ARCHIEF (bevroren, november 2026): afgerond onderzoek; draait niet in de cloud. Bij de refactor zijn alleen de
imports aangepast. Backtests via backtest.simulate gebruiken nu de centrale engine (kleine verschillen met de
oorspronkelijke cijfers: zie docs/refactor/3_engine_vergelijking.md).

Hulpbestand bij het onderzoek naar het TradingPool-model (video's van @TradingPool naast de data).

Belangrijk: de HistData-tijden blijken NY-lokale tijd MET zomertijd te zijn (nieuws van 8:30 ET staat
in de zomer op 08:30 in de bestanden). backtest.load_m1 leest ze als EST zonder zomertijd, waardoor alles
van half maart tot begin november 1 uur te laat staat. load_dst() corrigeert dat (zonder backtest.py te wijzigen).
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))   # repo-root (archief)


from core.data import load_histdata as load_dst  # noqa: E402,F401  (de lader staat nu in core/data.py)


if __name__ == "__main__":
    g, e = load_dst("XAUUSD"), load_dst("EURUSD")
    for d in ["2025-07-15", "2026-07-02"]:
        w = e.tz_convert("UTC").loc[f"{d} 11:00":f"{d} 15:00"]
        print(d, "grootste EURUSD-candle (UTC):", (w.High - w.Low).idxmax())
