# Fase 1 — Audit (2 november 2026)

Deze audit gaat uit van de code zoals die op GitHub staat (`nThijnS/TradingStrategie`, commit `74284fd`). De lokale map is geen Git-repository. De codebestanden zijn byte-voor-byte gelijk aan GitHub; alleen gegenereerde data (`lab*.json`, `learned.json`, `leren_*`) is lokaal ouder. Er zijn geen orders geplaatst, ook geen testorders, en er zijn geen API-verzoeken naar Capital.com gedaan: de sleutels staan alleen als GitHub-geheim.

## 1. Programmastroom

```
GitHub Actions-keten (tradingstrategie.yml, elke minuut, ~5u40 per run, herstart zichzelf)
 ├─ tradingstrategie.py --once      ICT op Yahoo 5m (NQ, EURUSD, GOUD) → ntfy-melding + logboek.json
 └─ elke 3 min:
     ├─ live_status.py               Yahoo 5m/1h/1d voor 15 markten → status.json + markt/*.json
     │    └─ lab_signals()           strategie die het lab koos, op 1h-candles → "nieuw"-signaal
     └─ demo_broker.py               leest status.json → orders op Capital.com DEMO (of OANDA demo)
          └─ demo_staat.json         welke signalen al verwerkt zijn (actions-cache)
Dagelijks 21:30 UTC (leren.yml): leren.py (ICT-variant per markt) → strategielab.py (strategie per markt)
Dashboard: docs/index.html (GitHub Pages) leest status.json, lab.json en demo.json van de branch "live"
```

## 2. Data, tijd en sessies

| Onderdeel | Bron | Interval | Historie | Tijdzone |
|---|---|---|---|---|
| ICT live | Yahoo (NQ=F, EURUSD=X, GC=F) | 5m | 30 dagen | NY; de lopende candle wordt weggelaten ✔ |
| ICT leren | Yahoo 5m (60 d) + eenmalig HistData 1m | 5m | 2025 t/m okt 2026 | HistData met de zomertijd-fix (`load_dst`) ✔ |
| Strategielab | Yahoo 1h | 1h | ~730 dagen | UTC |
| Live signalen lab | Yahoo 1h, cache 10 min | 1h | 60 dagen | UTC; **lopende candle wordt níet weggelaten ✘** |
| Broker | Capital.com demo-API | – | – | snapshot zonder tijdcontrole |

- Yahoo-futures (NQ=F, GC=F, CL=F …) lopen 10–15 minuten achter. Het lab vergelijkt die prijzen met spot-CFD's bij Capital.com, en die verschillen (bijvoorbeeld goud-future tegenover spot). `demo_broker` corrigeert met een "basis" (brokerprijs min Yahoo-koers).
- `is_open()` kent geen feestdagen en past voor alle futures en forex dezelfde uren toe.

## 3. Backtest en walk-forward

- **ICT (`leren.py`):** 48 varianten per markt, gescoord op gemiddelde min 1 standaardfout met recency-weging. De keuze valt op dezelfde data waarop de score staat: er is geen apart testdeel.
- **Strategielab:** zes soorten met elk twee varianten.
  - Walk-forward: 240 dagen train, 60 dagen test, steeds opschuivend. Daarbinnen is de variantkeuze netjes chronologisch.
  - Instap op de open van de volgende candle.
  - Als stop en doel in dezelfde candle vallen, rekent het lab de stop eerst. Dat is conservatief ✔.
  - Kosten zijn een vast deel van de prijs.
- **Het probleem (selectiebias):** `choose()` kiest per markt de strategie met de beste ondergrens *op de walk-forward-testtrades*. Die testdata wordt dus wél gebruikt om te kiezen.
  - Over 15 markten × 6 soorten (90 combinaties, ~180 varianten, plus 48 ICT-varianten) is de kans groot dat er toevallig een paar boven 0 uitkomen.
  - "Ondergrens = gemiddelde − 1 SE > 0" laat bij een strategie zonder voordeel ~16% door. Bij 90 nul-combinaties zijn dat er ~14 die toevallig slagen.
  - Er is geen onaangeroerd eindtestdeel.
- **Onzekerheid:** de standaardfout gaat uit van onafhankelijke trades. Er is geen correctie voor clustering in de tijd en geen correctie voor het aantal geprobeerde varianten.
- **Wat ontbreekt:**
  - financieringskosten (trades tot 12 uur kunnen over het dagelijkse rollmoment heen);
  - slippage;
  - een gevoeligheidstest voor kosten en parameters.
- **Benchmark:** kopen-en-houden is er, maar in procenten. Dat is niet vergelijkbaar met R.

