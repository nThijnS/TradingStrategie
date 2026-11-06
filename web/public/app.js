import { STATUSSEN, filter, samenvoegen, tel, telHerkomst } from "./model.js";

const $ = (id) => document.getElementById(id);
const esc = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const VERVERS_MS = 2 * 60000;
const OPSLAG = "marketpilot-laatste-status";

const NL = new Intl.DateTimeFormat("nl-NL", { timeZone: "Europe/Amsterdam", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const KORT = new Intl.DateTimeFormat("nl-NL", { timeZone: "Europe/Amsterdam", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const geldig = (t) => t && Number.isFinite(Date.parse(t));
const dt = (t) => (geldig(t) ? NL.format(new Date(t)) : "onbekend");
const tijd = (t, f = NL) => (geldig(t) ? `<time datetime="${esc(t)}">${esc(f.format(new Date(t)))}</time>` : `<time>onbekend</time>`);

function geleden(t) {
  if (!geldig(t)) return "onbekend";
  const min = Math.round((Date.now() - Date.parse(t)) / 60000);
  if (min < 1) return "zojuist";
  if (min < 60) return `${min} min geleden`;
  if (min < 48 * 60) return `${Math.round(min / 60)} uur geleden`;
  return `${Math.round(min / 1440)} dagen geleden`;
}
function duur(s) {
  if (s == null) return "niet gemeten";
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${s % 60} s`;
  return `${Math.floor(s / 3600)} u ${Math.floor((s % 3600) / 60)} min`;
}

const STATUS = Object.fromEntries(STATUSSEN);
const ICOON = { wachtend: "…", klaar: "✓", mislukt: "✕", aandacht: "!" };
const statusLab = (s) => `<span class="lab s-${esc(s)}">${s === "bezig" ? `<i class="draait" aria-hidden="true"></i>` : `<i aria-hidden="true">${ICOON[s] || "?"}</i>`}${esc(STATUS[s] || s)}</span>`;
const HERKOMST = { live: "Live", verouderd: "Verouderd", demo: "Demo, fictief", ontbreekt: "Ontbreekt" };
const herkomstLab = (h) => `<span class="lab k-${esc(h)}">${esc(HERKOMST[h] || h)}</span>`;
const bewijsLab = (a) => (a.geverifieerd ? "" : `<span class="lab nietbewezen">Niet geverifieerd</span>`);
const SOORT = { fout: "Fout", blokkade: "Blokkade", goedkeuring: "Goedkeuring nodig" };

const staat = { data: null, filter: "alle", pagina: "agents" };
const alleAgents = () => [...staat.data.agents.bots, ...staat.data.agents.workflows];

function logLijst(regels, f = KORT) {
  return regels.length
    ? `<ol class="log">${regels.map((r) => `<li class="${esc(r.status)}">${tijd(r.t, f)}<span>${esc(r.tekst)}</span></li>`).join("")}</ol>`
    : `<p class="muted small">Nog geen activiteit bekend.</p>`;
}
const meldingBlok = (m) => (m ? `<p class="melding ${m.soort === "fout" ? "fout" : ""}"><b>${esc(SOORT[m.soort] || "Melding")}:</b> ${esc(m.tekst)}</p>` : "");

function agentRij(a) {
  return `<article class="agent herkomst h-${esc(a.herkomst)}" aria-labelledby="ag-${esc(a.id)}">
    <div class="a-wie"><h3 id="ag-${esc(a.id)}">${esc(a.naam)}</h3><p>${esc(a.taak)}</p></div>
    <div class="a-nu">
      <div class="labels">${statusLab(a.status)}${herkomstLab(a.herkomst)}${bewijsLab(a)}</div>
      <p class="stap">${esc(a.stap || "Geen stap bekend.")}</p>
      <p class="meta">Laatste activiteit: ${esc(geleden(a.laatste_activiteit))}. Duur: ${esc(duur(a.duur_s))}.</p>
      ${meldingBlok(a.melding)}
    </div>
    <div class="a-log">${logLijst(a.activiteit.slice(-3))}
      <button type="button" class="linkknop" data-detail="${esc(a.id)}" data-fid="d-${esc(a.id)}">Alle activiteit van ${esc(a.naam)}</button>
    </div>
  </article>`;
}

function groep(titel, uitleg, agents) {
  const zicht = filter(agents, staat.filter);
  if (!zicht.length) return "";
  return `<section><div class="kop"><h2>${esc(titel)}</h2><p>${esc(uitleg)}</p></div><div class="groep">${zicht.map(agentRij).join("")}</div></section>`;
}

function rAgents() {
  const alle = alleAgents(), n = tel(alle);
  const knop = (id, tekst, aantal) => `<button type="button" class="filter" data-filter="${id}" data-fid="f-${id}" aria-pressed="${staat.filter === id}">${esc(tekst)} <span class="num">${aantal}</span></button>`;
  const inhoud = groep("MarktRadar-bots", "De zes deelbots van één adviesronde.", staat.data.agents.bots)
    + groep("Automatisering", "Workflows op GitHub Actions.", staat.data.agents.workflows);
  $("p-agents").innerHTML = `<section aria-label="Filter op status"><div class="filters">${knop("alle", "Alle", alle.length)}${STATUSSEN.map(([s, t]) => knop(s, t, n[s])).join("")}</div></section>
    ${inhoud || `<div class="leeg"><strong>Geen agents met status ${esc(STATUS[staat.filter])}</strong><button type="button" class="linkknop" data-filter="alle" data-fid="f-leeg">Toon alle agents</button></div>`}`;
}

function radarKop(r) {
  const peil = r.ronde?.peilmoment;
  return `<section><div class="kop"><h2>${r.isDemo ? "Voorbeeldronde, fictief" : `Ronde ${esc(r.ronde?.ronde_id)}`}</h2>
    <p>${peil ? `Peilmoment ${esc(dt(peil))}. ` : ""}Alleen advies: MarktRadar plaatst geen orders. Voorspellingen zijn geen bewezen resultaten.</p></div>
    <div class="labels">${herkomstLab(r.herkomst)}${r.ronde?.status ? `<span class="lab s-${r.ronde.status === "volledig" ? "klaar" : "aandacht"}">${esc(r.ronde.status)}</span>` : ""}</div>
    ${r.reden ? `<div class="leeg herkomst h-ontbreekt"><strong>Geen echte MarktRadar-data</strong><span>${esc(r.reden)} ${esc(r.actie || "")}</span>${r.isDemo ? `<span class="muted">Hieronder staat fictieve demo-informatie uit een droge ronde.</span>` : ""}</div>` : ""}
  </section>`;
}

function verificatieBlok(r) {
  const v = r.verificatie || [], ok = v.filter((x) => x.geverifieerd).length;
  const wf = r.workflow;
  return `<div class="blok herkomst h-${r.workflow ? "live" : "demo"}"><h3>Is het bewezen?</h3>
    <p class="meta">${ok} van ${v.length} onderdelen bewezen met een echte run.</p>
    <ul class="bewijs">${v.map((x) => `<li class="${x.geverifieerd ? "ja" : "nee"}"><i aria-hidden="true">${x.geverifieerd ? "✓" : "–"}</i><div><b>${esc(x.naam)}</b><span>${x.geverifieerd ? "Bewezen" : "Niet geverifieerd"}. ${esc(x.bewijs)}</span>${x.link ? ` <a class="small" href="${esc(x.link)}" target="_blank" rel="noopener noreferrer">Run bekijken</a>` : ""}</div></li>`).join("")}</ul>
    <p class="meta">${wf ? `Workflowstatus: ${esc(STATUS[wf.status] || wf.status)}. ${esc(wf.stap || "")}` : "Workflowstatus onbekend: de dashboardserver is niet bereikbaar."}</p></div>`;
}

function briefingBlok(r) {
  const ronde = r.ronde, g = ronde?.gegevens;
  if (!ronde) return `<div class="leeg"><strong>Geen briefing</strong></div>`;
  return `<div class="blok herkomst h-${esc(r.herkomst)}"><h3>Briefing${r.isDemo ? ", fictief" : ""}</h3>
    ${ronde.samenvatting ? `<p>${esc(ronde.samenvatting)}</p>` : ""}
    <p class="briefing">${esc(ronde.briefing || "Geen briefing in deze ronde.")}</p>
  </div>
  <div class="blok herkomst h-${esc(r.herkomst)}"><h3>Herkomst van de gegevens</h3>
    ${g?.bots?.length ? `<div class="rol"><table><thead><tr><th scope="col">Bot</th><th scope="col">Gegevens tot</th><th scope="col">Gemaakt</th></tr></thead>
      <tbody>${g.bots.map((b) => `<tr><td>${esc(b.bot)}</td><td>${tijd(b.data_tot)}</td><td>${tijd(b.gemaakt_op)}</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted small">Geen botgegevens beschikbaar.</p>`}
    ${g?.bronnen?.length ? `<ul class="log">${g.bronnen.map((b) => `<li><time>${esc(dt(b.tijdstip))}</time><span>${b.url ? `<a href="${esc(b.url)}" target="_blank" rel="noopener noreferrer">${esc(b.naam)}</a>` : esc(b.naam)}</span></li>`).join("")}</ul>` : ""}
  </div>`;
}

function marktenBlok(r) {
  if (!r.markten?.length) return "";
  const rij = (m) => `<tr><td class="rij-kop">${esc(m.titel)}<small>${esc(m.markt)}, ${esc(m.soort)}</small></td>
    <td><span class="code o-${esc(m.oordeel)}">${esc(m.oordeel)}</span></td>
    <td>${m.richting !== "geen" ? esc(m.richting) : ""}</td>
    <td>${m.zekerheid != null ? `zekerheid <span class="num">${esc(Number(m.zekerheid).toFixed(2))}</span>` : ""}</td>
    <td>${esc(m.reden)}${m.toelichting ? ` ${esc(m.toelichting)}` : ""}</td></tr>`;
  return `<section><div class="kop"><h2>De 15 markten</h2><p>${r.isDemo ? "Fictieve signalen. " : ""}Een signaal is alleen een aanwijzing om verder te kijken. Markten die de Scout niet koos, staan op GEEN_ACTIE.</p></div>
    <div class="blok herkomst h-${esc(r.herkomst)} rol"><table class="markten"><thead><tr><th scope="col">Markt</th><th scope="col">Signaal</th><th scope="col">Richting</th><th scope="col">Zekerheid</th><th scope="col">Reden</th></tr></thead>
    <tbody>${r.markten.map(rij).join("")}</tbody></table></div></section>`;
}

const pct = (v) => (v == null ? "–" : `${(v * 100).toFixed(1)}%`);
const netto = (v) => (v == null ? "–" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`);
function scoreBlok(r) {
  const k = Object.entries(r.scorekaart || {});
  const rij = ([b, s]) => `<tr><td>${esc(b)}</td><td class="nr">${esc(s.n)}</td><td class="nr">${esc(s.dagen)}</td><td class="nr">${pct(s.trefkans)}</td><td class="nr">${s.brier == null ? "–" : esc(Number(s.brier).toFixed(3))}</td><td class="nr">${netto(s.netto)}</td><td class="nr">${netto(s.basislijn?.willekeurig)}</td><td class="nr">${netto(s.basislijn?.gisteren)}</td><td><span class="lab ${s.conclusie === "te weinig data" ? "s-aandacht" : "s-klaar"}">${esc(s.conclusie)}</span></td></tr>`;
  const maand = Object.entries(r.kosten_per_maand || {}).sort().pop();
  return `<section><div class="kop"><h2>Scorekaart</h2><p>${r.isDemo ? "Fictieve cijfers. " : ""}Conclusies pas vanaf ${esc(r.min_voorspellingen)} voorspellingen op ${esc(r.min_dagen)} dagen. Daaronder zegt een score niets. Netto is per voorspelling, na kosten; niets doen is altijd 0%.</p></div>
    ${k.length ? `<div class="blok herkomst h-${esc(r.herkomst)} rol"><table><thead><tr><th scope="col">Bot</th><th scope="col" class="nr">Voorspellingen</th><th scope="col" class="nr">Dagen</th><th scope="col" class="nr">Trefkans</th><th scope="col" class="nr">Brier</th><th scope="col" class="nr">Netto</th><th scope="col" class="nr">Willekeurig</th><th scope="col" class="nr">Richting gisteren</th><th scope="col">Stand</th></tr></thead><tbody>${k.map(rij).join("")}</tbody></table></div>`
      : `<div class="leeg herkomst h-${esc(r.herkomst)}"><strong>0 afgerekende voorspellingen: te weinig data</strong><span class="muted">Na de horizon van een ronde komen hier de uitkomsten.</span></div>`}
    <p class="opmerking">LLM-kosten${maand ? ` in ${esc(maand[0])}: $${esc(Number(maand[1]).toFixed(2))}` : ": nog geen"}${r.isDemo ? " (demo)" : ""}.</p></section>`;
}

function rRadar() {
  const r = staat.data.radar;
  $("p-marktradar").innerHTML = `${radarKop(r)}<div class="twee"><div class="groep">${briefingBlok(r)}</div>${verificatieBlok(r)}</div>${marktenBlok(r)}${scoreBlok(r)}`;
}

const NODIG = [
  ["Agentstatus van workflows", "Werkt zodra de site draait. Lees-token GITHUB_TOKEN is aan te raden."],
  ["MarktRadar-workflow", "Merge feat/marktradar naar main en zet ANTHROPIC_API_KEY als GitHub-secret."],
  ["MarktRadar-data", "Na de eerste geslaagde run bestaat de branch marktradar-data en verschijnt de echte ronde hier vanzelf."],
  ["Capital-sentiment", "Controleer in de eerste rondes of alle 15 markten sentiment krijgen."],
];
function rKoppelingen() {
  const d = staat.data;
  $("p-koppelingen").innerHTML = `<section><div class="kop"><h2>Databronnen</h2><p>Waar dit dashboard zijn gegevens vandaan haalt en hoe vers die zijn.</p></div>
    <div class="blok rol"><table><thead><tr><th scope="col">Bron</th><th scope="col">Stand</th><th scope="col">Toelichting</th></tr></thead><tbody>
    ${d.bronnen.map((b) => `<tr><td class="rij-kop">${esc(b.naam)}</td><td>${herkomstLab(b.staat)}</td><td>${esc(b.detail)} ${esc(b.actie || "")}</td></tr>`).join("")}</tbody></table></div></section>
    <section><div class="kop"><h2>Nog aan te sluiten</h2><p>Dit is nodig om alles echt te maken. Details staan in web/README.md.</p></div>
    <div class="blok rol"><table><tbody>${NODIG.map(([a, b]) => `<tr><td class="rij-kop">${esc(a)}</td><td>${esc(b)}</td></tr>`).join("")}</tbody></table></div></section>`;
}

function rStand() {
  const d = staat.data, alle = alleAgents(), n = tel(alle), h = telHerkomst(alle), v = d.radar.verificatie || [];
  const tellers = STATUSSEN.filter(([s]) => n[s]).map(([s, t]) => `<span>${n[s]} ${esc(t.toLowerCase())}</span>`).join("");
  const ronde = d.radar.isDemo ? "Geen echte ronde" : `${d.radar.herkomst === "verouderd" ? "Verouderd: " : ""}${dt(d.radar.ronde?.peilmoment)}`;
  const delen = [["live", "live"], ["verouderd", "verouderd"], ["demo", "demo"], ["ontbreekt", "ontbreekt"]].filter(([k]) => h[k]).map(([k, t]) => `${h[k]} ${t}`).join(", ");
  $("stand").innerHTML = `<div><dt>Agents</dt><dd class="tellers">${tellers}</dd></div>
    <div><dt>MarktRadar, laatste ronde</dt><dd>${esc(ronde)}</dd></div>
    <div><dt>Bewezen met een echte run</dt><dd>${v.filter((x) => x.geverifieerd).length} van ${v.length} onderdelen</dd></div>
    <div><dt>Herkomst agentgegevens</dt><dd>${esc(delen)}</dd></div>`;
  const b = [];
  if (d.modus === "geen-api") b.push(["demo", "<strong>De dashboardserver is niet bereikbaar.</strong> Alles op deze pagina is fictieve demo-informatie."]);
  else {
    if (d.modus === "verouderd") b.push(["verouderd", `<strong>Deze gegevens zijn verouderd.</strong> Laatst opgehaald ${esc(geleden(d.opgehaald_op))}.`]);
    if (h.demo || d.radar.isDemo) b.push(["demo", "<strong>Gearceerde blokken zijn fictieve demo-informatie.</strong> Blokken met een dichte rand komen echt van GitHub."]);
  }
  $("banner").innerHTML = b.map(([k, t]) => `<p class="banner herkomst h-${k}">${t}</p>`).join("");
  $("ververst").textContent = d.opgehaald_op ? `Opgehaald ${dt(d.opgehaald_op)}` : "Niet opgehaald";
}

const RENDER = { agents: rAgents, marktradar: rRadar, koppelingen: rKoppelingen };
function teken() {
  if (!staat.data) return;
  const focus = document.activeElement?.dataset?.fid;
  rStand();
  for (const f of Object.values(RENDER)) f();
  if (focus) document.querySelector(`[data-fid="${CSS.escape(focus)}"]`)?.focus();
}

function route(naarInhoud) {
  const h = location.hash.slice(1);
  if (h === "main") return;
  staat.pagina = RENDER[h] ? h : "agents";
  document.querySelectorAll(".page").forEach((p) => { p.hidden = p.id !== `p-${staat.pagina}`; });
  document.querySelectorAll(".tabs a").forEach((a) => (a.dataset.p === staat.pagina ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  if (naarInhoud) { window.scrollTo(0, 0); $("main").focus({ preventScroll: true }); }
}

function openDetail(id) {
  const a = alleAgents().find((x) => x.id === id);
  if (!a) return;
  const dlg = $("detail");
  dlg.innerHTML = `<div class="d-in herkomst h-${esc(a.herkomst)}">
    <div class="d-kop"><h2 id="detail-kop">${esc(a.naam)}</h2><button type="button" class="knop" data-sluit>Sluiten</button></div>
    <p class="muted">${esc(a.taak)}</p>
    <div class="labels">${statusLab(a.status)}${herkomstLab(a.herkomst)}${bewijsLab(a)}</div>
    <p>${esc(a.stap || "Geen stap bekend.")}</p>
    <p class="meta">Laatste activiteit: ${esc(dt(a.laatste_activiteit))}. Duur: ${esc(duur(a.duur_s))}.</p>
    ${meldingBlok(a.melding)}
    <h3>Activiteit</h3>
    ${logLijst(a.activiteit, NL)}
    ${a.link ? `<p><a href="${esc(a.link)}" target="_blank" rel="noopener noreferrer">Bekijken op GitHub</a></p>` : ""}
  </div>`;
  dlg.showModal();
}

async function haalJson(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

let demo = null;
async function laad() {
  const knop = $("reload");
  knop.disabled = true;
  demo ??= await haalJson("demo.json");
  let api = null, oud = false;
  try {
    api = await haalJson("/api/status");
    if (api.schema !== 1) throw new Error("schema");
    try { localStorage.setItem(OPSLAG, JSON.stringify(api)); } catch {}
  } catch {
    try { api = JSON.parse(localStorage.getItem(OPSLAG)); oud = Boolean(api); } catch { api = null; }
  }
  staat.data = samenvoegen(api, demo, new Date(), oud);
  teken();
  knop.disabled = false;
  $("meld").textContent = api && !oud ? "Status vernieuwd." : "Status kon niet worden vernieuwd.";
}

document.addEventListener("click", (e) => {
  const f = e.target.closest("[data-filter]");
  if (f) { staat.filter = f.dataset.filter; rAgents(); document.querySelector(`[data-fid="f-${CSS.escape(staat.filter)}"]`)?.focus(); return; }
  const d = e.target.closest("[data-detail]");
  if (d) return openDetail(d.dataset.detail);
  if (e.target.closest("[data-sluit]")) $("detail").close();
});
$("detail").addEventListener("click", (e) => { if (e.target === $("detail")) $("detail").close(); });
$("reload").addEventListener("click", laad);
window.addEventListener("hashchange", () => route(true));
route(false);
laad().catch(() => { $("p-agents").innerHTML = `<div class="leeg"><strong>Het dashboard kon niet laden.</strong><span>Vernieuw de pagina om het opnieuw te proberen.</span></div>`; });
setInterval(() => { if (!document.hidden) laad(); }, VERVERS_MS);
