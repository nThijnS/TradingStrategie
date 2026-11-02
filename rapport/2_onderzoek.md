# Fase 3–5 — Onderzoek markten en strategieën

Gemaakt 2026-11-02T17:18 met `python onderzoek.py` (gegevens: `rapport/onderzoek.json`). Het protocol staat bovenaan `onderzoek.py` en lag vast voordat de eindtest werd bekeken.

## Kernpunten

- **626 varianten** getest (198 markt × strategiefamilie-combinaties). **Geen enkele** haalt de selectiepoort (P1–P5). Geen variant faalt alléén op de Deflated Sharpe: elke variant faalt ook op minstens één eenvoudige toets.
- **PBO (CSCV)** van de lab-keuze "beste markt × strategie": **63%** (150 varianten, 29 maanden). Boven 50% betekent: de in-sample beste is vaker wel dan niet een slechte keuze voor de periode erna.
- **Voor/na op dezelfde eindtest (vanaf 2026-05-01):**
  - VOOR (het lab-protocol): 142 trades in 4 markten, netto **-3.0R**.
  - NA (de selectiepoort): 0 trades, **+0.0R** ("geen trade").
  - Dat "na" niet verliest, is geen bewezen verbetering. Het betekent alleen dat er niets wordt gehandeld dat niet bewezen is.

## Voor: wat het lab-protocol koos (alleen data vóór de eindtest) en hoe dat uitpakte

| Markt | Strategie | Variant | WF-ondergrens | Eindtest n | gem. R | netto R | 95%-interval (blokken) |
|---|---|---|---|---|---|---|---|
| GOUD | momentum | `{"er": 0.5}` | +0.018 | 40 | +0.084 | +3.4 | [-0.263, 0.443] |
| ZILVER | trend | `{"tp": 3.0}` | +0.036 | 42 | -0.030 | -1.3 | [-0.305, 0.123] |
| OLIE | volatiliteit | `{"p": 0.1}` | +0.003 | 55 | -0.067 | -3.7 | [-0.41, 0.227] |
| NVDA | meanrev | `{"k": 2.5}` | +0.022 | 5 | -0.286 | -1.4 | [-1.054, 0.556] |

De andere bestaande markten kregen ook in het oude protocol "geen trade". ICT is hier buiten beschouwing gelaten; die wordt apart door `leren.py` gekozen (eerdere toets met zomertijd-correcte data: geen voordeel op NQ/EURUSD in 2026).

## Markten (fase 3)

Bron Yahoo Finance. Dagen = handelsdagen met 1h-data. Sprongen = openingsgaten groter dan 8× de mediane candle (vaak future-rollovers). Correlatie = weekrendementen sinds nov 2024 (dagrendementen onderschatten de samenhang tussen markten die op verschillende tijden sluiten), hoogste absolute met een bestaande markt.

