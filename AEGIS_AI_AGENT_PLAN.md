# AegisAI — Coding Agent Execution Plan

> Feed each phase section below to your coding agent (Claude Code, Cursor, etc.) as its own task/prompt.
> Do NOT paste the whole file at once — work phase by phase, verify the deliverable, commit, then move to the next.
> Always end a phase with: `git add -A && git commit -m "Phase X: <summary>"`.

---

## Phase 0 — Repo Bootstrap (do this yourself, 15 min)

```bash
mkdir aegis-ai && cd aegis-ai
git init
mkdir -p backend/app/{api,agents,tools,rag,services,models} backend/tests
mkdir -p ml/{data/raw,data/processed,training,evaluation,models}
mkdir -p frontend/src/{dashboard,investigations,components}
mkdir -p evaluation/{datasets,scenarios}
mkdir -p monitoring/{prometheus,grafana}
mkdir -p knowledge/{incidents,documentation,experiments}
mkdir -p .github/workflows
touch README.md Makefile docker-compose.yml
```

---

## Phase 1 (Days 1–2) — Foundation

**Prompt for the agent:**

> Set up the base scaffolding for a project called AegisAI. Requirements:
> - FastAPI backend in `backend/app` with a health-check endpoint (`GET /health`), a `main.py` entrypoint, and clean separation of `api/`, `services/`, `models/` modules.
> - PostgreSQL as the primary database, using SQLAlchemy + Alembic for migrations. Create one initial table: `investigations` (id, created_at, query, status, root_cause, confidence, report_json).
> - A minimal React (Vite) frontend in `frontend/` with a single dashboard page that calls `GET /health` and displays status.
> - A `docker-compose.yml` that spins up: `backend`, `frontend`, `postgres`. Everything must work with a single `docker compose up`.
> - A `Makefile` with targets: `up`, `down`, `logs`, `test`, `migrate`.
> - A GitHub Actions workflow (`.github/workflows/ci.yml`) that installs deps and runs backend tests on push.
>
> Deliverable: `docker compose up` boots all services and the frontend shows a green "backend healthy" indicator.

**Acceptance check:** `docker compose up` → visit frontend → see healthy status. `make test` passes (even if just one trivial test).

---

## Phase 2 (Days 3–4) — ML Pipeline

**Prompt for the agent:**

> Build a small, realistic ML pipeline under `ml/` for **fraud/anomaly detection** (or API-latency anomaly detection — pick one and keep it consistent through later phases). Requirements:
> - `ml/training/train.py`: loads/generates a synthetic tabular dataset (e.g. transactions with `transaction_amount`, `merchant_category`, `hour_of_day`, `is_fraud`), trains an XGBoost or scikit-learn classifier, saves the model to `ml/models/model_<version>.pkl`.
> - `ml/evaluation/evaluate.py`: computes accuracy, precision, recall, F1 on a held-out set; writes a JSON report like:
>   ```json
>   {"model_version": "v1", "accuracy": 0.94, "precision": 0.91, "recall": 0.89, "timestamp": "...", "dataset_version": "..."}
>   ```
> - `ml/training/predict.py`: loads a given model version and serves predictions.
> - Generate **three deliberately different model versions**:
>   - `v1`: normal, healthy performance.
>   - `v2`: trained on a dataset with `transaction_amount` distribution shifted (+30%), causing a measurable rise in false positives.
>   - `v3`: trained with an injected labeling error causing degraded recall.
> - Add a FastAPI route `POST /predict` and `GET /models` (lists versions + their metrics) that read from `ml/models/`.
> - Store all metric reports under `ml/evaluation/reports/model_<version>.json`.
>
> Deliverable: running `python ml/training/train.py --version v2` (etc.) reproducibly creates a new model + metrics report, and the backend can serve predictions from any version.

**Acceptance check:** Three model versions exist with visibly different precision/recall. `/models` endpoint returns all three with metrics.

---

## Phase 3 (Days 5–6) — Monitoring & Simulated Incidents

**Prompt for the agent:**

> Add observability infrastructure and simulate production incidents. Requirements:
> - Add Prometheus + Grafana services to `docker-compose.yml`.
> - Instrument the FastAPI backend with `prometheus_fastapi_instrumentator` (or manual `prometheus_client` metrics) tracking: request count, request latency, `/predict` latency, error rate.
> - Add a small script `monitoring/simulate_incident.py` that replays traffic against `/predict` using v1, then switches to v2, producing a visible latency/precision anomaly in Grafana.
> - Add structured JSON logging (`backend/app/services/logger.py`) so logs can later be parsed by a "log analyzer" tool. Logs should include: timestamp, level, endpoint, model_version, latency_ms, status_code.
> - Provide a starter Grafana dashboard JSON under `monitoring/grafana/dashboards/aegis-overview.json` with panels for request rate, latency (p50/p95), error rate, and model version in use.
>
> Deliverable: `docker compose up` includes Prometheus scraping the backend and Grafana showing live panels. Running the incident simulator visibly changes the dashboards.

