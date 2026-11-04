# Meer handelskansen: onderzoek tijdframes, nieuws en livefeed (4 november 2026)

Er zijn geen orders geplaatst en geen strategieën geactiveerd. `config.json`, `learned.json`, `execution/`, `risk/`,
`learning/` en de poorten P1-P5 zijn ongewijzigd. Protocol: `research/tijdframes_protocol.json`, hash `aa51d1c1…`,
vastgelegd vóór het eerste resultaat van een lagere-tijdframevariant. Voorstel: `docs/refactor/7_tijdframes_voorstel.md`.

## Conclusie

**Geen enkele variant voldoet aan de besluitregel, dus de 1h-baseline blijft staan.** Geen enkele strategie haalt P1-P5
in welke variant dan ook, en er is geen reden om de bot anders in te stellen.

De beperkende factor is niet het aantal signalen. De strategieën hebben vóór kosten gemiddeld ongeveer 0R per trade, en
op 15m kosten trades in R bijna twee keer zoveel omdat de stop half zo groot is. Meer trades betekent dan meer kosten.

Een tweede bevinding staat los van de tijdframes: **de risicogrenzen zetten elke portefeuille al in de eerste helft van
de evaluatie stil.** Zie "Bot blokkeert zichzelf".

## Nulmeting: huidige 1h-aanpak op 15 markten

Yahoo, laatste 180 dagen, met de kosten uit het protocol. De lab-varianten zijn gekozen met kennis van deze periode, dus
deze cijfers zijn eerder te mooi dan te somber.

| Markt | Status 2 nov | Signalen per week (alle families) | Gem. R na kosten | Gevolgde strategie | Trades per week | Gem. R gevolgd | Totaal R |
|---|---|---:|---:|---|---:|---:|---:|
| BTC | onderzoek | 18,9 | -0,198 | momentum | 1,8 | -0,074 | -3,4 |
| ETH | onderzoek | 14,3 | -0,171 | trend | 2,3 | -0,028 | -1,7 |
| SOL | pauze | 1,4 | -0,375 | geen | 0 | n.v.t. | n.v.t. |
| EURUSD | onderzoek | 13,6 | -0,205 | volatiliteit | 1,8 | +0,009 | +0,4 |
| GBPUSD | onderzoek | 9,9 | -0,152 | meanrev | 1,7 | -0,055 | -2,3 |
| USDJPY | pauze | 16,3 | -0,180 | geen | 0 | n.v.t. | n.v.t. |
| NQ | onderzoek | 11,9 | +0,076 | breakout | 4,2 | +0,162 | +17,5 |
| ES | onderzoek | 11,1 | -0,072 | momentum | 1,6 | +0,250 | +10,3 |
| DAX | pauze | 5,4 | -0,077 | geen | 0 | n.v.t. | n.v.t. |
| GOUD | onderzoek | 11,6 | -0,004 | breakout | 3,3 | +0,050 | +4,2 |
| ZILVER | pauze | 12,6 | -0,137 | geen | 0 | n.v.t. | n.v.t. |
| OLIE | pauze | 13,9 | -0,191 | geen | 0 | n.v.t. | n.v.t. |
| AAPL | pauze | 6,0 | -0,245 | geen | 0 | n.v.t. | n.v.t. |
| NVDA | pauze | 4,8 | -0,226 | geen | 0 | n.v.t. | n.v.t. |
| MSFT | pauze | 4,7 | -0,096 | geen | 0 | n.v.t. | n.v.t. |

"Trades per week" is het tempo over de 180 dagen, geen telling per kalenderweek. Per markt zijn het 41 tot 108 trades, dus
de cijfers per markt zijn onzeker. NQ en ES dragen samen de hele plus, en die twee zitten in dezelfde risicogroep.

- **Gevolgde strategie per markt, zonder limieten:** 427 trades (16,6 per week), +0,058R per trade, +0,022R bij 1,5x
  kosten, 95%-interval -0,064 tot +0,115. Winst +1,43R, verlies -0,93R, 41,9% winnaars, drawdown 17,9R, langste
  verliesreeks 11. Niet te onderscheiden van nul.
