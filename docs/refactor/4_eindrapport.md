# Eindrapport refactor (3 november 2026)

Alle wijzigingen staan op de branch `refactor/clean-architecture`, in een kloon op deze Mac (`Documents/TradingStrategie/TradingStrategie-git`). Er is niets gepusht, niets op `main` veranderd en geen workflow gestart. Er zijn geen orders geplaatst. De demo-run in de rooktest had geen geheimen en weigerde terecht.

## 1. Oude versus nieuwe architectuur

| | Oud | Nieuw |
|---|---|---|
| Structuur | 12 losse scripts in de hoofdmap, plus 10 alleen lokaal | 10 pakketten (`core`, `strategies`, `backtesting`, `research`, `learning`, `risk`, `execution`, `storage`, `dashboard`, `app`), zie [ARCHITECTUUR.md](../ARCHITECTUUR.md) |
| Trade-simulatie | 8 varianten met verschillende aannames | 1: `backtesting/engine.py`. Uitzondering: 3 bevroren archiefscripts, zie §7 |
| Strategie-interface | geen | `strategies/base.py` (`Signal`); ICT, lab en ORB leveren signalen aan de engine |
| Marktdefinities/kosten | op 5 plekken | `core/markets.py` |
| Data ophalen | 3× Yahoo; HistData met tijdzonefout, correctie alleen lokaal | `core/data.py` met zomertijd-correcte HistData-lader in de repo |
| Statistiek | 3× | `backtesting/metrics.py` |
| Configuratie | globale dicts die bij elke aanroep verder werden ingekort | `core/config.py`: in-place, telkens vanaf de standaard (idempotent) |
| Opslag | elk script eigen paden en eigen JSON-code | `storage/paths.py`, `storage/jsonstore.py` (atomair), `storage/MANIFEST.md`, migraties met backup |
| Validatie | lab: walk-forward. Leren: geen | `research/validation.py`; leren rapporteert een chronologische controle (keuze ongewijzigd) |
| Experimenten | niet geregistreerd | `research/registry.py` → `rapport/experimenten.jsonl` |
| Tests | 68 (broker, risico, lab) | 117 (+ golden-regressie, engine, look-ahead, leren, config, opslag, data) |

## 2. Verwijderde bestanden

**Geen.** Elke oude bestandsnaam bestaat nog als doorverwijzing van een paar regels. De workflows, `Start TradingStrategie.command` en oude imports werken daardoor ongewijzigd.

Er zijn ook geen JSON-bestanden verwijderd of herschreven.

## 3. Samengevoegde functionaliteit

| Samengevoegd | Uit | In |
|---|---|---|
| Trade-simulatie | `outcome`, `backtest.simulate`, `leren.simulate5`, `strategielab.simulate`, `onderzoek.simulate`, `onderzoek.orb` | `backtesting/engine.py` (+ `backtesting/ict.py`) |
| Statistiek | `backtest.stats`, `strategielab.stats`, onderzoek-statistiek | `backtesting/metrics.py` |
| Walk-forward, splitsing, selectiepoort | `strategielab`, `onderzoek` | `research/validation.py` |
| Marktdata | `tradingstrategie.fetch`, `strategielab.fetch_all`/`clean`, `onderzoek.fetch`, `backtest.load_m1`, `tp_videos.load_dst` | `core/data.py` |
| Markten en kosten | `CFG["markets"]`, `strategielab.MARKETS`, `onderzoek.CANDIDATES`, `leren.COST`/`HISTDATA`, `backtest_multi.MARKETS` | `core/markets.py` |
| JSON laden/opslaan | 4 eigen varianten | `storage/jsonstore.py` (`execution/` bewust ongewijzigd) |
| HistData-backtests | `backtest.py`, `backtest_multi.py` | `research/histdata_ict.py` |

## 4. Nieuwe bestanden

- **Code:**
  - `core/{sessions,markets,data,config}.py`
  - `strategies/{base,ict_tjr,lab,classic}.py`
  - `backtesting/{engine,ict,metrics,prop}.py`
  - `research/{protocol,histdata_ict,validation,registry,engine_vergelijking}.py`
  - `learning/{ict,lab,journal}.py`
  - `storage/{paths,jsonstore,migrations}.py`
  - `app/alerts.py`
- **Verplaatst (inhoud ongewijzigd, alleen imports/paden):**
  - `risk/rules.py`
  - `execution/{runner,capital,instruments}.py`
  - `dashboard/status.py`
