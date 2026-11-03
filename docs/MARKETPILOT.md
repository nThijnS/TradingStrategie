# MarketPilot: naam, saldo, keten per markt en beperkingen (3 november 2026)

MarketPilot is de nieuwe naam van het project dat eerder TradingStrategie heette. Dit document beschrijft:
- welke verwijzingen zijn hernoemd en welke bewust zijn gebleven;
- hoe het demo-saldo en de storting van 3 november worden verwerkt;
- hoe elke markt door de keten loopt (data → onderzoek → selectie → signaal → demo-uitvoering);
- wat er per markt nog blokkeert.

Geen financieel advies. Historische en gesimuleerde resultaten zijn geen bewijs van toekomstige winst.

## 1. Naam

### Hernoemd (alleen zichtbare naam)

| Waar | Was | Nu |
|---|---|---|
| Website `docs/index.html` | titel en kop "TradingStrategie Radar"; tekst "GitHub > Actions > TradingStrategie" | "MarketPilot Radar"; "GitHub > Actions > MarketPilot" |
| Workflow `tradingstrategie.yml` | weergavenaam `TradingStrategie`, commentaar | `MarketPilot` |
| Commits van de workflows | auteur `TradingStrategie-bot` | `MarketPilot-bot` (zelfde e-mailadres) |
| Meldingen (macOS en ntfy, `app/alerts.py`) | titel "TradingStrategie" bij start en dagmelding | "MarketPilot" |
| Startbestand Mac | `Start TradingStrategie.command` | `Start MarketPilot.command`; het oude bestand start nu het nieuwe |
| `README.md`, `docs/ARCHITECTUUR.md`, docstrings (`storage/paths.py`, `backtesting/engine.py`, `learning/ict.py`) | TradingStrategie | MarketPilot |
| Versiegeschiedenis van het dashboard | – | versie 4.0 "Nieuwe naam MarketPilot" |

### Bewust behouden (technische identifiers)

| Identifier | Waarom niet veranderd |
|---|---|
| GitHub-repository `nThijnS/TradingStrategie` en de remote URL | Opdracht. |
| Website `https://nthijns.github.io/TradingStrategie/`, `REPO` in `docs/index.html`, de raw-URL's (`raw/main/lab.json`, branch `live`) | Deze URL's volgen de repositorynaam. Ze veranderen pas als de repository wordt hernoemd, en dan breken bladwijzers en de lopende keten. |
| Workflowbestand `.github/workflows/tradingstrategie.yml` | De keten herstart zichzelf via `actions/workflows/tradingstrategie.yml/dispatches`. Een nieuwe bestandsnaam breekt de lopende keten. |
| Concurrency-groep `tradingstrategie` | Een nieuwe groepsnaam laat tijdens de overgang twee ketens tegelijk draaien, met dubbele meldingen en orders tot gevolg. |
| Commando's en modules `tradingstrategie.py`, `leren.py`, `strategielab.py`, `broker.py`, `live_status.py`, `capital_instrumenten.py` en de andere doorverwijzingen | De workflows, de Mac-starter en oude imports roepen ze aan. |
| `localStorage`-sleutels `radar-risk` en `prop` op de website | Bewaarde instellingen van bezoekers blijven werken. |
| De map `TradingStrategie-git` op deze Mac | Lokale map; niet nodig voor de werking. |
| Gearchiveerde scripts (`research/archief/`, `dashboard/archief/`) en eerdere rapporten (`rapport/`, `docs/refactor/`) | Historische stukken; die beschrijven de toestand van toen. |

## 2. Saldo, storting en risicobasis

### Wat er gebeurd is

Op 3 november om ongeveer 13:23 UTC is de demo bij Capital.com aangevuld met de knop "Aanvullen met €10.000". Die telde € 10.000 op bij het bestaande saldo van € 995,05, zodat de broker nu **€ 10.995,05** toont. Het bedoelde totaal was € 10.000. Het saldo is daarna niet meer veranderd en de rekening is niet gereset.

### Hoe MarketPilot dit verwerkt (`risk/administratie.py`)

