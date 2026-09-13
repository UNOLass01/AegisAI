import { useState } from "react";
import { fetchIncident, fetchIncidents } from "../api.js";
import { useApi } from "../hooks.js";
import { Markdown } from "../components/markdown.jsx";
import { EmptyState, ErrorState, LoadingState, Panel, StatusTag } from "../components/ui.jsx";

function statusTone(status) {
  return status === "resolved" ? "green" : "rust";
}

export default function Incidents() {
  const { data, error, loading, reload } = useApi(fetchIncidents, {});
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const open = async (id) => {
    setSelected(id);
    setDetailLoading(true);
    setDetailError(null);
    try {
      setDetail(await fetchIncident(id));
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : String(err));
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div data-testid="page-incidents">
      <div className="page-head">
        <h1>Incidents</h1>
        <p>Past incident write-ups from the knowledge base.</p>
      </div>

      {!selected && (
        <Panel testid="incidents-list">
          {loading && <LoadingState text="Loading incidents" />}
          {error && <ErrorState message={`Could not load incidents: ${error}`} onRetry={reload} />}
          {data && data.length === 0 && <EmptyState text="No incident write-ups yet" />}
          {data && data.length > 0 && (
            <div className="row-list">
              {data.map((row) => (
                <div
                  key={row.id}
                  className="row clickable"
                  onClick={() => open(row.id)}
                  data-testid={`incident-row-${row.id}`}
                >
                  <span className="mono">#{row.id}</span>
                  <div className="grow">
                    <div className="title">{row.title}</div>
                    <div className="sub">
                      affects <span className="mono">{row.affected_feature ?? "—"}</span>
                    </div>
                  </div>
                  <StatusTag tone={statusTone(row.status)}>{row.status}</StatusTag>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}

      {selected && (
        <Panel testid="incident-detail">
          <button className="back-link" onClick={() => setSelected(null)} type="button">
            Back to incidents
          </button>
          {detailLoading && <LoadingState text="Loading write-up" />}
          {detailError && <ErrorState message={detailError} onRetry={() => open(selected)} />}
          {detail && (
            <>
              <h2>
                <span className="mono">#{detail.id}</span> {detail.title.replace(/^Incident #\d+:\s*/, "")}
              </h2>
              <p>
                <StatusTag tone={statusTone(detail.status)}>{detail.status}</StatusTag>{" "}
                <span className="small muted">
                  affects <span className="mono">{detail.affected_feature ?? "—"}</span>
                </span>
              </p>
              <Markdown text={detail.markdown} />
            </>
          )}
        </Panel>
      )}
    </div>
  );
}
