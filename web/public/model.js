// Beslist wat echt is en wat demo is. Draait in de browser en in de tests; geen DOM.
export const STATUSSEN = [
  ["bezig", "Bezig"], ["wachtend", "Wachtend"], ["klaar", "Klaar"], ["mislukt", "Mislukt"], ["aandacht", "Aandacht nodig"],
];
export const VEROUDERD_NA_MIN = 20;

const alsDemo = (a) => ({ ...a, herkomst: "demo", geverifieerd: false });
const metHerkomst = (a, h) => (a.herkomst === "live" ? { ...a, herkomst: h } : a);

export function samenvoegen(api, demo, nu, oudAntwoord = false) {
  if (!api) {
    return { modus: "geen-api", opgehaald_op: null, token_ingesteld: null,
      agents: { bots: demo.bots.map(alsDemo), workflows: demo.workflows.map(alsDemo) },
      radar: { ...demo.marktradar, beschikbaar: false, herkomst: "demo", isDemo: true, reden: "De dashboardserver is niet bereikbaar.", actie: "Controleer de Netlify-functie status.",
        workflow: null, verificatie: demo.verificatie },
      bronnen: demo.bronnen };
  }
  const leeftijdMin = (nu.getTime() - Date.parse(api.opgehaald_op)) / 60000;
  const oud = oudAntwoord || leeftijdMin > VEROUDERD_NA_MIN;
  const stempel = (a) => (oud ? metHerkomst(a, "verouderd") : a);
  const radarEcht = api.marktradar.beschikbaar;
  const m = api.marktradar;
  const radar = radarEcht
    ? { ...m, herkomst: oud && m.herkomst === "live" ? "verouderd" : m.herkomst, isDemo: false }
    : { ...m, ...pakDemo(demo.marktradar), herkomst: "demo", isDemo: true };
  return { modus: oud ? "verouderd" : "live", opgehaald_op: api.opgehaald_op, token_ingesteld: api.token_ingesteld,
    agents: { bots: api.bots.length ? api.bots.map(stempel) : demo.bots.map(alsDemo), workflows: api.workflows.map(stempel) },
    radar, bronnen: api.bronnen.map((b) => (oud && b.staat === "live" ? { ...b, staat: "verouderd" } : b)) };
}

const pakDemo = (d) => ({ ronde: d.ronde, markten: d.markten, scorekaart: d.scorekaart, min_voorspellingen: d.min_voorspellingen, min_dagen: d.min_dagen, kosten_per_maand: d.kosten_per_maand });

export function tel(agents) {
  const uit = Object.fromEntries(STATUSSEN.map(([s]) => [s, 0]));
  for (const a of agents) uit[a.status] = (uit[a.status] || 0) + 1;
  return uit;
}

export function telHerkomst(agents) {
  return agents.reduce((u, a) => ({ ...u, [a.herkomst]: (u[a.herkomst] || 0) + 1 }), {});
}

export const filter = (agents, status) => (status === "alle" ? agents : agents.filter((a) => a.status === status));
