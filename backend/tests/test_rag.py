"""Phase 4 tests: chunking, embedding providers, ingest/search roundtrip,
knowledge API, and the semantic ranking acceptance query.

All default tests use the deterministic hash provider + in-memory Qdrant
(fast, hermetic, no network). The real semantic check runs only with
RUN_SEMANTIC_TESTS=1 (needs torch + model download).
"""
import math
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag import chunking
from app.rag.embeddings import (
    HashEmbeddingProvider,
    clear_provider_cache,
    get_provider,
)
from app.rag.ingest import ensure_ingested, ingest_knowledge
from app.rag.retriever import search
from app.rag.store import (
    clear_client_cache,
    collection_count,
    collection_name,
    get_client,
)


def _find_repo_root() -> Path:
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / "knowledge").is_dir():
            return ancestor
    raise FileNotFoundError("repo root with knowledge/ not found")


REPO_ROOT = _find_repo_root()
KNOWLEDGE_DOCS = sorted((REPO_ROOT / "knowledge").rglob("*.md"))
client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_rag_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("QDRANT_URL", ":memory:")
    clear_provider_cache()
    clear_client_cache()
    yield
    clear_provider_cache()
    clear_client_cache()


def _memory_client():
    return get_client(url=":memory:")


# --- chunking ---


def test_chunker_parses_title_and_incident_id():
    text = "# Incident #011: drift\n\nSome body about precision.\n\nMore detail here."
    chunks = chunking.chunk_markdown(text, source="incidents/x.md")
    assert chunks
    assert chunks[0]["title"] == "Incident #011: drift"
    assert all(c["incident_id"] == "011" for c in chunks)
    assert all(c["source"] == "incidents/x.md" for c in chunks)
    assert [c["seq"] for c in chunks] == list(range(len(chunks)))


def test_chunker_respects_max_chars_and_handles_empty():
    assert chunking.chunk_markdown("   \n  ", source="x.md") == []
    long_para = "word " * 500
    chunks = chunking.chunk_markdown(long_para, source="x.md", max_chars=200)
    assert len(chunks) > 1
    assert all(len(c["text"]) <= 200 for c in chunks)


def test_chunker_returns_none_incident_for_plain_docs():
    chunks = chunking.chunk_markdown("# Deployment Config\n\nPorts.", source="d.md")
    assert chunks and chunks[0]["incident_id"] is None


# --- providers ---


def test_hash_provider_is_deterministic_normalized_and_384d():
    provider = HashEmbeddingProvider()
    first = provider.embed_batch(["precision drop", "unrelated text"])
    second = provider.embed_batch(["precision drop", "unrelated text"])
    assert first == second
    assert len(first[0]) == 384
    assert math.isclose(sum(v * v for v in first[0]), 1.0, rel_tol=1e-6)
    assert first[0] != first[1]


def test_get_provider_routing_and_unknown_name():
    assert get_provider("hash").slug == "hash-384"
    with pytest.raises(ValueError):
        get_provider("nope")


def test_openai_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        get_provider("openai")


# --- ingest + retrieve roundtrip ---


def test_ingest_indexes_all_ten_knowledge_docs_idempotently():
    assert len(KNOWLEDGE_DOCS) == 10
    mem = _memory_client()
    provider = get_provider("hash")
    first = ingest_knowledge(client=mem, provider=provider)
    assert first["documents"] == 10
    assert first["chunks"] > 10
    assert collection_count(mem, collection_name(provider)) == first["chunks"]
    second = ingest_knowledge(client=mem, provider=provider)
    assert collection_count(mem, collection_name(provider)) == first["chunks"]
    assert second["chunks"] == first["chunks"]


def test_ensure_ingested_only_ingests_once():
    mem = _memory_client()
    provider = get_provider("hash")
    assert ensure_ingested(client=mem, provider=provider)["status"] == "ingested"
    assert ensure_ingested(client=mem, provider=provider)["status"] == "exists"


def test_search_empty_collection_returns_no_hits():
    assert search("anything", k=3, client=_memory_client(),
                  provider=get_provider("hash")) == []


def test_search_distinctive_query_ranks_incident_011_first():
    mem = _memory_client()
    provider = get_provider("hash")
    ingest_knowledge(client=mem, provider=provider)
    hits = search("incident 011 false positives transaction amount drift",
                  k=3, client=mem, provider=provider)
    assert len(hits) == 3
    assert "incident-011" in hits[0]["source"]
    assert hits[0]["incident_id"] == "011"
    for hit in hits:
        assert {"text", "source", "title", "incident_id", "score"} <= set(hit)


def test_search_respects_k():
    mem = _memory_client()
    provider = get_provider("hash")
    ingest_knowledge(client=mem, provider=provider)
    assert len(search("fraud model", k=1, client=mem, provider=provider)) == 1


# --- HTTP API ---


def test_knowledge_ingest_then_search_flow():
    resp = client.post("/knowledge/ingest")
    assert resp.status_code == 200, resp.text
    assert resp.json()["documents"] == 10
    resp = client.post(
        "/knowledge/search",
        json={"query": "incident 011 false positives transaction amount drift", "k": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"].startswith("incident 011")
    assert len(body["hits"]) == 3
    top = body["hits"][0]
    assert "incident-011" in top["source"]
    assert top["incident_id"] == "011"
    assert top["score"] > 0


def test_knowledge_search_validates_input():
    assert client.post("/knowledge/search", json={"query": "", "k": 5}).status_code == 422
    assert client.post("/knowledge/search", json={"query": "x", "k": 0}).status_code == 422


def test_knowledge_search_empty_index_returns_empty_hits():
    resp = client.post("/knowledge/search", json={"query": "precision", "k": 3})
    assert resp.status_code == 200
    assert resp.json()["hits"] == []


def test_knowledge_search_returns_503_when_store_unreachable(monkeypatch):
    import app.api.knowledge as knowledge_api

    def boom(*args, **kwargs):
        raise ConnectionError("qdrant down")

    monkeypatch.setattr(knowledge_api, "search", boom)
    resp = client.post("/knowledge/search", json={"query": "precision", "k": 3})
    assert resp.status_code == 503


# --- real semantic ranking (opt-in, needs model download) ---


@pytest.mark.skipif(
    os.getenv("RUN_SEMANTIC_TESTS") != "1",
    reason="needs sentence-transformers model download",
)
def test_semantic_search_precision_drop_returns_incident_011():
    from qdrant_client import QdrantClient

    provider = get_provider("local")
    mem = QdrantClient(":memory:")
    ingest_knowledge(client=mem, provider=provider)
    hits = search("why did precision drop", k=3, client=mem, provider=provider)
    assert hits, "no hits from semantic search"
    assert "incident-011" in hits[0]["source"], [h["source"] for h in hits]
