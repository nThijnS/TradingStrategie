# MarketPilot-webapp voor Netlify

Dit dashboard toont de agents en MarktRadar. Het kijkt alleen mee: het start of stopt niets, plaatst geen orders en schrijft niets naar GitHub.

## Wat er staat

| Map of bestand | Inhoud |
|---|---|
| `../netlify.toml` | Build, headers en beveiligingsregels |
| `public/` | De pagina zonder buildstap. Alleen deze map wordt gepubliceerd |
| `public/demo.json` | Fictieve demo-informatie, gemaakt uit `python -m marktradar --droog` |
| `netlify/functions/status.mjs` | `GET /api/status`, de enige plek die omgevingsvariabelen leest |
| `lib/` | Haalt GitHub-data op en zet die om naar het agentformaat |
| `tests/` | Tests zonder netwerk: `npm test` |

Er zijn geen npm-pakketten nodig.

## Deployen op Netlify

1. Maak op Netlify een site uit de repository `nThijnS/TradingStrategie` en kies de branch waarop deze app staat.
2. De instellingen komen uit `netlify.toml`, dus je hoeft geen build-instellingen in te vullen.
3. Zet de omgevingsvariabelen hieronder bij de site.
4. Deploy. De build draait eerst de tests; als die falen, gaat de deploy niet door.

De URL is openbaar voor wie hem kent. De pagina staat op `noindex` en toont alleen gegevens die nu al openbaar zijn op GitHub. Wil je een wachtwoord, gebruik dan Netlify Password Protection; dat hangt af van je abonnement.

## Omgevingsvariabelen

| Naam | Nodig | Doel |
|---|---|---|
| `GITHUB_TOKEN` | Aanbevolen | Hogere limiet bij GitHub. Geheim: alleen op Netlify zetten |
| `GITHUB_REPO` | Nee | Standaard `nThijnS/TradingStrategie` |
| `MARKTRADAR_DATA_BRANCH` | Nee | Standaard `marktradar-data` |

Maak voor `GITHUB_TOKEN` een fine-grained token met alleen toegang tot deze repository en leesrecht op **Actions** en **Contents**. Zonder token werkt de site ook, maar geldt de gedeelde limiet van 60 verzoeken per uur. De status wordt dan 15 minuten bewaard in plaats van 1 minuut, en bij de limiet toont de site een duidelijke melding.

Sleutels zoals `ANTHROPIC_API_KEY` en de `CAPITAL_*`-gegevens horen bij de GitHub-workflows. Zet die niet op Netlify.

## Lokaal draaien

```bash
cd web && npm run dev
```

De site staat dan op <http://127.0.0.1:8788>. Zet een token eventueel in `web/.env` (zie `.env.example`); dat bestand wordt niet gecommit.

## Herkomstlabels

| Label | Betekenis |
|---|---|
| Live | Zojuist opgehaald uit de echte bron |
| Verouderd | Echt, maar te oud: opgehaald meer dan 20 minuten geleden, of een ronde ouder dan 96 uur |
| Demo, fictief | Verzonnen voorbeeld, herkenbaar aan de gearceerde rand |
| Ontbreekt | De bron gaf geen antwoord |
| Niet geverifieerd | Er is geen bewijs uit een echte run |

Als MarktRadar-data ontbreekt, blijven de workflowkaarten echt en zijn alleen de MarktRadar-onderdelen demo. Als de functie niet bereikbaar is, toont de pagina de laatst bewaarde data als verouderd, en anders alles als demo.

## Wat nog ontbreekt

| Onderdeel | Stand | Nodig |
|---|---|---|
| Workflowstatus | Gekoppeld aan GitHub Actions | Alleen de token, voor de limiet |
| MarktRadar-workflow | Staat nog niet op `main` | Merge `feat/marktradar` |
| Echt model | Nooit aangeroepen | `ANTHROPIC_API_KEY` als GitHub-secret |
| MarktRadar-data | Branch bestaat nog niet | Eerste geslaagde run. Daarna verschijnen ronde, bots en scorekaart vanzelf |
| Capital-sentiment | Nooit opgehaald | Bestaande `CAPITAL_*`-secrets; de eerste ronde laat zien of het werkt |
| Duur per bot | Niet gemeten | MarktRadar slaat dit niet op; het dashboard toont "niet gemeten" |

Een onderdeel wordt pas "bewezen" door data: de functie kijkt naar geslaagde geplande of handmatige runs, een niet-droge ronde, modellen met kosten en compleet sentiment. Zie `verificatie` in `lib/marktradar.mjs`.

## Een databron toevoegen

Maak in `lib/` een module die de bron vertaalt naar dit formaat en voeg die toe in `lib/status.mjs`. Geef de browser alleen deze velden; `schoon()` verwijdert daarna bekende sleutelvormen.

```js
{
  id, naam, taak,
  groep: "marktradar" | "workflow",
  status: "bezig" | "wachtend" | "klaar" | "mislukt" | "aandacht",
  herkomst: "live" | "verouderd" | "demo" | "ontbreekt",
  geverifieerd: false,
  laatste_activiteit: "ISO-tijd of null",
  duur_s: null,
  stap: "huidige of laatst bekende actie",
  melding: null, // of { soort: "fout" | "blokkade" | "goedkeuring", tekst }
  activiteit: [{ t, tekst, status }], // oud naar nieuw
  link: null,
}
```

Geen financieel advies. Voorspellingen zijn geen bewezen resultaten.