- **Archief:**
  - `research/archief/` (8 scripts, eerder alleen lokaal)
  - `dashboard/archief/` (dashboard v1)
- **Tests:**
  - `tests/fixtures.py`
  - `tests/golden/`
  - `tests/test_{golden,engine,core,strategy_learning}.py`
- **Documentatie:**
  - `docs/ARCHITECTUUR.md`
  - `docs/refactor/1_audit.md` … `4_eindrapport.md`
  - `storage/MANIFEST.md`

## 5. Technische verbeteringen

1. **Eén trade-simulatie met vastgelegde regels.** Leren, backtests, lab, onderzoek en het logboek rekenen nu op dezelfde manier.
2. **Correcties in de ICT-afhandeling.** Elke correctie is apart gemeten in [3_engine_vergelijking.md](3_engine_vergelijking.md).
   - Een doel in de vulcandle van een limietorder telt niet meer. Dat was optimistisch.
   - Tijdsluiting na precies 5 uur. Dat was 5u05m of 1 candle te laat.
   - Bij DOL zonder liquiditeit valt het doel terug op 1R, zoals de app. Het leren rekende met 2R en beoordeelde dus andere trades dan de app neemt.
   - Een open voorbij de stop sluit op de open.
3. **HistData-tijdzone.**
   - De correcte lader staat in de repo.
   - `leren.py --histdata` en de ORB in het onderzoek werkten op GitHub niet, omdat `tp_videos.py` ontbrak. Dat werkt nu.
   - De oude lader blijft beschikbaar via `--oud`.
4. **Slippage en kosten expliciet** in één kostenmodel. Onderdelen: prijspunten, fractie, slippage in R en financiering per rollover. De waarden zijn niet veranderd.
5. **Configuratie idempotent.** `apply_settings()` kon bij een tweede aanroep markten en sessies kwijtraken. Nu begint het telkens vanaf de standaard.
6. **Versie op geheugenrijen** (`sim`), zodat oude en nieuwe simulatie herkenbaar zijn. Het leren waarschuwt zolang ze gemengd zijn.
7. **Chronologische controle** van de ICT-keuze in het journaal: de laatste 60 dagen tegenover de periode ervoor. Dit is alleen rapportage.
8. **`.gitignore`**: staatbestanden van de keten (`logboek.json`, `demo_staat.json`, `live_staat.json`, …) en afgeleide uitvoer kunnen niet meer per ongeluk in de repo komen.

## 6. Uitgevoerde tests en resultaten

| Test | Resultaat |
|---|---|
| Unit- en regressietests, Python 3.9 (lokaal) | **117/117 groen** |
| Zelfde tests, Python 3.12 + pandas 3.1 + numpy 2.5 + yfinance 1.7 (zoals GitHub Actions nu installeert) | **117/117 groen** |
| De 68 bestaande tests (broker, risico, lab) | ongewijzigd groen |
| Golden ICT-detectie: setups, entries en weigeringen identiek aan de oude code (4 configuraties, synthetische data) | **identiek** |
| Golden lab, onderzoek, walk-forward, Donchian/TSMOM, leren-score | **identiek** |
| Lab, alle 15 markten, oude en nieuwe code op dezelfde Yahoo-data | **0 verschillen** |
| HistData-referentie: de oude code reproduceert NQ strenger 1R +12,0R / −1,2R (eerdere backtest) | gereproduceerd; nieuw: +11,9R / −1,2R |
| `tradingstrategie.py --scan` op live data, oud en nieuw | setups identiek; 2 uitkomsten anders (TP in de vulcandle, sluiten 15:55 vs 16:05) |
| `live_status.py`, `broker.py` (zonder geheimen), `leren.py --geen-data`, `strategielab.py --markt` | zelfde uitvoer, alleen koersen die tussen de runs bewogen |
| Website (`docs/index.html`) lokaal met de nieuwe `status.json`/`markt/`/`lab.json` | dashboard en marktgrafiek renderen, geen consolefouten |
| Archiefscripts | alle 10 importeren |
| Workflows | inhoudelijk ongewijzigd; dezelfde scriptnamen en bestandspaden. **Niet gestart.** |

## 7. Resterende problemen en beslissingen voor jou

