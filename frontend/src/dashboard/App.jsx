import { useState } from "react";
import Evaluation from "../pages/Evaluation.jsx";
import Incidents from "../pages/Incidents.jsx";
import Investigations from "../pages/Investigations.jsx";
import Models from "../pages/Models.jsx";
import Overview from "../pages/Overview.jsx";
import SystemHealth from "../pages/SystemHealth.jsx";

const PAGES = [
  { id: "overview", label: "Overview", glyph: "◉", component: Overview },
  { id: "models", label: "Models", glyph: "▦", component: Models },
  { id: "incidents", label: "Incidents", glyph: "▤", component: Incidents },
  { id: "investigations", label: "Investigations", glyph: "◈", component: Investigations },
  { id: "evaluation", label: "Evaluation", glyph: "▥", component: Evaluation },
  { id: "health", label: "System health", glyph: "〜", component: SystemHealth },
];

export default function App() {
  const [page, setPage] = useState("overview");
  const active = PAGES.find((p) => p.id === page) ?? PAGES[0];
  const ActiveComponent = active.component;

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">AegisAI</div>
        <div className="brand-sub">ML incident console</div>
        <nav aria-label="Primary">
          {PAGES.map((entry) => (
            <button
              key={entry.id}
              className={entry.id === page ? "active" : ""}
              onClick={() => setPage(entry.id)}
              type="button"
              data-testid={`nav-${entry.id}`}
            >
              <span className="glyph" aria-hidden="true">
                {entry.glyph}
              </span>
              {entry.label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="content">
        <ActiveComponent />
      </main>
    </div>
  );
}
