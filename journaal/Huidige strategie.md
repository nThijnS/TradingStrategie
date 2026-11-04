# Huidige strategie

Bijgewerkt: 2026-11-03 20:36 NY. De bot kiest dit per markt zelf uit alle strategieën (ICT is er één van) met een vaste poort tegen overfitting; zie learning/selector.py.

| markt | status | strategie | ondergrens validatie | sinds | reden |
|---|---|---|---|---|---|
| BTC | onderzoek | Onderzoek: Momentum (geen orders)  | - | 2026-11-02 | geen strategie haalt de poort; momentum is in train en validatie positief en wordt gevolgd zonder orders |
| ES | onderzoek | Onderzoek: Momentum (geen orders)  | - | 2026-11-02 | geen strategie haalt de poort; momentum is in train en validatie positief en wordt gevolgd zonder orders |
| ETH | onderzoek | Onderzoek: Trend volgen (geen orders)  | - | 2026-11-02 | geen strategie haalt de poort; trend is in train en validatie positief en wordt gevolgd zonder orders |
| EURUSD | onderzoek | Onderzoek: Volatiliteit (squeeze) (geen orders)  | - | 2026-11-02 | geen strategie haalt de poort; volatiliteit is in train en validatie positief en wordt gevolgd zonder orders |
| GOUD | onderzoek | Onderzoek: Breakout (geen orders)  | - | 2026-11-02 | geen strategie haalt de poort; breakout is in train en validatie positief en wordt gevolgd zonder orders |
| NQ | onderzoek | Onderzoek: Breakout (geen orders)  | - | 2026-11-02 | geen strategie haalt de poort; breakout is in train en validatie positief en wordt gevolgd zonder orders |
| OLIE | onderzoek | Onderzoek: Volatiliteit (squeeze) (geen orders)  | - | 2026-11-03 | geen strategie haalt de poort; volatiliteit is in train en validatie positief en wordt gevolgd zonder orders |
| AAPL | pauze | Geen trade  | - | 2026-10-30 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| DAX | pauze | Geen trade  | - | 2026-10-30 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| GBPUSD | pauze | Geen trade  | - | 2026-11-03 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| MSFT | pauze | Geen trade  | - | 2026-10-30 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| NVDA | pauze | Geen trade  | - | 2026-11-02 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| SOL | pauze | Geen trade  | - | 2026-11-02 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| USDJPY | pauze | Geen trade  | - | 2026-10-30 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |
| ZILVER | pauze | Geen trade  | - | 2026-11-02 | geen strategie haalt de poort en geen is in beide perioden positief: pauze |

Status: **actief** = haalt de poort, signalen tellen (orders op het demo-account); **onderzoek** = in train en validatie positief maar nog niet genoeg bewijs, wordt gevolgd zonder orders; **pauze** = niets.