- **Met de risicoregels:** 119 trades (4,6 per week), drawdown 4,88%, 296 weigeringen door de grenscontrole.
- **Samenhang:** de 427 trades zijn 337 onafhankelijke weddenschappen (gemiddelde dagcorrelatie tussen markten 0,03).
  Met de risicoregels stonden er hoogstens 3 posities tegelijk open, waarvan 2 in dezelfde groep.
- **Echte demo:** één order (GOUD long, 2 november, -€ 4,95). Daaruit valt niets te concluderen.

### Waarom strategieën afvallen

Per 2 november, 78 getoetste families: P4 66×, P2 64×, P5 64×, P3 39×, P1 19×. Bijna elke familie valt op meerdere
poorten tegelijk, dus één drempel is niet het knelpunt. Alleen NQ-breakout en ES-momentum vallen uitsluitend op P4. Dat
is geen bewijs dat ze goed zijn: P4 corrigeert juist voor het aantal geprobeerde varianten.

## De vier varianten

6 markten (EURUSD, GBPUSD, NQ, ES, GOUD, ZILVER), HistData. Ontwikkeling 2 maart 2025 - 26 april 2026, evaluatie 26 april
- 23 oktober 2026. Getest: 10 strategieën × 4 varianten × 6 markten = 240 combinaties. De poort rekende met 40 proeven per
markt. Bij V1 en V2 is de evaluatie niet maagdelijk: die strategieën zijn op deze periode eerder bekeken.

### Aanbod: alle 10 strategieën samen in de evaluatie, zonder keuze

| Variant | Uitgevoerd per week | Bruto R | Netto R | Bij 1,5x kosten | Ondergrens | Stop (mediaan) | Geweigerd op spread |
|---|---:|---:|---:|---:|---:|---:|---:|
| V1 1h | 173 | 0,000 | -0,081 | -0,118 | -0,178 | 0,34% | 0,2% |
| V2 4h + 1h | 99 | -0,003 | -0,083 | -0,120 | -0,201 | 0,34% | 0,2% |
| V3 15m | 232 | +0,015 | -0,141 | -0,215 | -0,278 | 0,16% | 5,5% |
| V4 15m + 5m | 163 | +0,046 | -0,109 | -0,182 | -0,255 | 0,16% | 5,2% |

- **Meer trades:** alleen V3 geeft er meer: +34% tegenover V1. V2 geeft 43% minder en V4 6% minder, omdat filters
  signalen wegnemen.
- **Kosten:** op 15m en 5m kost een trade ongeveer 0,155R tegen 0,08R op 1h. Elke kleine bruto verbetering verdwijnt daarin.
- **Poort:** 0 van de 120 geteste families haalt P1-P5, in geen enkele variant. Portefeuille A (wat de bot zou mogen
  handelen) is dus overal leeg.

### Signalen, totaalresultaat en blootstelling

Alle 10 strategieën samen. Valide setups en uitgevoerd per week gelden voor de hele periode van 85,7 weken, de andere
kolommen voor de evaluatie. Drawdown en verliesreeks tellen overlappende strategieën mee, dus lees die als orde van grootte en niet als
portefeuille.

| Variant | Valide setups p/w | Uitgevoerd p/w | Trades | Weddenschappen | Totaal R | Max DD | Verliesreeks |
|---|---:|---:|---:|---:|---:|---:|---:|
| V1 1h | 281 | 187 | 4448 | 702 | -361,0 | 410,6R | 35 |
| V2 4h + 1h | 164 | 108 | 2540 | 404 | -211,5 | 273,8R | 36 |
| V3 15m | 434 | 249 | 5975 | 414 | -841,9 | 874,5R | 34 |
| V4 15m + 5m | 292 | 176 | 4192 | 370 | -455,4 | 493,2R | 31 |

- **Dubbel uitvoeren:** één strategie heeft per markt maar één positie tegelijk en elke setup wordt maar één keer een trade.
  Het verschil tussen setups en uitgevoerd komt vooral daardoor.
