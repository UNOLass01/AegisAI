import { useEffect, useRef, useState } from "react";
import { fetchInvestigations, fetchSummary } from "../api.js";
import { formatNumber, formatTime, useApi } from "../hooks.js";
import { EmptyState, ErrorState, LoadingState, Metric, Panel, Sparkline } from "../components/ui.jsx";

function errorTone(share) {
  if (share === null || share === undefined) {
    return undefined;
  }
  return share > 0.01 ? "rust" : "green";
}

export default function Overview() {
  const summary = useApi(fetchSummary, { pollMs: 5000 });
  const investigations = useApi(() => fetchInvestigations(8), {});
  const [rateHistory, setRateHistory] = useState([]);
  const historyRef = useRef([]);

  useEffect(() => {
    if (summary.data && Number.isFinite(summary.data.request_rate_per_s)) {
      historyRef.current = [...historyRef.current, summary.data.request_rate_per_s].slice(-40);
      setRateHistory([...historyRef.current]);
    }
  }, [summary.data]);

  return (
    <div data-testid="page-overview">
      <div className="page-head">
        <h1>Overview</h1>
        <p>Live serving posture at a glance. Refreshes every 5 seconds.</p>
      </div>

      <Panel title="Serving" testid="overview-metrics">
        {summary.loading && !summary.data && <LoadingState text="Loading system summary" />}
        {summary.error && !summary.data && (
          <ErrorState message={`Backend unreachable: ${summary.error}`} onRetry={summary.reload} />
        )}
        {summary.data && (
          <div className="metric-row">
            <Metric label="Request rate" value={formatNumber(summary.data.request_rate_per_s)} unit="req/s" />
            <Metric
              label="Error rate"
              value={summary.data.error_share_5xx === null ? "—" : `${formatNumber(summary.data.error_share_5xx * 100, 2)}%`}
              tone={errorTone(summary.data.error_share_5xx)}
            />
            <Metric label="Active model version" value={summary.data.active_model_version ?? "none"} />
            <Metric
              label="Avg agent step latency"
              value={summary.data.agent_avg_step_latency_s === null ? "—" : formatNumber(summary.data.agent_avg_step_latency_s * 1000, 0)}
              unit={summary.data.agent_avg_step_latency_s === null ? "" : "ms"}
            />
          </div>
        )}
        {summary.data && !summary.data.prometheus_reachable && (
          <p className="small muted" style={{ marginTop: 8 }}>
            Prometheus unreachable — serving metrics unavailable, investigation count is live.
          </p>
        )}
      </Panel>

      <Panel title="Recent investigations" testid="overview-timeline">
        {investigations.loading && <LoadingState text="Loading investigations" />}
        {investigations.error && (
          <ErrorState message={`Could not load investigations: ${investigations.error}`} onRetry={investigations.reload} />
        )}
        {investigations.data && investigations.data.length === 0 && (
          <EmptyState text="No investigations yet — ask a question on the Investigations page" />
        )}
        {investigations.data && investigations.data.length > 0 && (
          <div className="row-list">
            {investigations.data.map((row) => (
              <div className="row" key={row.id}>
                <span className={`dot ${row.status === "complete" ? "green" : "rust"}`} />
                <div className="grow">
                  <div className="title">{row.query}</div>
                  <div className="sub mono">{formatTime(row.created_at)}</div>
                </div>
                <span className="mono small">{row.root_cause ? `${row.root_cause.slice(0, 48)}…` : "—"}</span>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Request rate trend" testid="overview-sparkline">
        <Sparkline points={rateHistory} />
        <div className="chart-note">Rolling client-side window from the summary feed.</div>
      </Panel>
    </div>
  );
}
