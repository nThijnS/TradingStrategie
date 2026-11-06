import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";
import { MARKTEN, WORKFLOWS } from "../lib/config.mjs";
import { markten, verificatie } from "../lib/marktradar.mjs";
import { schoon } from "../lib/schoon.mjs";
import { bouwStatus } from "../lib/status.mjs";
import { workflowAgent } from "../lib/workflows.mjs";
import { filter, samenvoegen, tel } from "../public/model.js";

const nu = new Date("2026-11-10T13:00:00Z");
const hier = (p) => new URL(`../${p}`, import.meta.url);
const demo = JSON.parse(readFileSync(hier("public/demo.json")));
const kop = (h = {}) => new Headers(h);
const json = (data) => ({ ok: true, status: 200, headers: kop(), json: async () => data });
const niet = (status, h) => ({ ok: false, status, headers: kop(h), json: async () => ({}) });

const run = (x = {}) => ({ id: 1, display_title: "Titel", event: "schedule", status: "completed", conclusion: "success", run_started_at: "2026-11-10T12:45:00Z",
  created_at: "2026-11-10T12:45:00Z", updated_at: "2026-11-10T12:50:00Z", html_url: "https://github.com/x/y/actions/runs/1", ...x });
const wf = WORKFLOWS.find((w) => w.id === "marktradar");
const rondeEcht = (x = {}) => ({ ronde_id: "2026-11-10", peilmoment: "2026-11-10T12:45:00Z", droog: false, status: "volledig", markten: ["NQ"], oordelen: [{ markt: "NQ", oordeel: "VOLGEN", reden: "r", richting: "omhoog", steun: ["charts"], zekerheid: 0.6 }],
  voorspellingen: [{}], ontbreekt: [], niet_meegeteld: [], modellen: { news: ["claude-opus-5-5"] }, kosten_usd: 0.04, briefing: "b",
  ruw: { sentiment: { data_tot: "2026-11-10T12:40:00Z", gemaakt_op: "2026-11-10T12:45:00Z", bevindingen: [{ bronnen: [{ naam: "Capital", url: "https://x.test/", tijdstip: "2026-11-10T12:30:00Z" }] }], ontbreekt: [] } }, ...x });

// Nep-GitHub. routes: pad -> antwoord; onbekend pad is 404.
function nep(routes = {}) {
  const log = [];
  const f = async (url, opt) => {
    log.push({ url: String(url), opt });
    for (const [pad, a] of Object.entries(routes)) if (String(url).includes(pad)) return typeof a === "function" ? a() : a;
    return niet(404);
  };
  return { f, log };
}

test("markten komen overeen met core/markets.py", () => {
  const py = readFileSync(hier("../core/markets.py"), "utf8");
  const start = py.indexOf("LAB_MARKETS = [");
  const blok = py.slice(start, py.indexOf("\n]", start));
  const namen = [...blok.matchAll(/naam="(\w+)"/g)].map((m) => m[1]);
  assert.deepEqual(MARKTEN.map((m) => m.markt), namen);
  assert.equal(MARKTEN.length, 15);
});

test("alle gevolgde workflows bestaan of staan in deze branch", () => {
  const bestanden = readdirSync(hier("../.github/workflows"));
  for (const w of WORKFLOWS) assert.ok(bestanden.includes(w.bestand), w.bestand);
});

test("workflow die GitHub niet kent is een blokkade en niet geverifieerd", () => {
  const a = workflowAgent(wf, { ok: false, status: 404 }, null, nu, "x/y");
  assert.equal(a.status, "aandacht");
  assert.equal(a.geregistreerd, false);
  assert.equal(a.geverifieerd, false);
  assert.equal(a.melding.soort, "blokkade");
  assert.match(a.stap, /Nog nooit/);
});

