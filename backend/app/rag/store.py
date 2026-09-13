"""Qdrant vector-store helpers.

Connection resolution:
- ``QDRANT_URL`` set (docker: ``http://qdrant:6333``) -> remote server.
- ``QDRANT_URL=:memory:`` (tests) -> in-process ephemeral instance.
- otherwise -> embedded persistent store under the repo root
  (``.qdrant_data/``, override with ``QDRANT_LOCAL_PATH``).

One collection per embedding provider (dimensions differ), e.g.
``aegis_knowledge_minilm-l6-v2``.
"""
import os
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

_client_cache: dict[str, QdrantClient] = {}


def find_repo_root() -> Path:
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / "knowledge").is_dir():
            return ancestor
    raise FileNotFoundError("repo root with knowledge/ not found")


def get_client(url: str | None = None, path: str | None = None) -> QdrantClient:
    url = url if url is not None else os.getenv("QDRANT_URL", "")
    if url:
        key = f"url:{url}"
        if key not in _client_cache:
            _client_cache[key] = QdrantClient(url=url) if url != ":memory:" else QdrantClient(":memory:")
        return _client_cache[key]
    if path is None:
        path = os.getenv("QDRANT_LOCAL_PATH", str(find_repo_root() / ".qdrant_data"))
    key = f"path:{path}"
    if key not in _client_cache:
        _client_cache[key] = QdrantClient(path=path)
    return _client_cache[key]


def clear_client_cache() -> None:
    _client_cache.clear()


def collection_name(provider) -> str:
    return f"aegis_knowledge_{provider.slug}"


def ensure_collection(client: QdrantClient, provider) -> str:
    name = collection_name(provider)
    if not client.collection_exists(name):
        client.create_collection(
            name,
            vectors_config=VectorParams(size=provider.dim, distance=Distance.COSINE),
        )
    return name


def collection_count(client: QdrantClient, collection: str) -> int:
    if not client.collection_exists(collection):
        return 0
    return client.count(collection, exact=True).count


def upsert_chunks(
    client: QdrantClient, collection: str, chunks: list[dict], vectors: list[list[float]]
) -> int:
    import uuid

    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{c['source']}#{c['seq']}")),
            vector=vector,
            payload={
                "text": c["text"],
                "source": c["source"],
                "title": c["title"],
                "incident_id": c["incident_id"],
                "seq": c["seq"],
            },
        )
        for c, vector in zip(chunks, vectors)
    ]
    client.upsert(collection_name=collection, points=points)
    return len(points)


def search_vectors(
    client: QdrantClient, collection: str, vector: list[float], k: int
) -> list[tuple[float, dict]]:
    response = client.query_points(
        collection_name=collection, query=vector, limit=k, with_payload=True
    )
    return [(point.score, dict(point.payload or {})) for point in response.points]
