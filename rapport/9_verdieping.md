# Verdieping: originele papers, data-controle en nieuwe metingen

Datum: 5 november 2026. Vervolg op [rapport 8](8_markt_quant_ict.md); dit herhaalt dat rapport niet. Cijfers: `rapport/marktonderzoek2.json`, code: `research/marktonderzoek2.py`. Er is niets aan de bot veranderd en geen strategie getoetst.

**Bewust niet gemeten:** maandeinde, COT, funding, slotmomentum en combinaties. Als ik die nu bekijk, zijn ze straks niet meer zuiver te toetsen.

## 1. Wat verandert er?

1. **FVG's worden in echte data minder vaak gevuld dan in door elkaar gegooide data.** "Een FVG wordt meestal gevuld" zegt dus niets: toeval doet het vaker. Na de vulling is de richting een muntworp.
2. **Het omkeereffect bij ronde getallen uit 1996–98 zien we nu niet terug.** Ronde getallen gedragen zich hier als willekeurige niveaus.
3. **De 15 markten zijn ongeveer 5,3 onafhankelijke bets.** Dat zet een plafond op wat combineren kan opleveren.
4. **Stops zijn geen harde grens.** Bij heropening na een sluiting is 1 op de 20 koerssprongen op indices groter dan 3 keer de uur-ATR.
5. **Spreads zijn in stress duurder.** Op de 10 drukste dagen zijn ze op indices en goud 1,3 tot 1,6 keer zo groot; op enkele momenten lopen ze bij aandelen op tot 0,4–0,9%.
6. **Drie hypotheses uit rapport 8 zijn door het lezen van de originelen bijgesteld.** De nieuwe volgorde staat in deel 6.

## 2. Nieuwe metingen

### FVG tegen toeval

5m-candles in NY AM (9:30–11:30). "Door elkaar" betekent dezelfde candles per dag in willekeurige volgorde. "Gevuld" betekent binnen 12 candles terug op het midden van de gap. De laatste kolommen meten 12 candles na de vulling, in de richting van de FVG.

| Markt | FVG per 100 candles (echt / toeval) | Gevuld (echt / toeval) | Na vulling echt | Na vulling toeval | Richting klopt (echt / toeval) |
|---|---:|---:|---:|---:|---:|
| NQ | 23,4 / 24,9 | 66,1% / 75,1% | -0,04 ±0,06 ATR | -0,06 ±0,06 ATR | 50,7% / 50,1% |
| ES | 23,4 / 26,1 | 67,3% / 74,8% | +0,06 ±0,06 ATR | +0,05 ±0,06 ATR | 51,6% / 50,0% |
| GOUD | 21,1 / 24,0 | 69,8% / 75,5% | -0,03 ±0,05 ATR | -0,00 ±0,06 ATR | 50,4% / 50,4% |
| EURUSD | 22,5 / 26,4 | 72,0% / 75,5% | +0,01 ±0,05 ATR | -0,09 ±0,06 ATR | 49,6% / 49,1% |
| GBPUSD | 22,7 / 26,8 | 70,5% / 75,4% | -0,07 ±0,06 ATR | +0,00 ±0,06 ATR | 48,9% / 50,6% |
| BTC | 25,9 / 30,4 | 70,2% / 74,8% | -0,10 ±0,05 ATR | +0,03 ±0,05 ATR | 47,5% / 49,6% |

- Elke vierde candle maakt een FVG: het is geen bijzonder patroon.
- In toeval wordt 75% gevuld, in echte data 66–72%. Echte data lopen dus iets vaker door.
- Geen van de markten laat na de vulling een richting zien die er in de toevalsreeks niet ook is. BTC is zelfs licht negatief.
- **Grens:** door elkaar gooien binnen een dag haalt ook de volatiliteitsopbouw weg. Dit toetst de losse FVG, niet de hele ICT-volgorde.

### Ronde getallen (naar Osler)

Eerste aanraking per dag tussen 9:00 en 16:00 NY. "Terug" betekent dat de prijs 15 minuten later aan dezelfde kant staat als ervoor; BTC op 5m, dus na 15 minuten via 3 candles. Willekeurige niveaus liggen op 37% en 71% van de stap.

