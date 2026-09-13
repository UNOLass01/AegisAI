# AegisAI

AI-powered investigation agent for ML production incidents (fraud/anomaly detection).

> Phase 2 — ML pipeline live: three versioned fraud models served via `POST /predict`, listed via `GET /models`.
> See `AEGIS_AI_AGENT_PLAN.md` for the phased execution plan.

## Quickstart

```bash
docker compose up --build
```

- Backend: http://localhost:8000 (`GET /health` → `{"status":"ok"}`, docs at `/docs`)
- Frontend: http://localhost:5173 — shows a green "backend healthy" indicator.
- Postgres: `localhost:5432` (user/pass/db: `aegis`), migrations run automatically via Alembic.

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
