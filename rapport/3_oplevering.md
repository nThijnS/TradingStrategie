# Fase 7 — Oplevering (2 november 2026)

Er zijn geen orders verstuurd, ook geen demo- of testorders. Er zijn geen API-verzoeken naar Capital.com gedaan: de sleutels staan alleen als GitHub-geheim. Er is niets naar GitHub geüpload. Alle wijzigingen staan alleen lokaal. Reservekopieën van de oude bestanden staan in de scratchpad van de sessie.

## 1. Belangrijkste auditbevindingen

Details staan in [1_audit.md](1_audit.md).

1. **Look-ahead in live signalen.** Het lab rekende op de nog lopende Yahoo-uurcandle. Dat signaal kreeg bovendien een tijd in de toekomst, waardoor de 20-minutengrens het niet tegenhield. De demo-bot kon dus handelen op een signaal dat in de backtest nooit bestond. **Opgelost.**
2. **Selectiebias in het lab.**
   - De walk-forward-testtrades werden ook gebruikt om tussen 6 strategieën × 15 markten te kiezen.
   - PBO van die keuze: **63%**.
   - Op een onaangeroerde eindtest verloor het oude protocol **−3,0R over 142 trades**.
3. **Brokerkoppeling niet fail-closed.** Dat betrof:
   - een aangenomen contractwaarde;
   - geen accountcontrole;
   - een time-out die als "mislukt" telde;
   - geen controle of stop-loss en take-profit echt op de positie staan;
   - dubbele orders mogelijk als de cache-staat wegviel.
4. **Risicolimieten telden posities, geen risico.** Er was geen correlatielimiet en kosten zaten niet in de positiegrootte.
5. **Tegenstrijdigheid.** Dashboard en status zeiden "nooit orders", terwijl de demo-bot automatisch orders plaatst.

## 2. Gewijzigde en nieuwe bestanden

| Bestand | Wat |
|---|---|
| `risico.py` (nieuw) | Pure risicologica, zonder netwerk.<br>• **Instrument:** lotSize/scalingFactor moet 1 zijn, anders geen order. Ordergrootte en decimalen moeten bekend zijn.<br>• **Koers:** status TRADEABLE, geen vertraging, niet ouder dan 180 s.<br>• **Niveaus:** stop en doel aan de goede kant, het doel komt per markt en strategie uit de data (optionele ondergrens `min_rr`, standaard uit), brokerminimum, spread ≤ 0,25R, koersafwijking bij een marktorder ≤ 0,3R, limietprijs nog niet voorbij de markt.<br>• **Positiegrootte:** uit het risicobudget, (stopafstand + spread + slippage) en de wisselkoers naar de accountvaluta; afgerond op de brokerstap, met min/max-grootte.<br>• **Portefeuille:** risico per trade, open risico samen (vanaf de huidige prijs tot de stop), dag- en totaalgrens (worst case), max open, max per gecorreleerde groep (dollarrichting bij forex) en hefboom. Gelijktijdige signalen worden opgeteld. Een positie zonder stop blokkeert alles. |
| `broker_capital.py` (nieuw) | Capital.com-client met aparte adressen voor demo en live.<br>• Wacht zelf op de rate limits en logt opnieuw in bij 401.<br>• Leesverzoeken worden herhaald; orderverzoeken **nooit**: een time-out geeft "uitkomst onbekend".<br>• Bevestiging via `/confirms`, met wachten bij 404.<br>• Leest stopniveaus én stopafstanden, `workingOrderId` en `contractSize`.<br>• Geheimen komen nooit in foutmeldingen. |
| `broker.py` (nieuw) | Orderuitvoering.<br>• Demo is standaard. Live vraagt 7 aparte opt-ins (zie §6) en valt nooit terug op demo.<br>• Het account wordt bij de broker gecontroleerd met `PUT/GET /session`.<br>• Vlak voor elke order haalt hij account, posities, orders en koers opnieuw op.<br>• Eén positie per instrument.<br>• Het journaal wordt atomair opgeslagen vóór het verzenden.<br>• Na de order controleert hij of stop en doel er echt staan; anders sluit of annuleert hij.<br>• "Onbekend" wordt bij de broker nagezocht en nooit opnieuw verstuurd.<br>• Noodstop, tijdsluiting en een aparte staat voor demo en live. |
| `demo_broker.py` | Alleen nog een doorverwijzing naar `broker.py`, zodat oude aanroepen blijven werken. De OANDA-koppeling is vervallen: die rekende met een aangenomen contractwaarde en kon het account niet controleren. |
| `live_status.py` | Lab-signalen alleen op afgesloten candles (`closed_bars`). De signaaltijd is nu de sluittijd van de candle. Financiering telt mee. De modustekst is correct. |
| `strategielab.py` | Financieringskosten per nacht (rollover 17:00 NY) in de simulatie. De docstring is eerlijk over orders en selectiebias. De keuze-logica zelf is **niet** veranderd: die blijft het demo-forward-test-mechanisme. |
| `onderzoek.py` (nieuw) | Het vooraf vastgelegde testprotocol (fase 3–5) en de rapportgenerator. |
| `capital_instrumenten.py` (nieuw) + `.github/workflows/instrumenten.yml` (nieuw) | Leest instrumentgegevens bij Capital.com, alleen lezen, en schrijft `rapport/instrumenten.json`. Handmatig te starten. |
| `.github/workflows/tradingstrategie.yml` | Roept `broker.py` aan.<br>• Live-geheimen en `CAPITAL_MODUS` als omgeving (leeg = niets).<br>• Variabele `NOODSTOP`.<br>• Aparte cache voor `live_staat.json`. |
| `.github/workflows/tests.yml` (nieuw) | Draait de tests bij elke codewijziging. |
| `config.json` | Nieuw:<br>• `"broker": {"modus": "demo"}`<br>• `"noodstop": false`<br>• `"live"`: niet gevalideerd, geen strategieën vrijgegeven, strengere limieten. |
| `docs/index.html` | De zin "nooit orders" is vervangen.<br>• Modusbalk: DEMO / LIVE / LIVE GEBLOKKEERD.<br>• Laatste API-controle, noodstop en orders met onbekende uitkomst.<br>• Open risico en groepslimiet.<br>• Kopjes volgen de modus. |
| `tests/` (nieuw) | 67 tests.<br>• Risicologica, modus en opt-in, accountcontrole, live-vrijgave, noodstop.<br>• Dubbele orders (ook als de staat kwijt is), journaal vóór verzenden, time-out → onbekend → teruggevonden of niet gevonden.<br>• Brokerweigering, ontbrekende bescherming, limietorder met alleen afstanden, koppeling via `workingOrderId`, onbekende contractgrootte.<br>• Verouderde en toekomstige signalen, te brede spread.<br>• HTTP-laag: geen herhaling bij een order, wel bij lezen; herinloggen; geen geheimen in fouten.<br>• Lopende candle; instap na het signaal; stop eerst; financiering; DSR, PBO en bootstrap. |
| `rapport/` (nieuw) | Dit rapport, de audit, het onderzoek en `onderzoek.json`. |