| Markt | Stap | Rond: terug | Willekeurig: terug | Verschil | Aantal (rond / willekeurig) |
|---|---:|---:|---:|---:|---:|
| EURUSD | 0,01 | 49,5% | 53,6% | -4,1 ±4,2 | 208 / 422 |
| GBPUSD | 0,01 | 44,1% | 47,7% | -3,6 ±3,9 | 247 / 503 |
| NQ | 100 | 50,6% | 49,8% | +0,8 ±1,5 | 1617 / 3176 |
| ES | 50 | 49,8% | 50,0% | -0,2 ±2,4 | 621 / 1254 |
| GOUD | 10 | 53,0% | 53,6% | -0,6 ±1,2 | 2378 / 4773 |
| ZILVER | 1 | 49,9% | 48,7% | +1,2 ±2,3 | 713 / 1439 |
| BTC | 1.000 | 51,1% | 52,6% | -1,5 ±1,6 | 1412 / 2862 |

Osler vond in 1996–98 voor dollar-mark 59,3% tegen 54,8%. Hier is geen enkel verschil groter dan ruwweg 2 standaardfouten, en de EUR en GBP gaan de andere kant op. Onze definitie is niet gelijk aan die van Osler en de periode is kort, dus dit weerlegt het oude resultaat niet. Het laat wel zien dat het nu niet zomaar te gebruiken is.

### Breedte

Over 448 gemeenschappelijke handelsdagen is het effectieve aantal onafhankelijke markten **5,3**. De eerste factor verklaart 35% van de samenhang, en 6 factoren verklaren 80%.

Combineren helpt dus wel, maar de winst in Sharpe is bij gelijkwaardige bets ruwweg de wortel van het aantal: ongeveer 2,3 keer, niet 3,9 keer. Dit is rekenwerk op de fundamentele wet, geen meting van een strategie.

### Staarten en gaten

| Markt | Kurtosis dag | Slechtste / beste dag | Dagen > 3 sd | Uren > 3 ATR | Grootste uur | Gat p50 / p95 / max (ATR) |
|---|---:|---:|---:|---:|---:|---:|
| BTC | 3,3 | -12,6% / +11,1% | 10 | 2,0% | 13,8 ATR | 0,3 / 1,1 / 4,1 |
| ETH | 3,6 | -15,9% / +19,0% | 11 | 2,0% | 13,0 ATR | 0,4 / 1,4 / 2,9 |
| SOL | 3,4 | -21,5% / +21,7% | 8 | 1,4% | 12,9 ATR | 0,4 / 1,7 / 3,4 |
| EURUSD | 3,0 | -1,8% / +2,2% | 10 | 1,5% | 10,6 ATR | 0,6 / 3,5 / 5,0 |
| GBPUSD | 0,6 | -1,6% / +1,3% | 2 | 1,4% | 14,1 ATR | 0,4 / 2,9 / 4,3 |
| USDJPY | 2,3 | -2,4% / +2,0% | 11 | 1,6% | 16,8 ATR | 0,4 / 3,2 / 11,6 |
| NQ | 10,8 | -6,3% / +11,6% | 6 | 2,7% | 8,7 ATR | 0,6 / 3,8 / 6,1 |
| ES | 18,4 | -6,1% / +9,6% | 6 | 2,2% | 10,7 ATR | 0,6 / 3,9 / 5,9 |
| DAX | 10,7 | -6,2% / +9,1% | 4 | 1,7% | 10,1 ATR | 0,5 / 3,1 / 8,0 |
| GOUD | 3,9 | -9,3% / +6,1% | 5 | 1,4% | 8,2 ATR | 0,3 / 2,0 / 4,6 |
| ZILVER | 21,4 | -30,4% / +9,9% | 4 | 1,5% | 8,5 ATR | 0,3 / 1,9 / 4,0 |
| OLIE | 3,3 | -10,6% / +13,8% | 9 | 1,6% | 15,1 ATR | 0,5 / 3,8 / 15,1 |
| AAPL | 7,7 | -8,7% / +12,9% | 9 | 4,0% | 16,0 ATR | 0,5 / 2,1 / 7,6 |
| NVDA | 4,0 | -14,9% / +15,4% | 6 | 3,1% | 12,2 ATR | 0,6 / 2,7 / 7,7 |
| MSFT | 7,1 | -6,6% / +11,8% | 7 | 3,7% | 23,5 ATR | 0,6 / 2,2 / 7,9 |

