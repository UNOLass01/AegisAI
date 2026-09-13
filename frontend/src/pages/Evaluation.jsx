import { fetchEvaluation } from "../api.js";
import { useApi } from "../hooks.js";
import {
  Bars,
  EmptyState,
  ErrorState,
  LoadingState,
  Metric,
  Panel,
  StatusTag,
} from "../components/ui.jsx";

export default function Evaluation() {
  const { data, error, loading, reload } = useApi(fetchEvaluation, {});

  return (
    <div data-testid="page-evaluation">
      <div className="page-head">
        <h1>Evaluation</h1>
        <p>How the agent scores across scripted incident scenarios.</p>
      </div>

      {loading && (
        <Panel>
          <LoadingState text="Loading evaluation results" />
        </Panel>
      )}
      {error && (
        <Panel>
          <ErrorState
            message={
              error.includes("404")
                ? "No evaluation results yet — run evaluation/evaluation.py"
                : `Could not load evaluation results: ${error}`
            }
            onRetry={reload}
          />
        </Panel>
      )}
      {!loading && !error && !data && (
        <Panel>
          <EmptyState text="No evaluation results yet — run evaluation/evaluation.py" />
        </Panel>
      )}
      {data && (
        <>
          <Panel title={`Scorecard — ${data.n_scenarios} scenarios`} testid="evaluation-scorecard">
            <div className="metric-row">
              <Metric
                label="Root cause accuracy"
                value={`${Math.round((data.summary.root_cause_accuracy ?? 0) * 100)}%`}
              />
              <Metric
                label="Evidence grounding"
                value={`${Math.round((data.summary.evidence_grounding ?? 0) * 100)}%`}
              />
              <Metric
                label="Tool selection"
                value={`${Math.round((data.summary.tool_selection ?? 0) * 100)}%`}
              />
              <Metric
                label="Report completeness"
                value={`${Math.round((data.summary.report_completeness ?? 0) * 100)}%`}
              />
              <Metric label="Avg latency" value={`${Number(data.summary.avg_latency_s ?? 0).toFixed(1)}s`} />
              <Metric label="Avg tokens" value={`${Math.round(data.summary.avg_tokens ?? 0)}`} />
            </div>
            <p className="small muted">
              Generated <span className="mono">{data.generated_at ?? "—"}</span>
            </p>
          </Panel>

          <Panel title="Per-scenario root cause" testid="evaluation-chart">
            <Bars
              items={(data.scenarios ?? []).map((s) => ({
                label: s.id,
                value: s.root_cause_accuracy,
              }))}
            />
          </Panel>

          <Panel title="Scenarios" testid="evaluation-table">
            <table className="data-table">
              <thead>
                <tr>
                  <th>scenario</th>
                  <th>expected</th>
                  <th>predicted</th>
                  <th>verdict</th>
                  <th>grounding</th>
                  <th>latency</th>
                </tr>
              </thead>
              <tbody>
                {(data.scenarios ?? []).map((s) => (
                  <tr key={s.id} data-testid={`eval-row-${s.id}`}>
                    <td className="mono">{s.id}</td>
                    <td className="mono">{s.expected_root_cause}</td>
                    <td className="mono">{s.predicted_key || "—"}</td>
                    <td>
                      <StatusTag tone={s.root_cause_accuracy >= 1 ? "green" : "rust"}>
                        {s.root_cause_accuracy >= 1 ? "pass" : "fail"}
                      </StatusTag>
                    </td>
                    <td className="mono">{Number(s.evidence_grounding ?? 0).toFixed(2)}</td>
                    <td className="mono">{Number(s.latency_s ?? 0).toFixed(1)}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Panel>
        </>
      )}
    </div>
  );
}
