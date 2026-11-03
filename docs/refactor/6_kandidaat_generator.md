# Kandidaat-generator (3 november 2026)

Het systeem stelt nu zelf nieuwe strategievarianten voor en toetst ze. De kandidatenlijst hoeft daardoor niet meer met de hand te worden uitgebreid. De code staat in `learning/generator.py`; het register heet `kandidaten.json`.

## Van idee tot actieve strategie

1. **Maken.** Dit gebeurt dagelijks in de workflow *Leren*, per markt en per strategiefamilie.
   - De generator neemt als ouder de variant die op **train** het best is. Train = alles vóór de laatste 180 dagen.
   - Hij maakt buren: één instelling één stap omhoog of omlaag in een vast raster van bestaande instellingen.
     - Doel in R, stop in ATR, lookback.
     - Efficiëntie, band, kanaal en squeeze-drempel.
   - Hoogstens 2 nieuwe per familie per dag, ook als de workflow opnieuw draait.
   - Nooit twee keer dezelfde variant.
2. **Zeven op train** (alleen data vóór de grens). Een kandidaat moet aan alles voldoen:
   - ≥ 30 trades;
   - vaak genoeg handelen om in 180 dagen 30 trades te halen;
   - gemiddeld positief **na 1,5× kosten**.

   Wie faalt, krijgt de status "afgewezen op train" en de reden wordt gelogd.
3. **Pool.**
   - Wie slaagt, gaat de pool in. Per familie per markt passen er hoogstens 4.
   - Is de pool vol, dan valt de zwakste op train af.
   - De variant die nu gekozen is (actief of in onderzoek), valt er nooit uit.
4. **Toetsen.**
   - De pool doet mee in de dagelijkse selectie, met **dezelfde poort P1–P5** als elke strategie.
   - De validatie bestaat uit de laatste 180 dagen. Die data lag bij het maken en zeven altijd ná de grens.
   - Na de aanmaak wordt per kandidaat ook "na aanmaak" bijgehouden: trades op data die bij het maken nog niet bestond.
5. **Actief** wordt een kandidaat alleen als hij de poort haalt. Anders blijft de markt op onderzoek of pauze.

## Waarom het systeem de poort niet kan versoepelen

- **De drempels staan niet in de generator.** De generator kan de poort niet aanpassen. Een test bevriest de drempels: 180 dagen, 30/30 trades, 1,5× kosten, DSR ≥ 0,95, 20 nieuwe trades, 60 dagen en 0,05R.
- **Elke geprobeerde variant telt mee** in het aantal proeven voor de Deflated Sharpe (P4), ook een afgewezen of verdrongen variant.
  - Dat aantal kan alleen stijgen.
  - Hoe meer de generator probeert, hoe strenger de poort. Ook dat is getest.
- **De validatie wordt bij het maken niet gebruikt.** Getest: totaal andere data na de grens geeft exact dezelfde voorstellen, zeef en pool.

## Uitkomst op echte data (kopie, 6 opeenvolgende runs)

- Per run worden 150 varianten voorgesteld. Daarvan haalden er 50–60% de zeef niet, meestal op kosten of te weinig trades.
- Bij 22 families werd een gegenereerde variant de op train gekozen variant.
- **Geen enkele kandidaat haalde de poort.**
- Dichtst bij kwam EURUSD/Volatiliteit (squeeze 5%, stop 2×ATR, doel 1,5R):
  - 31 validatietrades met een positieve ondergrens (+0,125R);
  - toch afgewezen op de Deflated Sharpe: 0,13, met 86 varianten geprobeerd op EURUSD.
- De markten blijven dus op onderzoek of pauze. Er komen geen orders.
- Rekentijd: ±11 seconden voor 15 markten.

## Logging

- **`kandidaten.json`** bevat per markt:
  - `proeven`;
  - per familie elke kandidaat met ouder, regel, aanmaakdatum, status, reden, train-maten en "na aanmaak";
  - een gebeurtenissenlog met de laatste 2 000 regels.
- **`lab.json` → `markten[].kandidaten`:** het aantal proeven voor P4, de kandidaten van vandaag en de poolgrootte.
- **Workflow-uitvoer:** één regel per kandidaat, bijvoorbeeld `kandidaat NQ trend: sm 2 -> 1.5 -> in pool (...)`.

## Grenzen

- **ICT wordt nog niet gegenereerd.** De ICT-uitkomsten komen uit het leergeheugen met 48 vaste varianten. Nieuwe ICT-varianten vragen een herberekening op HistData, die alleen lokaal staat.
- **Het raster is vast.** Er komen geen nieuwe strategiefamilies of indicatoren bij.
