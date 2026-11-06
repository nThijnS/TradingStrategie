# Toets van de vijf ideeën

Datum: 5 november 2026. Protocol `vijf-v1` (`research/vijf_protocol.json`) is vastgelegd vóór de eerste uitslag; de sha256 staat in `rapport/vijf.json`. Code: `research/vijf.py`, tests: `tests/test_vijf.py`. Geen orders.

## Uitkomst

**Geen van de 9 combinaties is toelaatbaar. De bot blijft ongewijzigd.** De teller staat nu op 876 proeven.

- **Herbalancering op NQ** komt het dichtst bij: alleen P4 faalt. Toch is het geen kandidaat, omdat train rond nul zit en het effect na de steekproef van de paper verdwijnt (zie hieronder).
- **De andere vier** vallen duidelijk af.
- **Kosten:** in `core/markets.py` zijn de kosten op alle 15 markten te laag. Op SOL scheelt het 0,47R per trade.

## Uitslag per idee

Evaluatie is de laatste 180 dagen van de gebruikte reeks. Bij combineren en funding is een dag de eenheid; de R is dus niet per trade.

| Idee | Markt | Train | Evaluatie | Bij 1,5× kosten | E1 / E2 | Ondergrens | DSR markt / scan | Valt op |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Combineren | portefeuille | +0,046R (372) | +0,015R (122) | +0,008R | +0,042R / -0,026R | -0,072R | 0,29 / 0,08 | P2, P4, P5 |
| Herbalancering | ES | +0,007R (114) | +0,140R (67) | +0,129R | +0,142R / +0,100R | -0,047R | 0,04 / 0,00 | P2, P4, P5 |
| Herbalancering | NQ | +0,004R (114) | +0,303R (67) | +0,298R | +0,295R / +0,304R | +0,022R | 0,08 / 0,01 | P4 |
| Slotmomentum | ES | -0,039R (72) | -0,036R (37) | -0,044R | -0,012R / -0,086R | -0,138R | 0,00 / 0,00 | P2, P3, P4, P5 |
| Slotmomentum | NQ | -0,069R (77) | -0,012R (36) | -0,018R | +0,011R / -0,076R | -0,078R | 0,00 / 0,00 | P2, P3, P4, P5 |
| COT | portefeuille | -0,085R (103) | -0,073R (30) | -0,085R | -0,064R / -0,118R | -0,178R | 0,00 / 0,00 | P2, P3, P4, P5 |
| Funding | BTC | – | – | – | – | – | – | P1 |
| Funding | ETH | – | – | – | – | – | – | P1 |

- **Combineren:** de gekozen variant gebruikt 9 van de 60 stromen, namelijk die met winst op train. In de evaluatie houdt die +0,008R bij 1,5× kosten over, en E2 is negatief. Alle 60 stromen samen geven −0,056R. Combineren maakt van rond nul geen winst.
- **Herbalancering:** zie hieronder.
- **Slotmomentum:** bruto ook al rond nul of negatief (−0,02R op ES, 0,00R op NQ in de evaluatie). De data is HistData, niet de future. Op deze 2 jaar is er niets van te zien.
- **COT:** bruto licht positief (+0,09R in de evaluatie), na financiering negatief, zoals verwacht.
- **Funding:** handelt te zelden voor P1. De richting klopt bovendien niet met het idee: zie hieronder.

## Herbalancering nader bekeken

| Maat | ES | NQ |
|---|---:|---:|
| Trades op CFD, 2 jaar | 181 | 181 |
| Gemiddeld netto | +0,056R | +0,114R |
| Short (172 trades) | +0,077R | +0,136R |
| Long (9 trades) | −0,344R | −0,304R |

Lange reeks op Yahoo-futures, bruto, ES de dag na het signaal:

| Periode | Dagen | Per dag | t-waarde |
|---|---:|---:|---:|
| 2001–2012 | 1.068 | +13,2 bp | 3,0 |
| 2013–2019 | 551 | +0,2 bp | 0,1 |
| 2020–2026 | 664 | +12,3 bp | 2,6 |
| Alles | 2.302 | +9,8 bp | 3,8 |

Bijgerekend na de uitslag, dus geen protocoltoets:

| Maat | Waarde |
|---|---:|
| Na de steekproef van de paper (vanaf 18 maart 2023) | 375 dagen, −1,9 bp, t −0,4 |
| Long-dagen, hele reeks | 354 dagen, +38,4 bp |
| Short-dagen, hele reeks | 1.948 dagen, +4,6 bp |
| Jaren met een plus | 18 van 27 |
| Deflated Sharpe lange reeks, 876 proeven | 0,72 (eis 0,95) |

**Lezing:** de bruto winst over 25 jaar komt vooral van long-dagen, vaak herstel na een daling. Op CFD waren dat er maar 9, en die verloren. De CFD-winst komt juist van shorts. Dat is dus niet hetzelfde effect, en na de steekproef van de paper is het op deze meting weg. Op 2 jaar is de poort bovendien bijna niet te halen: bij deze Sharpe zijn ruwweg 2.000 trades nodig, ongeveer 20 jaar handelen (schatting, geen meting).

## Funding nader bekeken

Bruto rendement over 7 dagen sinds 2021, overlappende vensters:

| Markt | Signaal aan | Signaal uit | Slechtste 5%, aan / uit |
|---|---:|---:|---:|
| BTC | +1,43% (385 dagen) | +0,39% | −11,3% / −11,4% |
| ETH | +2,98% (359 dagen) | +0,38% | −10,4% / −15,6% |

Hoge funding ging hier niet vooraf aan slechtere weken. De hypothese wordt op deze data niet gesteund.

**Lange COT-reeks:** op Yahoo-futures sinds 2014 gemiddeld +0,40% per maand bruto, t 0,9, Sharpe 0,24. Zwak en niet aangetoond.

## Kostenmodel

Gemeten is 1,5 keer de spread per trade, op de basisvarianten; de aanname is `kosten` uit `core/markets.py`. Het verschil komt deels door de halve spread slippage, die de aanname niet heeft.

| Markt | Aanname | Gemeten | Verschil per trade |
|---|---:|---:|---:|
| SOL | 0,089R | 0,554R | +0,465R |
| AAPL | 0,072R | 0,155R | +0,083R |
| NVDA | 0,048R | 0,129R | +0,081R |
| ZILVER | 0,069R | 0,135R | +0,066R |
| MSFT | 0,070R | 0,134R | +0,063R |
| GBPUSD | 0,054R | 0,103R | +0,049R |
| OLIE | 0,062R | 0,092R | +0,030R |
| USDJPY | 0,045R | 0,071R | +0,026R |
| ETH | 0,073R | 0,098R | +0,025R |
| EURUSD | 0,045R | 0,068R | +0,023R |
| BTC | 0,116R | 0,129R | +0,013R |
| GOUD | 0,021R | 0,031R | +0,011R |
| NQ | 0,021R | 0,031R | +0,010R |
| ES | 0,030R | 0,040R | +0,010R |
| DAX | 0,031R | 0,039R | +0,008R |

`core/markets.py` is in dit onderzoek niet gewijzigd.

## Grenzen

- Financiering is de stand van 4 november 2026, toegepast op het verleden; ontvangen rente telt niet mee.
- 2 jaar CFD-data heeft weinig onderscheidend vermogen. "Niet aangetoond" is dus niet hetzelfde als "bestaat niet".
- Yahoo-futures hebben rolsprongen en zijn bruto; de lange reeksen zijn alleen informatie.
- Alle vijf ideeën kwamen uit de literatuur en zijn hier met één vaste variant getoetst.
