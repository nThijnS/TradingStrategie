"""DE trade-simulatie van MarketPilot. Alle backtests, het leren, het strategielab, het onderzoek en de
live-status (uitkomst van setups) gebruiken deze ene implementatie.

Regels (gelden voor elke strategie en elk tijdframe):
  Instap    MARKET: tegen de opgegeven prijs op de open van de startcandle (de candle NA het signaal).
            LIMIT:  gevuld in de eerste candle vanaf de startcandle die de limietprijs raakt, tegen de limietprijs
                    (geen prijsverbetering bij een gat: voorzichtig).
  Volgorde  per candle: eerst een gat tussen candles (weekend/beurs dicht: sluiten op de vorige close), dan een
            open voorbij de stop (uitstap op de open), dan de stop, dan een open voorbij het doel, dan het doel.
            Stop en doel in dezelfde candle: stop eerst (voorzichtig).
  Vulcandle bij een limietorder is onbekend of het doel vóór of na de vulling werd geraakt. Standaard telt een
            doel in de vulcandle daarom NIET (tp_on_fill_bar=False); de stop wel.
  Tijd      een trade mag open blijven tot de deadline (max_bars candles, max_hours uur, of uiterlijk close_at
            op de dag van de instap) en sluit op de close van de laatste candle die vóór of op de deadline eindigt.
  Data op   loopt de data op terwijl de trade nog open is, dan is reason "open" (exit = laatste close).
  Kosten    netto R = bruto R - (prijskosten + fractie x instapprijs) / risico - financiering - slippage (in R).
            Financiering: rente/365 per rollover (17:00 NY ≈ 22:00 UTC) x positiewaarde / risico.
"""
from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Costs:
    price: float = 0.0          # spread + commissie (+ slippage) per rondgang, in prijspunten
    frac: float = 0.0           # spread + commissie per rondgang, als deel van de instapprijs
    slippage_r: float = 0.0     # extra slippage per trade, in R
    financing: float = 0.0      # rente per jaar over de positiewaarde, per nacht (rollover) aangerekend
    rollover_hour_utc: int = 22

    def trade_cost_r(self, entry, risk, mult=1.0):
        return mult * (self.price + self.frac * entry) / risk

    def financing_r(self, entry, risk, nights):
        return self.financing / 365 * nights * entry / risk if self.financing else 0.0


@dataclass(frozen=True)
class Exits:
    max_bars: Optional[int] = None        # hoogstens zoveel candles in de trade (de instapcandle telt mee)
    max_hours: Optional[float] = None     # hoogstens zoveel uur na de start van de instapcandle
    close_at: Optional[str] = None        # "16:00": uiterlijk dan dicht, op de dag van de instap (tijd van de index)
    gap_hours: Optional[float] = None     # gat tussen twee candles groter dan dit: sluiten op de vorige close
    tp_on_fill_bar: bool = False          # zie de modulekop
    be_at: Optional[float] = None         # stop naar de instap zodra de trade zoveel R in de plus heeft gestaan


@dataclass
class Trade:
    side: int
    entry_time: pd.Timestamp
    entry: float
    stop: float
    tp: Optional[float]
    exit_time: pd.Timestamp
    exit: float
    reason: str             # "stop", "tp", "time", "gap", "signal" of "open" (data op, trade loopt nog)
    bars: int               # aantal candles in de trade
    risk: float
    gross_r: float
    cost_r: float
    fin_r: float
    slip_r: float
    nights: int
    entry_i: int
    exit_i: int

    @property
    def net_r(self):
        return self.gross_r - self.cost_r - self.fin_r - self.slip_r

    @property
    def minutes(self):
        return (self.exit_time - self.entry_time).total_seconds() / 60

    def to_dict(self):
        d = asdict(self)
        d["net_r"] = self.net_r
        return d


class Bars:
    """OHLC als numpy-arrays (snel), uit een DataFrame met Open/High/Low/Close of o/h/l/c."""

    def __init__(self, df, bar=None):
        cols = ("Open", "High", "Low", "Close") if "Open" in df else ("o", "h", "l", "c")
        self.o, self.h, self.l, self.c = (df[k].to_numpy(dtype=float) for k in cols)
        self.t = df.index
        self.n = len(df)
        if bar is None:
            d = np.diff(self.t[:200].asi8) if self.n > 1 else np.array([60_000_000_000])
            bar = pd.Timedelta(int(np.median(d)), "ns")
        self.bar = pd.Timedelta(bar)

    def index_at(self, ts):
        """Eerste candle die op of na `ts` begint."""
        return int(self.t.searchsorted(ts, side="left"))


def rollovers(a, b, hour_utc=22):
    """Hoe vaak de trade over het dagelijkse rollmoment (17:00 NY ≈ 22:00 UTC) heen ging: dan betaal je financiering."""
    if b <= a:
        return 0
    first = a.normalize() + pd.Timedelta(hours=hour_utc)
    if first <= a:
        first += pd.Timedelta(days=1)
    return 0 if b < first else int((b - first) / pd.Timedelta(days=1)) + 1


