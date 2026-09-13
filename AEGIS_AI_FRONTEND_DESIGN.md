# AegisAI — Frontend Design Spec

Hand this to the coding agent alongside `AEGIS_AI_AGENT_PLAN.md` (Phase 8 / Frontend Polish).
Concept: **"instrument panel meets case file"** — an evidence trail, not a chat transcript.

## Design tokens

```css
--bg-page:        #EDEEEA;  /* cool paper grey, not warm cream */
--bg-panel:       #FFFFFF;
--border:         #D8D9D3;  /* hairline, 1px */
--ink:            #1B2430;  /* primary text — deep blue-black, not pure black */
--ink-secondary:  #5B6472;  /* muted text */

--rust:           #A8461D;  /* anomaly / alert / unhealthy — reserved, never decorative */
--rust-bg:        #F3E3DA;
--rust-border:    #E3C7B4;
--rust-text-on-bg:#5C2C15;

--evidence-green: #3A6B52;  /* healthy / confirmed / resolved */
--green-bg:       #E1EAE4;

--instrument-blue:#2F5D8A;  /* data accents, charts, trace timing */
--blue-bg:        #E3EBF2;

--font-ui:   'IBM Plex Sans', sans-serif;   /* all UI chrome, labels, prose */
--font-data: 'IBM Plex Mono', monospace;    /* ONLY for numbers, IDs, timestamps, versions, code tokens — never decorative */
```

**Rule:** rust only appears on genuinely anomalous/degraded values. If everything is rust, nothing is. Mono font is reserved for data readouts — using it for headings or labels is a violation of the concept, not a style choice.

## Layout shell

Fixed left rail (icon + label nav): Overview, Models, Incidents, Investigations, Evaluation, System health.
Main content area: full-bleed panels on `--bg-page`, not a centered card grid. Panels are `--bg-panel` with 1px `--border`, 8px radius — asymmetric sizing per page, not a uniform card kit.

## Page-by-page spec

### Overview
- Top row: 4 metric readouts (request rate, error rate, active model version, avg agent latency) — mono numbers, sans labels above in `--ink-secondary`.
- Below: a compact timeline strip of the last 5–10 investigations (status dot + one-line query + timestamp), and a small system-health sparkline panel.

### Models
- One row per model version (v1, v2, v3…): version (mono), accuracy/precision/recall as mono numbers, a small inline trend arrow, deploy timestamp.
- Selecting a row expands to show the linked evaluation report JSON fields and a "compare to previous version" delta view — deltas in rust if degraded, green if improved.

### Incidents (knowledge base)
- List of past incidents as compact rows, not cards: incident id (mono), one-line title, affected feature, resolution status tag (rust = open, green = resolved).
- Detail view shows the full markdown doc from `knowledge/incidents/`.

### Investigations (the centerpiece — see mockup above)
- Query input at top (plain text field, "Ask about a system issue…" placeholder).
- Detail view: two-column — left is the evidence timeline (connected vertical line, one dot per tool call: metrics / logs / model / knowledge), right is confidence gauge + root cause + recommended actions.
- Full-width trace strip at the bottom: one pill per step with its duration (mono), plus total tokens and total time.
- List view (before opening a specific investigation): rows of past queries, root cause, confidence, timestamp.

### Evaluation
- Scorecard: 4–6 metric readouts (root cause accuracy, evidence grounding, tool selection accuracy, report completeness, avg latency, avg tokens) as large mono numbers with sans labels — same visual language as Overview's metric row for consistency.
- Below: a simple bar or line chart of scores per scenario, and a table of the 15–20 scenarios with pass/fail and expected-vs-actual root cause.

### System health
- Prometheus/Grafana-sourced charts embedded or proxied: request latency (p50/p95), error rate, token usage over time, cost over time.
- Reuse the instrument-blue accent for all chart lines; rust only for threshold breaches.

## Component rules

- **Confidence gauge**: SVG arc, 0–1 scale, colored by band (rust if <0.5, amber-adjacent neutral if 0.5–0.75, green if ≥0.75) — not a flat progress bar.
- **Evidence timeline**: vertical connector line + dot per step, because investigations genuinely are a sequence — this is the one place a numbered/sequential treatment is justified in the whole app.
- **Trace strip**: horizontal row of pills, one per agent step, mono duration inside each, colored by step type (blue = tool call, green = reasoning/synthesis).
- **Status/severity color**: rust = anomalous/needs attention, green = healthy/resolved, blue = neutral/informational. Never use rust for anything that isn't actually a problem.
- No rounded-card-grid treatment anywhere — rows and panels, not uniform cards.
- No ALL-CAPS labels, no middle-dot metadata strings, no "→" appended to buttons/links.
- Buttons: plain, sentence case, verb-first ("Run investigation", not "Submit").
- Empty states are invitations, not apologies ("No investigations yet — ask a question above" not "Nothing here").

## Typography scale

- Page/section headings: 16–18px, weight 500, `--font-ui`.
- Body/prose: 13–14px, weight 400, `--font-ui`, line-height 1.5.
- Data readouts (metrics, IDs, versions, timestamps, durations): `--font-data`, weight 400–500, sized to context (22–24px for hero metrics, 12–13px inline).
- No serif anywhere — this is a technical console, not an editorial surface.