| Markt | Kandidaat | 1h-dagen | candles/dag | platte candles | sprongen | hoogste correlatie | Besluit |
|---|---|---|---|---|---|---|---|
| BTC (Bitcoin) | nee | 726 | 24.0 | 0.0 | 2 | ETH +0.82 | bestaand |
| ETH (Ethereum) | nee | 726 | 24.0 | 0.0 | 2 | BTC +0.82 | bestaand |
| SOL (Solana) | nee | 726 | 24.0 | 0.0 | 2 | ETH +0.80 | bestaand |
| EURUSD (EUR/USD) | nee | 819 | 24.0 | 0.007 | 1 | GBPUSD +0.82 | bestaand |
| GBPUSD (GBP/USD) | nee | 819 | 24.0 | 0.008 | 0 | EURUSD +0.82 | bestaand |
| USDJPY (USD/JPY) | nee | 819 | 24.0 | 0.003 | 1 | EURUSD -0.64 | bestaand |
| NQ (Nasdaq 100) | nee | 734 | 23.0 | 0.0 | 6 | ES +0.95 | bestaand |
| ES (S&P 500) | nee | 734 | 23.0 | 0.001 | 6 | NQ +0.95 | bestaand |
| DAX (DAX 40) | nee | 730 | 9.0 | 0.0 | 5 | ES +0.55 | bestaand |
| GOUD (Goud) | nee | 733 | 23.0 | 0.0 | 6 | ZILVER +0.76 | bestaand |
| ZILVER (Zilver) | nee | 733 | 23.0 | 0.0 | 0 | GOUD +0.76 | bestaand |
| OLIE (Olie (WTI)) | nee | 731 | 23.0 | 0.003 | 3 | DAX -0.31 | bestaand |
| AAPL (Apple) | nee | 730 | 7.0 | 0.0 | 4 | ES +0.53 | bestaand |
| NVDA (Nvidia) | nee | 730 | 7.0 | 0.0 | 5 | NQ +0.71 | bestaand |
| MSFT (Microsoft) | nee | 730 | 7.0 | 0.0 | 8 | NQ +0.54 | bestaand |
| AUDUSD (AUD/USD) | ja | 819 | 24.0 | 0.01 | 0 | GBPUSD +0.69 | uitgesteld: data goed; deels dollar-factor (0,69 met GBP/USD); instrumentgegevens nog niet geverifieerd |
| USDCAD (USD/CAD) | ja | 819 | 24.0 | 0.007 | 1 | EURUSD -0.69 | uitgesteld: data goed; vooral dollar-factor (−0,69 met EUR/USD); instrumentgegevens nog niet geverifieerd |
| USDCHF (USD/CHF) | ja | 819 | 24.0 | 0.003 | 0 | EURUSD -0.82 | afgewezen: −0,82 met EUR/USD: vrijwel dezelfde weddenschap, geen spreiding |
| NZDUSD (NZD/USD) | ja | 819 | 24.0 | 0.011 | 2 | GBPUSD +0.80 | afgewezen: 0,80 met GBP/USD en een hogere spread: weinig spreiding voor meer kosten |
| EURGBP (EUR/GBP) | ja | 819 | 24.0 | 0.006 | 0 | EURUSD +0.36 | uitgesteld: beste spreiding van de forexparen (0,36 met EUR/USD); instrumentgegevens nog niet geverifieerd |
| EURJPY (EUR/JPY) | ja | 819 | 24.0 | 0.006 | 1 | USDJPY +0.65 | uitgesteld: 0,65 met USD/JPY; instrumentgegevens nog niet geverifieerd |
| US30 (Dow Jones) | ja | 734 | 23.0 | 0.0 | 4 | ES +0.90 | afgewezen: 0,90 met S&P 500: geen spreiding (de correlatiegroep telt ze toch als één) |
| FTSE (FTSE 100) | ja | 730 | 9.0 | 0.0 | 0 | DAX +0.73 | uitgesteld: 0,73 met DAX; Yahoo geeft alleen de beursuren (9 candles/dag), de CFD handelt bijna de hele dag: databron sluit niet aan |
| NIKKEI (Nikkei 225) | ja | 730 | 7.0 | 0.003 | 0 | NQ +0.59 | uitgesteld: matige samenhang (0,59 met Nasdaq), Aziatische uren; Yahoo-uren (7/dag) sluiten niet aan op de CFD |
| CAC (CAC 40) | ja | 729 | 9.0 | 0.0 | 4 | DAX +0.86 | afgewezen: 0,86 met DAX: geen spreiding |
| BRENT (Brent-olie) | ja | 729 | 23.0 | 0.002 | 4 | OLIE +0.92 | afgewezen: 0,92 met WTI-olie: geen spreiding |
| KOPER (Koper) | ja | 733 | 23.0 | 0.0 | 0 | ZILVER +0.50 | uitgesteld: redelijke spreiding (0,50 met zilver); spread en instrument nog niet geverifieerd |
| GAS (Aardgas) | ja | 725 | 23.0 | 0.003 | 13 | MSFT +0.20 | afgewezen: 13 prijssprongen in de Yahoo-future (rollovers): data sluit niet aan op een CFD; hoge kosten |

Geen enkele kandidaat is toegevoegd. Twee redenen:
- De instrumentgegevens bij Capital.com (epic, contractgrootte, spread, financiering, uren) zijn nog niet uitgelezen. Dat doet `capital_instrumenten.py`, met de demo-sleutels in GitHub.
- Geen strategie haalt op deze markten de poort.

Bestaande markten die sterk samenhangen (NQ–ES 0,95, BTC–ETH 0,82, EUR/USD–GBP/USD 0,82, goud–zilver 0,76, NVDA–NQ 0,71) blijven bestaan. `risico.py` telt ze voortaan als één groep: max 1 positie per groep en richting.

## Strategieën (fase 4): beste per familie

Per familie de variant met de hoogste validatie-ondergrens. gem. R is netto (kosten, slippage 0,02R en financiering); ×1,5 = met 50% hogere kosten. Interval = block-bootstrap per week, 95%.