- **Weddenschappen:** V3 heeft 34% meer trades dan V1, maar 41% minder onafhankelijke weddenschappen. Trades op dezelfde dag,
  in dezelfde groep en dezelfde richting tellen als één. De teller heeft een plafond, en V1 zit daar vermoedelijk dicht bij
  omdat die zonder richtingsfilter beide kanten op handelt. Lagere tijdframes leveren dus vooral meer van hetzelfde.

Blootstelling binnen de risicoregels (portefeuille B, evaluatie):

| Variant | Trades | Weddenschappen | Totaal R | Max DD | Verliesreeks | Max open | Max in groep | Slechtste dag | Correlatie |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| V1 1h | 103 | 90 | +5,2 | 9,3R | 7 | 3 | 2 | 1,67% | -0,04 |
| V2 4h + 1h | 27 | 22 | -7,1 | 10,9R | 6 | 2 | 1 | 1,04% | te weinig data |
| V3 15m | 32 | 18 | -5,8 | 10,3R | 7 | 3 | 1 | 2,70% | te weinig data |
| V4 15m + 5m | 71 | 53 | +0,9 | 9,5R | 8 | 2 | 2 | 1,60% | -0,04 |

Alle varianten bleven onder de daggrens van 3%. Alleen V3 raakte de trailinggrens. De correlatie is de gemiddelde samenhang van
dagresultaten tussen markten. Dagen zonder trade tellen als 0, dus bij zo weinig trades zegt dit getal weinig.

### Besluitregel op portefeuille B (per markt de beste keuze uit de ontwikkelperiode)

Dit is een meetinstrument, geen handelsvoorstel.

| Variant | Trades p/w | Gem. R | 1,5x kosten | Rendement | Max DD | Trailinggrens | ≥1,5x trades | Na kosten | E1 en E2 | Risico | Oordeel |
|---|---:|---:|---:|---:|---:|---|---|---|---|---|---|
| V1 1h | 4,0 | +0,050 | +0,017 | +2,4% | 4,56% | niet | n.v.t. | nee | nee | ja | baseline |
| V2 4h + 1h | 1,1 | -0,264 | -0,292 | -3,6% | 4,86% | niet | nee | nee | nee | ja | nee |
| V3 15m | 1,2 | -0,180 | -0,228 | -2,9% | 5,02% | **geraakt** | nee | nee | nee | nee | nee |
| V4 15m + 5m | 2,8 | +0,012 | -0,038 | +0,3% | 4,67% | niet | nee | nee | nee | ja | nee |

Let op: de +0,050R van V1 is grotendeels toeval van het moment waarop de grenzen blokkeerden. E2 is in alle vier leeg.

### Bot blokkeert zichzelf

Een order wordt geweigerd als alle open stops samen door de 5%-grens zouden gaan. Bij 0,5% risico per trade is dat na
een verlies van zo'n 9R. Bij 40% winnaars en een doel van 2R is zo'n reeks goed mogelijk. Daarna komt er geen trade meer
bij, dus de waarde kan niet herstellen en de hoogste waarde blijft staan: in de simulatie is de blokkade blijvend.

Dit gebeurde in de nulmeting en in alle vier de varianten: V1 151 weigeringen, V2 156, V3 350, V4 103.

Dat is geen fout in de grens. Ze doet wat ze moet doen, en de limieten zijn niet aangepast. Maar als een strategie ooit
door de poort komt, is een reeks van 9R genoeg om de bot blijvend stil te zetten, ook als de strategie goed is. Hoe je
dan handelt is een keuze voor de eigenaar.

### Controle na afloop: dezelfde gekozen strategieën zonder limieten

Niet vooraf vastgelegd en telt niet mee in het oordeel. Bedoeld om te laten zien wat de blokkade verbergt.

| Variant | Trades p/w | Bruto R | Netto R | 1,5x kosten | 95%-interval | Weddenschappen | E1 | E2 | Max DD | Verliesreeks |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|
| V1 1h | 10,0 | 0,000 | -0,087 | -0,126 | -0,328 tot +0,038 | 218 | -0,022 | -0,157 | 45,0R | 12 |
| V2 4h + 1h | 7,1 | +0,121 | +0,060 | +0,032 | -0,105 tot +0,155 | 142 | -0,007 | +0,115 | 10,5R | 6 |
| V3 15m | 14,9 | +0,021 | -0,083 | -0,131 | -0,267 tot +0,016 | 196 | -0,119 | -0,045 | 51,7R | 13 |
| V4 15m + 5m | 6,8 | +0,099 | -0,020 | -0,076 | -0,290 tot +0,077 | 125 | -0,037 | -0,005 | 25,8R | 14 |