## 3. Markten en strategieën

Details staan in [2_onderzoek.md](2_onderzoek.md).

- **Toegevoegd: niets.** Geen markt en geen strategie heeft genoeg bewijs. Instrumentgegevens bij Capital.com zijn nog niet uitgelezen.
- **Markten afgewezen** (geen spreiding of slechte data):
  - USD/CHF (−0,82 met EUR/USD)
  - NZD/USD (0,80 met GBP/USD)
  - Dow Jones (0,90 met S&P 500)
  - CAC 40 (0,86 met DAX)
  - Brent (0,92 met WTI)
  - Aardgas (13 rollover-sprongen in de data)
- **Markten uitgesteld** (eerst instrumentgegevens uitlezen, en een strategie moet de poort halen):
  - AUD/USD, USD/CAD, EUR/GBP (beste spreiding), EUR/JPY, koper
  - FTSE en Nikkei: de Yahoo-uren sluiten bovendien niet aan op de CFD.
- **Strategieën afgewezen:**
  - opening-range-breakout NQ/ES (alle 10 varianten negatief of rond 0);
  - Donchian 55/20 en time-series momentum op dagdata (te weinig trades, wisselend, en meerdaagse posities passen niet bij de daytrade-opzet);
  - regimefilter (haalt nergens de poort).
- **Strategie uitgesteld:** VWAP (geen betrouwbare volumedata).

## 4. Test op dezelfde eindtest (1 mei – eind okt 2026, niet gebruikt voor keuzes)

| | Trades | Netto R | Markten |
|---|---|---|---|
| **Voor**: lab-protocol, keuze met data tot 1 mei | 142 | **−3,0R** | goud momentum +3,4 · zilver trend −1,3 · olie squeeze −3,7 · NVDA mean reversion −1,4 |
| **Na**: vooraf vastgelegde poort (P1–P5) | 0 | **0R** | geen strategie geslaagd = geen trade |

Kosten inbegrepen: spread, slippage 0,02R en financiering. ICT valt buiten deze vergelijking.

- "Na" verdient niets. Het verliest alleen niet. **Dit is geen winstverbetering**, alleen het vermijden van handel zonder bewijs.
- Het interval van de beste "voor"-markt (goud: −0,26 tot +0,44R per trade) laat zien dat ook die winst toeval kan zijn.

