// Verzamelt alle bronnen tot één antwoord voor de browser. Een bron die faalt, raakt de andere bronnen niet.
// Een nieuwe databron: maak een module die naar het agentformaat vertaalt en voeg die hier toe. Zie web/README.md.
import { STANDAARD_DATA_BRANCH, STANDAARD_REPO, WORKFLOWS } from "./config.mjs";
import { foutTekst, maakClient } from "./github.mjs";
import { botsUitRonde, herkomstGegevens, isVerouderd, markten, verificatie } from "./marktradar.mjs";
import { schoon } from "./schoon.mjs";
import { workflowAgent } from "./workflows.mjs";

const RUNS_MARKTRADAR = 30;
const RUNS_ANDERS = 5;

export function leesInstellingen(env) {
  const repo = /^[\w.-]+\/[\w.-]+$/.test(env.GITHUB_REPO || "") ? env.GITHUB_REPO : STANDAARD_REPO;
  const branch = /^[\w./-]+$/.test(env.MARKTRADAR_DATA_BRANCH || "") ? env.MARKTRADAR_DATA_BRANCH : STANDAARD_DATA_BRANCH;
  return { repo, branch, token: env.GITHUB_TOKEN || "" };
}

async function haalWorkflow(gh, wf, metToken, nu, repo) {
  const antwoord = await gh.runs(wf.bestand, wf.id === "marktradar" ? RUNS_MARKTRADAR : RUNS_ANDERS);
  const run = antwoord.ok ? antwoord.data.workflow_runs?.[0] : null;
  // Zonder token gaat zuinig om met de limiet: stappen alleen voor runs die aandacht vragen.
  const stappen = run && (metToken || run.status !== "completed" || run.conclusion !== "success");
  const jobs = stappen ? await gh.jobs(run.id) : null;
  return { wf, antwoord, agent: workflowAgent(wf, antwoord, jobs, nu, repo) };
}

async function haalMarktRadar(gh, branch) {
  const dashboard = await gh.bestand(branch, "dashboard.json");
  if (!dashboard.ok) return { dashboard };
  const id = dashboard.data?.laatste?.ronde_id;
  const ronde = /^\d{4}-\d{2}-\d{2}$/.test(id || "") ? await gh.bestand(branch, `rondes/${id}.json`) : null;
  return { dashboard, ronde };
}

function radarOnbeschikbaar(herkomst, reden, actie) {
  return { beschikbaar: false, herkomst, reden, actie, ronde: null, markten: [], scorekaart: {}, min_voorspellingen: 100, min_dagen: 30, kosten_per_maand: {} };
}

function maakRadar(data, ronde, nu) {
  const d = data.data;
  const l = d.laatste || {};
  const bron = ronde || l;
  if (bron.droog === true || ronde?.droog) return radarOnbeschikbaar("ontbreekt", "De databranch bevat alleen een droge ronde met testdata.", "Laat de workflow een echte ronde draaien.");
  return { beschikbaar: true, herkomst: isVerouderd(l.peilmoment, nu) ? "verouderd" : "live", reden: null, actie: null,
    ronde: { ronde_id: l.ronde_id, peilmoment: l.peilmoment, status: l.status, briefing: l.briefing, samenvatting: l.toelichting?.samenvatting ?? null,
      ontbreekt: l.ontbreekt || [], kosten_usd: l.kosten_usd ?? null, modellen: l.modellen || {},
      voorspellingen: ronde?.voorspellingen?.length ?? null, gegevens: ronde ? herkomstGegevens(ronde) : { bots: [], bronnen: [] } },
    markten: markten(l), scorekaart: d.scorekaart || {}, min_voorspellingen: d.min_voorspellingen ?? 100, min_dagen: d.min_dagen ?? 30, kosten_per_maand: d.kosten_per_maand || {} };
}

export async function bouwStatus({ env = {}, doeFetch = fetch, nu = new Date() } = {}) {
  const { repo, branch, token } = leesInstellingen(env);
  const gh = maakClient({ repo, token, doeFetch });

  const [wfs, mr] = await Promise.all([
    Promise.all(WORKFLOWS.map((wf) => haalWorkflow(gh, wf, Boolean(token), nu, repo))),
    haalMarktRadar(gh, branch),
  ]);

  const radarWf = wfs.find((w) => w.wf.id === "marktradar");
  const ronde = mr.ronde?.ok ? mr.ronde.data : null;
  const dashboard = mr.dashboard.ok ? mr.dashboard.data : null;

  let radar;
  if (mr.dashboard.ok) radar = maakRadar(mr.dashboard, ronde, nu);
  else if (mr.dashboard.status === 404) radar = radarOnbeschikbaar("ontbreekt", `Geen dashboard.json op de branch ${branch}.`, "Laat de workflow een eerste ronde draaien.");
  else radar = radarOnbeschikbaar("ontbreekt", foutTekst(mr.dashboard), "Probeer het later opnieuw.");

  radar.workflow = { geregistreerd: radarWf.agent.geregistreerd, status: radarWf.agent.status, stap: radarWf.agent.stap, laatste_activiteit: radarWf.agent.laatste_activiteit, link: radarWf.agent.link };
  radar.verificatie = verificatie({ wfAgent: radarWf.agent, runsAntwoord: radarWf.antwoord, ronde: ronde?.droog === false ? ronde : null, dashboard });

  const antwoorden = wfs.filter((w) => w.antwoord.ok || w.antwoord.status === 404).length;
  const eersteFout = wfs.find((w) => !w.antwoord.ok && w.antwoord.status !== 404);
  const bronnen = [
    { id: "github", naam: "GitHub Actions", staat: antwoorden === wfs.length ? "live" : antwoorden ? "verouderd" : "ontbreekt",
      detail: eersteFout ? foutTekst(eersteFout.antwoord) : `${antwoorden} van ${wfs.length} workflows opgehaald uit ${repo}.`,
      actie: token || eersteFout?.antwoord.limiet ? null : "Stel GITHUB_TOKEN in voor een hogere limiet." },
    { id: "marktradar", naam: `MarktRadar-data (${branch})`, staat: radar.herkomst, detail: radar.reden || `Laatste ronde ${radar.ronde?.ronde_id}.`, actie: radar.actie },
  ];

  const antwoord = { schema: 1, opgehaald_op: nu.toISOString(), token_ingesteld: Boolean(token), repo, bronnen,
    workflows: wfs.map((w) => w.agent), bots: ronde && radar.beschikbaar ? botsUitRonde(ronde, nu) : [], marktradar: radar };
  return schoon(antwoord, [token]);
}
