import { STATUSSEN, filter, samenvoegen, tel, telHerkomst } from "./model.js";

const $ = (id) => document.getElementById(id);
const esc = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const VERVERS_MS = 2 * 60000;
const OPSLAG = "marketpilot-laatste-status";

const ZONE = { timeZone: "Europe/Amsterdam" };
const NL = new Intl.DateTimeFormat("nl-NL", { ...ZONE, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const KORT = new Intl.DateTimeFormat("nl-NL", { ...ZONE, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const UUR = new Intl.DateTimeFormat("nl-NL", { ...ZONE, hour: "numeric", hour12: false });
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
function groet() {
  const u = Number(UUR.format(new Date()));
  return u < 6 ? "Nog wakker?" : u < 12 ? "Goedemorgen" : u < 18 ? "Goedemiddag" : "Goedenavond";
}

const STATUS = Object.fromEntries(STATUSSEN);
const ICOON = { wachtend: "…", klaar: "✓", mislukt: "✕", aandacht: "!" };
const statusLab = (s) => `<span class="lab s-${esc(s)}">${s === "bezig" ? `<i class="draaitje" aria-hidden="true"></i>` : `<i aria-hidden="true">${ICOON[s] || "?"}</i>`}${esc(STATUS[s] || s)}</span>`;
const HERKOMST = { live: "Live", verouderd: "Verouderd", demo: "Demo, fictief", ontbreekt: "Ontbreekt" };
const herkomstLab = (h) => `<span class="lab k-${esc(h)}">${esc(HERKOMST[h] || h)}</span>`;
const bewijsLab = (a) => (a.geverifieerd ? "" : `<span class="lab nietbewezen">Niet geverifieerd</span>`);
const SOORT = { fout: "Fout", blokkade: "Blokkade", goedkeuring: "Goedkeuring nodig" };

// Elk robotje is een vaste combinatie van kleur en kopvorm; ogen en mond volgen de status.
const LOOK = {
  scout: ["#6ff2d0", 16, "antenne"], charts: ["#7cc4ff", 8, "oren"], news: ["#ffd166", 22, "antenne"], sentiment: ["#ff8cc3", 28, "hart"], skeptic: ["#ff9f6e", 6, "wenkbrauw"], chief: ["#c4b5ff", 14, "kroon"],
  keten: ["#6ff2d0", 10, "oren"], leren: ["#c4b5ff", 20, "hart"], marktradar: ["#ff8cc3", 12, "antenne"], tests: ["#7cc4ff", 4, "antenne"], capitaldata: ["#ffd166", 10, "oren"], feedmeting: ["#ff9f6e", 18, "antenne"], instrumenten: ["#9be564", 8, "oren"],
};
function robot(id, status) {
  const [kleur, hoek, extra] = LOOK[id] || ["#c4b5ff", 14, "antenne"];
  const inkt = "#151031";
  const top = {
    antenne: `<path d="M32 15V8" stroke="${kleur}" stroke-width="3.4" stroke-linecap="round"/><circle cx="32" cy="7" r="3.4" fill="${kleur}"/>`,
    oren: `<rect x="5" y="27" width="6" height="14" rx="3" fill="${kleur}"/><rect x="53" y="27" width="6" height="14" rx="3" fill="${kleur}"/>`,
    hart: `<path d="M32 13s-7-4.5-7-8.5a3.7 3.7 0 0 1 7-1.5 3.7 3.7 0 0 1 7 1.5c0 4-7 8.5-7 8.5z" fill="${kleur}"/>`,
    wenkbrauw: `<path d="M25 9l14 6" stroke="${kleur}" stroke-width="3.4" stroke-linecap="round"/>`,
    kroon: `<path d="M21 15l-2-10 7 5 6-7 6 7 7-5-2 10z" fill="${kleur}"/>`,
  }[extra];
  const oog = { klaar: [`<path d="M18 33q5-6 10 0M36 33q5-6 10 0" stroke="${inkt}" stroke-width="3.4" fill="none" stroke-linecap="round"/>`, `<path d="M25 44q7 6 14 0" stroke="${inkt}" stroke-width="3.2" fill="none" stroke-linecap="round"/>`],
    mislukt: [`<path d="M19 28l8 8M27 28l-8 8M37 28l8 8M45 28l-8 8" stroke="${inkt}" stroke-width="3.4" stroke-linecap="round"/>`, `<path d="M25 47q7-6 14 0" stroke="${inkt}" stroke-width="3.2" fill="none" stroke-linecap="round"/>`],
    aandacht: [`<circle class="oog" cx="23" cy="32" r="5.2" fill="${inkt}"/><circle class="oog" cx="41" cy="32" r="5.2" fill="${inkt}"/>`, `<circle cx="32" cy="45" r="3.4" fill="${inkt}"/>`],
    wachtend: [`<path d="M18 33h10M36 33h10" stroke="${inkt}" stroke-width="3.4" stroke-linecap="round"/>`, `<path d="M27 45h10" stroke="${inkt}" stroke-width="3.2" stroke-linecap="round"/>`],
    bezig: [`<circle class="oog" cx="23" cy="32" r="4.4" fill="${inkt}"/><circle class="oog" cx="41" cy="32" r="4.4" fill="${inkt}"/>`, `<path d="M26 45h12" stroke="${inkt}" stroke-width="3.2" stroke-linecap="round"/>`],
  }[status] || ["", ""];
  return `<svg viewBox="0 0 64 64" aria-hidden="true" class="${status === "bezig" ? "bezig-robot" : ""}">${top}<rect x="10" y="15" width="44" height="40" rx="${hoek}" fill="${kleur}"/>${oog[0]}${oog[1]}</svg>`;
}

const staat = { data: null, filter: "alle", pagina: "crew" };
const alleAgents = () => [...staat.data.agents.bots, ...staat.data.agents.workflows];

function logLijst(regels, f = KORT) {
  return regels.length
    ? `<ol class="log">${regels.map((r) => `<li class="${esc(r.status)}">${tijd(r.t, f)}<span>${esc(r.tekst)}</span></li>`).join("")}</ol>`
    : `<p class="zacht klein">Nog geen activiteit bekend.</p>`;
}
const meldingBlok = (m) => (m ? `<p class="melding ${m.soort === "fout" ? "fout" : ""}"><b>${esc(SOORT[m.soort] || "Melding")}:</b> ${esc(m.tekst)}</p>` : "");

function agentKaart(a) {
  return `<article class="agent herkomst h-${esc(a.herkomst)}">
    <div class="ava">${robot(a.id, a.status)}</div>
    <div class="a-kop"><h3><button type="button" class="a-open" data-detail="${esc(a.id)}" data-fid="d-${esc(a.id)}">${esc(a.naam)}</button></h3>${statusLab(a.status)}</div>
    <p class="a-taak">${esc(a.taak)}</p>
    <div class="a-onder">
      <div class="labels">${herkomstLab(a.herkomst)}${bewijsLab(a)}</div>
      <p class="a-stap">${esc(a.stap || "Geen stap bekend.")}</p>
      <p class="meta">Laatste activiteit: ${esc(geleden(a.laatste_activiteit))}. Duur: ${esc(duur(a.duur_s))}.</p>
      ${meldingBlok(a.melding)}
      ${logLijst(a.activiteit.slice(-2))}
    </div>
  </article>`;
}

function groep(titel, uitleg, agents) {
  const zicht = filter(agents, staat.filter);
  if (!zicht.length) return "";
  return `<section class="rij"><div class="kop"><h2>${esc(titel)}</h2><p>${esc(uitleg)}</p></div><div class="lijst">${zicht.map(agentKaart).join("")}</div></section>`;
}

const ring = (ok, totaal) => {
  const omtrek = 2 * Math.PI * 26, deel = totaal ? ok / totaal : 0;
  return `<svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="26" fill="none" stroke="rgba(255,255,255,.1)" stroke-width="9"/>${ok ? `<circle cx="32" cy="32" r="26" fill="none" stroke="#6ff2d0" stroke-width="9" stroke-linecap="round" stroke-dasharray="${(deel * omtrek).toFixed(1)} ${omtrek.toFixed(1)}"/>` : ""}</svg>`;
};
const balk = (delen) => {
  const som = delen.reduce((s, [n]) => s + n, 0) || 1;
  let x = 0;
  return `<div class="balk" aria-hidden="true"><svg viewBox="0 0 100 10" preserveAspectRatio="none">${delen.map(([n, kleur]) => { const w = (n / som) * 100, r = `<rect x="${x}" y="0" width="${w}" height="10" fill="${kleur}"/>`; x += w; return r; }).join("")}</svg></div>`;
};

function hero(alle) {
  const hulp = alle.filter((a) => a.status === "mislukt" || a.status === "aandacht");
  const echt = hulp.filter((a) => a.herkomst !== "demo").length, demo = hulp.length - echt;
  const bezig = alle.filter((a) => a.status === "bezig").length;
  const zin = echt === 0 ? "Je crew heeft je nu niet nodig" : `${echt} ${echt === 1 ? "agent heeft" : "agents hebben"} je nodig`;
  const sub = [bezig ? `${bezig} bezig` : "", `${alle.filter((a) => a.status === "klaar").length} klaar`, demo ? `${demo} demo-voorbeelden met aandacht` : ""].filter(Boolean).join(", ");
  return `<section class="hero"><p class="groet">${esc(groet())}</p><h2>${esc(zin)}</h2><p class="sub">${esc(sub)}.</p></section>`;
}

function banners() {
  const d = staat.data, h = telHerkomst(alleAgents()), uit = [];
  if (d.modus === "geen-api") uit.push(["demo", "<strong>De server is niet bereikbaar.</strong> Alles hier is fictieve demo-informatie."]);
  else {
    if (d.modus === "verouderd") uit.push(["verouderd", `<strong>Deze gegevens zijn verouderd.</strong> Laatst opgehaald ${esc(geleden(d.opgehaald_op))}.`]);
    if (h.demo || d.radar.isDemo) uit.push(["demo", "<strong>Gearceerde blokken zijn fictief.</strong> Een dichte rand betekent echt."]);
  }
  return uit.map(([k, t]) => `<p class="demo-chip herkomst h-${k}"><span>${t}</span></p>`).join("");
}

function bento(alle) {
  const r = staat.data.radar, v = r.verificatie || [], ok = v.filter((x) => x.geverifieerd).length, h = telHerkomst(alle);
  const ronde = r.isDemo ? "Geen echte ronde" : dt(r.ronde?.peilmoment);
  return `<section class="bento" aria-label="Belangrijkste status">
    <a class="tegel breed herkomst h-${esc(r.herkomst)}" href="#radar"><span class="tit">MarktRadar${r.isDemo ? ", voorbeeld" : ""}</span><span class="groot">${esc(ronde)}</span>
      <div class="stipjes" aria-hidden="true">${(r.markten || []).map((m) => `<i class="o-${esc(m.oordeel)}"></i>`).join("")}</div></a>
    <a class="tegel" href="#radar"><span class="tit">Bewezen</span><div class="ringmeter">${ring(ok, v.length)}<span class="groot num">${ok}/${v.length}</span></div></a>
    <a class="tegel" href="#bronnen"><span class="tit">Herkomst</span><span class="groot">${h.live || 0} live</span><span class="zacht klein">${h.demo || 0} demo${h.verouderd ? `, ${h.verouderd} verouderd` : ""}${h.ontbreekt ? `, ${h.ontbreekt} ontbreekt` : ""}</span>
      ${balk([[h.live || 0, "#6ff2d0"], [h.verouderd || 0, "#ffd166"], [h.demo || 0, "#a892ff"], [h.ontbreekt || 0, "#a9a3c7"]])}</a>
  </section>`;
}

function rCrew() {
  const alle = alleAgents(), n = tel(alle);
  const knop = (id, tekst, aantal) => `<button type="button" class="filter" data-filter="${id}" data-fid="f-${id}" aria-pressed="${staat.filter === id}">${esc(tekst)} <span class="num">${aantal}</span></button>`;
  const inhoud = groep("MarktRadar-bots", "De zes deelbots van één adviesronde.", staat.data.agents.bots)
    + groep("Automatisering", "Workflows op GitHub Actions.", staat.data.agents.workflows);
  $("p-crew").innerHTML = `${hero(alle)}
    <div class="stories" role="list" aria-label="Je crew">${alle.map((a) => `<div role="listitem"><button type="button" class="story" data-detail="${esc(a.id)}" data-fid="s-${esc(a.id)}" aria-label="${esc(a.naam)}: ${esc(STATUS[a.status])}"><span class="ring r-${esc(a.status)}"><span>${robot(a.id, a.status)}</span></span><span class="naam">${esc(a.naam.replace(/-workflow|-keten| controleren/, ""))}</span></button></div>`).join("")}</div>
    ${banners()}
    ${bento(alle)}
    <div class="filters" role="group" aria-label="Filter op status">${knop("alle", "Alle", alle.length)}${STATUSSEN.map(([s, t]) => knop(s, t, n[s])).join("")}</div>
    ${inhoud || `<div class="waarschuwing"><strong>Geen agents met status ${esc(STATUS[staat.filter])}</strong><button type="button" class="filter" data-filter="alle" data-fid="f-leeg">Toon alle agents</button></div>`}`;
}

function radarKop(r) {
  const peil = r.ronde?.peilmoment;
  return `<section class="hero"><p class="groet">MarktRadar</p><h2>${r.isDemo ? "Voorbeeldronde, fictief" : `Ronde ${esc(r.ronde?.ronde_id)}`}</h2>
    <p class="sub">${peil ? `Peilmoment ${esc(dt(peil))}. ` : ""}Alleen advies: er worden geen orders geplaatst. Voorspellingen zijn geen bewezen resultaten.</p></section>
    <div class="labels">${herkomstLab(r.herkomst)}${r.ronde?.status ? `<span class="lab s-${r.ronde.status === "volledig" ? "klaar" : "aandacht"}">${esc(r.ronde.status)}</span>` : ""}</div>
    ${r.reden ? `<div class="waarschuwing herkomst h-ontbreekt"><strong>Geen echte MarktRadar-data</strong><span>${esc(r.reden)} ${esc(r.actie || "")}</span>${r.isDemo ? `<span class="zacht klein">Hieronder staat fictieve informatie uit een droge ronde.</span>` : ""}</div>` : ""}`;
}

function verificatieBlok(r) {
  const v = r.verificatie || [], ok = v.filter((x) => x.geverifieerd).length, wf = r.workflow;
  return `<div class="paneel herkomst h-${wf ? "live" : "demo"}"><div class="ringmeter">${ring(ok, v.length)}<div><h3>Is het bewezen?</h3><p class="meta">${ok} van ${v.length} met een echte run.</p></div></div>
    <ul class="bewijs">${v.map((x) => `<li class="${x.geverifieerd ? "ja" : "nee"}"><i aria-hidden="true">${x.geverifieerd ? "✓" : "?"}</i><div><b>${esc(x.naam)}</b><span>${x.geverifieerd ? "Bewezen" : "Niet geverifieerd"}. ${esc(x.bewijs)}</span>${x.link ? ` <a class="klein" href="${esc(x.link)}" target="_blank" rel="noopener noreferrer">Run bekijken</a>` : ""}</div></li>`).join("")}</ul>
    <p class="meta">${wf ? `Workflowstatus: ${esc(STATUS[wf.status] || wf.status)}. ${esc(wf.stap || "")}` : "Workflowstatus onbekend: de server is niet bereikbaar."}</p></div>`;
}

function briefingBlok(r) {
  const ronde = r.ronde, g = ronde?.gegevens;
  if (!ronde) return `<div class="paneel"><h3>Geen briefing</h3></div>`;
  return `<div class="rij"><div class="paneel herkomst h-${esc(r.herkomst)}"><h3>Briefing${r.isDemo ? ", fictief" : ""}</h3>
    ${ronde.samenvatting ? `<p>${esc(ronde.samenvatting)}</p>` : ""}
    <p class="briefing">${esc(ronde.briefing || "Geen briefing in deze ronde.")}</p></div>
    <div class="paneel herkomst h-${esc(r.herkomst)}"><h3>Herkomst van de gegevens</h3>
    ${g?.bots?.length ? `<ol class="log">${g.bots.map((b) => `<li>${tijd(b.data_tot, KORT)}<span>${esc(b.bot)}: gegevens tot dit moment, gemaakt ${esc(dt(b.gemaakt_op))}</span></li>`).join("")}</ol>` : `<p class="zacht klein">Geen botgegevens beschikbaar.</p>`}
    ${g?.bronnen?.length ? `<ol class="log">${g.bronnen.map((b) => `<li>${tijd(b.tijdstip, KORT)}<span>${b.url ? `<a href="${esc(b.url)}" target="_blank" rel="noopener noreferrer">${esc(b.naam)}</a>` : esc(b.naam)}</span></li>`).join("")}</ol>` : ""}
  </div></div>`;
}

function marktenBlok(r) {
  if (!r.markten?.length) return "";
  return `<section class="rij"><div class="kop"><h2>De 15 markten</h2><p>${r.isDemo ? "Fictieve signalen. " : ""}Een signaal is alleen een aanwijzing om verder te kijken. Tik voor de reden.</p></div>
    <div class="markten">${r.markten.map((m) => `<button type="button" class="markt m-${esc(m.oordeel)}" data-markt="${esc(m.markt)}" data-fid="m-${esc(m.markt)}"><b>${esc(m.titel)}</b><small>${esc(m.oordeel)}</small></button>`).join("")}</div></section>`;
}

const pct = (v) => (v == null ? "–" : `${(v * 100).toFixed(1)}%`);
const netto = (v) => (v == null ? "–" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(2)}%`);
function scoreBlok(r) {
  const k = Object.entries(r.scorekaart || {}), maand = Object.entries(r.kosten_per_maand || {}).sort().pop();
  const kaart = ([b, s]) => `<article class="score herkomst h-${esc(r.herkomst)}"><div class="score-kop"><h3>${esc(b)}</h3><span class="lab ${s.conclusie === "te weinig data" ? "s-aandacht" : "s-klaar"}">${esc(s.conclusie)}</span></div>
    <p class="meta"><span class="num">${esc(s.n)}</span> van ${esc(r.min_voorspellingen)} voorspellingen, <span class="num">${esc(s.dagen)}</span> van ${esc(r.min_dagen)} dagen</p>
    ${balk([[Math.min(s.n, r.min_voorspellingen), "#a892ff"], [Math.max(r.min_voorspellingen - s.n, 0), "rgba(255,255,255,.06)"]])}
    <dl class="cijfers"><div><dt>Trefkans</dt><dd>${pct(s.trefkans)}</dd></div><div><dt>Brier</dt><dd>${s.brier == null ? "–" : esc(Number(s.brier).toFixed(3))}</dd></div><div><dt>Netto</dt><dd>${netto(s.netto)}</dd></div><div><dt>Willekeurig</dt><dd>${netto(s.basislijn?.willekeurig)}</dd></div><div><dt>Richting gisteren</dt><dd>${netto(s.basislijn?.gisteren)}</dd></div></dl></article>`;
  return `<section class="rij"><div class="kop"><h2>Scorekaart</h2><p>${r.isDemo ? "Fictieve cijfers. " : ""}Conclusies pas vanaf ${esc(r.min_voorspellingen)} voorspellingen op ${esc(r.min_dagen)} dagen. Netto is per voorspelling, na kosten; niets doen is altijd 0%.</p></div>
    ${k.length ? `<div class="scorelijst">${k.map(kaart).join("")}</div>` : `<div class="waarschuwing herkomst h-${esc(r.herkomst)}"><strong>0 afgerekende voorspellingen: te weinig data</strong><span class="zacht klein">Na de horizon van een ronde komen hier de uitkomsten.</span></div>`}
    <p class="opmerking">LLM-kosten${maand ? ` in ${esc(maand[0])}: $${esc(Number(maand[1]).toFixed(2))}` : ": nog geen"}${r.isDemo ? " (demo)" : ""}.</p></section>`;
}

function rRadar() {
  const r = staat.data.radar;
  $("p-radar").innerHTML = `${radarKop(r)}<div class="tweekolom">${briefingBlok(r)}${verificatieBlok(r)}</div>${marktenBlok(r)}${scoreBlok(r)}`;
}

const NODIG = [
  ["Agentstatus van workflows", "Werkt nu. Een lees-token GITHUB_TOKEN op Netlify geeft een hogere limiet."],
  ["MarktRadar-workflow", "Merge feat/marktradar naar main en zet ANTHROPIC_API_KEY als GitHub-secret."],
  ["MarktRadar-data", "Na de eerste geslaagde run bestaat de branch marktradar-data en verschijnt de echte ronde hier vanzelf."],
  ["Capital-sentiment", "Controleer in de eerste rondes of alle 15 markten sentiment krijgen."],
];
function rBronnen() {
  const d = staat.data;
  $("p-bronnen").innerHTML = `<section class="hero"><p class="groet">Bronnen</p><h2>Waar komt het vandaan?</h2><p class="sub">${d.opgehaald_op ? `Opgehaald ${esc(dt(d.opgehaald_op))}.` : "Niet opgehaald."}</p></section>
    <section class="tabel">${d.bronnen.map((b) => `<article class="bron"><div class="bron-kop"><b>${esc(b.naam)}</b>${herkomstLab(b.staat)}</div><p class="zacht klein">${esc(b.detail)} ${esc(b.actie || "")}</p></article>`).join("")}</section>
    <section class="rij"><div class="kop"><h2>Nog aan te sluiten</h2><p>Dit is nodig om alles echt te maken.</p></div>
      <div class="tabel">${NODIG.map(([a, b]) => `<article class="bron"><b>${esc(a)}</b><p class="zacht klein">${esc(b)}</p></article>`).join("")}</div></section>
    <section class="rij"><div class="kop"><h2>Op je beginscherm</h2><p>iPhone: tik in Safari op Delen en kies Zet op beginscherm. Android: open het menu in Chrome en kies App installeren.</p></div></section>`;
}

const RENDER = { crew: rCrew, radar: rRadar, bronnen: rBronnen };
function teken() {
  if (!staat.data) return;
  const focus = document.activeElement?.dataset?.fid;
  const scroll = document.querySelector(".stories")?.scrollLeft;
  for (const f of Object.values(RENDER)) f();
  if (scroll) document.querySelector(".stories").scrollLeft = scroll;
  if (focus) document.querySelector(`[data-fid="${CSS.escape(focus)}"]`)?.focus();
}

function route(naarInhoud) {
  const h = location.hash.slice(1);
  if (h === "main") return;
  staat.pagina = RENDER[h] ? h : "crew";
  document.querySelectorAll(".page").forEach((p) => { p.hidden = p.id !== `p-${staat.pagina}`; });
  document.querySelectorAll(".tabs a").forEach((a) => (a.dataset.p === staat.pagina ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  if (naarInhoud) { window.scrollTo(0, 0); $("main").focus({ preventScroll: true }); }
}

function open(html) {
  const dlg = $("detail");
  dlg.innerHTML = `<div class="greep" aria-hidden="true"></div>${html}`;
  dlg.showModal();
  dlg.scrollTop = 0;
}

function openAgent(id) {
  const a = alleAgents().find((x) => x.id === id);
  if (!a) return;
  open(`<div class="d-in herkomst h-${esc(a.herkomst)}">
    <div class="d-kop"><div class="ava">${robot(a.id, a.status)}</div><h2 id="detail-kop">${esc(a.naam)}</h2><button type="button" class="rond" data-sluit aria-label="Sluiten"><span aria-hidden="true">✕</span></button></div>
    <p class="zacht">${esc(a.taak)}</p>
    <div class="labels">${statusLab(a.status)}${herkomstLab(a.herkomst)}${bewijsLab(a)}</div>
    <p>${esc(a.stap || "Geen stap bekend.")}</p>
    <p class="meta">Laatste activiteit: ${esc(dt(a.laatste_activiteit))}. Duur: ${esc(duur(a.duur_s))}.</p>
    ${meldingBlok(a.melding)}
    <h3>Activiteit</h3>
    ${logLijst(a.activiteit, NL)}
    ${a.link ? `<p><a href="${esc(a.link)}" target="_blank" rel="noopener noreferrer">Bekijken op GitHub</a></p>` : ""}
  </div>`);
}

function openMarkt(id) {
  const r = staat.data.radar, m = r.markten.find((x) => x.markt === id);
  if (!m) return;
  open(`<div class="d-in herkomst h-${esc(r.herkomst)}">
    <div class="d-kop"><h2 id="detail-kop">${esc(m.titel)}</h2><button type="button" class="rond" data-sluit aria-label="Sluiten"><span aria-hidden="true">✕</span></button></div>
    <p class="zacht">${esc(m.markt)}, ${esc(m.soort)}</p>
    <div class="labels"><span class="lab num">${esc(m.oordeel)}</span>${herkomstLab(r.herkomst)}</div>
    ${m.richting !== "geen" ? `<p>Richting ${esc(m.richting)}${m.zekerheid != null ? `, zekerheid <span class="num">${esc(Number(m.zekerheid).toFixed(2))}</span>` : ""}.</p>` : ""}
    <p>${esc(m.reden)}${m.toelichting ? ` ${esc(m.toelichting)}` : ""}</p>
    ${m.steun?.length ? `<p class="meta">Steun: ${esc(m.steun.join(", "))}.</p>` : ""}
    <p class="meta">Geen financieel advies. Een signaal is geen bewezen resultaat.</p>
  </div>`);
}

async function haalJson(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(String(r.status));
  return r.json();
}

let demo = null;
async function laad() {
  const knop = $("reload");
  knop.classList.add("draait");
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
  knop.classList.remove("draait");
  $("meld").textContent = api && !oud ? "Status vernieuwd." : "Status kon niet worden vernieuwd.";
}

document.addEventListener("click", (e) => {
  const f = e.target.closest("[data-filter]");
  if (f) { staat.filter = f.dataset.filter; rCrew(); document.querySelector(`[data-fid="f-${CSS.escape(staat.filter)}"]`)?.focus(); return; }
  const d = e.target.closest("[data-detail]");
  if (d) return openAgent(d.dataset.detail);
  const m = e.target.closest("[data-markt]");
  if (m) return openMarkt(m.dataset.markt);
  if (e.target.closest("[data-sluit]")) $("detail").close();
});
$("detail").addEventListener("click", (e) => { if (e.target === $("detail")) $("detail").close(); });
$("reload").addEventListener("click", laad);
window.addEventListener("hashchange", () => route(true));
route(false);
laad().catch(() => { $("p-crew").innerHTML = `<div class="waarschuwing"><strong>Het dashboard kon niet laden.</strong><span>Vernieuw de pagina om het opnieuw te proberen.</span></div>`; });
setInterval(() => { if (!document.hidden) laad(); }, VERVERS_MS);