**Acceptance check:** Grafana at `localhost:3000` shows request/latency panels updating in real time during the simulation script.

---

## Phase 4 (Days 7–8) — Knowledge Base & RAG

**Prompt for the agent:**

> Build the retrieval layer under `backend/app/rag/` and populate `knowledge/`. Requirements:
> - Populate `knowledge/documentation/` (model card per version, deployment config), `knowledge/incidents/` (2–3 past incident write-ups, e.g. "Incident #011: transaction_amount drift caused FP spike"), and `knowledge/experiments/` (short notes on each model version's training changes).
> - Build an ingestion script `backend/app/rag/ingest.py`: chunks these markdown files, embeds them (use a local sentence-transformers model or an embedding API — make it configurable via `EMBEDDING_PROVIDER`), and stores vectors in Qdrant or Chroma (add the chosen one to `docker-compose.yml`).
> - Build `backend/app/rag/retriever.py` exposing a `search(query: str, k: int) -> list[Chunk]` function with source metadata (filename, incident id).
> - Add a FastAPI route `POST /knowledge/search` for manual testing.
>
> Deliverable: querying "why did precision drop" returns the relevant incident #011 document via `/knowledge/search`.

**Acceptance check:** Ingestion script populates the vector DB; a manual query returns correctly ranked, relevant chunks with source attribution.

---

## Phase 5 (Days 9–10) — The Investigation Agent (core of the project)

**Prompt for the agent:**

> Build a single orchestrated agent (use LangGraph) under `backend/app/agents/investigation_agent.py`. This is the centerpiece — keep it to **one agent with multiple tools**, not multiple agents. Requirements:
> - Tools, each a thin wrapper in `backend/app/tools/`:
>   - `get_metrics(model_version=None, time_range=None)` — queries Prometheus for latency/error-rate/precision-proxy metrics.
>   - `analyze_logs(time_range=None)` — parses structured JSON logs for anomalies (error spikes, latency spikes).
>   - `analyze_model(version)` — reads the ML evaluation report(s), computes deltas vs. prior version.
>   - `search_knowledge(query)` — calls the RAG retriever from Phase 4.
>   - `generate_report(findings)` — composes the final structured incident report.
> - The agent graph: `investigate → {metrics, logs, model, knowledge in parallel or sequence} → reason → generate_report`.
> - LLM provider must be configurable via `LLM_PROVIDER` / `LLM_MODEL` env vars (support at least OpenAI-compatible API + a local/Ollama option as a stub).
> - Output schema (Pydantic model) for the final report:
>   ```python
>   class IncidentReport(BaseModel):
>       investigation_id: str
>       status: str
>       finding_summary: str
>       evidence: list[EvidenceItem]
>       root_cause_hypothesis: str
>       confidence: float
>       recommended_actions: list[str]
>   ```
> - Add `POST /investigate` endpoint: accepts a natural-language query (e.g. "Why did fraud detection degrade after v2?"), runs the agent, persists the `IncidentReport` to the `investigations` table, returns it.
>
> Deliverable: `POST /investigate {"query": "Why did fraud detection performance degrade after deployment v2?"}` returns a grounded report citing metrics deltas, log findings, and the matching past incident from the knowledge base.

**Acceptance check:** The agent's output correctly identifies data drift as root cause for the v2 scenario, with evidence from at least 2 different tools plus one knowledge-base citation.

---

## Phase 6 (Day 11) — Evaluation Harness

**Prompt for the agent:**

> Build an evaluation system under `evaluation/`. Requirements:
> - `evaluation/scenarios/`: 15–20 YAML/JSON scenario definitions, each with `problem`, `injected_condition`, `expected_root_cause`, `expected_tools_used`.
> - `evaluation/evaluation.py`: runs the investigation agent against every scenario and scores:
>   - **Root-cause accuracy** (does hypothesis match expected root cause, via keyword or embedding similarity match)
>   - **Tool selection accuracy** (were the expected tools invoked)
>   - **Evidence grounding** (does every claim in the report trace back to a tool result or retrieved doc — flag ungrounded claims)
>   - **Report completeness** (are all required fields populated non-trivially)
>   - **Latency** and **token usage** per run (from LLM API response metadata)
> - Output a summary report (`evaluation/results/latest.json` + printed table) like:
>   ```
>   Root cause accuracy       85%
>   Evidence grounding        92%
>   Tool selection            90%
>   Report completeness       88%
>   Avg latency               4.8s
>   Avg tokens                2,140
>   ```
> - Add `GET /evaluation/latest` endpoint so the frontend can display these numbers.
>
> Deliverable: `python evaluation/evaluation.py` runs all scenarios end-to-end and produces the summary above.

**Acceptance check:** All 15–20 scenarios execute without crashing; summary scores are computed and persisted.

---

## Phase 7 (Day 12) — Full Observability / Tracing

**Prompt for the agent:**

> Extend observability to cover the agent itself, not just the API. Requirements:
> - Add per-step tracing to the LangGraph agent (each tool call and LLM call as a span) — use OpenTelemetry or a lightweight custom tracer that logs: step name, duration, tokens in/out, cost estimate.
> - Persist traces to Postgres (`agent_traces` table: investigation_id, step, duration_ms, tokens, cost_usd, timestamp) or export to Grafana via Prometheus metrics (`agent_step_duration_seconds`, `agent_tokens_total`, `agent_cost_usd_total`).
> - Add a Grafana panel/dashboard section for agent-specific metrics: LLM latency, tool latency breakdown, token usage over time, cost over time.
> - Add `GET /investigations/{id}/trace` endpoint returning the full step-by-step trace for one investigation.
>
> Deliverable: after running `/investigate`, both Grafana and `/investigations/{id}/trace` show a clear step-by-step timeline of what the agent did, how long each step took, and its token/cost cost.

**Acceptance check:** A single investigation's trace clearly shows tool calls in order with timings and token counts.

---

## Phase 8 (Day 13) — Frontend Polish

**Prompt for the agent:**

> Build out the React dashboard with the following pages, each backed by the endpoints already built:
> - **Overview**: system health, request rate, error rate, active model version.
> - **Models**: list of model versions with their metrics (accuracy/precision/recall), trend indicators.
> - **Incidents**: list of past incidents from the knowledge base.
> - **Agent Investigations**: form to submit a new query, list of past investigations, detail view rendering the structured `IncidentReport` (evidence, root cause, confidence, recommended actions) and its trace timeline.
> - **Evaluation**: renders the latest evaluation summary as a scorecard + simple chart.
> - **System Health**: Prometheus/Grafana-sourced or backend-proxied metrics (latency, error rate charts).
>
> Use a clean, non-templated visual style (bias toward information density and clarity over decoration — this is a technical/ops tool, not a marketing page). Reuse a shared API client module; handle loading/error states everywhere.
>
> Deliverable: a coherent, navigable multi-page dashboard that lets a reviewer go from "submit a question" to "see the full grounded incident report" without touching the API directly.

**Acceptance check:** Every page loads real data from the backend with no console errors; submitting an investigation from the UI shows a live result.

---

## Phase 9 (Day 14) — Portfolio Packaging

**Prompt for the agent:**

> Produce the final portfolio artifacts. Requirements:
> - `README.md` with sections: Problem, Architecture (embed/describe the diagram), Demo (placeholder for GIF/video link), Features, Agent workflow, ML pipeline, Evaluation results (paste the scorecard), Observability, Deployment (`docker compose up` instructions), Technical decisions (why one agent not many, why LangGraph, why configurable LLM provider), Limitations, Future work.
> - An architecture diagram (Mermaid `.mmd` or SVG) under `docs/architecture.mmd` covering: UI → API → Agent → Tools → RAG/Vector DB, plus the monitoring stack.
> - A results table pulling live numbers from `evaluation/results/latest.json`.
> - Ensure `docker compose up` is the only setup step needed; double check `.env.example` covers all required variables (`LLM_PROVIDER`, `LLM_MODEL`, API keys, DB creds).
> - Add screenshots folder `docs/screenshots/` with placeholders noting which dashboard page each should capture.
>
> Deliverable: a README a stranger could follow to run the whole system in under 5 minutes, understand the architecture, and see real evaluation numbers.

**Acceptance check:** Fresh clone → `docker compose up` → working system, README fully describes it with no broken links/placeholders left unexplained.

---

## Interview-Readiness Checklist (review before submitting anywhere)

Be able to answer, in your own words, without notes:

- Why RAG here, and why is it *not* the centerpiece of the system?
- Why one agent + tools instead of a multi-agent architecture?
- How do you detect and measure hallucination / evidence grounding?
- What happens if the retrieval system returns nothing relevant?
- How would this scale to real production traffic?
- How do you detect model drift, concretely, in your pipeline?
- Where is the current bottleneck (latency, cost, or accuracy)?
- What would you change about the evaluation methodology if you had more time?

---

### Notes on using this file
- Do not hand the agent the whole roadmap at once — full context per phase keeps outputs focused and reviewable.
- After each phase, actually run the acceptance check yourself before moving on; don't trust "looks done."
- Keep the scope guardrails from the original plan in mind: no Kubernetes, no cloud infra, no fine-tuning, no >1 agent, no custom transformer, no complex auth — this is a 14-day portfolio project, not a production system.
