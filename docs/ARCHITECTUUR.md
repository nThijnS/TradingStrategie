# Architectuur TradingStrategie

Sinds de refactor van november 2026 (branch `refactor/clean-architecture`). Achtergrond: [refactor/](refactor/).

## Lagen

```
             ┌──────────── app/alerts.py ─────────────┐   meldingen (ntfy, macOS), logboek
             │                                        │
core/ ──► strategies/ ──► backtesting/engine.py ──► learning/ ──► learned.json / lab.json
 data       ict_tjr          (DE simulatie)          ict, lab
 markets    lab, classic          ▲                     │
 config     base (Signal)         │                     ▼
 sessions                    research/            dashboard/status.py ──► branch live ──► docs/ (website)
                             protocol, histdata_ict       │
                                                          ▼
                                          execution/runner.py ──► Capital.com (demo; live alleen na opt-in)
                                                 risk/rules.py
storage/: paden, JSON laden/opslaan, migraties (alle lagen)
```

| Map | Verantwoordelijkheid | Belangrijkste bestand |
|---|---|---|
| `core/` | tijd/sessies, marktdefinities en kosten, marktdata (Yahoo, HistData), configuratie | `config.py`, `markets.py`, `data.py` |
| `strategies/` | signalen, geen uitkomsten. Interface: `strategies/base.py` (`Signal`) | `ict_tjr.py` (de ICT/TJR-strategie) |
| `backtesting/` | **de enige trade-simulatie** (`engine.py`), ICT-koppeling (`ict.py`), statistiek, prop-firm | `engine.py` |
| `research/` | testprotocol, HistData-backtests, chronologische validatie, experimentregistratie, archief | `protocol.py` |
| `learning/` | per markt zelf kiezen tussen alle strategieën (ICT is er één van): actief / onderzoek / pauze; ICT-uitkomsten verzamelen; journaal | `selector.py`, `generator.py`, `lab.py`, `ict.py` |
| `risk/` | pure risicoregels (positiegrootte, limieten, correlatiegroepen) | `rules.py` |
| `execution/` | orderuitvoering Capital.com, instrumentcontrole | `runner.py` |
| `storage/` | bestandspaden, atomair opslaan, migraties met backup | `paths.py`, `MANIFEST.md` |
| `dashboard/` | data voor de website (`status.json`, `markt/*.json`) | `status.py` |
| `docs/` | website (GitHub Pages) en documentatie | `index.html` |
| `tests/` | unit-, regressie- (golden) en integratietests | |

## Afspraken

1. **Eén simulatie.** Een strategie levert signalen. Vulling, stop, doel, tijdsluiting en kosten komen uitsluitend uit `backtesting/engine.py` (regels bovenaan dat bestand). Een nieuwe strategie schrijft geen eigen trade-lus.
2. **Geen look-ahead.**
   - Signalen gebruiken alleen afgesloten candles.
   - Een market-instap gebeurt op de open van de volgende candle.
   - Bij een limietorder telt een doel in de vulcandle niet.
   - Getest in `tests/test_strategy_learning.py`: setups veranderen niet als er later data bij komt.
3. **Chronologisch kiezen.** Keuzes gebruiken alleen data van vóór de periode waarop ze getest worden. De strategie-selectie (`learning/selector.py`) kiest varianten op train en laat ze pas toe na de poort op de laatste 180 dagen. Een strategie die na inschakelen slecht presteert, gaat weer uit.
4. **Eén bron per gegeven.**
   - Marktdefinities en kosten staan in `core/markets.py`.
   - Paden staan in `storage/paths.py`.
   - Welk bestand wat bevat staat in `storage/MANIFEST.md`.
5. **Reproduceerbaar.**
   - Synthetische testdata gebruikt een vaste seed.
   - De bootstrap gebruikt een vaste seed.
   - Elke onderzoeksrun schrijft commit, versies en een data-vingerafdruk naar `rapport/experimenten.jsonl`.
6. **Oude namen blijven werken.** `tradingstrategie.py`, `leren.py`, `strategielab.py`, `live_status.py`, `broker.py`, `onderzoek.py`, `backtest.py`, `backtest_multi.py`, `capital_instrumenten.py`, `demo_broker.py`, `risico.py` en `broker_capital.py` zijn doorverwijzingen. De workflows en de Mac-starter roepen ze ongewijzigd aan.

## Nieuwe varianten (automatisch)

`learning/generator.py` stelt dagelijks zelf nieuwe varianten van bestaande strategieën voor en zeeft ze op train. Zie [refactor/6_kandidaat_generator.md](refactor/6_kandidaat_generator.md). Een nieuwe strategiefamilie toevoegen blijft handwerk, zie hieronder.

## Een strategie toevoegen

1. Schrijf in `strategies/<naam>.py` een functie die signalen geeft. Dat kan als bool-reeksen, zoals in `strategies/lab.py`, of als `Signal`-objecten, zoals in `strategies/classic.orb_signals`.
2. Laat de trades door `backtesting/engine.py` lopen. Voor 1h-strategieën gaat dat met `strategies.lab.run_signals`.
3. Toets de strategie met `research/protocol.py`: een vooraf vastgelegde selectiepoort met train, validatie en eindtest.
4. Live gaan kan pas na een positieve eindtest, ≥ 3 maanden demo en de vrijgave in `config.json` → `live.strategieen`.

## Tests

```bash
python -m unittest discover -s tests -v
```

De tests draaien zonder netwerk en zonder HistData. Ze draaien ook in GitHub Actions (`.github/workflows/tests.yml`).