| Markt | Strategie | Variant | Train n / gem. R | Validatie n / gem. R / ×1,5 | Val. ondergrens | DSR | Eindtest n / gem. R / interval | Faalt op |
|---|---|---|---|---|---|---|---|---|
| DAX | lab+regime:volatiliteit | `{"p": 0.2}` | 22 / +0.476 | 7 / +0.701 / +0.689 | +0.333 | 0.43 | 7 / +0.022 / [-0.463, 0.369] | P1, P4, P5 |
| NQ | lab+regime:volatiliteit | `{"p": 0.1}` | 39 / -0.020 | 9 / +0.793 / +0.781 | +0.095 | 0.02 | 18 / +0.333 / [-0.281, 0.948] | P1, P3, P4, P5 |
| GOUD | lab+regime:momentum | `{"er": 0.5}` | 70 / -0.091 | 20 / +0.520 / +0.513 | +0.087 | 0.01 | 18 / +0.300 / [-0.186, 0.729] | P1, P3, P4 |
| NZDUSD | lab:momentum | `{"er": 0.5}` | 168 / -0.001 | 41 / +0.332 / +0.294 | +0.076 | 0.02 | 46 / +0.131 / [-0.214, 0.396] | P3, P4 |
| AAPL | lab:meanrev | `{"k": 2.0}` | 96 / -0.007 | 28 / +0.161 / +0.137 | +0.061 | 0.01 | 23 / -0.024 / [-0.308, 0.135] | P1, P3, P4, P5 |
| ZILVER | lab:volatiliteit | `{"p": 0.1}` | 114 / -0.054 | 35 / +0.405 / +0.384 | +0.053 | 0.01 | 38 / -0.223 / [-0.502, -0.01] | P3, P4 |
| MSFT | lab+regime:breakout | `{"n": 24}` | 73 / -0.321 | 17 / +0.300 / +0.279 | +0.050 | 0.00 | 17 / +0.115 / [-0.445, 0.565] | P1, P3, P4, P5 |
| NQ | tsmom | `21/63/252, 3xATR` | 58 / -0.056 | 6 / +1.111 / +1.110 | +0.034 | 0.01 | 1 / -0.055 / – | P1, P3, P4, P5 |
| MSFT | lab+regime:momentum | `{"er": 0.3}` | 64 / -0.267 | 16 / +0.319 / +0.297 | +0.034 | 0.00 | 16 / +0.132 / [-0.342, 0.717] | P1, P3, P4, P5 |
| KOPER | lab:volatiliteit | `{"p": 0.2}` | 182 / -0.158 | 63 / +0.271 / +0.218 | +0.030 | 0.00 | 57 / -0.285 / [-0.589, 0.02] | P2, P3, P4 |
| MSFT | lab:breakout | `{"n": 48}` | 131 / -0.214 | 33 / +0.166 / +0.143 | +0.026 | 0.00 | 29 / +0.059 / [-0.201, 0.415] | P2, P3, P4, P5 |
| USDCHF | lab:trend | `{"tp": 3.0}` | 134 / -0.018 | 32 / +0.196 / +0.174 | +0.006 | 0.01 | 32 / -0.066 / [-0.468, 0.158] | P2, P3, P4, P5 |
| NZDUSD | lab+regime:momentum | `{"er": 0.5}` | 75 / +0.080 | 25 / +0.359 / +0.322 | +0.004 | 0.05 | 19 / +0.292 / [-0.298, 0.692] | P1, P2, P4, P5 |
| EURGBP | lab+regime:meanrev | `{"k": 2.5}` | 177 / -0.014 | 45 / +0.166 / +0.108 | -0.011 | 0.01 | 47 / -0.124 / [-0.394, 0.128] | P2, P3, P4, P5 |
| EURGBP | lab:meanrev | `{"k": 2.5}` | 198 / -0.029 | 49 / +0.180 / +0.123 | -0.012 | 0.01 | 51 / -0.119 / [-0.397, 0.133] | P2, P3, P4 |
| MSFT | lab:momentum | `{"er": 0.5}` | 54 / -0.289 | 21 / +0.216 / +0.194 | -0.017 | 0.00 | 19 / +0.081 / [-0.397, 0.316] | P1, P2, P3, P4, P5 |
| US30 | lab:trend | `{"tp": 2.0}` | 80 / +0.111 | 30 / +0.243 / +0.235 | -0.017 | 0.10 | 41 / -0.072 / [-0.344, 0.096] | P2, P4, P5 |
| ZILVER | lab:trend | `{"tp": 2.0}` | 86 / +0.033 | 22 / +0.313 / +0.298 | -0.018 | 0.03 | 42 / -0.032 / [-0.301, 0.088] | P1, P2, P4, P5 |
| NVDA | lab:meanrev | `{"k": 2.5}` | 38 / +0.050 | 7 / +0.445 / +0.429 | -0.029 | 0.04 | 5 / -0.286 / [-1.053, 0.526] | P1, P2, P4, P5 |
| NIKKEI | lab+regime:momentum | `{"er": 0.5}` | 60 / -0.031 | 7 / +0.655 / +0.643 | -0.032 | 0.01 | 11 / -0.532 / [-0.777, -0.342] | P1, P2, P3, P4, P5 |
| NQ | lab:volatiliteit | `{"p": 0.1}` | 125 / -0.063 | 44 / +0.307 / +0.295 | -0.033 | 0.01 | 41 / +0.106 / [-0.141, 0.547] | P2, P3, P4 |
| EURJPY | lab:breakout | `{"n": 24}` | 468 / -0.070 | 131 / +0.034 / -0.003 | -0.042 | 0.00 | 127 / -0.083 / [-0.223, 0.079] | P2, P3, P4, P5 |
| BTC | lab+regime:momentum | `{"er": 0.3}` | 111 / +0.012 | 51 / +0.162 / +0.111 | -0.051 | 0.01 | 38 / -0.002 / [-0.377, 0.468] | P2, P4, P5 |
| GOUD | lab:momentum | `{"er": 0.5}` | 126 / -0.045 | 38 / +0.237 / +0.230 | -0.052 | 0.01 | 40 / +0.084 / [-0.274, 0.438] | P2, P3, P4, P5 |
| USDCHF | lab:momentum | `{"er": 0.3}` | 374 / -0.119 | 95 / +0.092 / +0.062 | -0.056 | 0.00 | 101 / -0.251 / [-0.41, -0.051] | P2, P3, P4, P5 |
| NQ | orb | `60m, 2R` | 139 / -0.057 | 84 / -0.008 / -0.015 | -0.086 | 0.00 | 79 / -0.044 / [-0.208, 0.087] | P2, P3, P4, P5 |
| ES | orb | `60m, 2R` | 165 / -0.003 | 85 / +0.011 / +0.000 | -0.087 | 0.00 | 96 / -0.096 / [-0.249, 0.025] | P2, P3, P4, P5 |
| NQ | lab:trend | `{"tp": 3.0}` | 94 / +0.156 | 34 / -0.083 / -0.089 | -0.324 | 0.03 | 24 / +0.198 / [-0.282, 0.589] | P2, P4, P5 |

