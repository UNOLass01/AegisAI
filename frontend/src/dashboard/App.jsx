import { useCallback, useEffect, useState } from "react";
import { fetchHealth } from "../api.js";

const styles = {
  page: {
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
    background: "#0b1220",
    color: "#e5e7eb",
    minHeight: "100vh",
    margin: 0,
    padding: "32px",
  },
  card: {
    maxWidth: 560,
    margin: "0 auto",
    background: "#111c33",
    border: "1px solid #22314f",
    borderRadius: 12,
    padding: 24,
  },
  badge: (ok) => ({
    display: "inline-block",
    padding: "6px 12px",
    borderRadius: 999,
    fontWeight: 700,
    background: ok === true ? "#14532d" : ok === false ? "#7f1d1d" : "#374151",
    color: "#fff",
  }),
  button: {
    marginTop: 16,
    padding: "8px 14px",
    borderRadius: 8,
    border: "1px solid #334155",
    background: "#1e293b",
    color: "#fff",
    cursor: "pointer",
  },
  meta: { marginTop: 12, fontSize: 13, color: "#9ca3af" },
};

export default function App() {
  const [state, setState] = useState({ status: "checking", body: null, error: null });

  const check = useCallback(async () => {
    setState({ status: "checking", body: null, error: null });
    try {
      const body = await fetchHealth();
      setState({ status: body?.status === "ok" ? "healthy" : "unhealthy", body, error: null });
    } catch (err) {
      setState({ status: "unhealthy", body: null, error: String(err?.message ?? err) });
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  const ok = state.status === "healthy" ? true : state.status === "unhealthy" ? false : null;
  const label =
    state.status === "healthy"
      ? "backend healthy"
      : state.status === "unhealthy"
        ? "backend unreachable"
        : "checking…";

  return (
    <div style={styles.page}>
      <div style={styles.card}>
        <h1 style={{ marginTop: 0 }}>AegisAI Dashboard</h1>
        <p>Phase 1 — backend connectivity check via <code>GET /health</code>.</p>
        <span style={styles.badge(ok)} data-testid="health-badge">
          {ok === true ? "● " : ok === false ? "○ " : "… "}
          {label}
        </span>
        <div style={styles.meta} data-testid="health-detail">
          {state.body ? `Response: ${JSON.stringify(state.body)}` : null}
          {state.error ? `Error: ${state.error}` : null}
          {!state.body && !state.error ? "Contacting backend…" : null}
        </div>
        <button style={styles.button} onClick={check} type="button">
          Recheck
        </button>
      </div>
    </div>
  );
}
