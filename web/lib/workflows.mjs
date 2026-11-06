// Zet GitHub Actions-runs om naar het agentformaat. Geen netwerk; alles hier is met vaste invoer te testen.
import { foutTekst } from "./github.mjs";

const uren = (a, b) => (Date.parse(b) - Date.parse(a)) / 3.6e6;
const seconden = (a, b) => Math.max(0, Math.round((Date.parse(b) - Date.parse(a)) / 1000));

const EVENT = { schedule: "planning", workflow_dispatch: "handmatig of keten", push: "codewijziging", pull_request: "pull request" };

const CONCLUSIE = {
  success: ["klaar", "Geslaagd"], skipped: ["klaar", "Overgeslagen"], neutral: ["klaar", "Neutraal afgerond"],
  failure: ["mislukt", "Mislukt"], timed_out: ["mislukt", "Tijdslimiet bereikt"], startup_failure: ["mislukt", "Kon niet starten"],
  cancelled: ["aandacht", "Geannuleerd"], stale: ["aandacht", "Verlopen op GitHub"], action_required: ["aandacht", "Wacht op goedkeuring"],
};

export function statusVanRun(run) {
  if (run.status === "in_progress") return ["bezig", "Bezig"];
  if (run.status !== "completed") return ["wachtend", run.status === "waiting" ? "Wacht op goedkeuring" : "In de wachtrij"];
  return CONCLUSIE[run.conclusion] || ["aandacht", `Onbekende uitkomst: ${run.conclusion}`];
}

function stapVan(run, jobs) {
  const stappen = (jobs || []).flatMap((j) => j.steps || []);
  const actief = stappen.find((s) => s.status === "in_progress");
  if (actief) return `Bezig met: ${actief.name}`;
  const fout = stappen.find((s) => s.conclusion === "failure");
  if (fout) return `Mislukt bij: ${fout.name}`;
  return `${statusVanRun(run)[1]}: ${run.display_title}`;
}

function activiteit(runs, jobs) {
  const regels = runs.map((r) => {
    const [status, tekst] = statusVanRun(r);
    return { t: r.run_started_at || r.created_at, tekst: `${tekst} (${EVENT[r.event] || r.event})`, status };
  });
  // Stappen alleen bij een lopende of mislukte run; bij een geslaagde run is het rijtje runs nuttiger.
  const stappen = runs[0]?.conclusion === "success" ? [] : (jobs || []).flatMap((j) => j.steps || []);
  for (const s of stappen) {
    if (s.started_at) regels.push({ t: s.started_at, tekst: `Stap: ${s.name}`, status: s.conclusion === "failure" ? "mislukt" : "stap" });
  }
  return regels.sort((a, b) => Date.parse(a.t) - Date.parse(b.t)).slice(-14);
}

function basis(wf) {
  return { id: wf.id, naam: wf.naam, groep: "workflow", taak: wf.taak, geverifieerd: false, laatste_activiteit: null, duur_s: null,
    stap: null, melding: null, activiteit: [], link: null };
}

export function workflowAgent(wf, antwoord, jobsAntwoord, nu, repo) {
  const a = basis(wf);
  const pagina = `https://github.com/${repo}/actions/workflows/${wf.bestand}`;
  if (antwoord.status === 404) {
    return { ...a, status: "aandacht", herkomst: "live", stap: "Nog nooit gedraaid.", geregistreerd: false,
      melding: { soort: "blokkade", tekst: `${wf.bestand} staat niet op de standaardbranch van GitHub. Hij kan pas draaien na een merge.` } };
  }
  if (!antwoord.ok) {
    return { ...a, status: "aandacht", herkomst: "ontbreekt", stap: "Status niet opgehaald.", geregistreerd: null, link: pagina,
      melding: { soort: "fout", tekst: foutTekst(antwoord) } };
  }

  const runs = antwoord.data.workflow_runs || [];
  const run = runs[0];
  if (!run) {
    return { ...a, status: wf.vereist ? "aandacht" : "wachtend", herkomst: "live", stap: "Nog nooit gedraaid.", geregistreerd: true, link: pagina,
      melding: wf.vereist ? { soort: "blokkade", tekst: "De workflow staat op GitHub, maar heeft nog geen run." } : null };
  }

  const jobs = jobsAntwoord?.ok ? jobsAntwoord.data.jobs : null;
  const [status, tekst] = statusVanRun(run);
  const gestart = run.run_started_at || run.created_at;
  const klaar = run.status === "completed";
  const uit = { ...a, status, herkomst: "live", geregistreerd: true, link: run.html_url,
    geverifieerd: runs.some((r) => r.conclusion === "success"),
    laatste_activiteit: klaar ? run.updated_at : (run.updated_at || gestart),
    duur_s: run.status === "queued" ? null : seconden(gestart, klaar ? run.updated_at : nu.toISOString()),
    stap: stapVan(run, jobs), activiteit: activiteit(runs.slice(0, 5), jobs) };

  if (status === "mislukt") uit.melding = { soort: "fout", tekst: uit.stap };
  else if (tekst === "Wacht op goedkeuring") uit.melding = { soort: "goedkeuring", tekst: "Deze run wacht op goedkeuring op GitHub." };
  else if (status === "aandacht") uit.melding = { soort: "blokkade", tekst: `Laatste run: ${tekst.toLowerCase()}.` };
  else if (status === "klaar" && wf.maxUur && uren(run.updated_at, nu.toISOString()) > wf.maxUur) {
    uit.status = "aandacht";
    uit.melding = { soort: "blokkade", tekst: `Geen nieuwe run in de afgelopen ${wf.maxUur} uur.` };
  }
  return uit;
}
