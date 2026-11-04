"""
Risicologica voor orderuitvoering: instrument- en koerscontroles, orderniveaus, positiegrootte en limieten.

Alleen rekenwerk, geen netwerk: broker.py haalt de gegevens op en vraagt hier of een order mag.
Elke controle geeft een reden terug als het NIET mag; None betekent "in orde". Getest in tests/test_risico.py.

Uitgangspunten (fail closed):
- Ontbrekende of onbekende instrumentgegevens = geen order. Contractgrootte (lotSize) en scalingFactor moeten 1
  zijn; anders weten we niet zeker wat 1 unit per punt waard is.
- Risico wordt gemeten vanaf de HUIDIGE prijs tot de stop, inclusief een kostenbuffer (spread + slippage), en
  omgerekend naar de accountvaluta. Een open positie zonder stop blokkeert alle nieuwe orders.
- Gelijktijdige signalen worden één voor één beoordeeld; elk goedgekeurd signaal telt mee voor het volgende.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# Markten die samen in feite één weddenschap zijn. Per groep max `max_per_groep` posities in dezelfde richting.
# Bij USD-forex telt de richting van de dollar: EURUSD long = dollar short, USDJPY long = dollar long.
CORR_GROUPS = {
    "Amerikaanse aandelen/indices": {"NQ", "ES", "US30", "AAPL", "NVDA", "MSFT"},
    "Europese indices": {"DAX", "FTSE", "CAC"},
    "Edelmetalen": {"GOUD", "ZILVER"},
    "Energie": {"OLIE", "BRENT", "GAS"},
    "Crypto": {"BTC", "ETH", "SOL"},
    "Dollar (forex)": {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDJPY", "USDCAD", "USDCHF"},
}


@dataclass
class Instrument:
    markt: str
    epic: str
    ccy: str                      # valuta waarin de winst/verlies van dit instrument wordt uitgedrukt
    lot_size: float
    scaling: float
    min_size: float
    max_size: Optional[float]
    step: float                   # kleinste stap in ordergrootte
    decimals: int                 # prijsdecimalen
    min_stop: float               # minimale stop/doel-afstand, in prijs
    max_stop: Optional[float]
    bid: float
    ask: float
    status: str                   # "TRADEABLE" = open
    quote_time: Optional[datetime] = None


@dataclass
class Limits:
    risico_pct: float = 0.5           # risico per trade, % van de accountwaarde
    max_open_risico_pct: float = 1.5  # alle open trades samen, % van de accountwaarde
    dagverlies_pct: float = 3.0
    totaalverlies_pct: float = 5.0
    trailing: bool = True             # totaalgrens schuift mee met de hoogste accountwaarde
    max_open: int = 3                 # posities + wachtende orders
    max_per_groep: int = 1            # per gecorreleerde groep, zelfde richting
    hefboom: float = 30.0
    max_spread_r: float = 0.25        # spread hoogstens dit deel van de stopafstand
    slippage_r: float = 0.05          # extra kostenbuffer in de positiegrootte, als deel van de stopafstand
    max_drift_r: float = 0.30         # marktorder: prijs mag hoogstens zoveel R van het signaal weg zijn
    max_koers_leeftijd_s: int = 180   # brokerkoers ouder dan dit = verouderd
    min_rr: float = 0.0               # 0 = uit: het doel komt uit de data (leren.py / strategielab kiezen per markt)

    @classmethod
    def from_config(cls, d):
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)

    def problems(self, live=False):
        """Onzinnige of te ruime limieten. Live is strenger dan demo."""
        p = []
        caps = dict(risico_pct=1.0 if live else 2.0, max_open_risico_pct=3.0 if live else 6.0,
                    dagverlies_pct=5.0 if live else 10.0, totaalverlies_pct=10.0 if live else 20.0)
        for k, cap in caps.items():
            v = getattr(self, k)
            if not (isinstance(v, (int, float)) and 0 < v <= cap):
                p.append(f"{k}={v!r} moet tussen 0 en {cap:g} liggen")
        if self.max_open_risico_pct < self.risico_pct:
            p.append("max_open_risico_pct is kleiner dan risico_pct")
        if self.max_open_risico_pct >= self.dagverlies_pct:
            p.append("max_open_risico_pct moet kleiner zijn dan dagverlies_pct (anders kan één slechte ronde de daglimiet breken)")
        for k in ("max_open", "max_per_groep"):
            v = getattr(self, k)
            if not (isinstance(v, int) and 1 <= v <= (5 if live else 10)):
                p.append(f"{k}={v!r} ongeldig")
        if not (0 < self.hefboom <= 30):
            p.append("hefboom moet tussen 0 en 30 liggen")
        if not (0 <= self.min_rr <= 5):
            p.append("min_rr moet tussen 0 (uit) en 5 liggen")
        for k in ("max_spread_r", "slippage_r", "max_drift_r"):
            if not (0 <= getattr(self, k) <= 1):
                p.append(f"{k} moet tussen 0 en 1 liggen")
        return p


# ------------- Instrument en koers -------------
def check_instrument(inst: Instrument):
    if inst.lot_size != 1 or inst.scaling != 1:
        return f"contractgrootte niet geverifieerd (lotSize {inst.lot_size}, scalingFactor {inst.scaling})"
    if not (inst.min_size > 0 and inst.step > 0) or inst.decimals is None or inst.decimals < 0:
        return "ordergrootte of prijsdecimalen onbekend"
    if not inst.ccy:
        return "valuta van het instrument onbekend"
    return None


def check_quote(inst: Instrument, now: datetime, max_age_s: int):
    if inst.status != "TRADEABLE":
        return f"markt niet verhandelbaar (status {inst.status})"
    if not (inst.bid > 0 and inst.ask > 0 and inst.ask >= inst.bid):
        return f"ongeldige koers (bid {inst.bid}, ask {inst.ask})"
    if inst.quote_time is None:
        return "tijd van de brokerkoers onbekend"
    age = (now - inst.quote_time).total_seconds()
    if age > max_age_s:
        return f"brokerkoers is {age:.0f} s oud (max {max_age_s} s)"
    if age < -max_age_s:       # verkeerde tijdzone of klok: dan zegt de leeftijd niets
        return f"tijd van de brokerkoers ligt {-age:.0f} s in de toekomst"
    return None


def round_price(x, decimals):
    return round(x, decimals)


def floor_step(x, step):
    """Naar beneden afronden op de kleinste orderstap (zonder 0,30000000004-fouten)."""
    n = math.floor(x / step + 1e-9)
    dec = max(0, -math.floor(math.log10(step) + 1e-12))
    return round(n * step, dec)


# ------------- Orderniveaus -------------
@dataclass
class Plan:
    side: int            # +1 kopen, -1 verkopen
    soort: str           # "MARKET" of "LIMIT"
    entry: float
    stop: float
    tp: float
    size: float = 0.0
    risico_acc: float = 0.0   # verlies in accountvaluta als de stop geraakt wordt (incl. kostenbuffer)
    notional_acc: float = 0.0
    notes: list = field(default_factory=list)


def plan_levels(sig, inst: Instrument, lim: Limits, basis=0.0):
    """Instap, stop en doel bij de broker, met dezelfde afstanden als het signaal. Geeft (Plan, None) of (None, reden).

    sig: dict(kant, entry, stop, tp, soort, ref) in de prijzen van de signaalbron (Yahoo);
    basis: brokerprijs min bronprijs (bv. goud-future tegenover spot-CFD).
    """
    side = 1 if sig["kant"] == "LONG" else -1
    dist_stop, dist_tp = abs(sig["entry"] - sig["stop"]), abs(sig["tp"] - sig["entry"])
    if not (dist_stop > 0 and dist_tp > 0):
        return None, "stop of doel ontbreekt in het signaal"
    if (sig["stop"] - sig["entry"]) * side >= 0 or (sig["tp"] - sig["entry"]) * side <= 0:
        return None, "stop of doel aan de verkeerde kant van de instap"
    if lim.min_rr and dist_tp / dist_stop < lim.min_rr - 1e-9:
        return None, f"risk/reward 1:{dist_tp / dist_stop:.1f} is lager dan het minimum 1:{lim.min_rr:g}"
    spread = inst.ask - inst.bid
    if spread > lim.max_spread_r * dist_stop:
        return None, f"spread {spread:g} is te groot voor de stopafstand {dist_stop:g} (max {lim.max_spread_r:g}R)"
    if sig["soort"] == "MARKET":
        entry = inst.ask if side > 0 else inst.bid
        want = sig["entry"] + basis
        drift = (entry - want) * side / dist_stop
        if drift > lim.max_drift_r:
            return None, f"prijs is al {drift:.2f}R van het signaal weg (max {lim.max_drift_r:g}R)"
    else:
        entry = sig["entry"] + basis
        # limietorder moet aan de goede kant van de markt liggen, anders vult hij direct tegen een slechtere prijs
        if (side > 0 and entry >= inst.ask) or (side < 0 and entry <= inst.bid):
            return None, "limietprijs ligt al voorbij de huidige koers"
    d = inst.decimals
    p = Plan(side=side, soort=sig["soort"], entry=round_price(entry, d),
             stop=round_price(entry - side * dist_stop, d), tp=round_price(entry + side * dist_tp, d))
    real_stop = abs(p.entry - p.stop)
    if real_stop < inst.min_stop or abs(p.tp - p.entry) < inst.min_stop:
        return None, f"stop- of doelafstand kleiner dan het brokerminimum ({inst.min_stop:g})"
    if inst.max_stop and (real_stop > inst.max_stop or abs(p.tp - p.entry) > inst.max_stop):
        return None, f"stop- of doelafstand groter dan het brokermaximum ({inst.max_stop:g})"
    return p, None


def size_plan(p: Plan, inst: Instrument, lim: Limits, equity_acc, fx_inst_to_acc):
    """Positiegrootte uit het risicobudget, de stopafstand en de verwachte kosten. Vult p.size en p.risico_acc."""
    if not (fx_inst_to_acc and fx_inst_to_acc > 0):
        return "geen wisselkoers van de instrumentvaluta naar de accountvaluta"
    dist = abs(p.entry - p.stop)
    cost = (inst.ask - inst.bid) + lim.slippage_r * dist        # spread + slippage, per unit in prijs
    per_unit_acc = (dist + cost) * inst.lot_size * fx_inst_to_acc
    budget = equity_acc * lim.risico_pct / 100
    size = floor_step(budget / per_unit_acc, inst.step)
    if inst.max_size:
        size = min(size, floor_step(inst.max_size, inst.step))
    if size < inst.min_size:
        return f"positie te klein ({size:g}, broker-minimum {inst.min_size:g}) bij {lim.risico_pct:g}% risico"
    p.size = size
    p.risico_acc = size * per_unit_acc
    p.notional_acc = size * p.entry * inst.lot_size * fx_inst_to_acc
    return None


# ------------- Portefeuille -------------
def group_of(markt):
    return next((g for g, ms in CORR_GROUPS.items() if markt in ms), None)


def direction_in_group(markt, side):
    """Richting binnen de groep; bij de dollargroep is dat de richting van de dollar."""
    if group_of(markt) == "Dollar (forex)":
        return side * (-1 if markt.endswith("USD") else 1)
    return side


@dataclass
class Book:
    """Wat er nu open staat. open_risks: verlies (accountvaluta) als alle stops geraakt worden, vanaf de huidige
    prijs; None = positie zonder stop. exposures: (markt, kant) per open positie of wachtende order."""
    equity: float
    day_start: float
    peak: float
    start: float
    open_risks: list
    exposures: list
    used_notional: float = 0.0


def check_portfolio(book: Book, lim: Limits, p: Plan, markt):
    """Mag deze trade er nog bij? Geeft een reden als het niet mag."""
    floor = (book.peak if lim.trailing else book.start) * (1 - lim.totaalverlies_pct / 100)
    day_floor = book.day_start * (1 - lim.dagverlies_pct / 100)
    if book.equity <= floor:
        return f"maximaal verlies geraakt (waarde {book.equity:,.2f} ≤ grens {floor:,.2f})"
    if book.equity <= day_floor:
        return f"daglimiet geraakt (waarde {book.equity:,.2f} ≤ {day_floor:,.2f})"
    if any(r is None for r in book.open_risks):
        return "er staat een positie open zonder stop-loss of met onbekend risico (contractgrootte): eerst oplossen"
    if len(book.exposures) >= lim.max_open:
        return f"al {len(book.exposures)} posities/orders open (max {lim.max_open})"
    open_risk = sum(book.open_risks)
    if open_risk + p.risico_acc > lim.max_open_risico_pct / 100 * book.equity + 1e-9:
        return (f"open risico {open_risk:,.2f} + deze trade {p.risico_acc:,.2f} is meer dan "
                f"{lim.max_open_risico_pct:g}% van de accountwaarde")
    worst = book.equity - open_risk - p.risico_acc
    if worst <= day_floor:
        return f"als alle stops geraakt worden ({worst:,.2f}) breekt de daglimiet ({day_floor:,.2f})"
    if worst <= floor:
        return f"als alle stops geraakt worden ({worst:,.2f}) breekt de maximale-verliesgrens ({floor:,.2f})"
    g = group_of(markt)
    if g:
        same = sum(1 for m, s in book.exposures if group_of(m) == g and direction_in_group(m, s) == direction_in_group(markt, p.side))
        if same >= lim.max_per_groep:
            return f"al {same} trade(s) in dezelfde richting in de groep '{g}' (max {lim.max_per_groep})"
    if book.used_notional + p.notional_acc > lim.hefboom * book.equity:
        return f"hefboom zou boven 1:{lim.hefboom:g} komen"
    return None


def add_to_book(book: Book, p: Plan, markt):
    """Een goedgekeurde order meetellen voor de volgende signalen in dezelfde ronde."""
    book.open_risks.append(p.risico_acc)
    book.exposures.append((markt, p.side))
    book.used_notional += p.notional_acc
