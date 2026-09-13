"""Retrieval over the ingested knowledge base.

``search(query, k)`` returns grounded chunks with source metadata
(filename, incident id, title) and similarity scores.
"""
from typing import TypedDict

from app.rag.embeddings import get_provider
from app.rag.store import collection_name, get_client, search_vectors


class Chunk(TypedDict):
    text: str
    source: str
    title: str
    incident_id: str | None
    score: float


def search(
    query: str, k: int = 5, client=None, provider=None
) -> list[Chunk]:
    provider = provider or get_provider()
    client = client or get_client()
    collection = collection_name(provider)
    if not client.collection_exists(collection):
        return []
    query_vector = provider.embed_batch([query])[0]
    hits = search_vectors(client, collection, query_vector, k)
    return [
        Chunk(
            text=payload.get("text", ""),
            source=payload.get("source", ""),
            title=payload.get("title", ""),
            incident_id=payload.get("incident_id"),
            score=float(score),
        )
        for score, payload in hits
    ]
