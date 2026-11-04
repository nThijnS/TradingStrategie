# Voorstel: meer valide kansen onderzoeken (4 november 2026)

Geschreven na de inspectie en vóór het eerste resultaat van een lagere-tijdframevariant. Het protocol ligt vast in
`research/tijdframes_protocol.json`; `rapport/tijdframes.json` bewaart de hash ervan bij elke run.

## Wat de inspectie liet zien

- **Tijdframes.** Het lab test en handelt op één tijdframe: 1h, ongeveer 2 jaar Yahoo-data, trades van maximaal 12 uur.
  Alleen ICT gebruikt 5m. 15m, 4h en 1d staan alleen op de grafieken.
- **Geen orders op dit moment.** Op main staat geen enkele markt op `actief`. Het orderlog van `demo.json` toont één
  order (GOUD long, 2 november), goed voor -€ 4,95. Dat is te weinig om conclusies uit te trekken.
- **Afwijzingen op 2 november.** Bijna elke familie valt op meerdere poorten tegelijk. De poorten zijn dus niet één
  knelpunt: er is te weinig bewezen voordeel. NQ-breakout en ES-momentum vallen alleen op P4.
- **Kosten.** De gemeten spread van 3 november is op een aantal markten hoger dan het model: GOUD 0,019% tegen 0,010%,
  ZILVER 0,10% tegen 0,06%, SOL 0,50% tegen 0,12%, aandelen 0,13-0,22% tegen 0,05%. Dat is één meting, mogelijk buiten
  de beursuren. Op lagere tijdframes wegen kosten zwaarder, omdat de stop kleiner is.
- **Uitvoerbaarheid.** `risk/rules.py` weigert een order als de spread meer is dan 0,25R. Dat knijpt juist op 5m.
- **Data.** Lokaal staat 1m-HistData van 1 januari 2025 tot 23 oktober 2026 voor 6 markten: EURUSD, GBPUSD, NQ, ES,
  GOUD en ZILVER. Voor de andere 9 markten is geen 15m/5m-historie, want Yahoo geeft die maar zo'n 60 dagen.
- **Live data.** Live signalen komen van Yahoo; futures en aandelen kunnen 10-15 minuten achterlopen. Dat is voor 1h te
  doen, maar niet voor een 5m-instap. De bestaande Capital.com-client leest al wel koersen.
- **Nieuws.** Het project heeft geen nieuws- of kalenderbron. In `research/archief/backtest_tp_v2.py` worden
  "nieuwsmomenten" afgeleid uit de prijs zelf; dat kijkt vooruit en mag niet als filter terugkomen.

## Voorstel

1. **Nulmeting** van de huidige 1h-aanpak op alle 15 markten: signalen per week, resultaat na kosten, drawdown,
   gelijktijdige posities en afwijzingen per poort.
2. **Vier vaste varianten** op dezelfde 6 markten en perioden. Geen zoektocht naar instellingen.
3. **Tijdsvolgorde.** Keuzes alleen op de ontwikkelperiode; de laatste 180 dagen blijven voor de evaluatie.
4. **Twee portefeuilles.** A is wat de ongewijzigde poort toelaat. B meet wat de beste keuze uit de ontwikkelperiode had
   opgeleverd. B is alleen een meetinstrument en mag nooit handelen.
5. **Nieuws:** alleen opties, kosten en beperkingen in kaart brengen. Geen bron toevoegen.
6. **Livefeed:** een alleen-lezen meting van de Capital.com-feed bouwen en draaien, zonder orders.

## Grenzen

Alleen nieuwe bestanden voor onderzoek en meting. `config.json`, `learned.json`, `execution/runner.py`, `risk/`,
`learning/selector.py` en de poorten blijven ongewijzigd. Er wordt geen strategie geactiveerd.
