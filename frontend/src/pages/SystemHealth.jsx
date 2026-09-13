import { useState } from "react";
import { GRAFANA_BASE, promRange } from "../api.js";
import { useApi } from "../hooks.js";
import { ErrorState, LineChart, LoadingState, Panel } from "../components/ui.jsx";

const CHARTS = [
  {
    id: "latency",
    title: "Request latency p50 / p95",
    targets: [
      {
        label: "p50",
        expr: "histogram_quantile(0.50, sum by (le, handler) (rate(http_request_duration_seconds_bucket[2m])))",
      },
      {
        label: "p95",
        expr: "histogram_quantile(0.95, sum by (le, handler) (rate(http_request_duration_seconds_bucket[2m])))",
      },
    ],
  },
  {
    id: "errors",
    title: "Error rate (5xx share)",
    breach: { label: "5xx share", over: 0.01 },
    targets: [
      {
        label: "5xx share",
        expr: 'sum(rate(http_requests_total{status=~"5.."}[2m])) / sum(rate(http_requests_total[2m])) or vector(0)',
      },
    ],
  },
  {
    id: "tokens",
    title: "Agent token usage",
    targets: [
      {
        label: "tokens in",
        expr: "sum by (direction) (rate(agent_tokens_total[2m]))",
      },
    ],
  },
  {
    id: "cost",
    title: "Agent cost (cumulative USD)",
    targets: [{ label: "USD", expr: "sum(agent_cost_usd_total)" }],
  },
];

function ChartPanel({ chart }) {
  const [minutes, setMinutes] = useState(15);
  const { data, error, loading, reload } = useApi(
    async () => {
      const results = [];
      for (const target of chart.targets) {
        const series = await promRange(target.expr, minutes, 15);
        if (target.label === "tokens in") {
          results.push(...series.map((s) => ({
            label: s.metric.direction ?? "?",
            points: s.points,
          })));
        } else {
          const merged = new Map();
          for (const s of series) {
            for (const [t, v] of s.points) {
              merged.set(t, (merged.get(t) ?? 0) + v);
            }
          }
          results.push({
            label: target.label,
            points: [...merged.entries()].sort((a, b) => a[0] - b[0]),
          });
        }
      }
      return results;
    },
    { deps: [minutes, chart.id] }
  );

  return (
    <Panel
      title={chart.title}
      testid={`health-chart-${chart.id}`}
      action={
        <select
          className="select-input"
          style={{ width: "auto" }}
          value={minutes}
          onChange={(e) => setMinutes(Number(e.target.value))}
          aria-label="Time range"
        >
          <option value={5}>5m</option>
          <option value={15}>15m</option>
          <option value={60}>1h</option>
        </select>
      }
    >
      {loading && <LoadingState text="Loading chart" />}
      {error && (
        <ErrorState
          message={`Prometheus unreachable: ${error}. Start the stack and try again.`}
          onRetry={reload}
        />
      )}
      {!loading && !error && <LineChart series={data} breach={chart.breach} />}
      <div className="chart-note">
        Sourced live from Prometheus. Full dashboards in{" "}
        <a href={GRAFANA_BASE} target="_blank" rel="noreferrer">
          Grafana
        </a>
        .
      </div>
    </Panel>
  );
}

export default function SystemHealth() {
  return (
    <div data-testid="page-health">
      <div className="page-head">
        <h1>System health</h1>
        <p>Serving and agent telemetry, straight from Prometheus.</p>
      </div>
      {CHARTS.map((chart) => (
        <ChartPanel key={chart.id} chart={chart} />
      ))}
    </div>
  );
}