def _last_allowed(B, kf, exits):
    """Index van de laatste candle die nog in de trade mag zitten (n of meer = geen limiet binnen de data)."""
    last = B.n + 10**9
    if exits.max_bars is not None:
        last = min(last, kf + exits.max_bars - 1)
    deadlines = []
    t0 = B.t[kf]
    if exits.max_hours is not None:
        deadlines.append(t0 + pd.Timedelta(hours=exits.max_hours))
    if exits.close_at is not None:
        hh, mm = map(int, exits.close_at.split(":"))
        deadlines.append(t0.normalize() + pd.Timedelta(hours=hh, minutes=mm))
    for dl in deadlines:
        # laatste candle met start + lengte <= deadline; als de vulling al later valt: de vulcandle zelf.
        # Ligt de deadline voorbij de data, dan is nog niet bekend hoe de trade afloopt (reason "open").
        pos = int(B.t.searchsorted(dl - B.bar, side="right"))
        if pos >= B.n:
            continue
        last = min(last, max(pos - 1, kf))
    return last


def simulate(B, side, entry, stop, tp, start_i, order="LIMIT", exits=Exits(), costs=Costs(),
             fill_until_i=None, exit_long=None, exit_short=None):
    """Simuleer één trade op candles B (Bars). Geeft een Trade, of None als een limietorder niet gevuld werd
    of het risico niet positief is."""
    o, h, l, c, t, n = B.o, B.h, B.l, B.c, B.t, B.n
    risk = (entry - stop) * side
    if risk <= 0 or start_i >= n:
        return None
    long = side > 0
    if order == "MARKET":
        kf = start_i
    else:
        end = n if fill_until_i is None else min(n, fill_until_i + 1)
        lows, highs = (l[start_i:end], None) if long else (None, h[start_i:end])
        hit = np.flatnonzero(lows <= entry) if long else np.flatnonzero(highs >= entry)
        if not len(hit):
            return None
        kf = start_i + int(hit[0])
    last = _last_allowed(B, kf, exits)
    ex = exit_long if long else exit_short
    cur_stop = stop
    exit_p, exit_k, reason = None, None, None
    k = kf
    while k < n:
        later = k > kf or order == "MARKET"
        if k > kf and exits.gap_hours is not None and (t[k] - t[k - 1]) > pd.Timedelta(hours=exits.gap_hours):
            exit_p, exit_k, reason = c[k - 1], k - 1, "gap"
            break
        if later and ((long and o[k] <= cur_stop) or (not long and o[k] >= cur_stop)):
            exit_p, exit_k, reason = o[k], k, "stop"
            break
        if (long and l[k] <= cur_stop) or (not long and h[k] >= cur_stop):
            exit_p, exit_k, reason = cur_stop, k, "stop"
            break
        if tp is not None:
            if later and ((long and o[k] >= tp) or (not long and o[k] <= tp)):
                exit_p, exit_k, reason = o[k], k, "tp"
                break
            if (later or exits.tp_on_fill_bar) and ((long and h[k] >= tp) or (not long and l[k] <= tp)):
                exit_p, exit_k, reason = tp, k, "tp"
                break
        if ex is not None and ex[k] and k + 1 < n:
            exit_p, exit_k, reason = o[k + 1], k + 1, "signal"
            break
        if exits.be_at is not None:
            fav = (h[k] - entry) / risk if long else (entry - l[k]) / risk
            if fav >= exits.be_at:
                cur_stop = entry
        if k >= last:
            exit_p, exit_k, reason = c[k], k, "time"
            break
        k += 1
    if exit_p is None:
        exit_p, exit_k, reason = c[n - 1], n - 1, "open"
    gross = (exit_p - entry) * side / risk
    nights = rollovers(t[kf], t[exit_k], costs.rollover_hour_utc) if costs.financing else 0
    return Trade(side=side, entry_time=t[kf], entry=float(entry), stop=float(stop), tp=None if tp is None else float(tp),
                 exit_time=t[exit_k], exit=float(exit_p), reason=reason, bars=exit_k - kf + 1, risk=float(risk),
                 gross_r=float(gross), cost_r=float(costs.trade_cost_r(entry, risk)),
                 fin_r=float(costs.financing_r(entry, risk, nights)), slip_r=float(costs.slippage_r),
                 nights=nights, entry_i=kf, exit_i=exit_k)


def simulate_signal(B, sig, exits=Exits(), costs=Costs(), **kw):
    """Een strategies.base.Signal simuleren. LIMIT: vullen vanaf sig.fill_from (of sig.time);
    MARKET: instap op de eerste candle vanaf sig.fill_from (of sig.time)."""
    start = B.index_at(sig.fill_from if sig.fill_from is not None else sig.time)
    return simulate(B, sig.side, sig.entry, sig.stop, sig.tp, start, sig.order, exits, costs, **kw)
