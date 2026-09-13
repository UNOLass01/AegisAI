# Deployment Config

## Services (`docker compose up --build`)

| Service | Port | Purpose |
|---|---|---|
| backend (FastAPI) | 8000 | `/health`, `/predict`, `/models`, `/knowledge/*`, `/metrics` |
| frontend (Vite) | 5173 | dashboard |
| postgres | 5432 | `investigations` table via Alembic |
| prometheus | 9090 | scrapes `backend:8000/metrics` every 5s |
| grafana | 3000 | "AegisAI Overview" dashboard (admin/admin) |
| qdrant | 6333 | vector DB for the knowledge base |

## Key environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://aegis:aegis@postgres:5432/aegis` | Postgres connection |
| `QDRANT_URL` | `http://qdrant:6333` (docker) | vector DB connection |
| `EMBEDDING_PROVIDER` | `local` | `local` (sentence-transformers), `openai`, or `hash` (deterministic fallback) |
| `OPENAI_API_KEY` | — | required only for `EMBEDDING_PROVIDER=openai` |
| `SKIP_RAG_AUTO_INGEST` | unset | set to `1` to skip background knowledge ingestion at startup |
| `LOG_LEVEL` | `INFO` | backend log verbosity |

## Endpoints

- `GET /health`, `GET /models`, `POST /predict` (fields: `transaction_amount`,
  `merchant_category`, `hour_of_day`, `model_version`, optional `ground_truth`)
- `POST /knowledge/search` (`query`, `k`) and `POST /knowledge/ingest`
- `GET /metrics` (Prometheus exposition)
