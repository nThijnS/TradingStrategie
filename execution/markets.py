"""Capital.com-epic per markt (was execution/runner.EPICS; die naam blijft werken).

Deze lijst is een voorstel, geen vrijgave. Een markt krijgt alleen demo-orders als rapport/instrumenten.json
(workflow "Instrumenten controleren", alleen lezen) het instrument bevestigt; zie execution/instruments.verified.
"""
EPICS = {"GOUD": "GOLD", "ZILVER": "SILVER", "OLIE": "OIL_CRUDE", "NQ": "US100", "ES": "US500", "DAX": "DE40",
         "EURUSD": "EURUSD", "GBPUSD": "GBPUSD", "USDJPY": "USDJPY", "BTC": "BTCUSD", "ETH": "ETHUSD", "SOL": "SOLUSD",
         "AAPL": "AAPL", "NVDA": "NVDA", "MSFT": "MSFT"}

# Hoeveel de brokerkoers hoogstens van de bronkoers (Yahoo) mag afwijken. Futures tegenover een CFD op de
# spotprijs verschillen een paar tienden procent tot ruim een procent; een groter verschil wijst op een verkeerd
# instrument of een andere eenheid (bijvoorbeeld centen of een tiende van de index). Geen risicolimiet.
MAX_BASIS_PCT = 5.0

# Instrumenttype bij Capital.com per marktsoort, zoals rapport/instrumenten.json van 3 november 2026 ze voor alle
# 15 markten teruggaf. Een epic met een ander type is niet het bedoelde instrument en wordt niet verhandeld.
INSTRUMENT_TYPES = {"crypto": "CRYPTOCURRENCIES", "forex": "CURRENCIES", "index": "INDICES", "grondstof": "COMMODITIES",
                    "aandeel": "SHARES"}
