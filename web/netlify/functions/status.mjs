// GET /api/status: alleen lezen. De token blijft hier; de browser krijgt alleen het opgeschoonde antwoord uit lib/status.mjs.
import { bouwStatus } from "../../lib/status.mjs";

export default async (req) => {
  if (req.method !== "GET") return new Response(null, { status: 405, headers: { Allow: "GET" } });
  try {
    const data = await bouwStatus({ env: process.env });
    const seconden = data.token_ingesteld ? 60 : 900;      // zonder token zuinig: 60 verzoeken per uur, gedeeld met andere sites
    return Response.json(data, { headers: {
      "Cache-Control": "public, max-age=0, must-revalidate",
      "Netlify-CDN-Cache-Control": `public, durable, max-age=${seconden}, stale-while-revalidate=${seconden}`,
    } });
  } catch (e) {
    console.error("status mislukt", e?.name);              // alleen het type: foutteksten kunnen geheimen bevatten
    return Response.json({ fout: "De status kon niet worden opgebouwd." }, { status: 500, headers: { "Cache-Control": "no-store" } });
  }
};

export const config = { path: "/api/status" };
