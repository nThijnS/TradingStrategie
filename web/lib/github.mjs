// Alleen lezen: deze client doet uitsluitend GET-verzoeken. De token gaat alleen naar de twee hosts van GitHub.
const API = "https://api.github.com";
const RAW = "https://raw.githubusercontent.com";

export function maakClient({ repo, token, doeFetch = fetch, timeoutMs = 6000 }) {
  const koppen = { "User-Agent": "marketpilot-dashboard", ...(token ? { Authorization: `Bearer ${token}` } : {}) };

  async function get(url, extra) {
    try {
      const r = await doeFetch(url, { method: "GET", headers: { ...koppen, ...extra }, signal: AbortSignal.timeout(timeoutMs) });
      if (r.ok) return { ok: true, status: r.status, data: await r.json() };
      const limiet = (r.status === 403 || r.status === 429) && r.headers.get("x-ratelimit-remaining") === "0";
      return { ok: false, status: r.status, limiet };
    } catch (e) {
      return { ok: false, status: 0, netwerk: e?.name || "fout" };
    }
  }

  const api = (pad) => get(`${API}/repos/${repo}${pad}`, { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" });
  return {
    runs: (bestand, aantal) => api(`/actions/workflows/${bestand}/runs?per_page=${aantal}&exclude_pull_requests=true`),
    jobs: (runId) => api(`/actions/runs/${runId}/jobs?per_page=10`),
    bestand: (branch, pad) => get(`${RAW}/${repo}/${encodeURIComponent(branch)}/${pad}`),
  };
}

export function foutTekst(a) {
  if (a.limiet) return "De limiet van GitHub is bereikt. Stel GITHUB_TOKEN in voor een hogere limiet.";
  if (a.status === 401) return "GitHub weigert de token (HTTP 401). Controleer GITHUB_TOKEN.";
  if (a.status === 403) return "GitHub weigert toegang (HTTP 403). Controleer de rechten van GITHUB_TOKEN.";
  if (a.status) return `GitHub gaf HTTP ${a.status}.`;
  return "GitHub gaf geen antwoord.";
}
