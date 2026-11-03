"""ICT-setups (strategies/ict_tjr.py) door de centrale engine halen. Eén plek voor de app, het logboek,
de live-status, het leren en de HistData-backtests.

Tijdsluiting per gebruik (dit zijn regels van de strategie, geen simulatiekeuzes):
  LIVE_EXITS   app, logboek en live-status: uiterlijk 16:00 NY dicht (daytrade)
  LEARN_EXITS  leren en HistData-backtests: hoogstens 5 uur in de trade (zoals alle eerdere backtests en leren.py)
"""
from backtesting import engine
from strategies.ict_tjr import BAR, target_price

LIVE_EXITS = engine.Exits(close_at="16:00")
LEARN_EXITS = engine.Exits(max_hours=5)
REASON_NL = {"stop": "stop", "tp": "TP", "time": "dicht 16:00", "open": "loopt nog", "gap": "dicht 16:00", "signal": "dicht 16:00"}


def bars(df):
    return df if isinstance(df, engine.Bars) else engine.Bars(df)


def trade(df, s, target=None, exits=LEARN_EXITS, costs=engine.Costs(), fallback_r=None):
    """Simuleer een setup. target None = het TP van de setup zelf; anders een vast R-getal of "DOL" (met de
    terugval van de app, cfg["tp_r"]). Geeft een engine.Trade of None (geen entry)."""
    if s.get("entry_hit") is None:
        return None
    B = bars(df)
    tp = s["tp"] if target is None else target_price(s, target, fallback_r)
    start = B.index_at(s["entry_hit"])
    until = B.index_at(s["entry_hit"] + BAR) - 1          # de vulling zit in de 5m-candle van entry_hit
    side = 1 if s["side"] == "LONG" else -1
    return engine.simulate(B, side, s["entry"], s["stop"], tp, start, "LIMIT", exits, costs, fill_until_i=until)


def outcome(df, s):
    """Uitkomst voor de app, het logboek en de live-status (zonder kosten): (uitkomst, R)."""
    tr = trade(df, s, exits=LIVE_EXITS)
    if tr is None:
        return "geen entry", 0.0
    if tr.reason == "open":
        return "loopt nog", 0.0
    return REASON_NL[tr.reason], tr.gross_r

