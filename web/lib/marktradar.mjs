// Zet de bestanden van de branch marktradar-data om naar wat het dashboard toont. Bewijs komt alleen uit echte data.
import { BOTS, MARKTEN, MIN_DAGEN_STABIEL, RONDE_VEROUDERD_UUR } from "./config.mjs";
import { veiligeLink } from "./schoon.mjs";

const tekstLijst = (x) => (Array.isArray(x) ? x.filter((i) => typeof i === "string") : []);
const OPDRACHT_MENS = new Set(["schedule", "workflow_dispatch"]);

export function isVerouderd(peilmoment, nu) {
  const t = Date.parse(peilmoment);
  return !Number.isFinite(t) || nu.getTime() - t > RONDE_VEROUDERD_UUR * 3.6e6;
}

export function markten(laatste) {
  const per = new Map((laatste?.oordelen || []).map((o) => [o.markt, o]));
  const tekst = laatste?.toelichting?.markten || {};
  return MARKTEN.map(({ markt, titel, soort }) => {
    const o = per.get(markt);
    if (!o) return { markt, titel, soort, oordeel: "GEEN_ACTIE", bekeken: false, reden: "Niet gekozen door de Scout.", richting: "geen", zekerheid: null, steun: [], toelichting: null };
    return { markt, titel, soort, oordeel: o.oordeel, bekeken: true, reden: o.reden, richting: o.richting, zekerheid: o.zekerheid, steun: tekstLijst(o.steun), toelichting: tekst[markt] || null };
  });
}

function herkomstVan(ronde, nu) {
  return isVerouderd(ronde.peilmoment, nu) ? "verouderd" : "live";
}

function regelsBot(id, ronde) {
  const prefix = `${id}: `;
  return tekstLijst(ronde.ontbreekt).filter((x) => x.startsWith(prefix)).map((x) => x.slice(prefix.length));
}

function botAgent(cfg, ronde, nu) {
  const herkomst = herkomstVan(ronde, nu);
  const a = { id: cfg.id, naam: cfg.naam, groep: "marktradar", taak: cfg.taak, herkomst, duur_s: null, link: null };
  const model = (ronde.modellen?.[cfg.id] || []).length > 0;

  if (cfg.id === "chief") {
    const tel = (w) => (ronde.oordelen || []).filter((o) => o.oordeel === w).length;
    const regels = tekstLijst(ronde.ontbreekt);
    return { ...a, status: ronde.status === "volledig" ? "klaar" : "aandacht", geverifieerd: model, laatste_activiteit: ronde.peilmoment,
      stap: `Oordelen vastgelegd: ${tel("VOLGEN")} volgen, ${tel("ONDERZOEKEN")} onderzoeken, ${tel("GEEN_ACTIE")} geen actie.`,
      melding: regels.length ? { soort: "blokkade", tekst: `Onvolledige ronde: ${regels.length} onderdeel of onderdelen ontbreken.` } : null,
      activiteit: [{ t: ronde.peilmoment, tekst: "Ronde vastgelegd", status: "stap" }, ...regels.map((x) => ({ t: ronde.peilmoment, tekst: x, status: "aandacht" }))].slice(0, 12) };
  }

  const u = ronde.ruw?.[cfg.id];
  const regels = regelsBot(cfg.id, ronde);
  if (!u) {
    const lege = (ronde.markten || []).length === 0 && cfg.id !== "scout";
    return { ...a, status: lege ? "klaar" : "mislukt", geverifieerd: false, laatste_activiteit: ronde.peilmoment,
      stap: lege ? "Niet nodig: de Scout koos geen markten." : "Geen geldige uitvoer in deze ronde.",
      melding: !lege ? { soort: "fout", tekst: regels[0] || "De bot leverde geen geldige uitvoer." } : null,
      activiteit: regels.map((x) => ({ t: ronde.peilmoment, tekst: x, status: "mislukt" })) };
  }
  const bevindingen = u.bevindingen || [];
  const veto = u.veto || [];
  const nietGeteld = (ronde.niet_meegeteld || []).filter((n) => n.bot === cfg.id);
  const t = u.gemaakt_op || ronde.peilmoment;
  return { ...a, status: regels.length ? "aandacht" : "klaar", laatste_activiteit: t,
    geverifieerd: !cfg.llm || model,
    stap: `${bevindingen.length} bevinding(en)${veto.length ? `, ${veto.length} veto` : ""}.`,
    melding: regels.length ? { soort: "blokkade", tekst: regels[0] } : null,
    activiteit: [
      { t: u.data_tot, tekst: "Gegevens gelezen tot dit tijdstip", status: "stap" },
      { t, tekst: `${bevindingen.length} bevinding(en) vastgelegd`, status: "klaar" },
      ...regels.map((x) => ({ t, tekst: x, status: "aandacht" })),
      ...nietGeteld.map((n) => ({ t, tekst: `${n.markt} niet meegeteld: ${n.reden}`, status: "aandacht" })),
      ...veto.map((v) => ({ t, tekst: `Veto op ${v.markt}: ${v.reden}`, status: "aandacht" })),
    ].slice(0, 12) };
}