test("runstatus wordt goed vertaald", () => {
  const met = (r) => workflowAgent(wf, json && { ok: true, status: 200, data: { workflow_runs: [run(r)] } }, null, nu, "x/y");
  assert.equal(met({}).status, "klaar");
  assert.equal(met({}).geverifieerd, true);
  assert.equal(met({ conclusion: "failure" }).status, "mislukt");
  assert.equal(met({ conclusion: "failure" }).melding.soort, "fout");
  assert.equal(met({ status: "in_progress", conclusion: null }).status, "bezig");
  assert.equal(met({ status: "queued", conclusion: null }).status, "wachtend");
  assert.equal(met({ status: "waiting", conclusion: null }).melding.soort, "goedkeuring");
  assert.equal(met({ conclusion: "cancelled" }).status, "aandacht");
  assert.equal(met({ conclusion: "cancelled" }).geverifieerd, false);
});

test("een run die te lang uitblijft vraagt aandacht", () => {
  const a = workflowAgent(wf, { ok: true, data: { workflow_runs: [run({ updated_at: "2026-11-01T12:00:00Z" })] } }, null, nu, "x/y");
  assert.equal(a.status, "aandacht");
  assert.match(a.melding.tekst, /Geen nieuwe run/);
});

test("de huidige of mislukte stap komt uit de jobs", () => {
  const stappen = [{ name: "Eerst", status: "completed", conclusion: "success", started_at: "2026-11-10T12:45:00Z" }, { name: "Ronde draaien", status: "in_progress", conclusion: null, started_at: "2026-11-10T12:46:00Z" }];
  const a = workflowAgent(wf, { ok: true, data: { workflow_runs: [run({ status: "in_progress", conclusion: null })] } }, { ok: true, data: { jobs: [{ steps: stappen }] } }, nu, "x/y");
  assert.equal(a.stap, "Bezig met: Ronde draaien");
  const tijden = a.activiteit.map((r) => Date.parse(r.t));
  assert.deepEqual(tijden, [...tijden].sort((x, y) => x - y));
});

test("altijd 15 markten; niet bekeken is GEEN_ACTIE", () => {
  const m = markten({ oordelen: [{ markt: "NQ", oordeel: "VOLGEN", reden: "r", richting: "omhoog", steun: [], zekerheid: 0.6 }] });
  assert.equal(m.length, 15);
  assert.equal(m.find((x) => x.markt === "NQ").oordeel, "VOLGEN");
  assert.equal(m.filter((x) => x.oordeel === "GEEN_ACTIE" && !x.bekeken).length, 14);
});

test("zonder data is niets geverifieerd", () => {
  const v = verificatie({ wfAgent: { geregistreerd: false }, runsAntwoord: { ok: false, status: 404 }, ronde: null, dashboard: null });
  assert.ok(v.every((x) => x.geverifieerd === false));
  assert.equal(v.length, 6);
});

test("een ronde zonder sleutels bewijst model en sentiment niet", () => {
  const ronde = rondeEcht({ modellen: {}, kosten_usd: 0, ontbreekt: ["klantsentiment: geen sleutels"], ruw: { sentiment: { bevindingen: [] } } });
  const v = Object.fromEntries(verificatie({ wfAgent: { geregistreerd: true }, runsAntwoord: { ok: true, data: { workflow_runs: [run()] } }, ronde, dashboard: {} }).map((x) => [x.id, x.geverifieerd]));
  assert.deepEqual(v, { workflow: true, run: true, data: true, model: false, sentiment: false, stabiel: false });
});

test("een geslaagde run door een codewijziging telt niet als echte ronde", () => {
  const v = verificatie({ wfAgent: { geregistreerd: true }, runsAntwoord: { ok: true, data: { workflow_runs: [run({ event: "push" })] } }, ronde: null, dashboard: null });
  assert.equal(v.find((x) => x.id === "run").geverifieerd, false);
});

test("volledig bewijs maakt alles groen", () => {
  const runs = [6, 7, 8, 9, 10].map((d) => run({ run_started_at: `2026-11-${String(d).padStart(2, "0")}T12:45:00Z` }));
  const v = verificatie({ wfAgent: { geregistreerd: true }, runsAntwoord: { ok: true, data: { workflow_runs: runs } }, ronde: rondeEcht(), dashboard: {} });
  assert.ok(v.every((x) => x.geverifieerd), JSON.stringify(v.filter((x) => !x.geverifieerd)));
});

