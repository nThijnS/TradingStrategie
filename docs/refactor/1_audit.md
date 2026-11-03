# Fase 1 — Repository-audit (3 november 2026)

Uitgangspunt: `main` op GitHub (commit `4fd8869`) plus de lokale map, die geen git-repo is.
De Python-code op GitHub en lokaal is identiek. Alleen de JSON-bestanden die de bot dagelijks bijwerkt verschillen; GitHub is daar nieuwer.
Tien onderzoeksscripts staan **alleen lokaal**.

Legenda advies: **B** = behouden, **V** = verbeteren, **S** = samenvoegen, **A** = archiveren (bewaren, niet meer actief), **W** = verwijderen.

## 1. Actieve code (draait in de cloud of lokaal)

| Bestand | Functie | Gebruikt door | Afhankelijk van | Problemen | Advies |
|---|---|---|---|---|---|
| `tradingstrategie.py` (817 r.) | ICT/TJR-detectie (`analyse`), meldingen (macOS + ntfy), logboek, `--scan`, `--once` | workflow TradingStrategie (elke minuut), `live_status`, `leren`, alle backtests | yfinance, pandas | Strategie, configuratie, data ophalen, meldingen en simulatie (`outcome`) in één bestand. `CFG`/`SET` zijn globale dicts die `apply_settings()` muteert. `outcome()` is een eigen trade-simulatie (5m, zonder kosten, dicht om 16:00). | **S/V**: strategie → `strategies/`, data → `core/`, meldingen → `app/`, simulatie → `backtesting/` |
| `live_status.py` | Schrijft `status.json` + `markt/*.json` voor de website | workflow (elke 3 min) | tradingstrategie, strategielab | Gebruikt `ts.outcome` voor de status van setups | **B/V** → `dashboard/status.py` |
| `leren.py` | Zelflerende ICT-parameterselectie, Obsidian-journaal | workflow Leren (dagelijks 21:30 UTC) | tradingstrategie; `--histdata` importeert `tp_videos` en `backtest` | Eigen simulatie `simulate5`. **DOL-terugval 2R**, terwijl de app terugvalt op `tp_r` (1R): leren beoordeelt dus andere trades dan de app handelt. `--histdata` werkt niet vanaf GitHub (`tp_videos.py` ontbreekt). Kosten (`COST`) dubbel met `backtest_multi`. Geen chronologische validatie: de keuze wordt gescoord op hetzelfde geheugen. | **S/V** → `learning/ict.py` + `learning/journal.py` |
| `strategielab.py` | 6 strategiefamilies × 15 markten op 1h-data, walk-forward, keuze per markt | workflow Leren, `live_status`, `onderzoek` | yfinance, leren (geheugen) | Eigen simulatie `simulate`. Selectiebias (gedocumenteerd in rapport/2). `stats` dubbel met `backtest.stats` en `onderzoek.summary`. | **S/V** → `strategies/lab.py` + `learning/lab.py` |
| `broker.py` | Orderuitvoering Capital.com (demo standaard, live met 7 opt-ins, noodstop) | workflow (elke 3 min) | risico, broker_capital | Goed getest (fail-closed). ICT-tijdsluiting = `max_uren` 12 u, terwijl leren 5 u simuleert en `outcome` om 16:00 sluit. | **B** → `execution/runner.py` (code ongewijzigd) |
| `broker_capital.py` | Capital.com REST-client | broker, capital_instrumenten | urllib | — | **B** → `execution/capital.py` |
| `risico.py` | Pure risicologica (sizing, limieten, correlatiegroepen) | broker | — | — | **B** → `risk/rules.py` |
| `demo_broker.py` | Doorverwijzing naar broker.py (oude naam) | niets meer (workflow roept broker.py aan) | broker | — | **B** als shim |
| `capital_instrumenten.py` | Leest instrumentgegevens (alleen lezen) | workflow Instrumenten | broker_capital | Nog nooit gedraaid (`rapport/instrumenten.json` bestaat niet) | **B** → `execution/instruments.py` |
| `onderzoek.py` | Vooraf vastgelegd testprotocol (train/validatie/eindtest, DSR, PBO, bootstrap) + rapport | handmatig | strategielab; ORB importeert `tp_videos` | Kopie van de lab-simulatie (+ uitstap-signalen, slippage). ORB heeft een derde eigen simulatielus. Faalt (ORB) vanaf GitHub door ontbrekend `tp_videos`. | **S/V** → `research/protocol.py` + `research/statistics.py` |
| `backtest.py` | HistData-lader, 1m-simulatie, `stats`, `prop_sim` | alle backtests, leren `--histdata` | tradingstrategie | **`load_m1` leest HistData als EST zonder zomertijd** (Etc/GMT+5): zomerresultaten 1 uur verschoven. De correctie staat alleen lokaal in `tp_videos.py`. Eigen simulatie `simulate`, die een TP in de vul-candle telt (optimistisch). | **S/V** → `core/data.py` + `backtesting/` |
| `backtest_multi.py` | ICT op 4 markten (HistData) | handmatig | backtest | Gebruikt de foute tijdzone-lader | **V** → `research/` |
| `Start TradingStrategie.command` | Dubbelklik-starter Mac | gebruiker | .venv | — | **B** |

