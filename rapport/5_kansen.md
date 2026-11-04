# Kansen-onderzoek: goede maandwinst op 10k binnen de regels

Datum: 4 november 2026. Protocol `kansen-v1` (`research/kansen_protocol.json`) is vastgelegd vóór de eerste uitslag.
Data: 2 jaar uurcandles met bied- en laatprijs van Capital.com (demo, alleen-lezen), tot 4 november 2026. Uitkomsten per variant staan in `rapport/kansen.json`.

## Uitkomst

**Geen enkele variant haalt P1–P5. Er is dus niets ingebouwd en de bot handelt hetzelfde als eerst.** Dat volgt uit de regel die vooraf is vastgelegd: alleen wat slaagt gaat het lab in.

De risicolimieten, P1–P5, live-instellingen en de actieve configuratie zijn niet aangeraakt. Er zijn geen orders geplaatst en niets is handmatig op actief gezet.

Winst over een maand is niet te garanderen. Langer vasthouden verlaagt het verlies per trade flink, maar levert nog geen aantoonbare winst op.

## Wat er getoetst is

51 markten, waarvan 36 ook op 4h. In totaal 363 familie-markt-combinaties. De cijfers gaan over de laatste 180 dagen. Trades op de bestaande markten zijn apart geteld van trades op de nieuwe markten.

| Idee | Trades | Vóór kosten | Na kosten | Bij 1,5× kosten | Slaagt |
|---|---:|---:|---:|---:|---|
| Huidige 1h-aanpak op brokerprijzen | 9.409 | −0,017R | −0,116R | −0,163R | nee |
| Dure uren overslaan | 8.116 | −0,020R | −0,111R | −0,153R | nee |
| Langer vasthouden op 4h (tot 120 uur) | 1.481 | +0,030R | −0,031R | −0,052R | nee |
| Extra markten, 1h | 21.256 | −0,029R | −0,130R | −0,177R | nee |
| Extra markten, 4h | 3.220 | −0,068R | −0,143R | −0,167R | nee |

Wat dit betekent:

- **Meer markten helpt niet.** De extra markten zijn slechter dan de bestaande, vooral op 4h.
- **Meer crypto helpt niet.** Capital.com biedt 246 cryptomarkten aan, maar alleen BTC (0,06%) en ETH (0,07%) hebben een lage spread. De overige goedkoopste munten zitten rond 0,50%, ongeveer zeven keer zo duur. Dat is één meting per markt, op één moment. BTC, ETH en SOL zitten bovendien al in de bot, en de limiet van één trade per groep geldt ook voor crypto.
- **Dure uren overslaan helpt nauwelijks**: 0,01R.
- **Langer vasthouden is de enige hefboom die werkt.** Het verlies bij 1,5× kosten daalt van −0,163R naar −0,052R, omdat de stop groter is en de kosten dus minder wegen. Het komt uit op ongeveer nul, niet op winst.

## Waarom het niet slaagt

Reden per combinatie (één combinatie kan op meerdere poorten falen):

| Poort | Combinaties die erop falen |
|---|---:|
| P4 Deflated Sharpe | 255 |
| P2 validatie positief | 252 |
| P5 zonder 5 beste trades | 249 |
| P3 training positief | 220 |
| P1 genoeg trades | 132 |

De hoogste uitschieters op de evaluatieperiode (zoals OLIE op 4h met +0,30R over 27 trades) falen elk op minstens twee poorten, en P4 hoort daar altijd bij. Dat past bij toeval uit honderden combinaties. Goud is op 4h het sterkst in de ontwikkelperiode (+0,20R, daarna +0,05R op de evaluatie), maar die keuze is achteraf gemaakt en goud haalt de poorten niet.

## Wat 10k per maand zou doen met 4h

Dit is de beste beschikbare optie, gesimuleerd met de ongewijzigde limieten: 0,5% risico, maximaal 3 open, 1 per groep, 3% dagverlies en 5% verlies vanaf de top. Elke maand start opnieuw op €10.000. Periode: 24 maanden, circa 29 trades per maand. De simulatie is beschrijvend en geen toets.

| Kosten | Gemiddeld per maand | Mediaan | Positieve maanden | Beste | Slechtste |
|---|---:|---:|---:|---:|---:|
| Normaal | −€5 | +€14 | 12 van 24 | +€593 | −€623 |
| 1,5× | −€22 | −€17 | 12 van 24 | +€575 | −€645 |

De 5%-limiet werd in 2 tot 3 van de 24 maanden geraakt. De kans op een winstmaand is dus ongeveer die van een muntworp, en de spreiding is groot. In de echte bot start de limiet niet elke maand opnieuw, dus de echte kans om stilgezet te worden is groter.

## Wat er nodig is voor een goede maand

Rekenvoorbeeld met 40 trades per maand, winst van 2R, 0,5% risico en de 5%-limiet vanaf de top:

| Voordeel per trade | Kans op winst | Kans op +5% of meer | Kans dat de limiet raakt |
|---|---:|---:|---:|
| −0,16R (huidige 1h) | 19% | 3% | 69% |
| −0,05R (4h) | 35% | 9% | 53% |
| 0R | 43% | 14% | 45% |
| +0,1R | 60% | 26% | 32% |
| +0,2R | 75% | 42% | 21% |
| +0,3R | 86% | 59% | 13% |

Een doel van +5% (€500) is 10R netto. Zelfs met een voordeel van +0,2R haal je dat in minder dan de helft van de maanden, en zo'n voordeel is in geen van de getoetste ideeën te zien. Binnen de regels kan alleen een strategie met echt voordeel dit halen. Meer markten of meer trades vergroten bij nul voordeel alleen de kans dat de limiet raakt.

## Wat nog kan

- **4h-families meedraaien in het lab, zonder orders.** Het lab verzamelt dan nieuwe vooruitkijkende data op de variant met de laagste kosten. De bot heeft daarvoor een vasthoudtijd per strategie nodig (nu 12 uur). Dat is een nieuwe keuze die afwijkt van de regel in `kansen-v1`, dus alleen op verzoek. Het voegt 6 proeven per markt toe. Bovendien haalt swing_breakout P1 gemiddeld maar net, swing_pullback net niet en swing_trend bij lange na niet.
- **P1 op portefeuilleniveau beoordelen** in plaats van per markt. Dat is een wijziging van de poorten en valt buiten de huidige afspraken.

## Beperkingen

- Twee jaar is kort, en de financieringstarieven zijn de stand van vandaag, niet historisch.
- Ontvangen rente telt niet mee. Dat is voorzichtig gerekend.
- De maandsimulatie gebruikt alle zes de 4h-varianten door elkaar en houdt geen rekening met de sessie-regels per markt.
- Aandelen zijn niet op 4h getoetst, omdat ze dagelijks sluiten.
- AAPL, NVDA en MSFT hadden geen marktsoort in de lijst. Ze zijn wel op 1h getoetst.
- Markten met 5.000 candles of minder zijn overgeslagen (3 van de 54).

## Reproduceren

Run geregistreerd in `rapport/experimenten.jsonl` (commit `ce48a3f`, schone code). Een tweede run gaf exact dezelfde `rapport/kansen.json`.

Data ophalen: workflow `capitaldata.yml`. Toetsen: `python -W ignore -m research.kansen <map> --uit rapport/kansen.json`.
