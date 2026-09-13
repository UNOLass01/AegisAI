FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
ENV HF_HOME=/hf-cache

WORKDIR /code

# Build context is the repo root (see docker-compose.yml).
COPY backend/requirements.txt .
COPY backend/requirements-ml.txt .
# CPU-only torch first (default PyPI wheels are CUDA-bundled and huge).
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch
RUN pip install --no-cache-dir -r requirements-ml.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/tests ./tests
# Simulator + observability configs so the image stays self-contained/testable.
COPY monitoring ./monitoring
# Model artifacts + reports so /predict and /models work out of the box.
COPY ml ./ml
# RAG corpus (ingested into Qdrant at startup / via POST /knowledge/ingest).
COPY knowledge ./knowledge

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