- "Gat" is de koerssprong bij heropening na meer dan 2 uur zonder candles, in uur-ATR.
- De dikste staarten zitten bij ZILVER (21,4, door de val van januari 2026) en ES (18,4, door april 2025).
- **Gevolg:** de backtest-engine sluit gaten op de open, dus dat is verwerkt. Live risico per trade kan groter zijn dan 1R; de grenzen in `risk/` moeten dat aankunnen.

### Spread in stress

Tussen 9:00 en 16:00 NY, op de 10 dagen met de grootste som van uurranges.

| Markt | Normaal | Top 10 dagen | Factor | Hoogste ooit |
|---|---:|---:|---:|---:|
| BTC | 0,057% | 0,062% | 1,1× | 0,16% |
| ETH | 0,071% | 0,085% | 1,2× | 0,15% |
| SOL | 0,500% | 0,500% | 1,0× | 0,56% |
| EURUSD | 0,006% | 0,005% | 0,9× | 0,12% |
| GBPUSD | 0,010% | 0,010% | 1,0× | 0,17% |
| USDJPY | 0,007% | 0,007% | 1,0× | 0,06% |
| NQ | 0,007% | 0,010% | 1,3× | 0,04% |
| ES | 0,006% | 0,008% | 1,3× | 0,04% |
| DAX | 0,006% | 0,009% | 1,5× | 0,04% |
| GOUD | 0,010% | 0,015% | 1,6× | 0,05% |
| ZILVER | 0,069% | 0,106% | 1,5× | 0,58% |
| OLIE | 0,047% | 0,083% | 1,8× | 0,14% |
| AAPL | 0,050% | 0,073% | 1,4× | 0,63% |
| NVDA | 0,064% | 0,105% | 1,6× | 0,39% |
| MSFT | 0,038% | 0,053% | 1,4× | 0,87% |

Backtests met een vaste spread zijn op de dagen die er het meest toe doen dus te gunstig.

### Wanneer valt de dagtop of -bodem?

Aandeel van de dagen waarop het hoogste of laagste punt in die sessie valt, tegen het aandeel uren van die sessie.

| Markt | NY-ochtend: top / bodem / uren | NY-middag: top / bodem / uren | Avond: top / bodem / uren |
|---|---:|---:|---:|
| BTC | 18% / 17% / 13% | 17% / 20% / 17% | 28% / 30% / 17% |
| ETH | 14% / 16% / 13% | 17% / 20% / 17% | 29% / 30% / 17% |
| SOL | 16% / 15% / 13% | 16% / 20% / 17% | 30% / 32% / 17% |
| EURUSD | 16% / 17% / 13% | 13% / 14% / 17% | 32% / 35% / 17% |
| GBPUSD | 16% / 16% / 13% | 13% / 12% / 17% | 33% / 35% / 17% |
| USDJPY | 13% / 15% / 13% | 13% / 11% / 17% | 41% / 34% / 17% |
| NQ | 24% / 26% / 13% | 28% / 21% / 17% | 22% / 27% / 15% |
| ES | 22% / 21% / 13% | 34% / 25% / 17% | 19% / 25% / 15% |
| DAX | 19% / 17% / 13% | 12% / 14% / 17% | 21% / 18% / 15% |
| GOUD | 22% / 21% / 13% | 16% / 14% / 17% | 24% / 26% / 13% |
| ZILVER | 19% / 20% / 13% | 18% / 15% / 17% | 21% / 25% / 13% |
| OLIE | 19% / 23% / 13% | 22% / 21% / 17% | 21% / 16% / 13% |
| AAPL | 44% / 35% / 19% | 25% / 24% / 25% | 13% / 14% / 21% |
| NVDA | 35% / 34% / 19% | 20% / 21% / 25% | 22% / 24% / 21% |
| MSFT | 36% / 38% / 19% | 25% / 22% / 25% | 15% / 17% / 21% |

