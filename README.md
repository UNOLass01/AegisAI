# AegisAI

AI-powered investigation agent for ML production incidents (fraud/anomaly detection).

> Phase 5 — investigation agent live: one LangGraph agent + 5 tools answers "why did v2 degrade?" with a grounded report.
> See `AEGIS_AI_AGENT_PLAN.md` for the phased execution plan.

## Quickstart

```bash
docker compose up --build
```

- Backend: http://localhost:8000 (`GET /health` → `{"status":"ok"}`, docs at `/docs`)
- Frontend: http://localhost:5173 — shows a green "backend healthy" indicator.
- Postgres: `localhost:5432` (user/pass/db: `aegis`), migrations run automatically via Alembic.
- Prometheus: http://localhost:9090 (scrapes `backend:8000/metrics` every 5s)
- Grafana: http://localhost:3000 (admin/admin, anonymous viewer enabled) — "AegisAI Overview" dashboard
- Qdrant: http://localhost:6333 (knowledge-base vectors; auto-ingested at backend startup)

## Simulate an incident

```bash
docker compose up --build -d
python monitoring/simulate_incident.py
```

Phase A replays clean traffic against v1; Phase B replays drifted traffic (+30% amounts)
against v2 at higher concurrency. Expected output (deterministic seeds):

- Phase A: precision ≈ 0.80, avg latency ≈ 45ms
- Phase B: precision ≈ 0.52, avg latency ≈ 285ms

Watch Grafana: the model-mix panel flips v1→v2, the precision panel drops, p95 latency jumps.
Backend logs are structured JSON (timestamp, level, endpoint, model_version, latency_ms, status_code).

## ML pipeline (fraud detection)

Synthetic tabular transactions (`transaction_amount`, `merchant_category`, `hour_of_day` → `is_fraud`),
RandomForest classifier, fully reproducible (fixed seeds).

```bash
pip install -r ml/requirements.txt
python ml/training/train.py --version v1   # also v2, v3 — writes model + metrics report
python ml/evaluation/evaluate.py --version v2
python ml/training/predict.py --version v2 --amount 250 --category electronics --hour 3
```

| Version | Training data | acc | prec | rec | F1 |
|---|---|---|---|---|---|
| v1 | clean baseline | 0.953 | 0.740 | 0.665 | 0.700 |
| v2 | legit `transaction_amount` +30% (drift) | 0.932 | 0.603 | 0.527 | 0.562 |
| v3 | 30% fraud labels flipped (labeling bug) | 0.942 | 0.793 | 0.413 | 0.543 |

v2 shows the drift signature (precision −0.14, FP 39→58); v3 shows the labeling-bug
signature (recall −0.25). Reports live in `ml/evaluation/reports/model_<version>.json`.

## API

- `GET /health` → `{"status":"ok"}`
- `GET /models` → all versions with metrics + artifact presence
- `POST /predict` → `{"transaction_amount": 900, "merchant_category": "electronics", "hour_of_day": 3, "model_version": "v2"}` returns `is_fraud` + `fraud_probability`
- `POST /knowledge/search` → `{"query": "why did precision drop", "k": 3}` returns ranked chunks with `source`, `incident_id`, `title`, `score`
- `POST /knowledge/ingest` → (re)ingest the `knowledge/` corpus into Qdrant
- `POST /investigate` → `{"query": "Why did fraud detection performance degrade after deployment v2?"}` runs the agent, persists the report, returns it

## Investigation agent

One LangGraph agent (`backend/app/agents/investigation_agent.py`), five tools
(`backend/app/tools/`), fan-out evidence gathering → reason → report:

| Tool | Source |
|---|---|
| `get_metrics` | Prometheus: precision/volume/latency per version, error share |
| `analyze_logs` | structured JSON request logs (spike detection) |
| `analyze_model` | offline report deltas vs previous version |
| `search_knowledge` | RAG retriever (incident write-ups with attribution) |
| `generate_report` | deterministic evidence assembly + narrative |

Evidence is assembled from tool outputs in all modes (grounding by
construction). Narrative reasoning uses `LLM_PROVIDER`: `openai`
(OpenAI-compatible API), `ollama`, or `stub` — a deterministic
evidence-based fallback used when no key is configured (and in tests).

Example verdict for the v2 scenario: root cause "data drift in
transaction_amount" at 0.91 confidence, citing offline deltas (precision
0.74→0.60, FP 39→58), live Prometheus metrics, log findings, and Incident
#011. Reports persist to the `investigations` table.

## Knowledge base & RAG

Corpus in `knowledge/` (10 docs): model cards per version, deployment config,
3 incident write-ups (#011 drift/FP spike, #014 labeling bug, #009 latency),
and per-version experiment notes. Chunks carry filename + incident-id attribution.

```bash
# Manual ingest (auto-ingest also runs in the background at backend startup):
python backend/app/rag/ingest.py
```

Embedding provider via `EMBEDDING_PROVIDER`: `local` (sentence-transformers
MiniLM, default in docker), `openai` (needs `OPENAI_API_KEY`), or `hash`
(deterministic fallback used by tests). Vector store via `QDRANT_URL`
(docker: `http://qdrant:6333`; `:memory:` in tests). One Qdrant collection per
provider, e.g. `aegis_knowledge_minilm-l6-v2`.

Local semantic use needs CPU torch first (docker handles this automatically):

```bash
pip install --index-url https://download.pytorch.org/whl/cpu torch
pip install -r backend/requirements-ml.txt
```

## Useful commands

| Command | What it does |
|---|---|
| `make up` / `make down` / `make logs` | Start / stop / follow all services |
| `make test` | Run backend tests (`pytest`) |
| `make migrate` | Apply DB migrations (`alembic upgrade head`) |

## Layout

- `backend/` — FastAPI app (`app/api`, `app/agents`, `app/tools`, `app/rag`, `app/services`, `app/models`) + `tests/`
- `ml/` — training / evaluation / models + data dirs
- `frontend/` — React (Vite) dashboard (`src/dashboard`, `src/investigations`, `src/components`)
- `evaluation/` — scenario definitions + harness
- `monitoring/` — Prometheus + Grafana configs
- `knowledge/` — incidents / documentation / experiments (RAG corpus)
- `.github/workflows/` — CI
