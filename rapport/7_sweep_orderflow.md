# Mislukte sweep als uitbraak, en orderflow

Datum: 5 november 2026. Protocol `sweep-orderflow-v1` (`research/sweep_orderflow_protocol.json`) is vastgelegd vóór de eerste uitslag; de sha256 staat in `rapport/sweep_orderflow.json`. Tests: `tests/test_sweep_orderflow.py`.

## Uitkomst

**Geen van de 19 getoetste strategie-markt-paren is toelaatbaar. De bot blijft ongewijzigd.** Orderflow geeft op crypto een klein, statistisch niet aangetoond voordeel, dat na kosten niets positiefs oplevert.

Aanleiding was NQ op 4 november: London High geveegd, terugsluiten, daarna omhoog doorbreken. Die dag zit niet in de data van deze toets.

## Mislukte sweep wordt uitbraak (HistData, januari 2025 tot 23 oktober 2026)

Evaluatie is de laatste 180 dagen. De variant is gekozen op de periode daarvoor.

| Markt | Gekozen variant | Train | Evaluatie | Eval. bij 1,5× kosten | Ondergrens | DSR | Valt op |
|---|---|---:|---:|---:|---:|---:|---|
| NQ | markt, 2R | +0,060R (137) | −0,254R (49) | −0,264R | −0,400R | 0,00 | P2, P4, P5 |
| GOUD | markt, 1R | +0,069R (106) | +0,297R (29) | +0,286R | +0,023R | 0,19 | P1, P4 |
| EURUSD | markt, 2R | −0,066R (134) | +0,015R (55) | −0,020R | −0,191R | 0,00 | P2–P5 |
| GBPUSD | markt, 2R | −0,013R (146) | −0,223R (57) | −0,264R | −0,507R | 0,00 | P2–P5 |

- Op NQ verloor de regel in de evaluatie ongeveer 12R over 49 trades. Dagen als 4 november bestaan, maar wegen hier niet op tegen de dagen waarop de uitbraak mislukt.
- GOUD is het enige lichtpuntje: één trade te kort voor P1 en ruim onder de Deflated Sharpe. Bij 46 geteste combinaties is zo'n uitschieter door toeval te verwachten. Het is geen resultaat, hoogstens iets om op nieuwe data te blijven volgen.

## Orderflow

### Wat kan en wat niet

| Bron | Inhoud | Bruikbaar |
|---|---|---|
| HistData | Alleen prijs | Nee |
| Yahoo NQ/ES 5m | Totaalvolume, geen koop/verkoop, 60 dagen | Nee: kan P1 niet halen |
| Binance BTC, ETH, SOL 5m | Volume met agressieve kopers (taker buy), 2 jaar | Ja |

Footprint, delta of orderboek op NQ, ES of goud vraagt CME-tickdata, die we niet hebben. **Dit rapport zegt daarom niets over orderflow op NQ.** Binance-flow is spotflow van één beurs; de bot zou op Capital.com-CFD's handelen.

### Uitslag op crypto

Gemiddelde over BTC, ETH en SOL bij 1,5× kosten in de evaluatie. Geen enkele haalt P2 of P4.

| Strategie | BTC | ETH | SOL | Bruto evaluatie (BTC / ETH / SOL) |
|---|---:|---:|---:|---:|
| Uitbraak zonder flow | −0,434R | −0,115R | −0,204R | −0,086 / +0,102 / +0,041 |
| Uitbraak met flowbevestiging | −0,291R | −0,040R | −0,118R | −0,021 / +0,159 / +0,070 |
| ICT zonder flow | −0,387R | −0,468R | −0,544R | +0,202 / +0,021 / −0,080 |
| ICT met absorptie | −0,309R | −0,596R | −0,366R | +0,227 / −0,134 / +0,099 |
| CVD-divergentie | −2,048R | −2,166R | −1,307R | −0,020 / −0,203 / −0,173 |

- **Uitbraak met flowbevestiging:** beter dan zonder filter in de evaluatie op alle zes combinaties, en in de ontwikkelperiode op vijf van de zes (ETH 2R gelijk). Na afloop vergeleken, dus geen protocoltoets: uitbraken met bevestiging gaven bruto +0,081R (534 trades), zonder −0,003R (256 trades). Dat verschil van 0,084R heeft een t-waarde van 1,2 en is niet aangetoond. Een deel van de nettowinst komt doordat deze trades grotere stops hebben, waardoor de kosten in R kleiner zijn.
- **ICT met absorptie:** wisselend per markt, geen patroon.
- **CVD-divergentie:** bruto rond nul, en door de krappe stops kosten van 1,1R tot 2,0R per trade.

## Grenzen

- Geen wijziging aan P1–P5, risicolimieten, live-instellingen of orderuitvoering. Geen orders.
- Crypto: uitkomst op 5m met stop eerst, dus voorzichtig. Kosten uit de aannames van `core/markets.LAB_MARKETS` van vóór [PR #8](https://github.com/nThijnS/TradingStrategie/pull/8), niet gemeten bij Capital.com. Daardoor zijn vooral de SOL-cijfers te gunstig: daar rekende dit onderzoek 0,12%, gemeten is 0,75%. De conclusie verandert daardoor niet.
- De filterdrempels (dr ≥ 0,10 en relvol ≥ 1,5) zijn één keer vastgelegd en niet afgesteld. Andere drempels zijn niet getoetst.
