# AegisAI

AI-powered investigation agent for ML production incidents (fraud/anomaly detection).

> Phase 1 — foundation live: FastAPI + Postgres + React dashboard via Docker.
> See `AEGIS_AI_AGENT_PLAN.md` for the phased execution plan.

## Quickstart

```bash
docker compose up --build
```

- Backend: http://localhost:8000 (`GET /health` → `{"status":"ok"}`, docs at `/docs`)
- Frontend: http://localhost:5173 — shows a green "backend healthy" indicator.
- Postgres: `localhost:5432` (user/pass/db: `aegis`), migrations run automatically via Alembic.

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