| Begrip | Waarde nu | Bron |
|---|---|---|
| Saldo bij de broker (NAV) | **€ 10.995,05**, zo getoond | Capital.com, elke ronde |
| Startkapitaal | € 1.000,00 | `config.json` → `administratie.startkapitaal` (het eerste saldo dat de bot zag, 31 oktober) |
| Geldstromen | **+€ 10.000,00** storting op 3 november | `config.json` → `administratie.geldstromen`, met de hand vastgelegd |
| Inleg | € 11.000,00 | startkapitaal + geldstromen |
| Handelsresultaat | **−€ 4,95** (de GOUD-trade van 2 november) | saldo − inleg |
| Risicobasis | **€ 10.000** | `config.json` → `demo.risicokapitaal` |
| Risicovermogen | € 9.995,05 | min(risicobasis + handelsresultaat, saldo) |
| Risico per trade | hoogstens **€ 49,98** (0,5% van € 9.995,05; nooit meer dan € 50) | `demo.risico_pct` × min(risicovermogen, risicobasis) |

- **De storting is geen winst.** Het handelsresultaat is saldo min inleg, dus een geldstroom verandert het niet.
  - Het dashboard toont het saldo, de geldstromen en het handelsresultaat apart.
  - De grafiek toont de accountwaarde zonder geldstromen, zonder sprong van € 10.000.
- **Dag- en totaalverliesgrens.** Die rekenen met het risicovermogen: risicobasis + handelsresultaat. De piek en de dagstart worden bewaard als handelsresultaat. Een storting schuift ze daardoor niet op en maakt ook geen extra ruimte. De percentages zijn ongewijzigd (3% per dag, 5% meeschuivend). Omgerekend naar het saldo bij de broker:
  - totaalgrens € 10.500,00: dat is € 495 ruimte, 5% van € 10.000 min het eerdere verlies;
  - daggrens € 10.695,20: ongeveer € 300 ruimte, 3% van € 9.995,05.
- **Ter vergelijking: de huidige code op `main`** zet de piek op € 10.995,05 (totaalgrens € 10.445,30). De dagstart blijft € 995,05, dus de daggrens is € 965,20. Voor de rest van 3 november is de daglimiet daar dus in feite uit.
- **Het risicokapitaal is zichtbaar en in te stellen.** Het staat in `config.json` → `demo.risicokapitaal` en verschijnt op het dashboard met de bron erbij.
  - Zonder die sleutel rekent de bot met de inleg: startkapitaal + geldstromen.
  - Een ongeldige waarde blokkeert nieuwe orders met de reden erbij.
  - Live heeft een eigen sleutel (`live.risicokapitaal`); die is niet ingesteld en niet veranderd.

### Onzekerheid en hoe je een geldstroom vastlegt

- **Geen afleiding uit de brokerhistorie.** De bot leest alleen trades uit de historie (`/history/transactions?type=TRADE`). Of een demo-aanvulling daar als storting verschijnt, is niet gecontroleerd. Daarom wordt een geldstroom nooit automatisch afgeleid.
- **Controle via de waardereeks.** Voor elke vastgelegde geldstroom kijkt de bot of de opgeslagen waardereeks rond dat tijdstip een sprong van dat bedrag laat zien. Voor de storting van 3 november is dat zo (13:11 → 13:28 UTC: +€ 10.000,00). Dat staat als controle op het dashboard; het is geen bron.
- **Onverklaarde saldowijzigingen.** Verandert het saldo tussen twee rondes, terwijl er geen open posities waren, geen trade is gesloten en geen geldstroom is vastgelegd, dan markeert de bot dat als onverklaarde saldowijziging. Tot die is vastgelegd, plaatst hij geen nieuwe orders, en piek en dagstart worden in die tijd niet bijgewerkt.
  - Met open posities controleert de bot dit niet: rente en kosten zijn dan niet van een storting te scheiden.
- **Zo leg je iets vast** in `config.json` (wordt elke ronde gelezen):

  ```json
  "administratie": {
    "startkapitaal": {"bedrag": 1000.0, "datum": "2026-10-31", "bron": "..."},
    "geldstromen": [{"t": "2026-11-03T13:22:58+00:00", "bedrag": 10000.0, "omschrijving": "..."}],
    "geaccepteerd": []
  }
  ```

  - **Bedrag:** positief voor een storting, negatief voor een opname.
  - **Tijd:** `t` moet een tijdzone hebben. De tijd van de storting komt van de klok van het Capital.com-platform bij de klik.
  - **Geaccepteerd:** hier kun je een onverklaarde wijziging met haar id goedkeuren zonder haar als geldstroom te boeken, bijvoorbeeld brokerkosten.

