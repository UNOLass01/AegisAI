const API_BASE = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const PROM_BASE = (import.meta.env.VITE_PROM_URL ?? "http://localhost:9090").replace(/\/$/, "");
const GRAFANA_BASE = (import.meta.env.VITE_GRAFANA_URL ?? "http://localhost:3000").replace(/\/$/, "");

async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`${url} failed with ${res.status}`);
  }
  return res.json();
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${url} failed with ${res.status}${text ? `: ${text.slice(0, 200)}` : ""}`);
  }
  return res.json();
}

export const fetchHealth = () => getJson(`${API_BASE}/health`);
export const fetchModels = () => getJson(`${API_BASE}/models`);
export const fetchIncidents = () => getJson(`${API_BASE}/incidents`);
export const fetchIncident = (id) => getJson(`${API_BASE}/incidents/${encodeURIComponent(id)}`);
export const fetchInvestigations = (limit = 20) =>
  getJson(`${API_BASE}/investigations?limit=${limit}`);
export const fetchInvestigation = (id) => getJson(`${API_BASE}/investigations/${id}`);
export const runInvestigation = (query) => postJson(`${API_BASE}/investigate`, { query });
export const fetchTrace = (hexId) =>
  getJson(`${API_BASE}/investigations/${encodeURIComponent(hexId)}/trace`);
export const fetchEvaluation = () => getJson(`${API_BASE}/evaluation/latest`);
export const fetchSummary = () => getJson(`${API_BASE}/system/summary`);

/** Prometheus range query -> [{ metric, points: [[timestampMs, value], ...] }]. */
export async function promRange(expr, minutes = 15, stepSeconds = 15) {
  const end = Math.floor(Date.now() / 1000);
  const start = end - minutes * 60;
  const params = new URLSearchParams({
    query: expr,
    start: String(start),
    end: String(end),
    step: `${stepSeconds}s`,
  });
  const res = await fetch(`${PROM_BASE}/api/v1/query_range?${params}`);
  if (!res.ok) {
    throw new Error(`prometheus query failed with ${res.status}`);
  }
  const body = await res.json();
  if (body.status !== "success") {
    throw new Error(`prometheus query error: ${body.error ?? "unknown"}`);
  }
  return (body.data.result ?? []).map((series) => ({
    metric: series.metric,
    points: (series.values ?? [])
      .map(([t, v]) => [t * 1000, v === null ? null : Number(v)])
      .filter(([, v]) => v !== null && Number.isFinite(v)),
  }));
}

export { API_BASE, PROM_BASE, GRAFANA_BASE };
