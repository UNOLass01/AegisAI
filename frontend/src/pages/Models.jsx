import { useState } from "react";
import { fetchModels } from "../api.js";
import { useApi } from "../hooks.js";
import { EmptyState, ErrorState, LoadingState, Panel } from "../components/ui.jsx";

const METRICS = ["accuracy", "precision", "recall", "f1"];

function deltaClass(delta, invert) {
  if (delta === null || delta === undefined || Math.abs(delta) < 1e-9) {
    return "delta-flat";
  }
  const good = invert ? delta < 0 : delta > 0;
  return good ? "delta-up" : "delta-down";
}

function Trend({ current, previous, invert = false }) {
  if (previous === null || previous === undefined) {
    return <span className="muted">—</span>;
  }
  const delta = current - previous;
  if (Math.abs(delta) < 1e-9) {
    return <span className="delta-flat">=</span>;
  }
  const up = delta > 0;
  const cls = deltaClass(delta, invert);
  return (
    <span className={cls} title={`delta ${delta >= 0 ? "+" : ""}${delta.toFixed(4)}`}>
      {up ? "▲" : "▼"}
    </span>
  );
}

export default function Models() {
  const { data, error, loading, reload } = useApi(fetchModels, {});
  const [open, setOpen] = useState(null);

  const models = [...(data?.models ?? [])].sort((a, b) =>
    String(a.model_version).localeCompare(String(b.model_version))
  );
  const byVersion = Object.fromEntries(models.map((m) => [m.model_version, m]));

  return (
    <div data-testid="page-models">
      <div className="page-head">
        <h1>Models</h1>
        <p>Versioned fraud models with offline metrics. Select a row for the full report and deltas.</p>
      </div>

      <Panel testid="models-list">
        {loading && <LoadingState text="Loading models" />}
        {error && <ErrorState message={`Could not load models: ${error}`} onRetry={reload} />}
        {data && models.length === 0 && <EmptyState text="No model versions found" />}
        {data && models.length > 0 && (
          <div className="row-list">
            {models.map((model) => {
              const metrics = model.metrics ?? {};
              const versions = Object.keys(byVersion).sort();
              const prev = byVersion[versions[versions.indexOf(model.model_version) - 1]];
              const expanded = open === model.model_version;
              return (
                <div key={model.model_version}>
                  <div
                    className="row clickable"
                    onClick={() => setOpen(expanded ? null : model.model_version)}
                    data-testid={`model-row-${model.model_version}`}
                  >
                    <span className="mono" style={{ fontWeight: 500 }}>{model.model_version}</span>
                    {METRICS.map((name) => (
                      <span key={name} className="small">
                        <span className="muted">{name.slice(0, 4)} </span>
                        <span className="mono">
                          {metrics[name] === undefined ? "—" : Number(metrics[name]).toFixed(3)}
                        </span>{" "}
                        <Trend current={metrics[name]} previous={prev?.metrics?.[name]} />
                      </span>
                    ))}
                    <span className="grow" />
                    <span className="muted small mono">
                      {metrics.timestamp ? new Date(metrics.timestamp).toLocaleString() : ""}
                    </span>
                  </div>
                  {expanded && (
                    <div style={{ padding: "4px 4px 14px 4px" }} data-testid={`model-detail-${model.model_version}`}>
                      <dl className="kv">
                        <dt>dataset</dt>
                        <dd>{metrics.dataset_version ?? "—"}</dd>
                        <dt>true / false positives</dt>
                        <dd>{metrics.true_positives ?? "—"} / {metrics.false_positives ?? "—"}</dd>
                        <dt>true / false negatives</dt>
                        <dd>{metrics.true_negatives ?? "—"} / {metrics.false_negatives ?? "—"}</dd>
                        <dt>artifact</dt>
                        <dd>{model.artifact_present ? "present" : "missing"}</dd>
                      </dl>
                      {prev ? (
                        <table className="data-table" style={{ marginTop: 10 }}>
                          <thead>
                            <tr>
                              <th>metric</th>
                              <th>{prev.model_version}</th>
                              <th>{model.model_version}</th>
                              <th>delta</th>
                            </tr>
                          </thead>
                          <tbody>
                            {[...METRICS, "false_positives", "false_negatives"].map((name) => {
                              const a = prev.metrics?.[name];
                              const b = metrics[name];
                              const delta = a === undefined || b === undefined ? null : b - a;
                              const invert = name.startsWith("false_");
                              return (
                                <tr key={name}>
                                  <td className="mono">{name}</td>
                                  <td className="mono">{a === undefined ? "—" : Number(a).toFixed(4)}</td>
                                  <td className="mono">{b === undefined ? "—" : Number(b).toFixed(4)}</td>
                                  <td className={`mono ${delta === null ? "" : deltaClass(delta, invert)}`}>
                                    {delta === null ? "—" : `${delta >= 0 ? "+" : ""}${delta.toFixed(4)}`}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      ) : (
                        <p className="small muted">First version — nothing to compare.</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}