### Migratie van de brokerstatus

- **Wanneer.** De status (`demo_staat.json` in de Actions-cache) wordt bij de eerste ronde met de nieuwe code eenmalig omgezet.
- **Wat er overblijft.**
  - De oude velden `start_saldo`, `piek`, `dag` en `dag_start` blijven staan en worden als ruwe accountwaarde bijgewerkt.
  - Hun waarden van vóór de migratie staan ook in `administratie.migratie.oud`.
  - De ruwe waardereeks blijft onaangeroerd.
- **Hoe piek en dagstart worden bepaald.**
  - De nieuwe piek is het hoogste handelsresultaat in de 15-minutenreeks. Een kortere piek tussen twee meetpunten kan daardoor ontbreken; voor 31 oktober was dat € 0,26.
  - De dagstart wordt omgerekend met de inleg aan het begin van de dag.
- **Gecontroleerd** met de opgeslagen stand van de branch `live`: dat gaf de getallen uit de tabel hierboven.
- **Achteraf vastleggen werkt ook.** Veranderen het startkapitaal of de geldstromen in `config.json`, dan leidt de bot piek en dagstart opnieuw af uit de ruwe gegevens, tot aan de eerste onverklaarde saldowijziging. De oude waarden komen in `administratie.herberekend`. Zo blijft een storting die eerst als winst meetelde (bijvoorbeeld tijdens een open positie) de grenzen niet vertekenen.
- **Saldo kleiner dan de risicobasis.** Is `demo.risicokapitaal` groter dan de inleg, bijvoorbeeld na een opname, dan blokkeert de bot nieuwe orders met die reden. Verlaag dan het risicokapitaal of leg de geldstroom vast.

## 3. Wat "een markt doet mee" betekent

Er zijn vier niveaus. Dat een markt in `core/markets.py` of in het instrumentrapport staat, betekent niet dat er orders mogen komen.

| Niveau | Markten nu | Waar het wordt bepaald |
|---|---|---|
| Data wordt verzameld | alle 15 (1-uurs Yahoo voor het lab); ICT 5m voor NQ, EURUSD en GOUD | `core/markets.py`, `core/data.py` |
| Onderzocht | alle 15: vijf lab-families; ICT daarnaast op NQ, EURUSD en GOUD | `learning/lab.py`, `learning/generator.py`, `learning/selector.py` |
| Instrument geverifieerd | alle 15 (rapport van 3 november, 13:16 UTC) | `rapport/instrumenten.json` + `execution/instruments.verified` |
| Er kunnen geldige signalen ontstaan | **geen**: dat kan alleen bij status `actief`, en geen enkele strategie haalt de poort P1–P5 | `lab.json` → `keuze.status`, `learned.json` (ICT) |
| Vrijgegeven voor demo-orders | **geen**, omdat er geen actieve strategie is | `execution/runner.py` |

Live (echt geld) staat los hiervan uit. `config.json` → `live.strategieen` is leeg, en live vraagt 7 opt-ins.

## 4. De keten per stap

1. **Data.**
   - Bron: Yahoo, 1-uurs candles. `core/data.clean` verwijdert dubbele, lege en onmogelijke candles en telt ze.
   - Is de data ouder dan 25 minuten, dan heet de status "vertraagd" en komt er geen order.
2. **Onderzoek.**
   - Vijf families plus ICT op drie markten.
   - Nieuwe varianten komen alleen uit trainingsdata, met instapinstellingen eerst.
3. **Selectie.**
   - De poort P1–P5 is ongewijzigd: 180 dagen validatie, 30/30 trades, 1,5× kosten, DSR ≥ 0,95, 5 beste trades eruit.
4. **Signaal.**
   - Alleen een strategie met status `actief` geeft signalen. Dat wordt gecontroleerd in het dashboard én in de runner.
   - ICT-setups tellen alleen als ICT voor die markt actief is in `learned.json`.
