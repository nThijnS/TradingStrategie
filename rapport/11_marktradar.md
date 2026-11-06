# MarktRadar: oplevering

Datum: 6 november 2026. Branch `feat/marktradar`, nog niet gecommit. Opdracht: [MARKTRADAR_PROMPT.md](../docs/MARKTRADAR_PROMPT.md), bronnenkeuze: [MARKTRADAR_FASE0.md](../docs/MARKTRADAR_FASE0.md). Geen financieel advies.

## Uitkomst

MarktRadar is gebouwd en getest, maar heeft nog nooit met het echte model gedraaid. Of nieuws en sentiment voordeel opleveren is onbewezen. Na 876 proeven heeft geen enkele strategie de selectiepoort gehaald, en MarktRadar verandert dat niet.

MarktRadar geeft alleen advies. Het kan geen orders plaatsen en raakt `execution/`, `config.json`, `learned.json` en de risicoregels niet.

## Wat er is gebouwd

| Bot | Taak | Werkwijze |
|---|---|---|
| Scout | Kiest maximaal 5 opvallende markten | Vaste regels op beweging, volatiliteit, volume en agenda |
| Charts | Technische stand per markt | Bestaande code uit `strategies/lab.py`, geen LLM |
| News | Agenda en Fed-berichten | Agenda uit code, berichten gelabeld door de LLM |
| Sentiment | Klantposities tegen eigen historie | Vaste regels, geeft nooit een richting |
| Skeptic | Tegenbewijs en veto | LLM met bewijsplicht op aangeleverde feiten |
| Chief | Regelt de ronde en geeft oordelen | Vaste regels; de LLM schrijft alleen de toelichting |

Verder: afrekening met scorekaart, ntfy-melding, eigen workflow (`.github/workflows/marktradar.yml`) en een MarktRadar-tab op het dashboard.

## Bronnen en kosten

| Bron | Gebruik | Kosten | Stand |
|---|---|---|---|
| Yahoo Finance | Koersen | Gratis | Werkt |
| Federal Reserve RSS | Nieuws | Gratis | Werkt |
| Forex Factory-weekbestand | Agenda | Gratis, voorwaarden niet gevonden | Werkte, gaf daarna één keer een HTTP-fout na meerdere verzoeken op één dag |
| Capital.com klantsentiment | Sentiment | Bestaande demo-inlog | Nog nooit aangeroepen |
| Claude API | Labels, tegenbewijs, tekst | Maximaal $0,25 per dag | Nog nooit aangeroepen |

Met `claude-opus-5-5` ($4 in, $20 uit per miljoen tokens) kost een ronde met 1.000 tokens in en 500 uit per aanroep ongeveer $0,04. Echte rondes zullen meer tokens gebruiken; de werkelijke kosten zijn nog niet gemeten.

## Getest

- 448 tests slagen op Python 3.9 en 3.12, zonder netwerk en sleutels.
- Een droge ronde en een echte ronde zonder sleutels werken. In die laatste krijgt elke markt `GEEN_ACTIE`.
- De echte Anthropic-SDK is getest tegen een lokale nepserver.
- De dashboardpagina is in de browser bekeken op desktop en telefoonbreedte, ook met een lege dataset en een kwaadaardige tekst.
- Beveiligingsregels zijn tijdelijk uitgeschakeld om te controleren dat de tests daarop falen.
- `execution/`, `risk/`, `learning/`, `strategies/`, `core/`, `config.json`, `learned.json`, `requirements.txt` en de workflow van de minuutketen zijn niet gewijzigd.

## Nog niet bewezen

- Hoe het echte model labelt, oordeelt en reageert op verborgen instructies.
- Of de Capital-demo echte sentimentwaarden geeft voor alle 15 markten, en of de `marketId` gelijk is aan de epic.
- Of een extra Capital-login de minuutketen stoort.
- Of de workflow op GitHub werkt. Hij kan pas draaien na een merge naar `main`.
- Of MarktRadar stabiel draait over meerdere dagen.
- Of `max_tokens` 6000 genoeg is. Te weinig geeft een afgekapt antwoord en dan `GEEN_ACTIE`.

## Bewuste grenzen

- **Zekerheden zijn niet gemeten.** Charts en News staan op maximaal 0,60. De drempels 0,60 en 0,55 en de straf van 10% zijn startwaarden en moeten vaststaan voordat het scoren begint.
- **Injectie is beperkt, niet onmogelijk.** Een gemanipuleerd bericht kan samen met Charts `VOLGEN` halen als de Skeptic er geen veto op geeft. Het kan nooit een order worden.
- **Het filter op actiewoorden is eenvoudig.** Andere formuleringen kunnen erlangs.
- **De scorekaart toetst geen strategie.** Een goede score is pas reden om een idee via protocol P1-P5 te toetsen. Conclusies pas vanaf 100 voorspellingen op 30 dagen.

## Data is publiek

De workflow bewaart rondes, metingen, kosten en uitkomsten op de branch `marktradar-data`. De repo is publiek, dus iedereen kan die lezen, inclusief percentages van Capital.com en samenvattingen van nieuws. Controleer vóór de merge of je dat wilt.
