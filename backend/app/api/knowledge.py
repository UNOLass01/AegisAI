"""Knowledge-base routes: semantic search + (re)ingestion."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.rag.ingest import ensure_ingested, ingest_knowledge
from app.rag.retriever import search

router = APIRouter(tags=["knowledge"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    k: int = Field(default=5, ge=1, le=20)


class SearchHit(BaseModel):
    text: str
    source: str
    title: str
    incident_id: str | None
    score: float


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


def _unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=f"Knowledge base unavailable ({exc}). "
        "Trigger POST /knowledge/ingest once embeddings are configured.",
    )


@router.post("/knowledge/search", response_model=SearchResponse)
def knowledge_search(body: SearchRequest) -> dict:
    try:
        hits = search(body.query, k=body.k)
    except Exception as exc:  # connection errors, missing model, ...
        raise _unavailable(exc) from exc
    return {"query": body.query, "hits": hits}


@router.post("/knowledge/ingest")
def knowledge_ingest() -> dict:
    try:
        return ingest_knowledge()
    except Exception as exc:
        raise _unavailable(exc) from exc


@router.post("/knowledge/ensure-ingested")
def knowledge_ensure_ingested() -> dict:
    try:
        return ensure_ingested()
    except Exception as exc:
        raise _unavailable(exc) from exc
