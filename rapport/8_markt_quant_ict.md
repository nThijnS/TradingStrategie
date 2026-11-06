# Hoe markten werken, hoe quants handelen en wat we nog niet gebruiken

Datum: 5 november 2026. Dit is onderzoek: er is niets aan de bot veranderd en er is geen strategie getoetst. Cijfers van deel 1: `rapport/marktonderzoek.json`, code: `research/marktonderzoek.py`.

**Aangevuld door [rapport 9](9_verdieping.md):** de originele papers stelden de top 5 bij. Waar de twee verschillen, geldt rapport 9.

Bewijslabels: **[P]** peer-reviewed, **[W]** working paper of instelling, **[B]** boek of beschrijving door tweede hand, **[N]** nieuws, **[M]** marketing, blog of forum. Nummers verwijzen naar de bronnenlijst.

## 1. Samenvatting

1. **Op 2 jaar data zien we geen eenvoudige voorspelbaarheid.** Op 1 uur en dag zijn de markten niet te onderscheiden van toeval; alleen op 5m is er een heel kleine terugkeer in forex en crypto.
2. **Het drukke moment is voorspelbaar, de richting niet.** De ochtend in New York is 2 tot 4 keer zo beweeglijk als rustige uren, maar dat zegt niets over omhoog of omlaag.
3. **Een geveegd niveau is ongeveer een muntworp.** Ongeveer de helft van de vegingen sluit terug en na 4 uur staat de prijs net zo vaak terug als verder. Gemiddeld neigt het eerder naar doorlopen dan naar terugkeren.
4. **Onze kostenaannames kloppen op een paar markten niet.** SOL kost bij Capital.com 0,50% spread tegen 0,12% in `core/markets.py`. Ook NVDA, ZILVER, AAPL en MSFT zijn te laag ingeschat. Eerdere uitslagen op die markten zijn dus te gunstig. Hersteld in [PR #8](https://github.com/nThijnS/TradingStrategie/pull/8).
5. **Kosten laten ruimte op NQ, ES, DAX en goud,** en vooral in de ochtend van New York. Dat is ruimte, geen bewezen voordeel. SOL valt af, en BTC en ZILVER zitten ongunstig.
6. **De 15 markten zijn ongeveer 6 groepen.** Dat beperkt hoeveel onafhankelijke bets we echt hebben.
7. **Quants winnen vooral met breedte, kosten en risico.** Veel kleine onafhankelijke voordelen, geen enkel magisch patroon. Gepubliceerde voordelen slijten, en de grote ongelukken kwamen door drukte in dezelfde trade en door hefboom.
8. **Je stelling over ICT klopt deels.** De kern (stops weghalen, mislukte uitbraak, grote partij achter de schermen) is aantoonbaar ouder. Voor directe overname vond ik geen bewijs, en ik vond geen peer-reviewed toets van ICT zelf.
9. **Het beste onafhankelijke bewijs is genuanceerder dan ICT.** Onderzoek naar orders in forex laat zien dat prijzen voor uren versnellen bij stopclusters, en juist vaker omkeren bij take-profits op ronde getallen. Een veging is dus geen vaste omkeer, en dat past bij punt 3.
10. **Top 5 om te toetsen:** signalen combineren, herbalanceringssignaal, slotmomentum op grote dagen, COT-positionering en crypto-funding als risicofilter (volgorde uit rapport 9). Orderboek-orderflow, nieuws met AI en regimes vallen voorlopig af.

## 2. Deel 1: alle markten, 2 jaar terug

### Bronnen per markt

| Markt | Uurdata (Capital.com) | 5m-data |
|---|---|---|
| BTC | 2024-11-04 t/m 2026-11-04, 17310 candles | Binance 2024-11-03 t/m 2026-11-03 |
| ETH | 2025-01-23 t/m 2026-11-04, 15415 candles | Binance 2024-11-03 t/m 2026-11-03 |
| SOL | 2024-12-14 t/m 2026-11-04, 16353 candles | Binance 2024-11-03 t/m 2026-11-03 |
| EURUSD | 2024-11-04 t/m 2026-11-04, 12433 candles | HistData 2025-01-01 t/m 2026-10-23 |
| GBPUSD | 2024-11-04 t/m 2026-11-04, 12433 candles | HistData 2025-01-01 t/m 2026-10-23 |
| USDJPY | 2024-11-04 t/m 2026-11-04, 12433 candles | Yahoo 60d 2026-08-12 t/m 2026-11-04 |
| NQ | 2024-11-04 t/m 2026-11-04, 12177 candles | HistData 2025-01-01 t/m 2026-10-23 |
| ES | 2024-11-04 t/m 2026-11-04, 12161 candles | HistData 2025-01-01 t/m 2026-10-23 |
| DAX | 2024-11-04 t/m 2026-11-04, 12167 candles | Yahoo 60d 2026-08-13 t/m 2026-11-04 |
| GOUD | 2024-11-04 t/m 2026-11-04, 11824 candles | HistData 2025-01-01 t/m 2026-10-23 |
| ZILVER | 2024-11-04 t/m 2026-11-04, 11824 candles | HistData 2025-01-01 t/m 2026-10-23 |
| OLIE | 2024-11-04 t/m 2026-11-04, 11819 candles | Yahoo 60d 2026-08-26 t/m 2026-11-04 |
| AAPL | 2024-11-04 t/m 2026-11-04, 7945 candles | Yahoo 60d 2026-08-12 t/m 2026-11-04 |
| NVDA | 2024-11-04 t/m 2026-11-04, 7945 candles | Yahoo 60d 2026-08-12 t/m 2026-11-04 |
| MSFT | 2024-11-04 t/m 2026-11-04, 7946 candles | Yahoo 60d 2026-08-12 t/m 2026-11-04 |

ETH en SOL beginnen later bij Capital.com. Voor USDJPY, DAX, OLIE, AAPL, NVDA en MSFT is 5m alleen via Yahoo beschikbaar, dus 60 dagen: die 5m-cijfers zijn zwak.

### Volatiliteit en dagrange

| Markt | Jaarvol. | Laagste–hoogste 30d-vol. | Dagrange | Uurrange | Rustigst → drukst uur | Piek (NY) |
|---|---:|---:|---:|---:|---:|---:|
| BTC | 43,6% | 19,9–82,5% | 2,91% | 0,47% | 0,37 → 0,88% | 10:00 |
| ETH | 69,1% | 27,8–106,0% | 4,40% | 0,72% | 0,58 → 1,18% | 10:00 |
| SOL | 75,7% | 31,5–150,9% | 5,15% | 0,88% | 0,72 → 1,37% | 10:00 |
| EURUSD | 7,1% | 3,3–13,6% | 0,59% | 0,10% | 0,05 → 0,18% | 10:00 |
| GBPUSD | 6,8% | 3,4–11,1% | 0,61% | 0,10% | 0,06 → 0,19% | 10:00 |
| USDJPY | 9,1% | 2,5–15,8% | 0,71% | 0,12% | 0,07 → 0,18% | 10:00 |
| NQ | 21,8% | 8,8–49,9% | 1,64% | 0,24% | 0,06 → 0,63% | 9:00 |
| ES | 16,0% | 6,5–42,6% | 1,10% | 0,17% | 0,05 → 0,40% | 10:00 |
| DAX | 17,3% | 7,5–40,6% | 1,29% | 0,22% | 0,04 → 0,46% | 3:00 |
| GOUD | 24,0% | 10,3–49,8% | 1,78% | 0,31% | 0,18 → 0,54% | 9:00 |
| ZILVER | 50,0% | 17,2–138,6% | 3,18% | 0,56% | 0,31 → 1,04% | 9:00 |
| OLIE | 42,7% | 18,3–88,9% | 3,06% | 0,54% | 0,00 → 0,96% | 9:00 |
| AAPL | 29,3% | 9,6–63,5% | 2,14% | 0,40% | 0,12 → 1,25% | 9:00 |
| NVDA | 42,5% | 25,0–80,1% | 3,44% | 0,60% | 0,22 → 1,69% | 9:00 |
| MSFT | 28,2% | 10,5–46,4% | 2,16% | 0,40% | 0,14 → 1,20% | 9:00 |

Dagrange en uurrange zijn medianen, in procent van de prijs. Tijden in New Yorkse tijd. In vrijwel alle markten ligt de piek tussen 9:00 en 11:00; DAX piekt om 3:00 (opening Europa). De sessietabellen per markt staan in de JSON.

### Trend of terugkeer

De variantieverhouding (VR) vergelijkt grote met kleine bewegingen: boven 1 is trend, onder 1 terugkeer, 1 is toeval. Achter de ± staat de standaardfout: pas bij ruwweg 2× de fout is het verschil met 1 echt.

| Markt | 5m (VR12) | 1h (VR24) | Dag (VR5) | 5m-bron |
|---|---:|---:|---:|---|
| BTC | 0,94 ±0,03 | 0,95 ±0,06 | 0,93 ±0,11 | Binance |
| ETH | 0,98 ±0,02 | 1,06 ±0,06 | 0,95 ±0,11 | Binance |
| SOL | 0,94 ±0,02 | 0,98 ±0,07 | 0,89 ±0,12 | Binance |
| EURUSD | 0,92 ±0,02 | 0,95 ±0,07 | 0,96 ±0,12 | HistData |
| GBPUSD | 0,92 ±0,02 | 0,98 ±0,06 | 0,96 ±0,11 | HistData |
| USDJPY | 0,96 ±0,06 | 1,07 ±0,07 | 0,95 ±0,11 | Yahoo 60d |
| NQ | 0,99 ±0,05 | 0,99 ±0,10 | 0,84 ±0,15 | HistData |
| ES | 0,95 ±0,07 | 0,97 ±0,13 | 0,81 ±0,20 | HistData |
| DAX | 1,08 ±0,06 | 0,94 ±0,10 | 0,79 ±0,17 | Yahoo 60d |
| GOUD | 0,99 ±0,03 | 1,02 ±0,10 | 0,89 ±0,15 | HistData |
| ZILVER | 0,99 ±0,04 | 0,97 ±0,12 | 0,91 ±0,17 | HistData |
| OLIE | 1,03 ±0,05 | 0,92 ±0,10 | 0,95 ±0,12 | Yahoo 60d |
| AAPL | 1,07 ±0,09 | 0,97 ±0,13 | 1,01 ±0,15 | Yahoo 60d |
| NVDA | 0,95 ±0,08 | 0,94 ±0,09 | 0,86 ±0,12 | Yahoo 60d |
| MSFT | 0,84 ±0,10 | 1,06 ±0,10 | 1,11 ±0,12 | Yahoo 60d |

- **5m:** BTC, SOL, EURUSD en GBPUSD liggen meetbaar onder 1. Een deel kan bied-laat-gestuiter zijn, en het effect is veel kleiner dan de kosten.
- **1 uur en dag:** geen enkele markt wijkt duidelijk af van 1. De eerste en tweede helft van de periode verschillen vaak (zie JSON), bijvoorbeeld MSFT 0,82 tegen 1,31, dus een "trendmarkt" is hier geen vaste eigenschap.
- Dit past bij wat we eerder vonden: bruto rond 0R.

### Kosten

De spread is gemeten op Capital.com, per uur over 2 jaar. Financiering is een momentopname van 4 november 2026 (per dag × 365, gelezen als procent per dag) en dus geen historie.

| Markt | Spread mediaan | Aanname in `core/markets.py` | Spread / uurrange NY-ochtend | Financiering long / short per jaar | Oordeel |
|---|---:|---:|---:|---:|---|
| NQ | 0,007% | 0,008% | 1,4% | -8,2% / 0,1% | gunstig |
| ES | 0,008% | 0,008% | 1,7% | -8,2% / 0,1% | gunstig |
| DAX | 0,007% | 0,010% | 1,9% | -6,6% / -1,5% | gunstig |
| GOUD | 0,010% | 0,010% | 2,0% | -13,9% / 10,9% | gunstig |
| EURUSD | 0,006% | 0,007% | 3,6% | -5,8% / 2,8% | gemiddeld |
| USDJPY | 0,007% | 0,008% | 4,2% | 6,9% / -9,9% | gemiddeld |
| NVDA | 0,082% | 0,050% | 5,0% | -8,2% / 0,1% | gemiddeld |
| MSFT | 0,060% | 0,050% | 5,0% | -8,2% / 0,1% | gemiddeld |
| OLIE | 0,047% | 0,050% | 5,2% | -4,0% / -4,0% | gemiddeld |
| GBPUSD | 0,010% | 0,009% | 5,8% | -1,5% / -1,5% | gemiddeld |
| AAPL | 0,066% | 0,050% | 5,9% | -8,2% / 0,1% | gemiddeld |
| ETH | 0,071% | 0,080% | 6,4% | -22,5% / 5,0% | gemiddeld |
| BTC | 0,057% | 0,080% | 7,3% | -22,5% / 5,0% | ongunstig |
| ZILVER | 0,077% | 0,060% | 8,3% | -13,9% / 10,9% | ongunstig |
| SOL | 0,500% | 0,120% | 39,4% | -22,5% / 5,0% | ongunstig |

- Het oordeel is mijn eigen indeling: onder 3% gunstig, 3–7% gemiddeld, daarboven ongunstig. Het gaat alleen om kosten.
- Aandelen zijn buiten de Amerikaanse sessie 2 tot 3 keer zo duur. De DAX is 's avonds 5 keer zo duur.
- Long aanhouden kost op indices ongeveer 8% per jaar, op goud 14% en op crypto 22%. Short kost vaak niets of levert iets op. Bij langer vasthouden telt dit zwaar.

### Samenhang tussen markten

- Gemiddelde correlatie tussen markten: 0,20 op gewone dagen, 0,18 op de 23 slechtste ES-dagen. Gemiddeld verdween de spreiding in stress dus niet.
- **Groepen:** indices met tech (ES–NQ 0,95, ES–DAX 0,76, NQ–NVDA 0,75), crypto (rond 0,85), dollar-forex (EURUSD–GBPUSD 0,81, EURUSD–USDJPY −0,65), metalen (goud–zilver 0,79), olie en losse aandelen.
- Op stressdagen is olie met ES meegegaan (0,57 tegen −0,21 normaal), en crypto juist niet (rond −0,1 tegen 0,45). Dat zijn maar 23 dagen en een selectie op slechte dagen, dus dit is geen vaste regel.

### Grote gebeurtenissen en regimes

| Datum | Beweging in onze data | Oorzaak volgens bronnen |
|---|---|---|
| 3–10 april 2025 | ES −6,1% op 4 april, +9,6% op 9 april, −3,9% op 10 april | Tarieven, daarna pauze van 90 dagen. Beste S&P-dag sinds 2008 [N 1, 2] |
| 10 oktober 2025 | ES −3,4% | Dreiging van 100% tarief op China; S&P −2,7% op de slotkoers, liquidaties crypto ongeveer $19 mrd volgens CoinGlass [N 3, 4] |
| 30 januari 2026 | Goud −9,4% | Nominatie Warsh als Fed-voorzitter; zilver ongeveer −30%. Mechanisme is interpretatie [N 5, 6] |
| 5–6 februari 2026 | BTC −12,6%, dan +11,1% | Geen enkele oorzaak vastgesteld: ETF-uitstroom, liquidaties en afbouw van hefboom worden genoemd [N 7, 8] |
| 6 maart 2026 | Olie +13,8% | Oorlog VS-Israël met Iran, zorgen over aanvoer [N 9, 10] |

Dit zijn log-rendementen per CFD-handelsdag (18:00 tot 18:00 NY), dus ze wijken af van officiële slotkoersen. De volatiliteit van ES zakte van gemiddeld 28,5% in Q2 2025 naar 9,8% in Q3 2025: regimes wisselen snel. De grootste bewegingen kwamen vrijwel allemaal met groot nieuws of gedwongen verkoop; dat was vooraf niet uit de koers af te lezen. Dat laatste is mijn conclusie, geen gemeten uitslag.

### Vegingen van niveaus

Eerste veging per dag tussen 9:00 en 16:00 NY op uurcandles, over alle markten. "Terug van het niveau" telt de prijs 4 uur later. Een positief gemiddelde betekent omkeer, negatief doorlopen, in ATR van 1 uur. Voor de Azië-niveaus van aandelen zijn er te weinig vegingen; die zijn weggelaten.

| Niveau | Kans per dag, per kant | Sluit terug | Vegingen | Na 4 uur terug van het niveau | Gemiddelde na 4 uur | Alleen als de candle terugsluit | Alleen als hij voorbij sluit |
|---|---:|---:|---:|---:|---:|---:|---:|
| vorige dag | 22% | 50% | 3623 | 49% | -0,07 ATR | -0,15 ATR | +0,01 ATR |
| Azië | 30% | 49% | 4056 | 50% | -0,05 ATR | -0,04 ATR | -0,06 ATR |
| Londen | 40% | 50% | 6626 | 50% | -0,05 ATR | -0,04 ATR | -0,05 ATR |

- Van de 45 combinaties van markt en niveau wijken er 3 meer dan 2 standaardfouten van nul af. Bij toeval verwacht je er ongeveer 2. Alle 3 wijzen op doorlopen.
- Terugsluiten maakt de kans op omkeer niet beter. Uurcandles zien niet alles wat op 5m gebeurt; dit is dus een grove meting.
- Per markt: zie `sweeps` in de JSON.

### Welke markten zijn kansrijk na kosten?

- **Ruimte in de kosten:** NQ, ES, DAX, goud, liefst in de ochtend van New York.
- **Twijfel:** EURUSD, USDJPY, NVDA, MSFT, OLIE, GBPUSD, AAPL, ETH. Aandelen alleen tijdens de Amerikaanse sessie.
- **Ongunstig:** BTC en ZILVER. **SOL valt af** bij deze spread.
- **Niemand heeft bewezen voordeel.** Kansrijk betekent alleen dat de kosten een eventueel voordeel niet meteen opeten.

## 3. Deel 2: hoe handelen quants, toen en nu

### Geschiedenis

| Periode | Wie | Wat | Bewijs |
|---|---|---|---|
| 1956–1969 | Kelly, Thorp | Inzetgrootte berekenen, kaarttellen, daarna convertible hedging. Princeton Newport van 1969 tot eind jaren 80, marktneutraal | [B 11] UC Irvine-archief |
| 1950–1983 | Donchian, Dennis, Eckhardt | Regels voor trendvolging, ATR-positiegrootte. De bekende Turtle-rendementen zijn niet onafhankelijk bevestigd | [M 12] |
| 1962–2007 | Gatev e.a., Avellaneda & Lee | Paren en statistische arbitrage. Winst daalt naarmate meer quants het doen | [P 13, 14] |
| 1880–nu | Hurst e.a., Moskowitz e.a. | Trendvolging over veel markten; winst komt uit breedte | [P 15, 16] |
| 1988–2018 | Renaissance Medallion | Gerapporteerd 66% per jaar vóór kosten. Werkwijze niet openbaar, dus niet te controleren | [W 17] |

**Niet onderzocht in deze ronde:** D.E. Shaw, factorbeleggen en de theorie van market making. Daarover staan hier dus geen conclusies.

### Wat ging er mis

- **LTCM 1998:** risico te laag ingeschat door korte historie en concentratie [P 18].
- **Quant quake 2007:** veel fondsen hadden dezelfde posities; gedwongen verkoop en wegvallende marktmakers versterkten elkaar. De auteurs noemen dit voorlopig en indirect bewijs [W 19].
- **Volmageddon 2018:** producten moesten na de beurs VIX-futures kopen, wat de stijging zelf versterkte; XIV verloor 84% volgens de BIS [W 20].
- **Les:** het gevaar zit in dezelfde trade met dezelfde hefboom, en in risico meten op een rustige periode.

### Hoe trade je quant

1. Idee met een reden: wie verliest, en waarom blijft dat bestaan?
2. Data controleren, inclusief kosten en tijdstippen.
3. Regels en proeven vooraf vastleggen.
4. Toetsen op aparte tijdvakken, gecorrigeerd voor het aantal pogingen [P 21, 22].
5. Veel kleine signalen samenvoegen tot een portfolio [B 23].
6. Risico per positie, per groep en in totaal.
7. Uitvoering en kosten meten en vergelijken met de toets.
8. Klein starten, blijven meten en stoppen als het slijt.

**Wat wij hebben:** stap 2, 3, 4 en 6 zitten goed in het project. **Wat ontbreekt:** stap 1 (de reden) en stap 5 (het portfolio).

### Wat bestaat nog, en wat past bij ons?

- **Slijt:** gepubliceerde voordelen zijn 26% lager buiten de steekproef en 58% lager na publicatie [P 24]. Winstnieuws-drift op grote aandelen is sinds 2006 weg [P 25]; dat wordt deels betwist [W 26].
- **Bestaat nog, maar duur op CFD:** trendvolging. Ons eigen rapport 6 (branch `feat/meer-kansen`) laat zien dat kosten en financiering vrijwel alles opeten.
- **Niet haalbaar:** latency, market making, tick-orderflow.
- **Mogelijk haalbaar:** voorspelbare stromen van grote partijen, positionering, breedte over markten.
- **Realisme:** 97% van de Braziliaanse dagtraders die meer dan 300 dagen doorgingen verloor geld [W 27]. ESMA meldt dat 74–89% van de retail-CFD-rekeningen verliest [W 28].

## 4. Deel 3: waar komt ICT vandaan

**Stelling: "ICT is oude kennis in een nieuw jasje". Oordeel: grotendeels waar voor de kern, niet aangetoond als directe overname.**

Over Huddleston vond ik alleen tweede-handsbronnen. Eén daarvan zegt dat de naam komt van de Inner Circle Workshop van Larry Williams [M 29]; dat is de enige directe lijn die ik vond, en die is niet bevestigd.

| ICT-begrip | Oudere naam | Bron en jaartal | Onafhankelijk bewijs? |
|---|---|---|---|
| Sweep / liquidity grab | Spring en upthrust; Turtle Soup | Wyckoff, begin 20e eeuw [M 30]; Connors & Raschke 1995/96 [M 31] | **Deels:** stopclusters bestaan, maar de prijs versnelt erdoorheen voor uren [P 32]. Dat steunt het mechanisme, niet de omkeer |
| Smart money / manipulatie | Composite Man | Wyckoff [M 30] | Nee, verhaal achteraf; moeilijk te weerleggen |
| Valse opening | Oops | Larry Williams, jaartal niet gevonden [M 33] | Niet gevonden |
| Fair value gap | Geen duidelijke oudere naam gevonden | – | **Niet gevonden** |
| Order block | Geen duidelijke oudere naam gevonden | – | **Niet gevonden** |
| Kill zone | Sessies, handelen op de drukste uren | Market Profile, 1985 [B 34] als verwant idee (mijn koppeling) | **Deels:** tijdstip van volatiliteit is echt (deel 1), richting niet |
| MSS | Trendbreuk, hogere toppen en bodems | Mijn koppeling, geen bron gezocht | Niet onderzocht |
| OTE | Fibonacci-terugval | Mijn koppeling, geen bron gezocht | Niet onderzocht |

Over technische regels in het algemeen: veel schijnbare winst valt weg na correctie voor het herhaald gebruiken van dezelfde data [P 35]. **Ik vond geen peer-reviewed toets van ICT** [M 36]. Dat is geen bewijs dat die niet bestaat; de zoekronde was beperkt. Wyckoff en Dow heb ik niet in origineel gezien, en voor Dow vond ik geen bron.

**Echt nieuw lijkt:** vooral de combinatie en de taal (kill zones, FVG, order blocks als vaste volgorde op lage tijdframes). **Nieuwe naam voor oud idee:** de sweep en het verhaal van de grote partij.

**Oudere ideeën die wij missen:**

- **Volume bij de veging.** Wyckoff en VSA lezen volume, spread en slot samen [M 33]. Onze ICT-code gebruikt geen volume.
- **Waardegebied.** Market Profile kijkt waar de meeste handel plaatsvond: ongeveer 70% van de sessie [B 34]. Wij kijken alleen naar hoog en laag.
- **De context van de range.** Een spring hoort bij een accumulatierange [M 30]. Wij tellen elke veging van elk niveau.
- **Dagniveau.** Turtle Soup werkt op 20-daagse uitersten [M 31], niet op intraday-niveaus.

Dit zijn ideeën, geen bewijs.

## 5. Deel 4: wat gebruiken we niet, en kunnen we wel gebruiken

| Idee | Waarom zou het werken | Bewijs | Data en kosten | Horizon | Op CFD en 10k | Oordeel |
|---|---|---|---|---|---|---|
| Orderboek / orderflow | Onbalans duwt de prijs direct | Sterk op zeer korte termijn [P 37]; eigen toets crypto: niet aangetoond (rapport 7) | CME-tick betaald, per GB [M 38] | Seconden | Nee: feed 12,5 s achter | **Laten vallen** |
| Gamma (GEX) | Dealers met short gamma handelen mee met de beweging | Goed: momentum laatste half uur bij negatieve gamma [P 39] | SpotGamma $89–299 per maand, site onduidelijk [M 40]; historie niet bevestigd. Gratis alternatief: dagen met grote beweging | Laatste 30 min | Ja op ES/NQ | **Eerst toetsen** met gratis benadering |
| Skew | Vraag naar crashbescherming | Niet onderzocht | Betaald | Dagen | Onbekend | Niet beoordeeld |
| COT-positionering | Hedgers betalen een premie aan speculanten | Gemengd: Sharpe 0,55 bruto in één studie, geen voorspelling in een andere [W 41, M 42] | Gratis bij CFTC, wekelijks | Weken | Ja, maar financiering telt | **Eerst toetsen** |
| Crypto-funding, open interest | Hoge hefboomvraag; hoge carry voorspelt crashes | Goed voor de carry en crashes [W 43]; funding zelf niet gecontroleerd | Gratis, derde partij noemt funding vanaf 2019 [M 44] | Dagen | Als risicofilter; short ontvangt nu financiering | **Eerst toetsen** |
| Liquidaties | Gedwongen verkoop | Alleen nieuws [N 4] | Onbekend | Uren | Onbekend | Later |
| VIX-curve | Stress in de curve | Zwak voor aandelen-timing [M 45] | Gratis | Dagen | Ja | **Laten vallen** als signaal |
| Kredietspreads | Stress bij banken gaat vooraf aan economie en koersen | Sterk voor de economie [P 46], niet getoetst voor korte handel | Gratis, grotendeels maandelijks | Maanden | Past niet bij onze horizon | **Laten vallen** voor nu |
| Rente, dollar | Mondiale financiering | Niet gevonden | Gratis | Onbekend | Onbekend | Niet beoordeeld |
| Nieuws met AI | Tekst sneller en breder lezen | Lijkt te werken, maar modellen onthouden uitkomsten: vooruitkijken [W 47, 48] | Nieuws met tijdstempels, kosten onbekend | Dag | Moeilijk zuiver te toetsen | **Laten vallen** voor nu |
| Signalen combineren | Veel kleine onafhankelijke bets | Sterke theorie; geldt alleen bij onafhankelijkheid en zonder kosten [B 23] | Hebben we | Alle | Ja, op goedkope markten | **Eerst toetsen (1)** |
| Relative value | Spreads keren terug | Vroeger sterk, daalt [P 13, 14] | Hebben we | Dagen | Twee keer kosten | **Laten vallen** |
| Regimes, volatiliteit sturen | Minder risico bij hoge volatiliteit | Betwist: werkt vaak niet in echte tijd [P 49] | Hebben we | Weken | Ja | **Laten vallen** als voordeel |
| Meta-labeling | Filtert signalen | Methode beschreven [B 50], artikel Joubert niet gevonden | Hebben we | Alle | Pas nuttig bij bruto voordeel | **Later** |
| Maandeinde-herbalancering | Grote fondsen handelen voorspelbaar | Geschatte kosten $16 mrd per jaar; betwist [W 51] | Hebben we | Dagen | Ja op ES/NQ | **Eerst toetsen** |
| Volume bij vegingen | Oudere methoden lezen volume | Geen onafhankelijk bewijs gevonden | Yahoo-volume, nog te controleren hoe ver terug | Uren | Ja | Later |

## 6. Top 5 om te toetsen

**Vervangen door deel 6 van [rapport 9](9_verdieping.md).** Hieronder de eerste versie, ter vergelijking.

**Vooraf repareren: het kostenmodel.** Gebruik de gemeten spreads per uur. Anders zijn alle uitslagen te gunstig voor SOL, NVDA, ZILVER, AAPL en MSFT.

1. **Signalen combineren.** *Hypothese:* een gewogen mix van bestaande signalen op NQ, ES, DAX, goud, EURUSD en USDJPY haalt samen de poort, terwijl losse signalen dat niet doen. *Data:* hebben we. *Reden:* dit is wat quants anders doen dan wij. Ook de kortste proef of er samen iets zit.
2. **Maandeinde-herbalancering.** *Hypothese (mijn vertaling van het mechanisme):* ES en NQ bewegen de laatste dagen van de maand tegen de maandrichting in. *Data:* hebben we. *Reden:* een duidelijke tegenpartij die moet handelen, weinig varianten.
3. **COT-positionering.** *Hypothese:* extreme speculatieve posities voorspellen rendement over 1 tot 4 weken op goud, olie, forex en indices. *Data:* gratis. *Reden:* echte nieuwe informatie, maar het bewijs is gemengd en financiering telt.
4. **Crypto-funding als risicofilter.** *Hypothese:* bij extreem hoge funding is de kans op een crash hoger; long uit of short op BTC en ETH verbetert de uitkomst. *Data:* gratis, eerst bevestigen hoe ver terug. *Reden:* degelijk BIS-onderzoek, en het past bij de financiering.
5. **Slotmomentum op dagen met grote bewegingen.** *Hypothese:* het laatste half uur volgt de dagrichting vooral op grote dagen, als benadering van negatieve gamma. *Data:* hebben we. *Reden:* degelijk bewijs [P 39], en goedkoop op ES. De eerdere uurversie slaagde niet, dus de verwachting is bescheiden.

Elk idee krijgt eerst een vastgelegd protocol en telt mee in de proeven (nu 867).

## 7. Wat afvalt

| Idee | Reden |
|---|---|
| Orderboek en tick-orderflow | Horizon te kort voor onze feed, spread te groot |
| Nieuws met AI | Zuiver toetsen is moeilijk en duur; winstnieuws-drift op grote aandelen is weg |
| VIX-curve als signaal | Zwak voor aandelen-timing |
| Kredietspreads | Horizon te lang |
| Relative value | Dubbele kosten en dalende winst |
| Regimes als voordeel | Vergroot hooguit een voordeel, en is betwist |
| Meer ICT-varianten | Veging is een muntworp en geen onafhankelijk bewijs voor FVG of order blocks |
| SOL | Spread 0,50% |

## 8. Bronnenlijst

**Links zijn gezien in zoekresultaten; de meeste bronnen zijn alleen via samenvatting of abstract gelezen, niet volledig.**

**Nieuws**
1. [N] [Russell Investments, april 2025](https://russellinvestments.com/content/ri/mi/en-gb/insights/russell-research/2025/04/tariff-pause-one-day-relief.html)
2. [N] [First Citizens, tarievenpauze](https://www.firstcitizens.com/content/dam/firstcitizens/pdfs/wealth/market-outlook/2025/making-sense-temporary-tariff-reprieve.pdf)
3. [N] [PBS/AP, 10 oktober 2025](https://www.pbs.org/newshour/economy/wall-street-tumbles-in-its-worst-day-since-april-after-trump-threatens-more-tariffs-on-china)
4. [N] [Gigazine, crypto-liquidaties](https://www.gigazine.net/gsc_news/en/20251014-crypto-market-record-liquidations)
5. [N] [The National, 30 januari 2026](https://www.thenationalnews.com/business/markets/2026/01/30/gold-plummets-and-dollar-strengthens-on-trumps-fed-chair-nomination/)
6. [N] [Fortune, Warsh](https://fortune.com/2026/01/31/what-happened-gold-silver-dollar-markets-kevin-warsh-fed-reaction/?rand=8593)
7. [N] [Good Morning America, bitcoin](https://www.goodmorningamerica.com/news/story/price-bitcoin-plummeted-experts-explain-129778940)
8. [N] [Cointelegraph via TradingView, drie theorieën](https://www.tradingview.com/news/cointelegraph:940985e5b094b:0-what-crashed-bitcoin-three-theories-behind-btc-s-trip-below-60k/)
9. [N] [Trading Economics, ruwe olie](https://tradingeconomics.com/commodity/crude-oil/news/531231)
10. [N] [StreetInsider, Iran en WTI](https://www.streetinsider.com/Commodities/Iran+war+sends+US+crude+futures+up+12%25+a+barrel/26121537.html)

**Quants**
11. [B] [UC Irvine, carrière Thorp](https://lib.uci.edu/online-exhibits/finding-edge-work-and-insights-edward-o-thorp/career-quantitative-finance)
12. [M] [TurtleTrader, Covel](https://www.turtletrader.com/turtle-trading/)
13. [P] [Gatev, Goetzmann, Rouwenhorst](https://typeset.io/pdf/pairs-trading-performance-of-a-relative-value-arbitrage-rule-3h4p6kue3i.pdf)
14. [P] [Avellaneda & Lee, Quantitative Finance 2010](https://econpapers.repec.org/RePEc:taf:quantf:v:10:y:2010:i:7:p:761-782)
15. [P] [Hurst, Ooi, Pedersen, JPM 2017](https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing?aqrPDF=1)
16. [P] [Moskowitz, Ooi, Pedersen, JFE 2012, samenvatting](https://alphaarchitect.com/cross-asset-signals-and-time-series-momentum/)
17. [W] [Cornell over Medallion, via Institutional Investor](https://www.institutionalinvestor.com/article/2bswymr8cih3jeaslxc00/portfolio/famed-medallion-fund-stretches-explanation-to-the-limit-professor-claims); publicatie in een tijdschrift niet bevestigd
18. [P] [Jorion 2000](https://ideas.repec.org/a/bla/eufman/v6y2000i3p277-300.html)
19. [W] [Khandani & Lo, NBER](https://nber.org/system/files/working_papers/w14465/w14465.pdf)
20. [W] [BIS Quarterly Review, maart 2018](https://www.bis.org/publ/qtrpdf/r_qt1803t.htm)
21. [P] [Bailey & López de Prado, Deflated Sharpe](https://papers.ssrn.com/abstract=2460551)
22. [P] [Sullivan, Timmermann, White 1999](https://econpapers.repec.org/RePEc:bla:jfinan:v:54:y:1999:i:5:p:1647-1691)
23. [B] [Robeco over de fundamentele wet](https://www.robeco.com/en-int/insights/2018/04/fundamental-law-of-active-management-shows-way-to-higher-information-ratio)
24. [P] [McLean & Pontiff, werkversie](https://ivey.uwo.ca/media/3775549/pontiff.pdf)
25. [P] [Martineau, Critical Finance Review 2022](https://nowpublishers.com/article/Details/CFR-0122)
26. [W] [UCLA Anderson over Subrahmanyam](https://anderson-review.ucla.edu/is-post-earnings-announcement-drift-a-thing-again/)
27. [W] [Chague e.a., Day Trading for a Living?](https://repositorio.fgv.br/items/e87d04fc-4b4c-4a56-ab5a-1c84c1afde1b/full)
28. [W] [ESMA, maart 2018](https://www.esma.europa.eu/node/84933)

**ICT en voorlopers**
29. [M] [ATAS over ICT](https://atas.net/blog/what-is-the-smart-money-concept-and-how-does-the-ict-trading-strategy-work)
30. [M] [Capital.com over Wyckoff](https://capital.com/en-gb/learn/technical-analysis/the-wyckoff-method); originele cursus niet gezien
31. [M] [Oxford Capital, Turtle Soup](https://oxfordstrat.com/?p=5614); [Stocks & Commodities](https://technical.traders.com/tradersonline/display.asp?art=2414)
32. [P] [Osler 2005, NY Fed-versie](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr150.pdf)
33. [M] [Oops-patroon](https://steadyoptions.com/articles/the-oops-signal-trade-r415/); [Volume Spread Analysis](https://safehaven.com/article/21587/volume-spread-analysis-improved-with-wyckoff-20)
34. [B] [Market Profile op Wikipedia](https://en.wikipedia.org/wiki/Market_profile)
35. [P] Zie 22
36. [M] [Blog over ICT-bewijs](https://thortradecopier.com/blog/does-ict-smart-money-concepts-work); alleen een vendorbron

**Data en signalen**
37. [P] [Cont, Kukanov, Stoikov 2014](https://arxiv.org/abs/1011.6402)
38. [M] [Databento, prijzen](https://databento.com/pricing)
39. [P] [Baltussen e.a., JFE 2021](https://econpapers.repec.org/RePEc:eee:jfinec:v:142:y:2021:i:1:p:377-403)
40. [M] [SpotGamma, kosten](https://support.spotgamma.com/hc/en-us/articles/1500002666102-What-is-the-cost-of-a-SpotGamma-Subscription); [FlashAlpha-review](https://flashalpha.com/articles/spotgamma-review-2026-pricing-features-alternatives)
41. [W] [Rouwenhorst & Tang](https://www7.uc.cl/economia/finance_uc/docs/conferences/11th/Rouwenhorst-Tale%20of%20two%20premiums.pdf)
42. [M] [CXO Advisory over speculatieve druk](https://www.cxoadvisory.com/commodity-futures/commodity-futures-investing-updates); originele artikel niet gezien
43. [W] [Schmeling, Schrimpf, Todorov, BIS 1087](https://www.bis.org/publ/work1087.pdf)
44. [M] [CryptoDataDownload-catalogus](https://api.cryptodatadownload.com/static/catalog/CDD_Data_Catalog.html)
45. [M] [Macrosynergy over de VIX-curve](https://macrosynergy.com/?p=41000)
46. [P] [Gilchrist & Zakrajšek, AER 2012](https://www.nber.org/papers/w17021)
47. [W] [Glasserman & Lin](https://arxiv.org/pdf/2309.17322)
48. [W] [A Test of Lookahead Bias in LLM Forecasts](https://arxiv.org/html/2512.23847v1)
49. [P] [Cederburg e.a., JFE 2020](https://econpapers.repec.org/RePEc:eee:jfinec:v:138:y:2020:i:1:p:95-117)
50. [B] [Inhoud Advances in Financial Machine Learning](https://toc.uni.li/FLMF049641.pdf)
51. [W] [Harvey, Mazzoleni, Melone, NBER 33554](https://ideas.repec.org/p/nbr/nberwo/33554.html); [tegengeluid L&G](https://am.landg.us.com/insights/insights-blog/a-rebuttal-of-rebalancing-downsides)
