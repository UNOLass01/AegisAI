"""Health-check endpoint (no DB dependency so /health works even if Postgres is down)."""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "aegis-ai"}
