// Lokaal starten zonder extra pakketten: npm run dev. Bedient web/public en /api/status zoals Netlify dat doet.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import functie from "./netlify/functions/status.mjs";

const PUBLIC = fileURLToPath(new URL("public", import.meta.url));
const SOORT = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".webmanifest": "application/manifest+json" };
const toml = await readFile(new URL("../netlify.toml", import.meta.url), "utf8");
const CSP = toml.match(/Content-Security-Policy = "([^"]+)"/)[1];     // dezelfde regels als op Netlify
const POORT = Number(process.env.PORT || 8788);

createServer(async (req, res) => {
  const pad = new URL(req.url, "http://localhost").pathname;
  if (pad === "/api/status") {
    if (process.env.GEEN_API) { res.writeHead(503); return res.end(); }
    const r = await functie(new Request(`http://localhost${pad}`, { method: req.method }));
    res.writeHead(r.status, { "Content-Type": "application/json" });
    return res.end(await r.text());
  }
  try {
    const bestand = join(PUBLIC, normalize(pad === "/" ? "index.html" : pad));
    if (!bestand.startsWith(PUBLIC)) throw new Error("buiten public");
    const inhoud = await readFile(bestand);
    res.writeHead(200, { "Content-Type": SOORT[extname(bestand)] || "application/octet-stream", "Content-Security-Policy": CSP });
    res.end(inhoud);
  } catch {
    res.writeHead(404);
    res.end("Niet gevonden");
  }
}).listen(POORT, "127.0.0.1", () => console.log(`http://127.0.0.1:${POORT}`));