5. **Instrument** (`execution/markets.py`, `execution/instruments.py`).
   - Een order mag alleen als `rapport/instrumenten.json` het instrument bevestigt:
     - de epic is gelijk;
     - er is geen fout of probleem;
     - het rapport komt uit de demo-omgeving;
     - het type past bij de marktsoort. Die laatste controle is nieuw. De types komen uit het rapport zelf: CRYPTOCURRENCIES, CURRENCIES, INDICES, COMMODITIES en SHARES.
   - Per order haalt de runner de gegevens opnieuw op bij de broker:
     - lotSize en scalingFactor = 1;
     - minimale ordergrootte en stap;
     - decimalen en valuta;
     - minimale stopafstand (als percentage);
     - status TRADEABLE en de leeftijd van de koers.
   - Wijkt de brokerkoers meer dan 5% af van de bronkoers, dan volgt een weigering.
6. **Grootte, risico en ordertype.**
   - De positiegrootte rekent met het risicovermogen, begrensd op de risicobasis (zie §2), en met de wisselkoers bij de broker (USD en JPY → EUR). Er wordt naar beneden afgerond op de stap.
   - Is de positie kleiner dan het brokerminimum, of is de spread groter dan 0,25 × de stopafstand, dan wordt de order geweigerd.
   - Lab = marktorder; ICT = limietorder die 60 minuten geldig is. Stop en doel gaan altijd mee.
7. **Uitvoering en herstel.**
   - Het journaal wordt vóór het versturen geschreven. Daarna volgt de bevestiging, en de controle dat stop en doel bij de broker staan; anders wordt de positie gesloten of de order geannuleerd.
   - Een time-out of een afgebroken run ("verzenden") geeft status "onbekend": de order wordt nagezocht en nooit opnieuw verstuurd.
   - Een fout bij één markt wordt gelogd en de andere markten gaan door.
   - Lab-trades sluiten 5 minuten vóór het beursslot of het weekend, zoals in de backtest.

Ongewijzigd: de noodstop, de controle op een verse `status.json`, de accountcontrole, de portefeuillelimieten (percentages), de live-opt-ins en de live-instellingen.

## 5. Status per markt

- **Status:** uit `lab.json` op `main` (Leren-run van 3 november, 03:00 UTC). "Getest" = 2 vaste + 2 gegenereerde varianten per familie; ICT heeft 48 vaste varianten.
- **Instrument:** uit `rapport/instrumenten.json` (3 november, 13:16 UTC).
- **Dry-run:** een nep-broker met de instrumentgegevens uit het rapport, een saldo van € 10.995,05, een kunstmatig signaal en een stop van 1,5 × de gemiddelde uurrange.

| Markt | Data (1h-candles) | Instrument | Onderzocht → gekozen | Status | Reden | Dry-run-order (nieuw) |
|---|---|---|---|---|---|---|
| BTC | 17 467, schoon | ja: BTCUSD, Bitcoin/USD | 5 → Momentum | onderzoek | P2, P4, P5 | 0,0833 BTC, € 49,96 |
| ETH | 17 464, schoon | ja: ETHUSD | 5 → Trend | onderzoek | P2, P4, P5 | 2,202 ETH, € 49,97 |
| SOL | 17 466, schoon | ja: SOLUSD | 5 → geen | pauze | niets positief in train én validatie | **geweigerd**: spread 0,46 > 0,25 × stop 1,26 |
| EURUSD | 17 181, schoon | ja: EURUSD | 5 + ICT → Volatiliteit | onderzoek | P2, P4, P5; ICT validatie −0,16R | 29 400, € 49,87 |
| GBPUSD | 17 184, schoon | ja: GBPUSD | 5 → Mean reversion | onderzoek | P2, P4, P5 | 26 000, € 49,89 |
| USDJPY | 17 086, schoon | ja: USDJPY (JPY) | 5 → geen | pauze | niets positief in beide perioden | 28 500, € 49,96 |
| NQ | 13 632, schoon | ja: US100, US Tech 100 | 5 + ICT → Breakout | onderzoek | alleen P4 (DSR 0,22) | 0,269, € 49,81 |
| ES | 13 636, schoon | ja: US500 | 5 → Momentum | onderzoek | alleen P4 (DSR 0,17) | 1,81, € 49,92 |
| DAX | 6 529, schoon | ja: DE40 (EUR) | 5 → geen | pauze | trend en volatiliteit P1 | 0,362, € 49,95, dicht 17:25 Frankfurt |
| GOUD | 13 672, schoon | ja: GOLD | 5 + ICT → Breakout | onderzoek | P2, P4, P5; ICT P1 | 2,23, € 49,88 |
| ZILVER | 13 666, schoon | ja: SILVER | 5 → geen | pauze | trend P1, de rest negatief | 83,4, € 49,93 |
| OLIE | 13 495, schoon | ja: OIL_CRUDE, "Crude Oil Spot" | 5 → geen | pauze | niets positief in beide perioden | 44,9, € 49,96 |
| AAPL | 5 058, schoon | ja: AAPL | 5 → geen | pauze | trend en volatiliteit P1 | 14,46, € 49,96, dicht 15:55 New York |
| NVDA | 5 058, schoon | ja: NVDA | 5 → geen | pauze | 3 families P1 | 17,1, € 49,74, dicht 15:55 New York |
| MSFT | 5 058, schoon | ja: MSFT | 5 → geen | pauze | 3 families P1 | 8,36, € 49,95, dicht 15:55 New York |