"Avond" bevat het begin en einde van de handelsdag (18:00), en uitersten vallen ook bij toeval vaker aan de randen van een periode. Daarom is de hoge score daar geen bewijs. De ochtend in New York scoort meestal boven zijn aandeel uren, wat past bij de hogere volatiliteit. Dit bewijst geen ICT-kill zone: het volgt uit waar de beweging zit.

## 3. Wat de originelen zeggen

| Bron | Rapport 8 zei | Origineel zegt | Gevolg |
|---|---|---|---|
| Harvey e.a. 2025, herzien 2026 [1] | Maandeinde: tegen de maandrichting | Twee signalen uit een gesimuleerde 60/40-portefeuille. Het drempelsignaal werkt binnen de maand, het kalendersignaal rond maandeinde. Na overgewicht aandelen dalen die de volgende dag 17 bp. Strategie: S&P tegen 10-jaars, Sharpe boven 1 over 1997–2023 | Hypothese herschreven; het gaat om een signaal uit aandelen en obligaties, niet om een kalenderdatum |
| Baltussen e.a. 2021 [2] | Slotmomentum bij negatieve gamma | Sharpe 0,87–1,73 per beleggingssoort vóór kosten. De auteurs melden dat het voor veel beleggers na kosten mogelijk niet haalbaar is, en een positieve netto Sharpe op S&P-futures bij kosten van 1 tick | Wij betalen ongeveer 0,6 punt op ES, ruim 2 ticks. Verwachting omlaag |
| Fan e.a. 2020 [3] | Sharpe 0,55 | Long-short over veel futures, maandelijks herbalanceren, premies van 2,51–4,12% per jaar | Financiering van 8–14% op long is groter dan de premie. Verwachting omlaag |
| Osler 2005 [4] | Prijs versnelt bij stopclusters | Klopt, en ook: bij clusters van take-profits, vooral ronde getallen, keert de prijs vaker om | Beide bestaan. Bij ons is de omkeer niet zichtbaar |
| McLean & Pontiff 2016 [5] | Ongeveer een derde lager | 26% lager buiten de steekproef en 58% lager na publicatie, 97 voorspellers | Cijfer bevestigd |
| Cederburg e.a. 2020 [6] | Werkt vaak niet in echte tijd | In directe vergelijking geen systematische verbetering, over 103 strategieën | Bevestigd |

De BIS-paper over crypto-carry kon ik niet in volledige tekst openen; daar heb ik alleen de samenvatting [7]. Die noemt dat hoge carry crashes voorspelt, maar geeft geen horizon of effectgrootte.

## 4. Open punten uit rapport 8, nu ingevuld

