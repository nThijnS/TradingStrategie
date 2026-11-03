# Implementatieplan refactor (branch `refactor/clean-architecture`)

## Randvoorwaarden die de structuur bepalen

1. **De lopende keten op `main` haalt bestanden op bij pad** (`config.json`, `learned.json`, `lab.json`, `NOODSTOP`, …) en de website leest `raw/main/lab.json`. Deze datapaden blijven daarom gelijk. Centralisatie gebeurt in de code (`storage/`), niet door bestanden te verplaatsen.
2. **De workflows roepen `tradingstrategie.py`, `live_status.py`, `broker.py`, `leren.py`, `strategielab.py` en `capital_instrumenten.py` aan.** Die namen blijven bestaan als dunne doorverwijzingen naar de nieuwe pakketten. Daardoor hoeven de workflows inhoudelijk niet te veranderen en blijft een merge veilig.
3. **GitHub Pages serveert `docs/`.** De website blijft daar. De Python-kant van het dashboard komt in `dashboard/`.
4. **De ICT-detectie (`analyse`) verandert niet.** Dat wordt bewezen met een vergelijking tegen de oude code (golden test).
5. **De orderuitvoering (`broker`, `risico`, `broker_capital`) verandert inhoudelijk niet**, alleen van plek. De 68 bestaande tests blijven groen.
6. **De datafiles in de repo worden op de branch niet herschreven.** Een migratie draait pas na de merge, met backup (zie stap 6).

## Doelstructuur

```
app/          alerts.py         meldingen, logboek, --scan/--once (was tradingstrategie.py)
core/         sessions.py       NY-tijd, sessies
              markets.py        alle marktdefinities en kosten op één plek
              data.py           Yahoo, HistData (zomertijd-correct), opschonen, resamplen
              config.py         standaardinstellingen, config.json en learned.json toepassen
strategies/   base.py           gemeenschappelijke interface (Signal, Strategy)
              ict_tjr.py        de ICT/TJR-strategie (ongewijzigde logica)
              lab.py            trend, momentum, mean reversion, breakout, volatiliteit
              classic.py        Donchian, TSMOM, ORB (onderzoek)
backtesting/  engine.py         DE trade-simulatie (één implementatie) + kostenmodel
              metrics.py        statistiek (stats, bootstrap, DSR, PBO)
              prop.py           prop-firm-simulatie
research/     protocol.py       vooraf vastgelegd testprotocol (was onderzoek.py)
              histdata_ict.py   ICT-backtests op HistData (was backtest.py/backtest_multi.py)
              validation.py     chronologische splitsing, walk-forward, selectiepoort
              registry.py       experimentregistratie
              archief/          afgeronde onderzoeksscripts (bevroren)
learning/     ict.py            zelflerende ICT-selectie (was leren.py)
              lab.py            strategielab-keuze (was strategielab.py)
              journal.py        Obsidian-journaal
risk/         rules.py          risicologica (was risico.py)
execution/    runner.py         orderuitvoering (was broker.py)
              capital.py        Capital.com-client (was broker_capital.py)
              instruments.py    instrumentcontrole (was capital_instrumenten.py)
storage/      paths.py          alle bestandspaden op één plek
              jsonstore.py      laden en atomair opslaan
              migrations.py     controleerbare migraties met backup
dashboard/    status.py         status.json en markt/*.json (was live_status.py)
docs/         index.html        website (GitHub Pages), refactor-documentatie
tests/
```

## Stappen (elk een eigen commit, tests na elke stap)

| # | Stap | Controle |
|---|---|---|
| 0 | Audit en plan | — |
| 1 | Golden-referentie vastleggen met de **oude** code: synthetische data (vaste seed) + HistData-samenvatting | bestanden in `tests/golden/` |
| 2 | `storage/` en `core/` (paden, JSON, sessies, markten, data, HistData-lader met zomertijd) | unit-tests; HistData-lader = `tp_videos.load_dst` |
| 3 | `strategies/` (ICT ongewijzigd + interface) en `app/alerts.py`; doorverwijzing `tradingstrategie.py` | ICT-setups identiek aan golden |
| 4 | `backtesting/engine.py`; alle simulaties erop aansluiten | lab en onderzoek identiek aan golden; ICT-verschillen gemeten en gedocumenteerd |
| 5 | `learning/`, `research/`, `dashboard/`, `execution/`, `risk/` + doorverwijzingen | alle tests, imports, rooktests van elk script |
| 6 | Opslag: manifest, versie op geheugenrijen, migratiescript (dry-run + backup), `.gitignore` | migratie op een kopie; impact gerapporteerd |
| 7 | Workflows en website controleren (lokaal draaien, preview) | geen workflow gestart, geen orders |
| 8 | Documentatie en eindrapport | — |

## Bewust niet in deze refactor

- Geen nieuwe strategieën, markten of parameterwijzigingen.
- Geen PostgreSQL: de datavolumes (< 2 MB JSON) vragen er niet om.
- De keuze-logica van leren en het lab blijft gelijk. Validatie wordt **erbij gerapporteerd**, niet als nieuwe poort ingevoerd: dat zou live gedrag veranderen en is een beslissing voor de eigenaar.
- Niets wordt naar GitHub gepusht. Deze machine heeft geen GitHub-inlog; de branch staat lokaal klaar.