Geen markt staat op actief, en geen markt is technisch geblokkeerd: alle 15 instrumenten zijn bevestigd. De dry-run-orders zijn alleen rekenwerk met een nep-broker. Ze laten zien dat de keten per marktsoort werkt; het zijn geen signalen.

## 6. Beperkingen per markt(soort)

- **Kostenaannames tegenover de gemeten spread.** Het onderzoek rekent met de kosten uit `core/markets.py`. Bij een paar markten was de spread in het rapport (één momentopname, voor aandelen buiten de beurstijd) hoger:

  | Markt | Gemeten spread | Aangenomen kosten |
  |---|---|---|
  | SOL | 0,50% | 0,12% |
  | AAPL | 0,13% | 0,05% |
  | NVDA | 0,22% | 0,05% |
  | MSFT | 0,15% | 0,05% |
  | GOUD | 0,019% | 0,010% |
  | ZILVER | 0,10% | 0,06% |

  Niet aangepast: één meting is te weinig, en een aanpassing verandert de onderzoeksuitkomsten. Bij elke order weigert de runner een spread die te groot is voor de stop.
- **Futures als databron (NQ, ES, GOUD, ZILVER, OLIE).**
  - Yahoo levert de doorlopende future, Capital.com de CFD. Het prijsverschil was op 3 november hoogstens 0,9% en wordt per order verrekend, met een vangnet van 5%.
  - Rolsprongen in de doorlopende future worden niet gecorrigeerd, want de roldata ontbreken.
- **Vertraging.** Futures- en aandelendata van Yahoo kunnen 10–15 minuten achterlopen. Een lab-signaal telt maar 20 minuten na het sluiten van de candle.
- **Aandelen en DAX.** Ze hebben maar 7–8 handelsuren per dag, dus minder trades. De handelsuren zijn die van de beurs; Capital.com geeft in `openingHours` ruimere CFD-uren. De bot sluit bij het beursslot, zoals de backtest.
- **Feestdagen** staan niet in de handelsuren. Dan meldt de broker de markt als dicht.
- **Minimale stopafstand.** Die wordt alleen als percentage verwerkt; alle 15 instrumenten geven een percentage.
- **ICT** draait alleen op NQ, EURUSD en GOUD.

## 7. Handmatige acties

1. Deze wijzigingen reviewen. Ze staan lokaal op `feat/marketpilot` en zijn niet gecommit.
   - Het instrumentrapport staat al op `main` (commit `0b1d9f5`), maar niet op deze branch. Zonder dat bestand weigert de runner alle orders (fail closed).
   - Na een merge met `main` is het rapport er.
2. **Na de merge:**
   - de eerste ronde zet de brokerstatus om; die regel staat dan in het journaal ("administratie");
   - controleer op het dashboard: saldo € 10.995,05, handelsresultaat −€ 4,95, storting +€ 10.000, risicobasis € 10.000.
3. **Een volgende storting of opname** leg je vast in `config.json` → `administratie.geldstromen`. Wordt er niets vastgelegd, dan blokkeert de bot nieuwe orders zodra hij de saldowijziging ziet.
4. **Het instrumentrapport opnieuw maken** (Actions > Instrumenten controleren) als een instrument verandert. Het rapport wordt dan op die branch gecommit.
5. De repository hernoemen is niet gedaan en is niet nodig.