## 2. Alleen lokaal (niet op GitHub)

| Bestand | Functie | Eigen simulatie? | Advies |
|---|---|---|---|
| `tp_videos.py` | **Zomertijd-correcte HistData-lader** `load_dst` | nee | **S** → `core/data.load_histdata` (nodig voor leren `--histdata` en ORB) |
| `backtest_dst.py`, `backtest_bias.py`, `backtest_tradingpool.py` | Afgeronde onderzoeken (resultaten in het geheugen/notities) | via `backtest.simulate` | **A** → `research/archief/`, met de gedeelde engine |
| `backtest_tp_model.py`, `backtest_tp_v2.py` | TradingPool-model (afgewezen) | ja (`exit_trade`) | **A** → `research/archief/` (bevroren; reproduceert historische cijfers) |
| `datafarm.py`, `datafarm_export.py` | LIT data farm + viewer-export (artifact) | ja | **A** → `research/archief/` |
| `dashboard.py`, `dashboard_export.py` | Dashboard v1 (lokale html + Claude-artifact) | gebruikt `outcome` | **A** → `dashboard/archief/` (vervangen door `docs/index.html`) |
| `artifact/`, `radar_artifact/`, `farm_artifact/` | Bronmappen van Claude-artifacts (snapshots) | — | lokaal laten, niet in de repo |
| `data/` (≈ 1 GB HistData + pkl-resultaten) | Historische data en backtestresultaten | — | lokaal laten (git-ignored, licentie HistData) |

## 3. Data en opslag

| Bestand | Schrijver | Lezer | Waar bewaard | Opmerking |
|---|---|---|---|---|
| `config.json` | gebruiker (dashboard-schakelaars) | tradingstrategie, broker | main | Instellingen voor meldingen, broker, live, demo |
| `learned.json` | leren | tradingstrategie (elke minuut), live_status | main (dagelijkse commit) | Overlapt deels met `config.json` (welke markt aan staat) |
| `leren_geheugen.json` (4 880 uitkomsten, 4 580 HistData + 300 Yahoo) | leren | leren, strategielab | main | Rijen hebben geen versie van de simulatie: een correctie mengt oude en nieuwe R-waarden |
| `leren_geschiedenis.json` | leren | live_status | main | keuze per dag |
| `lab.json` (0,5 MB), `lab_versies.json`, `lab_geschiedenis.json` | strategielab | live_status, **website** (`raw/main/lab.json`) | main | `lab_versies` en `lab_geschiedenis` overlappen (keuzes) |
| `logboek.json`, `verstuurd.json`, `demo_staat.json`, `live_staat.json` | keten | keten, leren | **alleen GitHub Actions-cache** | Cache verloopt na 7 dagen zonder gebruik: forward test en orderjournaal kunnen verdwijnen. Niet in `.gitignore`. |
| `status.json`, `demo.json`, `markt/*.json` | live_status, broker | website | branch `live` (force-push) | Afgeleid, geen historie nodig |
| `rapport/onderzoek.json` | onderzoek | rapport | main | |
| `journaal/` | leren | Obsidian, gebruiker | main | |

Paden die **niet** mogen veranderen zonder de keten te breken: `config.json`, `learned.json`, `leren_geschiedenis.json`, `lab.json`, `lab_geschiedenis.json`, `NOODSTOP` (de lopende keten haalt ze elke minuut op bij pad) en `docs/` (GitHub Pages bron).

## 4. GitHub Actions

| Workflow | Trigger | Schrijft | Geheimen/variabelen |
|---|---|---|---|
| `tradingstrategie.yml` | keten via `workflow_dispatch` + reserve-cron elke 3 u | branch `live` (force), caches | NTFY_TOPIC, CAPITAL_* (demo en live), CAPITAL_MODUS, NOODSTOP |
| `leren.yml` | dagelijks 21:30 UTC | commit op main | — |
| `tests.yml` | push van `*.py` (alle branches) | — | — |
| `instrumenten.yml` | handmatig | commit `rapport/instrumenten.json` | CAPITAL_* demo |

