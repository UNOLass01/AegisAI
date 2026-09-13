export function Panel({ title, action, children, testid }) {
  return (
    <section className="panel" data-testid={testid}>
      {(title || action) && (
        <div style={{ display: "flex", alignItems: "center", marginBottom: 12 }}>
          {title && <h2 className="panel-title" style={{ margin: 0 }}>{title}</h2>}
          {action && <div style={{ marginLeft: "auto" }}>{action}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Metric({ label, value, unit, tone }) {
  const color =
    tone === "rust" ? "var(--rust)" : tone === "green" ? "var(--evidence-green)" : undefined;
  return (
    <div className="metric">
      <div className="label">{label}</div>
      <div className="value" style={color ? { color } : undefined}>
        {value}
        {unit && <span className="unit"> {unit}</span>}
      </div>
    </div>
  );
}

function gaugeColor(confidence) {
  if (confidence < 0.5) {
    return "var(--rust)";
  }
  if (confidence < 0.75) {
    return "var(--amber)";
  }
  return "var(--evidence-green)";
}

/** SVG arc gauge for confidence (0-1), never a flat progress bar. */
export function Gauge({ value, testid }) {
  const clamped = Math.max(0, Math.min(1, Number(value) || 0));
  const angle = Math.PI * (1 - clamped);
  const cx = 60;
  const cy = 58;
  const r = 46;
  const x = cx + r * Math.cos(angle);
  const y = cy - r * Math.sin(angle);
  const color = gaugeColor(clamped);
  return (
    <svg width="120" height="70" viewBox="0 0 120 70" data-testid={testid} role="img"
      aria-label={`confidence ${clamped.toFixed(2)}`}>
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none"
        stroke="var(--border)" strokeWidth="10" strokeLinecap="round" />
      <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${x} ${y}`} fill="none"
        stroke={color} strokeWidth="10" strokeLinecap="round" />
      <text x={cx} y={cy - 2} textAnchor="middle" fontSize="17"
        fontFamily="var(--font-data)" fill="var(--ink)">
        {clamped.toFixed(2)}
      </text>
    </svg>
  );
}

/** Minimal sparkline from a numeric series. */
export function Sparkline({ points, width = 220, height = 44, testid }) {
  const values = (points ?? []).filter((v) => Number.isFinite(v));
  if (values.length < 2) {
    return <span className="muted small">not enough data yet</span>;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const coords = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - 4) + 2;
    const y = height - 4 - ((v - min) / span) * (height - 8);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg width={width} height={height} data-testid={testid} role="img" aria-label="trend">
      <polyline points={coords.join(" ")} fill="none" stroke="var(--instrument-blue)"
        strokeWidth="2" />
    </svg>
  );
}

/** Simple vertical bars for per-scenario pass/fail. */
export function Bars({ items, testid }) {
  if (!items || items.length === 0) {
    return <span className="muted small">no data</span>;
  }
  const width = Math.max(items.length * 26, 120);
  const height = 90;
  return (
    <svg width={width} height={height} data-testid={testid} role="img" aria-label="scores">
      {items.map((item, i) => {
        const h = Math.max(4, item.value * (height - 22));
        const x = i * 26 + 6;
        const passed = item.value >= 1;
        return (
          <g key={item.label}>
            <rect x={x} y={height - 18 - h} width={14} height={h} rx={2}
              fill={passed ? "var(--evidence-green)" : "var(--rust)"}>
              <title>{`${item.label}: ${item.value}`}</title>
            </rect>
            <text x={x + 7} y={height - 4} textAnchor="middle" fontSize="8"
              fill="var(--ink-secondary)">
              {item.label.replace(/^[a-z]+-0?/, "")}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Multi-series line chart over [timestampMs, value] points. */
export function LineChart({ series, height = 150, testid, breach = null }) {
  const usable = (series ?? []).filter((s) => s.points && s.points.length >= 2);
  if (usable.length === 0) {
    return <span className="muted small">no data in range</span>;
  }
  const width = 560;
  const allT = usable.flatMap((s) => s.points.map(([t]) => t));
  const allV = usable.flatMap((s) => s.points.map(([, v]) => v));
  const t0 = Math.min(...allT);
  const t1 = Math.max(...allT);
  const v0 = Math.min(...allV);
  const v1 = Math.max(...allV);
  const spanV = v1 - v0 || 1;
  const palette = ["var(--instrument-blue)", "var(--evidence-green)", "var(--amber)"];
  const project = ([t, v]) => [
    34 + ((t - t0) / Math.max(t1 - t0, 1)) * (width - 44),
    height - 20 - ((v - v0) / spanV) * (height - 30),
  ];
  return (
    <div data-testid={testid}>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="chart">
        {usable.map((s, i) => {
          const color =
            breach && s.label === breach.label && Math.max(...s.points.map(([, v]) => v)) > breach.over
              ? "var(--rust)"
              : palette[i % palette.length];
          const d = s.points.map((p, j) => `${j === 0 ? "M" : "L"}${project(p).map((n) => n.toFixed(1)).join(" ")}`).join(" ");
          return <path key={s.label} d={d} fill="none" stroke={color} strokeWidth="2" />;
        })}
        <text x={2} y={12} fontSize={9} fill="var(--ink-secondary)">
          {v1.toFixed(3)}
        </text>
        <text x={2} y={height - 6} fontSize={9} fill="var(--ink-secondary)">
          {v0.toFixed(3)}
        </text>
      </svg>
      <div className="small">
        {usable.map((s, i) => (
          <span key={s.label} style={{ marginRight: 14 }}>
            <span className="dot" style={{ background: palette[i % palette.length] }} />{" "}
            <span className="mono" style={{ fontSize: 12 }}>{s.label}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

export function StatusTag({ tone, children }) {
  return <span className={`tag ${tone}`}>{children}</span>;
}

export function LoadingState({ text = "Loading" }) {
  return (
    <div className="state-box">
      <span className="spinner" /> {text}
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="state-box error" data-testid="error-state">
      <div>{message || "Something failed to load."}</div>
      {onRetry && (
        <button className="btn secondary" style={{ marginTop: 10 }} onClick={onRetry} type="button">
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ text }) {
  return <div className="state-box">{text}</div>;
}