### Per hypothese

- **Donchian 55/20 en time-series momentum (21/63/252 dagen), dagdata:**
  - Te weinig trades in de validatie (meestal 6–19 per markt). P1 faalt dus overal.
  - De resultaten springen per markt alle kanten op.
  - Er komt financiering per nacht bij.
  - Deze strategieën houden posities dagen tot weken vast. Dat past niet bij de daytrade-opzet en de prop-regels van de bot.
  - **Afgewezen voor nu.**
- **Opening-range-breakout NQ/ES (HistData 1m, zomertijd-correct):**
  - Alle 10 varianten zijn negatief of rond 0, in train, validatie én eindtest.
  - **Afgewezen.**
- **VWAP-pullback:**
  - Niet getest. Voor forex en CFD's is er geen betrouwbare volumedata, en Yahoo-futures geven maar 60 dagen 5m-data.
  - **Uitgesteld**, tot er een volumebron is die aansluit op de broker.
- **Regimefilter op de lab-strategieën** (trendstrategieën alleen in een trendmarkt, mean reversion alleen in een zijwaartse markt):
  - Haalt ook nergens de poort; meestal te weinig trades.
  - Behandeld als filter, niet als eigen strategie. **Niet ingevoerd.**
- **Bestaande lab-strategieën:** geen enkele combinatie slaagt.
  - Nasdaq 100 trend volgen (op de site: +0,12R, interval −0,08 tot +0,32) was in de validatie (nov 2025 – apr 2026) negatief.
  - De positieve eindtest daarna heeft maar 24 trades en een interval dat ruim door 0 loopt.

## Beperkingen

- **Data:**
  - Yahoo 1h gaat ~730 dagen terug, dus de eindtest is maar 6 maanden.
  - Futures zijn continue contracten met rollovers. Capital.com handelt CFD's met andere uren en prijzen.
  - Yahoo-futures lopen 10–15 minuten achter.
- **Kosten:** dit zijn schattingen, niet bij Capital.com geverifieerd.
  - De spread is per markt vast gekozen.
  - Financiering is ruim gerekend.
  - Spreads bij nieuws en 's nachts zijn breder dan hier aangenomen.
- **Statistiek:**
  - Voor de DSR is aangenomen dat de proeven onafhankelijk zijn, met N = markt × familie. Varianten hangen samen, dus de echte N ligt lager.
  - De DSR rekent met de Sharpe per trade.
  - Het block-bootstrap-interval gebruikt weekblokken.
  - PBO is berekend op maandsommen.
- **Overlevingsbias:** de markten zijn vandaag gekozen. Aandelen als NVDA zijn achteraf winnaars, en dat vertekent kopen-en-houden en trendstrategieën.
- **Eindtest:** die is nu één keer bekeken. Een volgende ronde moet een nieuwe, latere eindtest gebruiken.