1. **Migratie van het leergeheugen (belangrijkste beslissing).**
   - De proefrun van `python -m storage.migrations proef 001` heeft niets geschreven. Uitkomst:
     - 775 van 4 880 uitkomsten veranderen.
     - **EURUSD** gaat van +0,058 naar −0,006.
     - **GOUD** gaat van +0,073 naar −0,059.
   - Na de migratie zet het leren daardoor **alle drie de ICT-markten op pauze**. De huidige keuzes leunen dus op de optimistische oude simulatie.
   - Ik heb de migratie niet uitgevoerd, omdat ze live gedrag verandert.
   - Zonder migratie mengt het geheugen oude rijen met dagelijks een handvol nieuwe.
   - Advies: draai haar na de merge lokaal. HistData is nodig, en de backup gaat automatisch.
2. **Pushen.** Deze Mac heeft geen GitHub-inlog (`gh` ontbreekt en git heeft geen credentials). Zie de stappen hieronder.
3. **Tijdsluiting verschilt tussen leren en uitvoering.**
   - Het leren en de backtests rekenen met 5 uur.
   - De app en het logboek sluiten om 16:00.
   - De broker sluit ICT-trades pas na 12 uur (standaard; instelbaar met `config.json` → `demo.max_uren`).
   - Dat is een strategiekeuze en heb ik niet veranderd. Advies: één waarde kiezen.
4. **Forward test en orderjournaal staan alleen in de Actions-cache**, die na 7 dagen zonder gebruik verloopt. Advies: het logboek dagelijks mee laten committen door de workflow Leren, of naar de branch `live` schrijven.
5. **Kosten niet geverifieerd.** De workflow `Instrumenten controleren` is nog nooit gedraaid.
6. **Bevroren archiefscripts met een eigen simulatie.** Het gaat om `backtest_tp_model.exit_trade`, `datafarm` en `dashboard_v1.live_outcome`. Ze draaien niet in de cloud en reproduceren historische onderzoeken. Daarom zijn ze niet herschreven.
7. **`execution/runner.py` heeft nog een eigen `load`/`save`.** Die is identiek aan `jsonstore`, maar bewust niet aangeraakt: de orderuitvoering is net herschreven en getest.
8. **HistData-gat.**
   - Op 10 oktober 2025 ontbreekt de candle van 10:58 tijdens de crash.
   - De engine rekent voorzichtig met de volgende open: −4,5R in één NQ-trade, tegen −1R bij de oude code.
   - Er kunnen meer ontbrekende minuten zijn. Een gatencontrole op de HistData is een kleine vervolgstap.

## Merge-stappen

1. Pushen vanaf een machine met GitHub-inlog:
   - `git push -u origin refactor/clean-architecture`
   - of met GitHub Desktop: *Add existing repository* → deze map.
2. Op GitHub draait dan alleen **Tests** op de branch.
   - Start **TradingStrategie** niet op de branch, anders draaien er twee ketens.
   - `schedule` draait alleen op `main`.
3. Maak een pull request en merge naar `main`.
   - De workflow *Leren* commit dagelijks JSON naar `main`. Die bestanden heeft de branch niet aangeraakt, dus een conflict is niet te verwachten.
4. De lopende keten pakt de nieuwe code op bij de volgende herstart van ~5u40, of eerder als je de lopende run annuleert.
5. Daarna, als je wilt: `python -m storage.migrations proef 001`, dan `uitvoeren 001`, dan `python leren.py --geen-data`, en de JSON committen.

## 8. Aanbevolen volgende fase

1. **Besluit over migratie 001** (punt 7.1) en, samenhangend, één tijdsluiting voor leren en uitvoering (punt 7.3).
2. **Leren met dezelfde selectiepoort als het onderzoek.**
   - Nu kiest het leren nog in-sample, met alleen een controle ter informatie.
   - Laat het een variant pas activeren na een positieve validatie op data die het niet kende, in hetzelfde protocol als `research/protocol.py`.
3. **Duurzame opslag van de forward test** (punt 7.4). Pas daarna is er genoeg echte data om ooit live te overwegen.
4. **Instrumentkosten verifiëren** en in `core/markets.py` zetten.
5. Daarna pas de AI-onderzoekslaag. Die kan bouwen op deze onderdelen:
   - de `Signal`-interface;
   - de engine;
   - `research/registry.py`, als experimentlogboek;
   - `research/validation.py`, als poortwachter.