- **D.E. Shaw.** Opgericht in 1988 door een hoogleraar informatica die eerder bij Morgan Stanley aan statistische arbitrage werkte. Begon marktneutraal [N 8].
- **Factoren.** Waarde en momentum werken over acht markten en beleggingssoorten [P 9]; carry gaf gemiddeld Sharpe 0,7, volgens een tweede-handsbron [P 10]. De hoge lat: een nieuwe factor heeft eigenlijk een t-waarde boven 3 nodig [P 11].
- **Market making.** Twee risico's: voorraad en handelen tegen beter geïnformeerden [P 12]. Niet voor ons.
- **Machine learning.** Bomen en neurale netten winnen op aandelen, en alle methoden vinden dezelfde signalen: momentum, liquiditeit en volatiliteit [P 13]. Dat is een breed aandelenpanel; ons probleem is veel kleiner.
- **Volatiliteitspremie.** Optieverkopers krijgen een premie die gewone factoren niet verklaren [P 14]. Volmageddon laat de keerzijde zien. Niet te doen op CFD's.
- **Skew.** Aandelen met de steilste smirk blijven 10,9% per jaar achter [P 15]. Dit vraagt optiedata en een breed aandelenuniversum; wij hebben 3 aandelen. **Laten vallen.**
- **Rente en dollar.** Cross-asset momentum: 45% hogere Sharpe dan gewone tijdreeksmomentum [P 16]; dollar-carry is een losstaande premie [P 17]. Maandelijks van aard, dus financiering telt zwaar. **Later.**
- **VPIN.** De bedenkers en critici zijn het oneens of het meer zegt dan volume en volatiliteit [W 18]. **Laten vallen.**
- **Nieuws.** Tekst kan rendement voorspellen [W 19], maar de zuivere toets is lastig [W 20]. Oordeel blijft staan.
- **Meta-labeling.** Bestaat als gepubliceerd artikel [M 21]; het artikel zelf niet gelezen.
- **Technische analyse.** Winst tot begin jaren 90, met twijfel over risico en kosten [P 22]. Sommige patronen voegen informatie toe [P 23]. Dow Theory: Hamilton haalde voor 1929 positieve risicogecorrigeerde rendementen [P 24]. Daarna minder, volgens een samenvatting.
- **Steunen en weerstanden.** Niveaus van banken voorspelden intraday-onderbrekingen beter dan willekeurige niveaus [P 25]. Dat is onafhankelijk bewijs dat niveaus kúnnen werken, wel in forex in de jaren 90.
- **Wyckoff.** *Studies in Tape Reading* verscheen in 1910 onder het pseudoniem Rollo Tape [B 26]. Tekst zelf niet gelezen; de cursus uit de jaren 30 niet bevestigd.
- **Nieuw idee: FOMC.** Aandelen stegen sterk in de uren vóór Fed-besluiten [P 27]. Goedkoop op ES en met weinig handelsmomenten. Niet in de top 5: te weinig trades voor P1 per jaar.

## 5. Datacontrole voor de toetsen

| Data | Gecontroleerd op 5 november | Resultaat |
|---|---|---|
| Funding Binance | API en maandbestanden | BTC vanaf september 2019; bestanden vanaf januari 2020 |
| Open interest en long/short Binance | Dagbestanden `metrics` | Vanaf september 2020 |
| COT | Bestanden CFTC 2024 bereikbaar | Ja, financieel en gedisaggregeerd |
| Yahoo 1h-volume NQ, ES, goud | Download | 2 jaar en 5 maanden, ruim 96% met volume |
| VIX, VIX3M, dollarindex, 10-jaars, HYG | Download dag | 10 jaar |

Dit vervangt de derde-partij-bron uit rapport 8 voor funding.

## 6. Bijgestelde volgorde

Vooraf blijft staan: **het kostenmodel repareren**, nu ook met duurdere spreads op drukke dagen.

| # | Idee | Hypothese | Verwachting |
|---|---|---|---|
| 1 | Signalen combineren | Een mix op de goedkope markten haalt de poort waar losse signalen dat niet doen | Bescheiden; plafond door 5,3 onafhankelijke bets |
| 2 | Herbalanceringssignaal | Het drempelsignaal uit een 60/40 van ES en 10-jaars (Yahoo) voorspelt ES de volgende dag, en alleen ES wordt verhandeld | Redelijk, duidelijke tegenpartij [ook 28]; wij missen de obligatiekant |
| 3 | Slotmomentum op grote dagen | Laatste half uur volgt de dag vooral op grote dagen | Laag, kosten ruim 2 ticks |
| 4 | COT | Speculatieve druk voorspelt 1–4 weken op goud, olie, forex, indices | Laag, financiering groter dan de premie; short is kansrijker |
| 5 | Crypto-funding als risicofilter | Extreme funding gaat vooraf aan grotere dalingen | Onzeker: geen studie gevonden die dit direct aantoont; de papers over perpetuals gaan over prijsvorming [29] |

De Sharpe-bewijzen uit deze papers komen uit lange reeksen met goedkope futures. Geen ervan is op CFD's gemeten.

## 7. Bronnen