- De V1-baseline is zonder limieten verliesgevend: -0,087R per trade. De +0,050R in de tabel hierboven zegt dus niets.
- V3 heeft de meeste trades, maar 384 trades zijn maar 196 onafhankelijke weddenschappen.
- V2 is de enige die positief blijft, maar met minder trades, E1 net negatief, een interval dat nul ruim omvat en een
  bevinding die pas achteraf is gezien. Het is een hypothese voor nieuwe data, geen resultaat.

### Bredere marktdekking

De 9 markten buiten de HistData-set voegen in de nulmeting 85,5 signalen per week toe (bovenop 70,7), met -0,183R per trade
tegen -0,084R. Dat is meer activiteit, niet meer kwaliteit. Op aandelen en SOL is de gemeten spread bovendien 2,6 tot 4,5
keer hoger dan het model. Voor deze markten is geen 15m/5m-historie getest, dus daar is alleen 1h bekeken.

### 1m: alleen datakwaliteit en uitvoerbaarheid

| Markt | Ontbreekt in handelsuren | Gaten >30 min | Platte candles | Dubbel |
|---|---:|---:|---:|---:|
| EURUSD | 0,93% | 18 | 1,02% | 0 |
| GBPUSD | 1,00% | 17 | 1,09% | 0 |
| NQ | 5,42% | 480 | 0,03% | 0 |
| ES | 5,68% | 479 | 0,48% | 0 |
| GOUD | 1,88% | 60 | 0,08% | 0 |
| ZILVER | 2,04% | 57 | 0,21% | 0 |

- NQ en ES hebben bijna elke handelsdag een gat, waarschijnlijk doordat de bron rond 16:15 New York stopt. Dat is niet
  verder uitgezocht.
- Uitstap op 1m in plaats van 5m verandert op V1 en V3 geen enkele uitkomst (stop/doel/tijd) en het gemiddelde hoogstens
  0,002R. 5m is dus fijn genoeg om uitstappen te simuleren. 1m voegt hier niets toe.

## Nieuws

Het project heeft geen tijdgestempelde nieuws- of kalenderbron, dus er is niets getest en niets toegevoegd. Nieuwsfilters
leveren in dit onderzoek dus 0 extra of vermeden trades op. De "nieuwsmomenten"
in `research/archief/backtest_tp_v2.py` komen uit de prijs zelf: dat kijkt vooruit en is geen bruikbare basis.

