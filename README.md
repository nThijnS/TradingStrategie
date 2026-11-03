# TradingStrategie

ICT/TJR-meldingen en onderzoek. De software draait in GitHub Actions.

- **Meldingen:** ntfy, elke minuut tijdens de sessies.
- **Zelflerend:** dagelijks wordt per markt een variant gekozen.
- **Strategielab:** 15 markten.
- **Orders:** op een Capital.com-**demo**. Live staat uit en kan alleen na 7 bewuste opt-ins.
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

Mac: dubbelklik `Start TradingStrategie.command`.