Let op: de keten start zichzelf op `github.ref_name`. Wie `TradingStrategie` handmatig op een andere branch start, start daar een tweede keten (die wacht in dezelfde concurrency-groep). `schedule` draait alleen op de standaardbranch.

## 5. Externe integraties

- **Yahoo Finance** (yfinance): 5m (60 d), 1h (730 d), 1d. Geen sleutel.
- **ntfy.sh**: pushmeldingen, onderwerp uit `NTFY_TOPIC` of het lokale `ntfy_topic.txt` (git-ignored).
- **Capital.com** REST (demo en live adres hard gescheiden).
- **GitHub API**: herstart van de keten met `GITHUB_TOKEN`.
- **jsdelivr**: lightweight-charts 4.1.3 op de website.
- Geen sleutels in de repo of de git-geschiedenis gevonden (alleen nepwaarden in de tests).

## 6. Dubbele functionaliteit

| Wat | Waar |
|---|---|
| Trade-simulatie | `tradingstrategie.outcome`, `backtest.simulate`, `leren.simulate5`, `strategielab.simulate`, `onderzoek.simulate`, `onderzoek.orb`, plus `backtest_tp_model.exit_trade` en `datafarm` (lokaal) — **8 varianten** |
| Statistiek | `backtest.stats`, `strategielab.stats`, `onderzoek.summary` |
| Data ophalen | `tradingstrategie.fetch`, `strategielab.fetch_all`, `onderzoek.fetch`; HistData: `backtest.load_m1` (fout) en `tp_videos.load_dst` |
| Kosten per markt | `leren.COST`, `backtest.COST_PTS`, `backtest_multi.MARKETS`, `strategielab.MARKETS`, `onderzoek.CANDIDATES` |
| Marktdefinities | `tradingstrategie.CFG["markets"]`, `strategielab.MARKETS`, `leren.HISTDATA`, `backtest_multi.MARKETS`, `broker.EPICS` |
| JSON laden | `leren.load`, `strategielab.load`, `broker.load`, `tradingstrategie.load_logbook` |
| Resample naar 5m/4h | `backtest.to5`, `live_status.resample`, `tradingstrategie.htf_state` |

## 7. Backtesting vs learning: verschillen in trade-logica

| Aspect | App/live (`outcome`, broker) | `backtest.simulate` (1m) | `leren.simulate5` (5m) | lab (1h) |
|---|---|---|---|---|
| Instap | limiet op entry, 5m | limiet, 1m vulling vanaf de 5m-candle | aangenomen gevuld op `entry_hit` | open volgende candle |
| TP bij DOL zonder liquiditeit | `tp_r` (standaard **1R**) | `s["tp"]` (= 1R) | **2R** | n.v.t. |
| TP in de vul-candle | telt | telt | telt | n.v.t. (instap op open) |
| Stop en TP in één candle | stop eerst | stop eerst | stop eerst | stop eerst |
| Uitstap op tijd | 16:00 NY | 16:00 NY of `max_hours` | 5 uur | 12 candles; broker 12 u |
| Kosten | geen | punten (incl. slippage) | punten (incl. slippage) | fractie + financiering |
| Slippage apart | — | — | — | alleen onderzoek (0,02R) |

## 8. Look-ahead en reproduceerbaarheid

- ICT-detectie: geen look-ahead gevonden. Pivots worden pas `n` candles later bevestigd, de HTF-staat geldt pas na de sluiting van de HTF-candle en de live data laat de lopende candle weg.
- Lab: signalen op de slot, instap op de volgende open. De look-ahead in de live signalen is op 2 november opgelost (`closed_bars`).
- `requirements.txt` heeft geen versies (`yfinance`, `pandas`). Een nieuwe pandas of yfinance kan resultaten stil veranderen.
- Er zijn geen tests voor de ICT-detectie, de backtests of leren. Bestaande tests: 68, alle groen (broker, risico, lab-statistiek).

## 9. Conclusie

De executielaag (broker, risico) is recent herschreven en goed getest; die blijft inhoudelijk ongewijzigd.
De zwakke plek is de onderzoek-/leerkant: acht losse simulaties met verschillende aannames.
De zelflerende laag beoordeelt bovendien trades met een andere TP-terugval en een andere tijdsluiting dan de app werkelijk gebruikt.
Het implementatieplan staat in [2_plan.md](2_plan.md).
