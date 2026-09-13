import { useEffect, useState } from "react";
import {
  fetchInvestigation,
  fetchInvestigations,
  fetchTrace,
  runInvestigation,
} from "../api.js";
import { formatTime } from "../hooks.js";
import { EvidenceTimeline, TraceStrip } from "../components/evidence.jsx";
import {
  EmptyState,
  ErrorState,
  Gauge,
  LoadingState,
  Panel,
  StatusTag,
} from "../components/ui.jsx";

function useAsyncAction() {
  const [state, setState] = useState({ loading: false, error: null });
  const run = async (fn) => {
    setState({ loading: true, error: null });
    try {
      const result = await fn();
      setState({ loading: false, error: null });
      return result;
    } catch (err) {
      setState({ loading: false, error: err instanceof Error ? err.message : String(err) });
      return null;
    }
  };
  return [state, run];
}

function InvestigationDetail({ report, trace, onBack }) {
  return (
    <div data-testid="investigation-detail">
      {onBack && (
        <button className="back-link" onClick={onBack} type="button">
          Back to investigations
        </button>
      )}
      <div className="two-col">
        <Panel title="Evidence trail">
          <EvidenceTimeline evidence={report.evidence} />
        </Panel>
        <div>
          <Panel title="Verdict">
            <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 12 }}>
              <Gauge value={report.confidence} testid="confidence-gauge" />
              <div>
                <div className="small muted">confidence</div>
                <div className="mono">{Number(report.confidence).toFixed(2)}</div>
                <div style={{ marginTop: 6 }}>
                  <StatusTag tone={report.status === "complete" ? "green" : "rust"}>
                    {report.status}
                  </StatusTag>
                </div>
              </div>
            </div>
            <h3>Root cause</h3>
            <p data-testid="root-cause">{report.root_cause_hypothesis}</p>
            <h3>Summary</h3>
            <p className="small">{report.finding_summary}</p>
            <h3>Recommended actions</h3>
            <ul className="action-list" data-testid="recommended-actions">
              {report.recommended_actions.map((action, i) => (
                <li key={i}>{action}</li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
      <Panel title="Agent trace">
        <TraceStrip spans={trace} />
      </Panel>
    </div>
  );
}

export default function Investigations() {
  const [query, setQuery] = useState("");
  const [list, setList] = useState(null);
  const [listError, setListError] = useState(null);
  const [listLoading, setListLoading] = useState(true);
  const [detail, setDetail] = useState(null);
  const [trace, setTrace] = useState([]);
  const [running, runQuery] = useAsyncAction();
  const [opening, openId] = useAsyncAction();

  const refreshList = async () => {
    setListLoading(true);
    setListError(null);
    try {
      setList(await fetchInvestigations(20));
    } catch (err) {
      setListError(err instanceof Error ? err.message : String(err));
    } finally {
      setListLoading(false);
    }
  };

  useEffect(() => {
    refreshList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (event) => {
    event.preventDefault();
    if (!query.trim() || running.loading) {
      return;
    }
    const report = await runQuery(() => runInvestigation(query.trim()));
    if (!report) {
      return;
    }
    let spans = [];
    try {
      const traceBody = await fetchTrace(report.investigation_id);
      spans = traceBody.spans ?? [];
    } catch {
      spans = [];
    }
    setDetail(report);
    setTrace(spans);
    setQuery("");
    refreshList();
  };

  const open = async (id) => {
    const body = await openId(() => fetchInvestigation(id));
    if (body) {
      setDetail(body.report ?? body);
      setTrace(body.trace ?? []);
    }
  };

  return (
    <div data-testid="page-investigations">
      <div className="page-head">
        <h1>Investigations</h1>
        <p>Ask about a system issue — the agent gathers evidence and reports back.</p>
      </div>

      {!detail && (
        <>
          <Panel testid="investigation-form">
            <form className="query-bar" onSubmit={submit}>
              <input
                className="text-input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask about a system issue…"
                aria-label="Investigation query"
                data-testid="investigation-input"
              />
              <button
                className="btn"
                type="submit"
                disabled={running.loading || !query.trim()}
                data-testid="investigation-submit"
              >
                {running.loading ? "Running investigation…" : "Run investigation"}
              </button>
            </form>
            {running.loading && (
              <p className="small muted" style={{ marginTop: 8 }}>
                <span className="spinner" /> Gathering metrics, logs, model and knowledge evidence…
              </p>
            )}
            {running.error && (
              <div style={{ marginTop: 8 }}>
                <ErrorState message={running.error} />
              </div>
            )}
          </Panel>

          <Panel title="Past investigations" testid="investigations-list">
            {listLoading && <LoadingState text="Loading investigations" />}
            {listError && <ErrorState message={listError} />}
            {list && list.length === 0 && !listLoading && (
              <EmptyState text="No investigations yet — ask a question above" />
            )}
            {list && list.length > 0 && (
              <div className="row-list">
                {list.map((row) => (
                  <div
                    key={row.id}
                    className="row clickable"
                    onClick={() => open(row.id)}
                    data-testid={`investigation-row-${row.id}`}
                  >
                    <span className={`dot ${row.status === "complete" ? "green" : "rust"}`} />
                    <div className="grow">
                      <div className="title">{row.query}</div>
                      <div className="sub">{(row.root_cause ?? "").slice(0, 90)}</div>
                    </div>
                    <span className="mono small">{Number(row.confidence ?? 0).toFixed(2)}</span>
                    <span className="muted small mono">{formatTime(row.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
            {opening.loading && <LoadingState text="Opening investigation" />}
            {opening.error && <ErrorState message={opening.error} />}
          </Panel>
        </>
      )}

      {detail && (
        <InvestigationDetail
          report={detail}
          trace={trace}
          onBack={() => {
            setDetail(null);
            setTrace([]);
          }}
        />
      )}
    </div>
  );
}