## 4. Strategie- en parameterselectie

- `learned.json` (ICT) en `lab_versies.json` (lab) worden elke werkdag automatisch bijgewerkt. Er is geen menselijke review; de eigenaar wilde dat zo.
- Er staan remmen op: minimaal aantal trades (20 en 30), een wisselmarge van 0,05R en "geen trade" als niets boven 0 komt. Die remmen beschermen niet tegen de selectiebias hierboven.
- Op het dashboard staat voor Nasdaq 100 trend volgen: 105 trades, +0,12R, 95%-interval −0,08 tot +0,32. Dat interval loopt door 0 en is ook nog door selectie opgeblazen. Er is dus geen bewijs voor een voordeel.

## 5. Capital.com-integratie (`demo_broker.py`)

| Punt | Bevinding |
|---|---|
| Omgeving | Vast demo-adres (`demo-api-capital…`). Live kan niet. ✔ voor nu |
| Account | `preferred` account of het eerste. Er wordt geen account-ID gecontroleerd en er is geen `PUT /session` |
| Authenticatie | Elke 3 min een nieuwe sessie met sleutel, e-mail en sleutelwachtwoord uit de omgeving. Er wordt niets gelogd ✔ |
| Instrumentcodes | Vaste lijst epics (`US100`, `GOLD` …). Deze zijn nooit via de API gecontroleerd |
| Contractgrootte | Aangenomen dat 1 unit = 1 valuta-eenheid per punt. `lotSize` en `scalingFactor` worden niet gelezen ✘ |
| Stopafstand | `minStopOrProfitDistance` wordt niet gecontroleerd. Prijsafronding gebeurt via `decimalPlacesFactor` ✔ |
| Orderbevestiging | `GET /confirms` direct na de order, zonder herhaalpoging. Bij een time-out of 404 heet de order "mislukt" terwijl die misschien wél is uitgevoerd ✘ |
| Bescherming | SL/TP gaan mee in de order, maar daarna wordt niet gecontroleerd of ze op de positie staan ✘ |
| Idempotentie | Alleen via `demo_staat.json` in de actions-cache. Die wordt pas aan het eind van een run van ~5u40 opgeslagen. Als de runner hard stopt, raakt de staat kwijt. Er is geen controle bij de broker op een bestaande positie of order ✘ |
| Koppeling positie ↔ signaal | Een gok: "de nieuwste order op hetzelfde instrument" |

## 6. Risicolimieten

- Er zijn limieten voor risico per trade (0,5%), maximaal open posities (3), dagverlies (3%) en een meeschuivend totaalverlies (5%). Er is ook een hefboomlimiet van 1:30.
- **Telling bij gelijktijdige signalen:** "worst case = (open + 1) × 0,5%". Dat telt posities in plaats van werkelijk risico. Een positie zonder stop, of een positie die bij een hogere NAV is geopend, wordt verkeerd geteld. Signalen in dezelfde ronde worden wel na elkaar opgeteld ✔.
- **Correlatie:** er is geen limiet. Drie long-trades op NQ, ES en NVDA zijn in feite één weddenschap.
- **Kosten in de positiegrootte:** spread en slippage tellen niet mee.
- **Hefboomberekening:** benaderend. USD-bedragen worden gedeeld door `acc_to_usd`, en dat is de verkeerde kant op.

## 7. Tegenstrijdigheden

1. Onderaan het dashboard staat: "deze site en de bot plaatsen nooit orders". `status.json` zegt "er worden nooit orders geplaatst". Toch plaatst `demo_broker.py` automatisch demo-orders.
2. De docstring van `strategielab.py` zegt "plaatst nooit orders". Klopt voor het lab zelf, maar zijn signalen gaan wél naar de demo-broker.
3. Het dashboard noemt het lab-resultaat "op nieuwe data". Door de selectie over strategieën is het dat maar half.
4. **Look-ahead in live gebruik:**
   - `lab_signals()` rekent op de laatste Yahoo-uurcandle, en die loopt nog. Nagegaan op 2 nov 16:03 UTC: de laatste candle begon om 16:00.
   - De backtest gebruikt alleen afgesloten candles. Live signalen kunnen dus verschijnen en weer verdwijnen ("repainten").
   - Het signaal krijgt als tijd het *einde* van die lopende candle, een tijdstip in de toekomst. De 20-minutengrens in `demo_broker` houdt het dus niet tegen.
5. Het dashboard zegt: "met een echte sleutel kan de bot niets doen". Dat klopt, maar er is ook geen live-modus, terwijl de opdracht die vraagt.