De volledige tekst doorzocht en de relevante passages gelezen: 1 tot en met 5. Nummer 6 alleen opgehaald, de cijfers komen uit de samenvatting. De overige alleen via abstract of samenvatting.

1. [W] [Harvey, Mazzoleni, Melone, NBER 33554](https://www.nber.org/papers/w33554)
2. [P] [Baltussen e.a., JFE 2021](https://econpapers.repec.org/RePEc:eee:jfinec:v:142:y:2021:i:1:p:377-403)
3. [P] [Fan e.a., Speculative Pressure](https://openaccess.city.ac.uk/id/eprint/23283)
4. [P] [Osler, NY Fed Staff Report 150](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr150.html)
5. [P] [McLean & Pontiff 2016](https://www.gwern.net/doc/economics/2016-mclean.pdf)
6. [P] [Cederburg e.a. 2020](https://www.lehigh.edu/~xuy219/research/COWY.pdf)
7. [W] [Schmeling, Schrimpf, Todorov, BIS 1087](https://www.bis.org/publ/work1087.pdf)
8. [N] [Public Integrity over D.E. Shaw](https://publicintegrity.org/politics/cyber-profits-add-up-to-secretive-success-story/)
9. [P] [Asness, Moskowitz, Pedersen 2013](https://www.aqr.com/library/journal-articles/value-and-momentum-everywhere)
10. [P] [Koijen e.a., Carry, JFE 2018](https://econpapers.repec.org/RePEc:eee:jfinec:v:127:y:2018:i:2:p:197-225); [samenvatting](https://www.etf.com/node/94312.md)
11. [P] [Harvey, Liu, Zhu 2016](https://papers.ssrn.com/abstract=2513152)
12. [P] [Avellaneda & Stoikov](https://math.nyu.edu/%7Eavellane/HighFrequencyTrading.pdf)
13. [P] [Gu, Kelly, Xiu 2020](https://nber.org/papers/w25398)
14. [P] [Carr & Wu 2009](https://ideas.repec.org/a/oup/rfinst/v22y2009i3p1311-1341..html)
15. [P] [Xing, Zhang, Zhao 2010](https://ideas.repec.org/a/cup/jfinqa/v45y2010i03p641-662_00.html)
16. [P] [Pitkäjärvi e.a. 2020](https://research.vu.nl/en/publications/cross-asset-signals-and-time-series-momentum/)
17. [P] [Lustig, Roussanov, Verdelhan 2014](https://www.nber.org/papers/w16427)
18. [W] [Andersen & Bondarenko](https://repec.econ.au.dk/repec/creates/rp/13/rp13_43.pdf); [Easley e.a.](https://papers.ssrn.com/abstract=2062450)
19. [W] [Ke, Kelly, Xiu](https://www.nber.org/papers/w26186)
20. [W] [Glasserman & Lin](https://arxiv.org/pdf/2309.17322)
21. [M] [Meta-Labeling op Wikipedia](https://en.wikipedia.org/wiki/Meta-Labeling)
22. [P] [Park & Irwin 2007](https://ideas.repec.org/a/bla/jecsur/v21y2007i4p786-826.html)
23. [P] [Lo, Mamaysky, Wang 2000](https://www.nber.org/papers/w7613)
24. [P] [Brown, Goetzmann, Kumar 1998](https://archive.nyu.edu/handle/2451/26858)
25. [P] [Osler 2000](https://www.newyorkfed.org/medialibrary/media/research/epr/00v06n2/0007osle.html)
26. [B] [Studies in Tape Reading, antiquariaat](https://www.baumanrarebooks.com/rare-books/wyckoff-richard-d-/studies-in-tape-reading/69891.aspx)
27. [P] [Lucca & Moench 2015](https://econpapers.repec.org/RePEc:bla:jfinan:v:70:y:2015:i:1:p:329-371)
28. [P] [Etula e.a., Dash for Cash](https://econpapers.repec.org/RePEc:oup:rfinst:v:33:y:2020:i:1:p:75-111.)
29. [W] [He e.a., Fundamentals of Perpetual Futures](https://arxiv.org/abs/2212.06888v2)
