"""AegisAI FastAPI entrypoint."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.health import router as health_router
from app.api.predict import router as predict_router
from app.middleware import RequestLoggingMiddleware

app = FastAPI(title="AegisAI", version="0.1.0")

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

# Standard HTTP metrics (request count, latency histogram, status codes).
Instrumentator().instrument(app).expose(app)


@app.get("/", tags=["root"])
def root() -> dict:
    return {"service": "aegis-ai", "docs": "/docs"}