## 5. Open risico's, databeperkingen en API-afhankelijkheden

1. **API niet echt getest.** De client volgt de officiële documentatie, maar is niet tegen de echte API gedraaid.
   - De documentatie toont bij posities geen `stopLevel`. Geeft de API die echt niet terug, dan sluit `broker.py` elke nieuwe positie meteen. Dat is veilig, en het staat in het log als "teruggedraaid".
   - **Controleer de eerste demo-trades** en draai `capital_instrumenten.py` (zie §6).
2. **Kosten en contractgrootte zijn aannames** tot `rapport/instrumenten.json` er is. Markten waarvan lotSize of scalingFactor niet 1 is, worden niet verhandeld.
3. **Data:**
   - Yahoo-futures lopen 10–15 minuten achter en wijken af van de CFD-prijzen. De basiscorrectie dekt het niveau, niet de vertraging.
   - De eindtest is maar 6 maanden.
   - Feestdagen worden niet herkend.
4. **Journaal staat in de actions-cache.** Die wordt pas aan het eind van een run opgeslagen. Als een runner hard stopt, raakt de staat kwijt. De broker-controle "één positie per instrument" vangt dubbele orders dan op, behalve als een positie al gesloten was binnen het signaalvenster.
5. **De repo is openbaar.** `demo.json` (saldo, posities, log) staat op de openbare branch `live`. **Maak de repo privé vóór live**, of publiceer `demo.json` dan niet meer.
6. **Bijstorten** op het account ziet de bot als winst: de startwaarde en de piek schuiven niet mee.
7. **De demo handelt nog steeds onbewezen lab-keuzes.** Dat is bewust: het is de forward-test met nepgeld. Het dashboard noemt dat resultaat geen bewijs meer.
8. **Leren in de cloud.** `leren.py` en het lab blijven elke dag automatisch kiezen; voor de demo is dat zonder review. Voor live geldt alleen de handmatige lijst `live.strategieen`.

## 6. Demo of live instellen (door de eigenaar zelf)

**Demo (standaard; staat al zo)**
1. De geheimen `CAPITAL_API_KEY`, `CAPITAL_IDENTIFIER` en `CAPITAL_PASSWORD` staan al in GitHub. Optioneel: `CAPITAL_DEMO_ACCOUNT_ID` om een vast demo-account af te dwingen.
2. Draai één keer *Actions → Instrumenten controleren → Run workflow*. Daarna staat `rapport/instrumenten.json` in de repo.

**Noodstop:**
- **Snel (binnen ~3 minuten):** zet in `config.json` `"noodstop": true`, of zet een bestand `NOODSTOP` in de repo. De keten haalt beide elke minuut op.
- **Variabele `NOODSTOP=1`** (*Settings → Secrets and variables → Actions → Variables*): werkt pas vanaf de volgende run. Dat kan tot 5u40 duren. Herstart de keten, of gebruik de snelle route.

Effect: geen nieuwe orders, en wachtende orders van de bot worden geannuleerd. **Open posities blijven open** met hun stop en doel bij de broker. Die sluit je zelf in Capital.com.

**Live (echt geld). Doe dit pas als een strategie de poort haalt én ≥ 3 maanden goed op demo draaide.** Alle stappen zijn nodig. Ontbreekt er één, dan handelt de bot niet en staat "LIVE GEBLOKKEERD" met de reden op het dashboard.
1. Maak de GitHub-repo **privé**.
2. Maak in Capital.com (live) een API-sleutel. Zet als geheimen:
   - `CAPITAL_LIVE_API_KEY`
   - `CAPITAL_LIVE_IDENTIFIER`
   - `CAPITAL_LIVE_PASSWORD`
   - `CAPITAL_LIVE_ACCOUNT_ID` (het exacte account-ID van het live-account)
3. Zet het geheim `CAPITAL_LIVE_BEVESTIGING` op precies `IK-HANDEL-MET-ECHT-GELD`.
4. Zet de variabele `CAPITAL_MODUS` op `live`.
5. In `config.json`:
   - `"broker": {"modus": "live"}`
   - `"live": {"limieten_gevalideerd": true, "strategieen": ["MARKT:strategie", ...], "limieten": {...}}`

   De limieten worden getoetst: risico per trade ≤ 1%, open risico ≤ 3% en kleiner dan het dagverlies, dagverlies ≤ 5%, totaal ≤ 10%, hefboom ≤ 30.
6. Terug naar demo: zet `"modus": "demo"`, of haal `CAPITAL_MODUS` weg. Live stoppen kan ook met de noodstop.
