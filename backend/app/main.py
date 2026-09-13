"""AegisAI FastAPI entrypoint."""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.evaluation import router as evaluation_router
from app.api.health import router as health_router
from app.api.incidents import router as incidents_router
from app.api.investigate import router as investigate_router
from app.api.knowledge import router as knowledge_router
from app.api.system import router as system_router
from app.api.predict import router as predict_router
from app.middleware import RequestLoggingMiddleware
from app.services.logger import get_logger

logger = get_logger("aegis")


async def _auto_ingest_knowledge() -> None:
    """Background knowledge ingestion so a fresh `docker compose up` self-heals.

    Never crashes boot: failures (no network for the embedding model, Qdrant
    down, ...) are logged and /knowledge/search reports 503 until
    POST /knowledge/ingest succeeds.
    """
    try:
        from app.rag.ingest import ensure_ingested

        stats = await asyncio.to_thread(ensure_ingested)
        logger.info(f"knowledge auto-ingest: {stats}")
    except Exception as exc:
        logger.warning(f"knowledge auto-ingest skipped: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("SKIP_RAG_AUTO_INGEST") != "1":
        asyncio.create_task(_auto_ingest_knowledge())
    yield


app = FastAPI(title="AegisAI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(health_router)
app.include_router(predict_router)
app.include_router(knowledge_router)
app.include_router(investigate_router)
app.include_router(evaluation_router)
app.include_router(incidents_router)
app.include_router(system_router)

# Standard HTTP metrics (request count, latency histogram, status codes).
Instrumentator().instrument(app).expose(app)


@app.get("/", tags=["root"])
def root() -> dict:
    return {"service": "aegis-ai", "docs": "/docs"}
