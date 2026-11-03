# Opslag: welk bestand, van wie, voor wie

Alle paden staan in `storage/paths.py`; laden en atomair opslaan gaat via `storage/jsonstore.py`.
De bestanden staan bewust nog op hun oude plek in de hoofdmap. De lopende keten op GitHub haalt `config.json`, `learned.json`, `lab.json` en `NOODSTOP` elke minuut op bij pad, en de website leest `raw/main/lab.json`.

Eén bron per gegeven:

| Gegeven | Enige bron | Schrijver | Lezers | Bewaard in |
|---|---|---|---|---|
| Instellingen (schakelaars, broker-modus, limieten) | `config.json` | eigenaar | app, broker | main |
| Gekozen ICT-variant per markt | `learned.json` | `learning/ict.py` | app (elke minuut), dashboard | main |
| ICT-uitkomsten per variant (leergeheugen) | `leren_geheugen.json` | `learning/ict.py` | leren, lab | main |
| Keuzegeschiedenis ICT (per dag) | `leren_geschiedenis.json` | `learning/ict.py` | dashboard | main |
| Lab-resultaten (dashboard) | `lab.json` | `learning/lab.py` | dashboard, website | main |
| **Strategieversies** lab: elke wissel, om terug te draaien | `lab_versies.json` | `learning/lab.py` | lab | main |
| Lab-dagregel (wat er vandaag getest en gekozen is) | `lab_geschiedenis.json` | `learning/lab.py` | website | main |
| Forward test: elke setup en weigering | `logboek.json` | app | leren (dagnotities), dashboard | Actions-cache + run-artifact |
| Verstuurde meldingen | `verstuurd.json` | app | app | Actions-cache |
| Orderjournaal demo / live | `demo_staat.json`, `live_staat.json` | broker | broker | Actions-cache |
| Live status en candles | `status.json`, `markt/*.json`, `demo.json` | dashboard, broker | website | branch `live` |
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