test("zonder databranch blijft de status werken en meldt hij wat ontbreekt", async () => {
  const { f, log } = nep({ "tradingstrategie.yml/runs": json({ workflow_runs: [run()] }) });
  const s = await bouwStatus({ env: {}, doeFetch: f, nu });
  assert.equal(s.marktradar.beschikbaar, false);
  assert.match(s.marktradar.reden, /dashboard\.json/);
  assert.equal(s.marktradar.verificatie.length, 6);
  assert.deepEqual(s.bots, []);
  assert.equal(s.workflows.length, WORKFLOWS.length);
  assert.equal(s.workflows.find((w) => w.id === "keten").status, "klaar");
  assert.ok(log.every((l) => l.opt.method === "GET"));
});

test("GitHub-limiet wordt een duidelijke fout", async () => {
  const { f } = nep({ "api.github.com": niet(403, { "x-ratelimit-remaining": "0" }) });
  const s = await bouwStatus({ env: {}, doeFetch: f, nu });
  assert.equal(s.workflows[0].herkomst, "ontbreekt");
  assert.match(s.workflows[0].melding.tekst, /limiet/);
  assert.equal(s.bronnen[0].staat, "ontbreekt");
});

test("netwerkstoring laat geen uitzondering door", async () => {
  const s = await bouwStatus({ env: {}, doeFetch: async () => { throw new Error("stuk"); }, nu });
  assert.equal(s.marktradar.beschikbaar, false);
  assert.equal(s.schema, 1);
});

test("een echte ronde levert zes bots en 15 markten", async () => {
  const r = rondeEcht();
  const { f } = nep({ "dashboard.json": json({ laatste: r, scorekaart: {}, min_voorspellingen: 100, min_dagen: 30 }), "rondes/2026-11-10.json": json(r), "marktradar.yml/runs": json({ workflow_runs: [run()] }) });
  const s = await bouwStatus({ env: {}, doeFetch: f, nu });
  assert.equal(s.marktradar.beschikbaar, true);
  assert.equal(s.marktradar.herkomst, "live");
  assert.equal(s.bots.length, 6);
  assert.equal(s.marktradar.markten.length, 15);
  assert.equal(s.bots.find((b) => b.id === "news").geverifieerd, false, "ruw.news ontbreekt, dus niet geverifieerd");
});

test("een oude ronde is verouderd en een droge ronde telt niet", async () => {
  const oud = rondeEcht({ peilmoment: "2026-10-30T12:45:00Z" });
  const a = await bouwStatus({ env: {}, doeFetch: nep({ "dashboard.json": json({ laatste: oud }), "rondes/": json(oud) }).f, nu });
  assert.equal(a.marktradar.herkomst, "verouderd");
  assert.ok(a.bots.every((b) => b.herkomst === "verouderd"));
  const droog = rondeEcht({ droog: true });
  const b = await bouwStatus({ env: {}, doeFetch: nep({ "dashboard.json": json({ laatste: droog }), "rondes/": json(droog) }).f, nu });
  assert.equal(b.marktradar.beschikbaar, false);
  assert.deepEqual(b.bots, []);
});

test("de token verschijnt nooit in het antwoord en gaat alleen naar GitHub", async () => {
  const token = "ghp_abcdefghijklmnop1234";
  const lek = run({ display_title: `fout met ${token} en sk-ant-api03-geheimgeheim` });
  const { f, log } = nep({ "/runs": json({ workflow_runs: [lek] }) });
  const s = JSON.stringify(await bouwStatus({ env: { GITHUB_TOKEN: token }, doeFetch: f, nu }));
  assert.ok(!s.includes(token));
  assert.ok(!s.includes("sk-ant-"));
  for (const l of log) assert.match(new URL(l.url).host, /^(api\.github\.com|raw\.githubusercontent\.com)$/);
  assert.ok(log.every((l) => l.opt.headers.Authorization === `Bearer ${token}`));
});

