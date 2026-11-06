# Kansen-onderzoek deel 2: andere bronnen van voordeel

Datum: 4 november 2026. Protocol `kansen-v2` (`research/kansen2_protocol.json`) is vastgelegd vóór de eerste uitslag. Uitkomsten staan in `rapport/kansen2.json`.

## Uitkomst

**Ook hier haalt niets P1–P5. Er is niets ingebouwd en de bot blijft ongewijzigd.** Samen met deel 1 zijn nu 381 combinaties op echte Capital-prijzen getoetst, plus 20 jaar trendvolging als informatie.

Binnen de huidige regels en bij deze broker is geen route gevonden naar een goede maandwinst. Gepubliceerde effecten bestaan wel, maar zijn hier na kosten te klein.

## Getoetste tijdstip-effecten

Elke strategie heeft één vaste variant, zonder afstelling. De cijfers zijn het gemiddelde van de markten per trade bij 1,5× kosten, op 2 jaar Capital-prijzen.

| Strategie | Bron | Ontwikkeling | Evaluatie (180 dagen) | Slaagt |
|---|---|---:|---:|---|
| Long rond de Europese opening (02:00–06:00 NY) | Boyarchenko e.a.; Bondarenko en Muravyev | −0,012R | +0,009R | nee |
| Long 's nachts (16:00–09:00 NY) | Boyarchenko e.a. | −0,045R | −0,027R | nee |
| Laatste uur met de dagrichting mee | Gao e.a. | −0,013R | −0,024R | nee |
| Uitbraak uit een dagband | Zarattini e.a. | +0,001R | −0,120R | nee |
| BTC en ETH long 21:00–23:00 UTC | Padysak en Vojtko, alleen via secundaire bronnen gezien | −0,046R | −0,162R | nee |

Alle 18 combinaties vallen op P4 en P5. Dat zijn geen grote verliezen, maar er is ook geen meetbare winst. De effecten zijn klein ten opzichte van de spreiding, en deze strategieën hebben per trade weinig te verdienen. Het Europese-openingseffect is in dit tijdvak niet zichtbaar.

## Trendvolging op dagcandles (alleen informatie)

Deze strategie kan P1 per markt niet halen, omdat ze te weinig handelt. De test laat zien of een besluit over P1 iets zou opleveren. Periode: 2005 tot nu, 18 markten, 1.429 trades.

| Periode | Trades | Vóór kosten | Na kosten |
|---|---:|---:|---:|
| 2005–2009 | 265 | +0,41R | +0,19R |
| 2010–2014 | 310 | +0,15R | −0,05R |
| 2015–2019 | 344 | +0,12R | −0,10R |
| 2020–2024 | 370 | +0,33R | +0,13R |
| 2025–nu | 140 | −0,03R | −0,22R |
| Totaal | 1.429 | +0,22R | +0,01R |

Vóór kosten is er een plus (t-waarde ongeveer 3), maar de kosten nemen vrijwel alles weg: gemiddeld ongeveer 0,2R per trade. Een trade loopt zo'n 50 dagen, dus de dagelijkse financiering van een CFD telt zwaar op.

Met 0,5% risico, maximaal 3 open en zonder verliesstop levert dit gemiddeld +0,4% per jaar op, en −1,6% per jaar over de laatste 5 jaar. Het beste jaar is +20% (2020), het slechtste −7,5%. **Een versoepeling van P1 zou daarom bij deze broker niets opleveren.**

Uitsplitsing achteraf, dus geen toets:

| Groep | Trades | Vóór kosten | Na kosten | Na kosten sinds 2021 |
|---|---:|---:|---:|---:|
| Crypto (BTC, ETH) | 98 | +2,07R | +1,81R | +0,36R |
| Metalen | 267 | +0,34R | +0,08R | −0,12R |
| Energie | 243 | +0,18R | +0,09R | −0,25R |
| Forex | 341 | +0,01R | −0,19R | −0,50R |
| Indices | 480 | −0,06R | −0,28R | −0,42R |

Bijna de hele plus komt van crypto, en die komt uit de grote stijging van BTC en ETH. Long-trades verdienen en shorts niet. Sinds 2021 blijft alleen crypto positief, over 56 trades: dat zijn er ongeveer 10 per jaar, goed voor rond de 2% per jaar bij 0,5% risico. Dat is geen route naar maandwinst.

## Waarom een andere route niet helpt

- **Echte futures:** daar betaal je geen dagelijkse CFD-financiering, maar op 10k past het niet. Een stop van 3 keer de dagrange is op ES nu ongeveer 292 punten. Dat is ongeveer $1.460 per microcontract, tegen een risicobudget van zo'n €50. Op goud is het ongeveer $2.330 per microcontract.
- **Meer risico per trade:** dat vergroot bij nul voordeel alleen de kans dat de limiet raakt, en valt buiten de afspraken.

## Conclusie

Over beide delen zien we hetzelfde: vóór kosten is er soms iets, na kosten bij deze broker ongeveer nul of minder. De poorten houden dat terecht tegen. De bot blijft op demo draaien en het lab blijft dagelijks controleren. Verder zoeken in dezelfde twee jaar data vergroot vooral de kans op een toevalstreffer.

## Beperkingen

- De financiering en spreads van vandaag zijn ook op het verleden toegepast. Ontvangen rente telt niet mee.
- Uurcandles benaderen de tijden: de opening van 09:30 is gemeten rond 09:00 en 10:00. De band-strategie is een vereenvoudiging van het artikel, dat met fijnere data en een andere uitstap werkt.
- Yahoo-futures zijn doorlopende reeksen met rollsprongen. BTC en ETH hebben minder historie dan de rest.
- Twee jaar Capital-data is te kort om kleine effecten aan te tonen of uit te sluiten.
- Bij de andere bronnen is alleen de samenvatting gelezen, niet elk volledig artikel.
