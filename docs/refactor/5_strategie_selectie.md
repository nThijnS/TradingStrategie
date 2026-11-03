# Strategie-selectie per markt (3 november 2026)

## Waar de selectie vastlag (vóór deze wijziging)

| Plek | Wat lag vast |
|---|---|
| `learning/ict.py` (`leren.py`) | Koos alleen tussen **ICT-varianten** en schreef `learned.json`. Daarmee zette het ICT per markt aan of uit, los van de andere strategieën. De score was in-sample, zonder validatie. |
| `learning/lab.py` (`strategielab.py`) | Koos per markt **apart** één strategie, op de walk-forward-testtrades die het ook voor de selectie gebruikte (selectiebias, PBO 63%). Er was geen kostentoets en geen correctie voor het aantal geprobeerde varianten. |
| Twee sporen tegelijk | Een markt kon tegelijk een actieve ICT-keuze (`learned.json`) en een lab-strategie (`lab.json`) hebben. Bij GOUD stonden ICT en Momentum allebei aan. ICT werd dus altijd naast het lab overgenomen. |
| Na inschakelen | Er was geen regel om een strategie uit te zetten op basis van nieuwe uitkomsten. Alleen de dagelijkse herberekening telde. |
| `journaal/Huidige strategie.md` | Toonde alleen ICT. |

## Wat er nu is

- `learning/selector.py`: één selector per markt. **ICT is één familie** naast trend, momentum, mean reversion, breakout en volatiliteit.
- De stappen staan bovenaan dat bestand. Kort:
  1. **Variant kiezen op train alleen.** Train = alles vóór de laatste 180 dagen. Een variant doet alleen mee als hij in train vaak genoeg handelt om in 180 dagen 30 trades te halen; anders kan hij P1 nooit halen.
  2. **Poort P1–P5 op de laatste 180 dagen.** Dezelfde poort als `research/protocol.py`:
     - P1: genoeg data (≥ 30 trades in train én in validatie);
     - P2: positief bij 1,5× kosten, met een block-bootstrap-ondergrens > 0;
     - P3: train positief;
     - P4: Deflated Sharpe ≥ 0,95, gecorrigeerd voor **alle** varianten die op die markt geprobeerd zijn (ICT-markten: 58);
     - P5: niet afhankelijk van de 5 beste trades.
  3. **Status per markt:**
     - **actief**: haalt de poort, signalen tellen;
     - **onderzoek**: in train én validatie positief, maar niet bewezen; gevolgd zonder orders;
     - **pauze**: geen van beide.
  4. **Nieuwe uitkomsten.** Na ≥ 20 nieuwe trades met een negatief gemiddelde gaat een actieve strategie uit, en die familie is 60 dagen geblokkeerd op die markt.
  5. **Rem op wisselen.** Wisselen gebeurt alleen bij een ondergrens die ≥ 0,05R hoger is. Een variant die de poort nog haalt, blijft staan.
- **Één strategie per markt.**
  - `learning/lab.py` is nu de enige schrijver van `learned.json`.
  - ICT staat alleen aan op een markt waar de selector ICT als actieve strategie koos.
  - `leren.py` verzamelt ICT-uitkomsten en schrijft het leerlog, maar zet zelf niets meer aan of uit.
- **Kostentoets voor ICT.** Nieuwe geheugenrijen krijgen `kosten_r`. Migratie 002 voegt dat toe aan de bestaande rijen; R verandert niet, dat wordt gecontroleerd.
- `journaal/Huidige strategie.md` toont nu alle 15 markten met status en reden.
- `lab.json` per strategie bevat nu:
  - `poort`, met redenen;
  - `train`;
  - `nieuw` = de validatie van de op train gekozen variant.
- `lab.json` per markt bevat `keuze.status` en `keuze.onderzoek`. De website heeft geen aanpassing nodig.
- Hersteld: in `leren.py` overschaduwde een variabele het datamodule. Daardoor kregen de dagnotities stil geen charts. Die fout zat er sinds de refactor van 3 november.

## Uitkomst op echte data (3 november, kopie, na migratie 002)

**Geen enkele strategie haalt op enige markt de poort.**

| Status | Markten |
|---|---|
| actief | – |
| onderzoek (geen orders) | SOL (Volatiliteit), GBPUSD (Mean reversion), NQ (Trend), ES (Momentum), GOUD (Mean reversion) |
| pauze | BTC, ETH, EURUSD, USDJPY, DAX, ZILVER, OLIE, AAPL, NVDA, MSFT |

- Het dichtst bij komt **ES / Momentum**: 40 validatietrades, +0,301R bij 1,5× kosten en een ondergrens van +0,061R. Het faalt alleen op P4: Deflated Sharpe 0,25.
- **ICT** wordt nu met een brede variant getoetst die genoeg handelt (39–58 validatietrades). Het faalt op de uitkomsten: in de validatie is het gemiddelde negatief (EURUSD −0,16R, NQ −0,15R). In een eerdere versie koos de selector smalle varianten met maar 14–18 trades. Die konden P1 nooit halen; dat is gerepareerd.

**Gevolg voor de demo-orders na de merge.**

- Het oude lab had Momentum (GOUD), Trend (ZILVER, NQ) en Mean reversion (NVDA) actief. Die geven dan geen demo-orders meer.
- ICT was al uit sinds migratie 001.
- Gecontroleerd: met de nieuwe keuzes levert `live_status.py` → `broker.signals()` 0 orderbare signalen.
- De orderuitvoering zelf (`execution/`) is niet veranderd.

## Wat nu automatisch gaat

| Wat | Hoe vaak |
|---|---|
| Uitkomsten verzamelen (ICT-geheugen, lab-trades) | dagelijks |
| Per markt een variant per familie kiezen (op train) | dagelijks |
| De poort toetsen | dagelijks |
| Een strategie in- of uitschakelen, of op onderzoek zetten | dagelijks |
| Uitschakelen en blokkeren na slechte nieuwe uitkomsten | dagelijks |
| ICT aan/uit in `learned.json` | dagelijks |
| Journaal en dashboard bijwerken | dagelijks |

## Wat nog handmatig vastligt

- **De kandidatenlijst.**
  - De strategiefamilies en hun varianten staan in `strategies/lab.py` en `learning/ict.py`.
  - De markten staan in `core/markets.py`. ICT kan alleen op NQ, EURUSD en GOUD, omdat alleen daar een ICT-geheugen is.
  - Het systeem bedenkt geen nieuwe strategieën of parameters. Dat is een volgende stap: zie "Volgende stap" hieronder.
- **De poortinstellingen** in `learning/selector.py`: 180 dagen, 30 trades, 0,95, enzovoort. Ze zijn bewust vast, zodat er niet achteraf aan gedraaid wordt.
- **Live (echt geld).** Dat blijft een handmatige vrijgave via `config.json` → `live.strategieen` en de 7 opt-ins. Een actieve status geeft alleen demo-orders.
- **Schakelaars** in `config.json`: markten en sessies voor ICT-meldingen, en de noodstop.

## Volgende stap (niet gedaan)

**Nieuwe kandidaten laten genereren en onderzoeken.** Elke nieuwe kandidaat telt mee in het aantal proeven (P4). Daardoor wordt de poort automatisch strenger naarmate er meer geprobeerd wordt.
