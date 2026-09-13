# AegisAI

AI-powered investigation agent for ML production incidents (fraud/anomaly detection).

> Phase 0 — repo bootstrap. Full scaffolding lands in Phase 1 (FastAPI + Postgres + React + Docker).
> See `AEGIS_AI_AGENT_PLAN.md` for the phased execution plan.

## Quickstart (target state, Phase 1+)

```bash
docker compose up
```

Frontend → backend health check → green "backend healthy" indicator.

## Layout

- `backend/` — FastAPI app (`app/api`, `app/agents`, `app/tools`, `app/rag`, `app/services`, `app/models`) + `tests/`
- `ml/` — training / evaluation / models + data dirs
- `frontend/` — React (Vite) dashboard (`src/dashboard`, `src/investigations`, `src/components`)
- `evaluation/` — scenario definitions + harness
- `monitoring/` — Prometheus + Grafana configs
- `knowledge/` — incidents / documentation / experiments (RAG corpus)
- `.github/workflows/` — CI