export const botsUitRonde = (ronde, nu) => BOTS.map((b) => botAgent(b, ronde, nu));

export function herkomstGegevens(ronde) {
  const bots = Object.entries(ronde.ruw || {}).map(([bot, u]) => ({ bot, data_tot: u.data_tot, gemaakt_op: u.gemaakt_op }));
  const bronnen = new Map();
  for (const u of Object.values(ronde.ruw || {})) {
    for (const b of u.bevindingen || []) {
      for (const s of b.bronnen || []) {
        const huidig = bronnen.get(s.naam);
        if (!huidig || s.tijdstip > huidig.tijdstip) bronnen.set(s.naam, { naam: s.naam, url: veiligeLink(s.url), tijdstip: s.tijdstip });
      }
    }
  }
  return { bots, bronnen: [...bronnen.values()] };
}

export function verificatie({ wfAgent, runsAntwoord, ronde, dashboard }) {
  const runs = runsAntwoord?.ok ? runsAntwoord.data.workflow_runs || [] : [];
  const geslaagd = runs.filter((r) => r.conclusion === "success" && OPDRACHT_MENS.has(r.event));
  const echt = ronde && ronde.droog === false;
  const dagen = new Set(geslaagd.map((r) => (r.run_started_at || r.created_at).slice(0, 10))).size;
  const sentiment = echt ? ronde.ruw?.sentiment : null;
  const sentimentMist = echt ? tekstLijst(ronde.ontbreekt).filter((x) => /sentiment/i.test(x)).length : 0;
  const onbekend = !runsAntwoord?.ok && runsAntwoord?.status !== 404;
  const item = (id, naam, ok, bewijs, link = null) => ({ id, naam, geverifieerd: Boolean(ok), bewijs, link });
  return [
    item("workflow", "Workflow staat op GitHub", wfAgent.geregistreerd === true,
      wfAgent.geregistreerd === true ? "GitHub kent marktradar.yml." : onbekend ? "Niet vast te stellen: GitHub gaf geen antwoord." : "GitHub kent marktradar.yml niet op de standaardbranch."),
    item("run", "Workflow heeft echt gedraaid", geslaagd.length > 0,
      geslaagd.length ? `Laatste geslaagde run: ${geslaagd[0].run_started_at}.` : "Geen geslaagde run gevonden.", geslaagd[0]?.html_url ?? null),
    item("data", "Rondedata staat op de databranch", Boolean(dashboard && echt),
      dashboard && echt ? `Ronde ${ronde.ronde_id} gelezen.` : "Geen echte ronde gevonden op de databranch."),
    item("model", "Echt model is aangeroepen", echt && Object.keys(ronde.modellen || {}).length > 0 && ronde.kosten_usd > 0,
      echt && Object.keys(ronde.modellen || {}).length ? `Model(len) in de laatste ronde, kosten $${ronde.kosten_usd}.` : "De laatste ronde bevat geen modelaanroep."),
    item("sentiment", "Capital-sentiment is opgehaald", sentiment && (sentiment.bevindingen || []).length > 0 && sentimentMist === 0,
      !sentiment ? "Geen sentiment-uitvoer gevonden." : sentimentMist ? `${sentimentMist} sentimentmelding(en) in de laatste ronde.` : "Sentiment compleet in de laatste ronde."),
    item("stabiel", `Stabiel op minstens ${MIN_DAGEN_STABIEL} dagen`, dagen >= MIN_DAGEN_STABIEL, `${dagen} dag(en) met een geslaagde run.`),
  ];
}
