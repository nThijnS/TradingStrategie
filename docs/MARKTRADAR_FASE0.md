# MarktRadar fase 0: inventaris (6 november 2026)

Dit is de uitkomst van fase 0 uit [MARKTRADAR_PROMPT.md](MARKTRADAR_PROMPT.md). Er is geen code gewijzigd. De bronnen zijn getest met kleine leesverzoeken vanaf deze Mac.

## Belangrijkste conclusie

Scout en Charts kunnen vrijwel helemaal op bestaande code draaien. Sentiment heeft gratis bronnen met historie. Voor News is de kalender geregeld, maar nieuwsberichten in brede dekking nog niet: GDELT, de enige brede gratis kandidaat, leverde in de test geen enkel artikel op. Daarom begint News met officiële bronnen.

Klantsentiment van Capital.com heeft geen historie in de API. Die reeks ontstaat alleen als we hem vanaf nu zelf opslaan.

## Herbruikbare code (op `origin/main`)

| Onderdeel | Bestaand | Gebruik in MarktRadar |
|---|---|---|
| Markten en kosten | `core/markets.py`, met gemeten kosten voor de 15 labmarkten | Scout, Charts, afrekening na kosten |
| Koersdata | `core/data.py`, `dashboard/status.py` (`fetch_cached`, `closed_bars`) | Scout, Charts |
| Marktstand en signalen | `strategies/lab.py` (`indicators`, `regime_now`, `signals`) | Charts |
| Tijd en sessies | `core/sessions.py`, `core/market_hours.py` | Rondetijd, geopende markten |
| Onderzoeksgeschiedenis | `rapport/*.md`, `rapport/experimenten.jsonl`, `kandidaten.json` | Skeptic |
| Vastleggen | `storage/`, `research/registry.py` | Rondes en reproduceerbaarheid |
| Meldingen | `app/alerts.py` (`push_phone`) | Briefing, maar zie aandachtspunt 1 |
| Workflowvoorbeeld | `.github/workflows/feedmeting.yml` (alleen lezen) | Basis voor de MarktRadar-workflow |

Er bestaat nog geen code voor nieuws, sentiment of LLM's, en `requirements.txt` heeft alleen yfinance, pandas en numpy.

### Aandachtspunten

1. `app/alerts.py` bevat ook de strategie- en logboekcode. Importeren is te breed; een klein eigen ntfy-bericht past beter.
2. `execution/capital.py` is de brokerclient en mag volgens de regels niet in MarktRadar. Het klantsentiment vraagt dus een aparte, kleine leesclient, met dezelfde inloggegevens. Die gegevens geven technisch ook toegang tot orders, dus de leesclient mag alleen `POST /session` en `GET /clientsentiment` kennen.
3. De `kandidaten.json`-teller en `proeven_scan` zijn nu de plek voor proeven. MarktRadar heeft geen eigen teller nodig zolang het alleen advies geeft. Pas als een idee een strategie wordt, telt het mee in het protocol.
4. Bouw vanaf `main`. De huidige map staat op `research/timeframes` en heeft niet-gecommitte wijzigingen van een andere sessie.

## Databronnen

| Bot | Bron | Test | Kosten en sleutel | Historie | Tijdstempel | Advies |
|---|---|---|---|---|---|---|
| Sentiment | Capital.com `/clientsentiment` | Documentatie gelezen, niet aangeroepen | Bestaande inlog | Geen in de API | Geen; zelf ophaaltijd vastleggen | **Gebruiken, direct verzamelen** |
| Sentiment | CFTC COT | Werkt, laatste rapport 27 oktober | Gratis, geen sleutel | Lang | Stand dinsdag, publicatie meestal vrijdag 15:30 ET | **Gebruiken als context** |
| Sentiment | Crypto Fear & Greed | Werkt, 3.197 dagen sinds 1 februari 2018 | Gratis, bronvermelding verplicht | Ja | Dagwaarde | **Gebruiken** voor BTC, ETH en SOL |
| Sentiment | Binance taker-flow | Werkt | Gratis, geen sleutel | 2+ jaar in `data/binance/` | Per candle | **Gebruiken** voor crypto |
| News | Federal Reserve RSS | Werkt | Gratis, geen sleutel | Alleen recente items per feed | `pubDate` | **Gebruiken als eerste nieuwsbron** |
| News | SEC EDGAR | Werkt (HTTP 200) | Gratis, geen sleutel | Ja | Te controleren in fase 3 | **Gebruiken** voor AAPL, NVDA en MSFT |
| News | Forex Factory-weekbestand | Werkt, met impact, forecast en previous | Gratis, voorwaarden niet gevonden | Alleen lopende week | Ja | **Tijdelijk gebruiken**, zelf opslaan, geen ruwe data publiceren |
| News | FRED-releasedatums | Documentatie gelezen | Gratis sleutel nodig | Ja | Alleen datum | **Reserve** voor de kalender |
| News | GDELT DOC 2.0 | Twee keer limietmelding, daarna leeg antwoord | Gratis, bronvermelding | Gedocumenteerd: 3 maanden | Ja | **Nog niet**, opnieuw testen vanuit GitHub Actions |
| News | Finnhub-kalender | Niet vast te stellen | Onbekend | Onbekend | Onbekend | **Niet gebruiken** tot de voorwaarden duidelijk zijn |

De GDELT-gebruiksvoorwaarden zijn alleen via zoekresultaten gezien, niet op de live pagina. Voor Capital.com is nog niet getest of de demo-omgeving echte waarden geeft of alle 15 markten dekt. Dat kan alleen via een workflow, omdat de inloggegevens in GitHub Secrets staan.

## Eerlijkheidsgrenzen

- **COT is al getoetst.** Het viel in protocol vijf-v1 af (0 van 9 toelaatbaar). Sentiment mag het tonen als context, maar niet als voorspeller. Hetzelfde geldt voor funding, dat daarom niet in de lijst staat.
- **Dagelijkse sentimentwaarden zijn traag.** Een ronde per dag kan alleen dagelijkse effecten meten.
- **100 voorspellingen duurt maanden.** Met maximaal 5 markten per dag kan het aantal snel lijken te groeien, maar voorspellingen op dezelfde dag hangen samen. Reken ook per dag en niet alleen per voorspelling.
- **Nieuwsbronnen zijn geen voorsprong.** Een Fed-bericht of kalenderdatum is al bij iedereen bekend. News helpt vooral bij context en risicomomenten.

## Aanbevolen start

- **Sentiment:** eerst Capital.com, zodat de eigen historie meteen begint. Fear & Greed daarna, omdat die meteen historie heeft.
- **News:** eerst Forex Factory-kalender plus Federal Reserve RSS. Dat is genoeg voor "wat staat er vandaag op de agenda en wat is er net gepubliceerd".
- **Fase 3 aanpassing:** de prompt noemt één bron per bot, dus de overige bronnen volgen pas na een stabiele eerste versie.

## Bronnen

- [Capital.com API](https://open-api.capital.com/)
- [GDELT DOC 2.0](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
- [GDELT over het project](https://www.gdeltproject.org/about.html)
- [CFTC Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)
- [Fear & Greed Index](https://alternative.me/crypto/fear-and-greed-index/)
- [Federal Reserve feeds](https://www.federalreserve.gov/feeds/feeds.htm)
- [SEC EDGAR API's](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [FRED release dates](https://fred.stlouisfed.org/docs/api/fred/releases_dates.html)
- [Finnhub economic calendar](https://finnhub.io/docs/api/economic-calendar)
- [PyPI forexfactory](https://pypi.org/project/forexfactory/)
