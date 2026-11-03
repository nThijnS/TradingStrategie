# Huidige strategie

Bijgewerkt: 2026-11-02 20:40 NY. De bot kiest dit per markt zelf uit alle strategieën (ICT is er één van) met een vaste poort tegen overfitting; zie learning/selector.py.

| markt | status | strategie | ondergrens validatie | sinds | reden |
|---|---|---|---|---|---|
| ES | onderzoek | Onderzoek: Momentum (geen orders)  | - | 2026-11-02 | geen strategie haalt de poort; momentum is in train en validatie positief en wordt gevolgd zonder orders |
| GBPUSD | onderzoek | Onderzoek: Mean reversion (geen orders)  | - | 2026-11-02 | geen strategie haalt de poort; meanrev is in train en validatie positief en wordt gevolgd zonder orders |
| GOUD | onderzoek | Onderzoek: Mean reversion (geen orders)  | - | 2026-11-02 | huidige strategie haalt de poort niet meer; geen strategie haalt de poort; meanrev is in train en validatie positief en wordt gevolgd zonder orders |
| NQ | onderzoek | Onderzoek: Trend volgen (geen orders)  | - | 2026-11-02 | huidige strategie haalt de poort niet meer; geen strategie haalt de poort; trend is in train en validatie positief en wordt gevolgd zonder orders |
| SOL | onderzoek | Onderzoek: Volatiliteit (squeeze) (geen orders)  | - | 2026-11-02 | geen strategie haalt de poort; volatiliteit is in train en validatie positief en wordt gevolgd zonder orders |
| AAPL | pauze | Geen trade  | - | 2026-10-30 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| BTC | pauze | Geen trade  | - | 2026-10-30 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| DAX | pauze | Geen trade  | - | 2026-10-30 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| ETH | pauze | Geen trade  | - | 2026-10-30 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| EURUSD | pauze | Geen trade  | - | 2026-10-30 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| MSFT | pauze | Geen trade  | - | 2026-10-30 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| NVDA | pauze | Geen trade  | - | 2026-11-02 | huidige strategie haalt de poort niet meer; geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| OLIE | pauze | Geen trade  | - | 2026-10-30 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| USDJPY | pauze | Geen trade  | - | 2026-10-30 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| ZILVER | pauze | Geen trade  | - | 2026-11-02 | huidige strategie haalt de poort niet meer; geen strategie haalt de poort en geen is in beide perioden positief: pauze |

Status: **actief** = haalt de poort, signalen tellen (orders op het demo-account); **onderzoek** = in train en validatie positief maar nog niet genoeg bewijs, wordt gevolgd zonder orders; **pauze** = niets.
