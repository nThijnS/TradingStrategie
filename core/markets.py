"""Alle marktdefinities en kostenaannames op één plek.

Kosten zijn aannames (spread + commissie + slippage, heen en terug) en zijn nog niet bij de broker
geverifieerd; zie execution/instruments.py en rapport/instrumenten.json.
"""

# ICT/TJR-markten van de meldingen-app. "cfg" overschrijft per markt de standaard (core.config.CFG).
#   cost      kosten per trade in prijspunten (zoals in alle eerdere HistData-backtests en leren.py)
#   histdata  (symbool, SMT-partner) bij HistData.com, voor backtests en de startvulling van het leergeheugen
#   alt       de prijs bij de broker/prop firm (US100 volgt de Nasdaq-100 index, niet de future)
#   learn_only  alleen meldingen als het leren hem aanzet (learned.json), wel altijd loggen
ICT_MARKETS = [
    dict(name="NQ", symbol="NQ=F", smt="ES=F", dec=2, cfg={}, alt=dict(symbol="^NDX", label="US100"),
         cost=2.0, histdata=("NSXUSD", "SPXUSD")),
    dict(name="EURUSD", symbol="EURUSD=X", smt="GBPUSD=X", dec=5,
         cfg=dict(tick=0.00002, disp_pct=0.6, disp_atr=1.2, tp_mode="DOL"),
         cost=0.00008, histdata=("EURUSD", "GBPUSD")),
    dict(name="GOUD", symbol="GC=F", smt="SI=F", dec=2, cfg=dict(tick=0.1), learn_only=True,
         cost=0.35, histdata=("XAUUSD", "XAGUSD")),
]

# Extra HistData-markten die alleen in onderzoek voorkwamen (tick = stopbuffer-eenheid, cost in prijspunten)
HISTDATA_RESEARCH = {
    "NQ": dict(sym="NSXUSD", smt="SPXUSD", tick=0.25, cost=2.0),
    "GOUD": dict(sym="XAUUSD", smt="XAUUSD", tick=0.05, cost=0.35),
    "EURUSD": dict(sym="EURUSD", smt="GBPUSD", tick=0.00002, cost=0.00008),
    "GBPUSD": dict(sym="GBPUSD", smt="EURUSD", tick=0.00002, cost=0.00012),
}

# Strategielab-markten (1h Yahoo). kosten = spread + commissie heen en terug, als deel van de prijs.
LAB_MARKETS = [
    dict(naam="BTC", symbool="BTC-USD", soort="crypto", titel="Bitcoin", kosten=0.0008),
    dict(naam="ETH", symbool="ETH-USD", soort="crypto", titel="Ethereum", kosten=0.0008),
    dict(naam="SOL", symbool="SOL-USD", soort="crypto", titel="Solana", kosten=0.0012),
    dict(naam="EURUSD", symbool="EURUSD=X", soort="forex", titel="EUR/USD", kosten=0.00007),
    dict(naam="GBPUSD", symbool="GBPUSD=X", soort="forex", titel="GBP/USD", kosten=0.00009),
    dict(naam="USDJPY", symbool="JPY=X", soort="forex", titel="USD/JPY", kosten=0.00008),
    dict(naam="NQ", symbool="NQ=F", soort="index", titel="Nasdaq 100", kosten=0.00008),
    dict(naam="ES", symbool="ES=F", soort="index", titel="S&P 500", kosten=0.00008),
    dict(naam="DAX", symbool="^GDAXI", soort="index", titel="DAX 40", kosten=0.0001),
    dict(naam="GOUD", symbool="GC=F", soort="grondstof", titel="Goud", kosten=0.0001),
    dict(naam="ZILVER", symbool="SI=F", soort="grondstof", titel="Zilver", kosten=0.0006),
    dict(naam="OLIE", symbool="CL=F", soort="grondstof", titel="Olie (WTI)", kosten=0.0005),
    dict(naam="AAPL", symbool="AAPL", soort="aandeel", titel="Apple", kosten=0.0005),
    dict(naam="NVDA", symbool="NVDA", soort="aandeel", titel="Nvidia", kosten=0.0005),
    dict(naam="MSFT", symbool="MSFT", soort="aandeel", titel="Microsoft", kosten=0.0005),
]

# Kandidaat-markten uit het onderzoek (fase 3). Kosten zijn voorzichtige schattingen, NIET geverifieerd.
CANDIDATES = [
    dict(naam="AUDUSD", symbool="AUDUSD=X", soort="forex", titel="AUD/USD", kosten=0.00010),
    dict(naam="USDCAD", symbool="CAD=X", soort="forex", titel="USD/CAD", kosten=0.00010),
    dict(naam="USDCHF", symbool="CHF=X", soort="forex", titel="USD/CHF", kosten=0.00012),
    dict(naam="NZDUSD", symbool="NZDUSD=X", soort="forex", titel="NZD/USD", kosten=0.00015),
    dict(naam="EURGBP", symbool="EURGBP=X", soort="forex", titel="EUR/GBP", kosten=0.00012),
    dict(naam="EURJPY", symbool="EURJPY=X", soort="forex", titel="EUR/JPY", kosten=0.00012),
    dict(naam="US30", symbool="YM=F", soort="index", titel="Dow Jones", kosten=0.00008),
    dict(naam="FTSE", symbool="^FTSE", soort="index", titel="FTSE 100", kosten=0.00012),
    dict(naam="NIKKEI", symbool="^N225", soort="index", titel="Nikkei 225", kosten=0.00020),
    dict(naam="CAC", symbool="^FCHI", soort="index", titel="CAC 40", kosten=0.00015),
    dict(naam="BRENT", symbool="BZ=F", soort="grondstof", titel="Brent-olie", kosten=0.0005),
    dict(naam="KOPER", symbool="HG=F", soort="grondstof", titel="Koper", kosten=0.0008),
    dict(naam="GAS", symbool="NG=F", soort="grondstof", titel="Aardgas", kosten=0.0015),
]

# Financiering per jaar over de positiewaarde (ruim geschat, long én short); overige soorten 6,5%
FINANCING = dict(crypto=0.20, forex=0.02)
FINANCING_DEFAULT = 0.065


def fin_rate(m):
    return FINANCING.get(m.get("soort"), FINANCING_DEFAULT)


def ict_market(name):
    return next(m for m in ICT_MARKETS if m["name"] == name)
