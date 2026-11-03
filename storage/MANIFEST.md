# Opslag: welk bestand, van wie, voor wie

Alle paden staan in `storage/paths.py`; laden en atomair opslaan gaat via `storage/jsonstore.py`.
De bestanden staan bewust nog op hun oude plek in de hoofdmap. De lopende keten op GitHub haalt `config.json`, `learned.json`, `lab.json` en `NOODSTOP` elke minuut op bij pad, en de website leest `raw/main/lab.json`.

Eén bron per gegeven:

| Gegeven | Enige bron | Schrijver | Lezers | Bewaard in |
|---|---|---|---|---|
| Instellingen (schakelaars, broker-modus, limieten, risicokapitaal) en de saldo-administratie (startkapitaal, geldstromen) | `config.json` | eigenaar | app, broker | main |
| ICT aan/uit + variant per markt (afgeleid van de strategie-selectie) | `learned.json` | `learning/lab.py` | app (elke minuut), dashboard | main |
| ICT-uitkomsten per variant (leergeheugen) | `leren_geheugen.json` | `learning/ict.py` | leren, lab | main |
| Keuzegeschiedenis ICT (per dag) | `leren_geschiedenis.json` | `learning/lab.py` | dashboard | main |
| Strategie-selectie per markt (status, poort per strategie) en lab-resultaten | `lab.json` | `learning/lab.py` | dashboard, website, broker (via status) | main |
| **Strategieversies** lab: elke wissel, om terug te draaien | `lab_versies.json` | `learning/lab.py` | lab | main |
| Door het systeem gegenereerde strategievarianten: pool, afgewezenen, aantal proeven per markt, gebeurtenissenlog | `kandidaten.json` | `learning/generator.py` (via `learning/lab.py`) | lab, selector (aantal proeven voor P4) | main |
| Lab-dagregel (wat er vandaag getest en gekozen is) | `lab_geschiedenis.json` | `learning/lab.py` | website | main |
| Forward test: elke setup en weigering | `logboek.json` | app | leren (dagnotities), dashboard | Actions-cache + run-artifact |
| Verstuurde meldingen | `verstuurd.json` | app | app | Actions-cache |
| Orderjournaal demo / live, plus `administratie` (piek en dagstart als handelsresultaat, onverklaarde saldowijzigingen, migratie met de oude waarden) | `demo_staat.json`, `live_staat.json` | broker | broker | Actions-cache |
| Live status en candles | `status.json`, `markt/*.json`, `demo.json` | dashboard, broker | website | branch `live` |
| Instrumentgegevens Capital.com (alleen lezen) én de vrijgave per instrument: zonder bevestiging hier geen demo-order | `rapport/instrumenten.json` | `execution/instruments.py` (workflow Instrumenten controleren) | broker | main |
| Onderzoeksresultaten | `rapport/onderzoek.json` | `research/protocol.py` | rapport | main |
| **Experimenten** (elke onderzoeksrun) | `rapport/experimenten.jsonl` | `research/registry.py` | eigenaar | main (lokaal toevoegen) |
| Migraties die gedraaid zijn | `storage/migraties.json` | `storage/migrations.py` | — | main |
| Backtest-trades (HistData) | `data/*.pkl` | `research/` | `research/` | lokaal (git-ignored) |

`lab_versies.json` en `lab_geschiedenis.json` lijken op elkaar, maar hebben een andere rol:

- **versies** is het wisselspoor per markt (alleen bij een wissel), om een keuze terug te draaien;
- **geschiedenis** is één regel per dag met alles wat getest is; die toont de website.

Ze zijn dus niet samengevoegd.

## Schema-versies

- Geheugenrijen in `leren_geheugen.json` hebben `sim` = de versie van de trade-simulatie.
  - Zonder `sim` = de oude simulatie (v1).
  - `sim: 2` = `backtesting/engine.py`.
  - `kosten_r` = kosten per trade in R (vanaf migratie 002), voor de kostentoets van de selector.
- `lab.json` heeft `versie: 2`.

## Migreren

`python -m storage.migrations` toont welke migraties er zijn. Elke migratie werkt in deze volgorde:

1. Eerst een proefrun die niets schrijft.
2. Daarna een backup in `backups/<tijd>/` met sha256-controle.
3. Dan schrijven en het resultaat teruglezen.
4. Tot slot een regel in `storage/migraties.json`.

Terugzetten gaat met `python -m storage.migrations terugzetten backups/<map>`.

## Bewaartermijn van de Actions-cache

`logboek.json` en het orderjournaal staan alleen in de GitHub Actions-cache. Die cache verloopt na 7 dagen zonder gebruik. Zolang de keten draait wordt hij elke run vernieuwd. Valt de keten langer dan een week stil, dan zijn de forward test en het orderjournaal weg.

Het logboek gaat ook als run-artifact mee, maar dat wordt maar 30 dagen bewaard.

Zie het eindrapport voor de aanbeveling.
