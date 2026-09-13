const TOOL_LABELS = {
  get_metrics: "metrics",
  analyze_logs: "logs",
  analyze_model: "model",
  search_knowledge: "knowledge",
};

/** Vertical evidence timeline: one dot per evidence item on a connector line. */
export function EvidenceTimeline({ evidence }) {
  if (!evidence || evidence.length === 0) {
    return <span className="muted small">no evidence recorded</span>;
  }
  return (
    <div className="evidence-timeline" data-testid="evidence-timeline">
      {evidence.map((item, i) => (
        <div className="ev-step" key={i}>
          <span className="ev-dot" />
          <div className="ev-tool">{TOOL_LABELS[item.tool] ?? item.tool}</div>
          <div className="ev-summary">{item.summary}</div>
          {item.source && <div className="ev-source">{item.source}</div>}
        </div>
      ))}
    </div>
  );
}

const STEP_KIND = {
  investigate: "synthesis",
  reason: "synthesis",
  generate_report: "synthesis",
};

/** Horizontal pill strip: one pill per agent step with mono duration. */
export function TraceStrip({ spans }) {
  if (!spans || spans.length === 0) {
    return <span className="muted small">no trace recorded</span>;
  }
  const totalMs = spans.reduce((sum, s) => sum + (Number(s.duration_ms) || 0), 0);
  const totalTokens = spans.reduce((sum, s) => sum + (Number(s.tokens) || 0), 0);
  return (
    <div className="trace-strip" data-testid="trace-strip">
      {spans.map((span, i) => (
        <span
          key={i}
          className={`trace-pill ${STEP_KIND[span.step] ? "synthesis" : ""}`}
          title={`${span.step}: ${span.timestamp ?? ""}`}
        >
          {span.step} <span className="dur">{Number(span.duration_ms).toFixed(1)}ms</span>
        </span>
      ))}
      <span className="trace-totals">
        {totalTokens} tokens · {totalMs.toFixed(0)}ms total
      </span>
    </div>
  );
}
