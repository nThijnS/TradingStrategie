# MarketPilot

Analyse, onderzoek en demo-uitvoering voor 15 markten, plus ICT/TJR-meldingen. De software draait in GitHub Actions.

MarketPilot heette eerder TradingStrategie. De GitHub-repository, de website-URL, de commando's en de workflowbestanden houden hun oude naam; zie [docs/MARKETPILOT.md](docs/MARKETPILOT.md).

- **Meldingen:** ntfy, elke minuut tijdens de sessies.
- **Zelflerend:** dagelijks wordt per markt een variant gekozen.
- **Strategielab:** 15 markten.
- **Orders:** op een Capital.com-**demo**, alleen voor een strategie die de selectiepoort haalt en een instrument dat het leesrapport bevestigt. Live staat uit en kan alleen na 7 bewuste opt-ins.
- **Saldo:** stortingen en opnames tellen niet als winst; de positiegrootte rekent met een vast risicokapitaal (`config.json` → `demo.risicokapitaal`).
- **Status per markt en saldoverwerking:** [docs/MARKETPILOT.md](docs/MARKETPILOT.md).
- **Website:** <https://nthijns.github.io/TradingStrategie/>

Geen financieel advies. Geen enkele strategie heeft tot nu toe de vooraf vastgelegde selectiepoort gehaald; zie [rapport/2_onderzoek.md](rapport/2_onderzoek.md).

## Structuur

Zie [docs/ARCHITECTUUR.md](docs/ARCHITECTUUR.md). Kort:

- `core/` bevat data, markten en configuratie.
- `strategies/` bevat de signalen.
- `backtesting/engine.py` is de enige trade-simulatie.
- `learning/` doet de automatische keuze.
- `research/` bevat het onderzoek.
- `risk/` en `execution/` regelen de orders.
- `storage/` regelt de opslag.
- `dashboard/` maakt de data voor de website in `docs/`.

## Veelgebruikte commando's

```bash
python tradingstrategie.py --scan          # setups van de afgelopen 30 dagen
python tradingstrategie.py --logboek       # forward test: setups, uitkomsten, weigeringen
python leren.py --geen-data                # leerkeuze opnieuw maken uit het bestaande geheugen
python strategielab.py --markt GOUD        # lab voor één markt (schrijft lab_test.json)
python -m storage.migrations               # migraties van de opgeslagen data
python -m unittest discover -s tests -v    # tests
```

Mac: dubbelklik `Start MarketPilot.command` (de oude `Start TradingStrategie.command` werkt ook nog).