test("ongeldige instellingen vallen terug op de standaard", async () => {
  const { f, log } = nep();
  await bouwStatus({ env: { GITHUB_REPO: "../../evil", MARKTRADAR_DATA_BRANCH: "a b" }, doeFetch: f, nu });
  assert.ok(log.every((l) => l.url.includes("nThijnS/TradingStrategie")));
});

test("schoon verbergt bekende sleutelvormen", () => {
  assert.equal(schoon({ a: ["Bearer abcdefghijkl"] }).a[0], "[verborgen]");
  assert.equal(schoon("github_pat_abcdefghijkl"), "[verborgen]");
});

const apiZonderData = () => ({ schema: 1, opgehaald_op: nu.toISOString(), token_ingesteld: false, bronnen: [{ id: "github", staat: "live" }], bots: [],
  workflows: [{ id: "keten", status: "klaar", herkomst: "live", geverifieerd: true }], marktradar: { beschikbaar: false, herkomst: "ontbreekt", reden: "r", verificatie: [], workflow: {} } });

test("ontbrekende MarktRadar-data wordt demo; workflows blijven echt", () => {
  const d = samenvoegen(apiZonderData(), demo, nu);
  assert.ok(d.agents.bots.length === 6 && d.agents.bots.every((b) => b.herkomst === "demo" && !b.geverifieerd));
  assert.equal(d.agents.workflows[0].herkomst, "live");
  assert.equal(d.radar.herkomst, "demo");
  assert.equal(d.radar.isDemo, true);
  assert.equal(d.radar.reden, "r");
  assert.equal(d.radar.markten.length, 15);
});

test("zonder server is alles demo en niets geverifieerd", () => {
  const d = samenvoegen(null, demo, nu);
  assert.equal(d.modus, "geen-api");
  assert.ok([...d.agents.bots, ...d.agents.workflows].every((a) => a.herkomst === "demo" && !a.geverifieerd));
  assert.ok(d.radar.verificatie.every((v) => !v.geverifieerd));
});

test("een oud antwoord wordt verouderd, geen live", () => {
  const api = { ...apiZonderData(), opgehaald_op: "2026-11-10T12:00:00Z" };
  const d = samenvoegen(api, demo, nu);
  assert.equal(d.modus, "verouderd");
  assert.equal(d.agents.workflows[0].herkomst, "verouderd");
  assert.equal(d.bronnen[0].staat, "verouderd");
  assert.equal(samenvoegen(apiZonderData(), demo, nu, true).modus, "verouderd");
});

test("filter en tellers", () => {
  const a = [{ status: "klaar" }, { status: "mislukt" }, { status: "klaar" }];
  assert.equal(filter(a, "klaar").length, 2);
  assert.equal(filter(a, "alle").length, 3);
  assert.equal(tel(a).klaar, 2);
  assert.equal(tel(a).bezig, 0);
});

test("demo-data is herkenbaar en scorekaart toont te weinig data", () => {
  assert.ok([...demo.bots, ...demo.workflows].every((a) => a.herkomst === "demo" && a.stap.startsWith("DEMO:")));
  assert.ok(Object.values(demo.marktradar.scorekaart).every((s) => s.conclusie === "te weinig data"));
  assert.match(demo.marktradar.ronde.briefing, /DROGE RONDE/);
});

test("publieke bestanden bevatten geen geheimen of bedieningsknoppen", () => {
  const bestanden = readdirSync(hier("public")).map((b) => readFileSync(hier(`public/${b}`), "utf8"));
  const alles = bestanden.join("\n");
  assert.doesNotMatch(alles, /process\.env|GITHUB_TOKEN=|sk-ant-|ghp_|github_pat_|Authorization/);
  assert.doesNotMatch(alles, /method:\s*["'](POST|PUT|DELETE|PATCH)/i);
  assert.doesNotMatch(alles, /api\.github\.com|anthropic\.com/);
});
