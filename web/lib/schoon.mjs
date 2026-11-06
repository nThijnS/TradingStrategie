// Laatste vangnet: alles wat naar de browser gaat, loopt hierdoorheen. Foutteksten en bottekst kunnen in theorie een sleutel bevatten.
const PATRONEN = [
  /sk-ant-[A-Za-z0-9_-]{8,}/g,
  /github_pat_[A-Za-z0-9_]{8,}/g,
  /\bgh[pousr]_[A-Za-z0-9]{8,}/g,
  /\bBearer\s+[A-Za-z0-9._~+/-]{8,}=*/gi,
  /x-access-token:[^@\s]+/gi,
];

export function schoonTekst(s, extra = []) {
  let uit = s;
  for (const p of PATRONEN) uit = uit.replace(p, "[verborgen]");
  for (const geheim of extra) if (geheim) uit = uit.split(geheim).join("[verborgen]");
  return uit;
}

export function schoon(w, extra = []) {
  if (typeof w === "string") return schoonTekst(w, extra);
  if (Array.isArray(w)) return w.map((x) => schoon(x, extra));
  if (w && typeof w === "object") return Object.fromEntries(Object.entries(w).map(([k, v]) => [k, schoon(v, extra)]));
  return w;
}

export function veiligeLink(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}