| Optie | Kosten | Wat het biedt | Beperking |
|---|---|---|---|
| [Federal Reserve FOMC-kalender](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) | gratis | Vergaderdata 2021-2027 | Geen kloktijden; toekomstige data voorlopig |
| [BLS-releaseschema](https://www.bls.gov/schedule/news_release/empsit.htm) | gratis | Banenrapport, 08:30, ook vooruit | Andere rapporten apart; oudere jaren op aparte pagina's |
| [FRED release dates](https://fred.stlouisfed.org/docs/api/fred/releases_dates.html) | gratis, sleutel nodig | Publicatiedata van veel reeksen | Alleen datums, geen tijden |
| Forex Factory-weekfeed | gratis | Huidige week | Lijkt geen historie of uitkomsten te hebben; geen officiële voorwaarden gevonden |
| [Financial Modeling Prep](https://site.financialmodelingprep.com/developer/docs/stable/economics-calendar) | onzeker, [vanaf USD 100 per maand volgens Datarade](https://datarade.ai/data-products/economic-calendar-api-350-indicators-financial-modeling-prep) | Kalender-API | Prijs en plan niet bevestigd |
| [Trading Economics](https://tradingeconomics.com/api/pricing.aspx) | onzeker, bronnen noemen USD 49-399 per maand | Kalender-API met historie | Prijzen spreken elkaar tegen |
| [Finnhub](https://finnhub.io/pricing) | onzeker, één vergelijkingssite noemt USD 3.500 per maand | Kalender | Niet in de gratis laag volgens die site; niet bevestigd |

De betaalde prijzen komen deels uit bronnen van derden. Controleer ze vóór een aankoop.

**Advies:** begin gratis. FOMC-besluiten en het banenrapport hebben vaste, vooraf bekende tijden, dus die lenen zich voor een
eerste risicofilter zonder look-ahead: geen nieuwe trade X minuten rond het moment, vergeleken met dezelfde strategie zonder
filter, met gemiste en vermeden trades apart. Omdat er nu geen strategie is die handelt, levert dat nog niets op voor de bot.

## Livefeed (Capital.com, alleen lezen)

Drie metingen van 20 minuten via de workflow Feedmeting. De cijfers hieronder komen uit de rustige nachtmeting (4 november,
00:14-00:34 UTC, run `01c0b3b`), tenzij er "London" staat. Alleen GET-verzoeken en de stream, geen orders. De uitvoer bevat
geen tokens: `rapport/feedmeting.json` en `rapport/feedmeting_london.json`.

**Oordeel 's nachts: 11 markten bruikbaar, 4 niet gemeten** omdat DAX, AAPL, NVDA en MSFT dicht waren.

**Oordeel tijdens London (4 november, 12:29-12:49 UTC, run `41829615753`): 12 markten bruikbaar, 3 niet gemeten.** DAX is nu
gemeten en bruikbaar. AAPL, NVDA en MSFT tellen als dicht, ook al kwamen er enkele honderden koersen binnen. Verder 34.904
koersen, 0 verbroken verbindingen, 0 dubbel, 0 terug in de tijd, 0% ontbrekende candles en een grootste gat van 16 s (SOL).
De koerstijden liepen mediaan 12,5 s achter, hoogstens 17,2 s. Op de markten die ook 's nachts open waren, lag de spread dicht bij die meting.

De opening van New York is nog niet gemeten, dus het bewijst nog niet dat de feed op drukke momenten goed blijft.

- **Stream:** 39.004 koersen, 0 verbroken verbindingen, 0 dubbele updates, 0 keer terug in de tijd, 0% ontbrekende
  1m-candles op open markten. Grootste gat: 67 s bij OLIE, anders onder 13 s.
- **Versheid:** koerstijden lopen op alle markten zo'n 16 s (max 21,5 s) achter op de klok van de runner. Dat kan vertraging
  op demo zijn of een klokverschil; de meting kan dat niet scheiden. Het blijft ruim onder de grens van 180 s.
- **Candles:** een nieuwe 1m-candle verschijnt zo'n 76 s na zijn start, dus ongeveer 16 s na het slot van de vorige minuut.
- **Historie:** 15m, 5m en 1m gaan op alle 15 markten minstens 730 dagen terug, 1095 dagen niet. Eén verzoek mag hoogstens
  1000 candles beslaan. Daarmee kan het onderzoek later op alle 15 markten met de echte brokerprijzen. Dit is getoetst met
  steekproefvensters van 12 uur, niet candle voor candle.
- **Tegen HistData:** 15m-candles sluiten zonder tijdverschuiving aan; prijsverschil 0,00-0,03%. HistData is voor deze 6
  markten dus een goede benadering.
- **Tegen Yahoo:** forex en crypto sluiten aan. Goud, zilver, NQ en ES wijken 0,5-0,7% af (future tegen CFD), olie -0,8% met
  een spreiding van 1,2%. **Yahoo-aandelencandles beginnen op :30, Capital.com op :00**, dus die zijn niet één op één te
  vergelijken.
- **Prijssoort:** Capital.com geeft bid en ask per candle; de vergelijking gebruikt het midden. HistData en Yahoo geven één
  prijs, dus spread zit daar niet in en moet apart gerekend worden.

### Spread per uur (mediaan per UTC-uur, slot van 1000 uurcandles)

| Markt | Normaal | Hoogste uur |
|---|---:|---:|
| GOUD | 0,0120% | 0,0127% (21:00) |
| ZILVER | 0,0826% | 0,1593% (21:00) |
| OLIE | 0,0427% | 0,0434% (22:00) |
| NQ | 0,0061% | 0,0134% (21:00) |
| ES | 0,0078% | 0,0195% (21:00) |
| DAX | 0,0079% | 0,0314% (23:00) |
| EURUSD | 0,0062% | 0,0351% (21:00) |
| GBPUSD | 0,0097% | 0,0527% (21:00) |
| USDJPY | 0,0076% | 0,0518% (21:00) |
| BTC | 0,0605% | 0,0607% (18:00) |
| ETH | 0,0705% | 0,0711% (15:00) |
| SOL | 0,5000% | 0,5000% (6:00) |
| AAPL | 0,1139% | 0,1621% (7:00) |
| NVDA | 0,1531% | 0,1780% (7:00) |
| MSFT | 0,1025% | 0,1567% (23:00) |

Bij forex en de Amerikaanse indices is de spread rond 21:00 UTC 2 tot 7 keer zo hoog. Het kostenmodel ligt te laag voor
ZILVER, GOUD, SOL en de drie aandelen. De spreadmeting in dit onderzoek (3 november) lag voor de meeste markten juist op of
boven het normale niveau.

### Bevinding in de actieve code: leeftijdscontrole deed niets

`/markets/{epic}` gaf in alle 600 metingen alleen `updateTime` (zo'n 1 uur vooruit op UTC) en nooit `updateTimeUTC`. Maar
`execution/capital.py` las juist `updateTimeUTC`. Daardoor was `quote_time` altijd leeg en sloeg `check_quote` de controle
op verouderde koersen (maximaal 180 s) over. De andere controles (status, delay, bid/ask) werkten wel. In dit onderzoek is de
handelscode niet aangepast. De reparatie is apart gemerged in [PR #6](https://github.com/nThijnS/TradingStrategie/pull/6)
(`cfa5ea4`, op verzoek van de eigenaar) en draait sinds 4 november. Ze is getest, maar nog niet door een echte order gebruikt.

Een extra meting liet zien dat `updateTime` precies `timezoneOffset` (1 uur) voorloopt. Teruggerekend waren de REST-koersen
0-15 seconden oud. De stream liep in dezelfde periode zo'n 16 seconden achter, dus die achterstand komt waarschijnlijk niet
door een klokverschil. De oorzaak is nog niet vastgesteld.

## Beperkingen

- Evaluatie van 180 dagen in één marktperiode. Per markt zijn er te weinig trades voor harde conclusies.
- De kosten in de varianten gebruiken één spreadmeting plus een aanname voor slippage, niet de spread per uur. Nieuws kan
  duurder zijn. Echte slippage is onbekend zolang er geen orders zijn.
- De bestaande families zijn gebouwd voor 1h. Ze op 15m draaien bewijst niet dat geen enkele 15m-strategie werkt.
- ICT viel buiten de toets.
- De portefeuillesimulatie boekt resultaat bij sluiting, zonder open winst of verlies tussendoor, en gebruikt de ene
  spreadmeting ook voor de spreadregel.
- Eén implementatiefout is vóór het bekijken van variantresultaten gevonden en hersteld: trades die in hun instapcandle sloten,
  bleven als open staan. Daarna zijn alleen diagnoses toegevoegd.

## Veilige vervolgstap

Voordat een variant ooit demo-orders krijgt, moet dit allemaal gebeuren, in deze volgorde:

1. Een nieuwe hypothese en protocol, met bijvoorbeeld V2 op nieuwe data. Niet de V2-uitkomst van nu als bewijs gebruiken.
2. Hetzelfde onderzoek op 2 jaar Capital.com-candles voor alle 15 markten, met de spread per uur. Daarna shadow mode zonder
   orders, minstens zolang tot P1 haalbaar is (30 trades per markt). Nieuwe feedmetingen tijdens de opening van New York horen daarbij.
3. De ongewijzigde poort P1-P5 op die data.
4. Pas daarna een aparte wijziging om de livefeed te gebruiken voor de instap, met tests en jouw akkoord.
