// Wat het dashboard volgt. Teksten komen uit rapport/11_marktradar.md en de workflowbestanden.

export const STANDAARD_REPO = "nThijnS/TradingStrategie";
export const STANDAARD_DATA_BRANCH = "marktradar-data";

// Moet gelijk zijn aan LAB_MARKETS in core/markets.py; tests/config.test.mjs controleert dat.
export const MARKTEN = [
  ["BTC", "Bitcoin", "crypto"], ["ETH", "Ethereum", "crypto"], ["SOL", "Solana", "crypto"],
  ["EURUSD", "EUR/USD", "forex"], ["GBPUSD", "GBP/USD", "forex"], ["USDJPY", "USD/JPY", "forex"],
  ["NQ", "Nasdaq 100", "index"], ["ES", "S&P 500", "index"], ["DAX", "DAX 40", "index"],
  ["GOUD", "Goud", "grondstof"], ["ZILVER", "Zilver", "grondstof"], ["OLIE", "Olie (WTI)", "grondstof"],
  ["AAPL", "Apple", "aandeel"], ["NVDA", "Nvidia", "aandeel"], ["MSFT", "Microsoft", "aandeel"],
].map(([markt, titel, soort]) => ({ markt, titel, soort }));

// maxUur: langer geen nieuwe run betekent aandacht nodig. Zonder maxUur draait de workflow alleen op verzoek.
export const WORKFLOWS = [
  { id: "keten", bestand: "tradingstrategie.yml", naam: "MarketPilot-keten", maxUur: 7,
    taak: "Controleert elke minuut de markten, stuurt meldingen en werkt de live status bij." },
  { id: "leren", bestand: "leren.yml", naam: "Leren", maxUur: 26,
    taak: "Leert dagelijks uit nieuwe data en zet elke markt op actief, onderzoek of pauze." },
  { id: "marktradar", bestand: "marktradar.yml", naam: "MarktRadar-workflow", maxUur: 96, vereist: true,
    taak: "Draait op handelsdagen één adviesronde vóór de opening van New York." },
  { id: "tests", bestand: "tests.yml", naam: "Tests",
    taak: "Draait de tests bij elke wijziging in de code." },
  { id: "capitaldata", bestand: "capitaldata.yml", naam: "Capitaldata",
    taak: "Haalt markten en uurcandles op bij Capital.com, alleen lezen." },
  { id: "feedmeting", bestand: "feedmeting.yml", naam: "Feedmeting",
    taak: "Meet de kwaliteit van de Capital.com-feed, alleen lezen." },
  { id: "instrumenten", bestand: "instrumenten.yml", naam: "Instrumenten controleren",
    taak: "Controleert instrumentgegevens bij Capital.com, alleen lezen." },
];

export const BOTS = [
  { id: "scout", naam: "Scout", taak: "Kiest maximaal 5 opvallende markten met vaste regels.", llm: false },
  { id: "charts", naam: "Charts", taak: "Bepaalt de technische stand per markt, zonder LLM.", llm: false },
  { id: "news", naam: "News", taak: "Volgt de agenda en labelt Fed-berichten met de LLM.", llm: true },
  { id: "sentiment", naam: "Sentiment", taak: "Vergelijkt klantposities met de eigen historie. Geeft nooit een richting.", llm: false },
  { id: "skeptic", naam: "Skeptic", taak: "Zoekt tegenbewijs en kan een veto geven.", llm: true },
  { id: "chief", naam: "Chief", taak: "Regelt de ronde en geeft oordelen met vaste regels. De LLM schrijft alleen de toelichting.", llm: true },
];

export const RONDE_VEROUDERD_UUR = 96;   // vrijdagochtend tot en met dinsdagochtend, inclusief weekend en één vrije dag
export const MIN_DAGEN_STABIEL = 5;      // weergavegrens van dit dashboard, geen onderdeel van MarktRadar
