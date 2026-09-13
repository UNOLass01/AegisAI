"""Ingest the knowledge/ markdown corpus into Qdrant.

Runnable as a script (from the repo root or backend/):

    python backend/app/rag/ingest.py
    python backend/app/rag/ingest.py --provider hash --qdrant-url :memory:

or imported:

    from app.rag.ingest import ingest_knowledge, ensure_ingested
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.rag.chunking import chunk_markdown  # noqa: E402
from app.rag.embeddings import get_provider  # noqa: E402
from app.rag.store import (  # noqa: E402
    collection_count,
    collection_name,
    ensure_collection,
    find_repo_root,
    get_client,
    upsert_chunks,
)

EMBED_BATCH_SIZE = 64


def find_knowledge_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    return find_repo_root() / "knowledge"


def ingest_knowledge(
    client=None, provider=None, knowledge_dir: str | Path | None = None
) -> dict:
    provider = provider or get_provider()
    client = client or get_client()
    knowledge_path = find_knowledge_dir(knowledge_dir)
    files = sorted(knowledge_path.rglob("*.md"))
    chunks: list[dict] = []
    for path in files:
        source = str(path.relative_to(knowledge_path))
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), source=source))
    collection = ensure_collection(client, provider)
    texts = [c["text"] for c in chunks]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        vectors.extend(provider.embed_batch(texts[start : start + EMBED_BATCH_SIZE]))
    upserted = upsert_chunks(client, collection, chunks, vectors)
    return {
        "documents": len(files),
        "chunks": upserted,
        "collection": collection,
        "provider": provider.slug,
    }


def ensure_ingested(client=None, provider=None, knowledge_dir=None) -> dict:
    """Ingest only when the provider's collection is empty (idempotent boot path)."""
    provider = provider or get_provider()
    client = client or get_client()
    collection = ensure_collection(client, provider)
    existing = collection_count(client, collection)
    if existing:
        return {"status": "exists", "chunks": existing, "collection": collection}
    stats = ingest_knowledge(client=client, provider=provider, knowledge_dir=knowledge_dir)
    stats["status"] = "ingested"
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest knowledge/ into Qdrant.")
    parser.add_argument("--provider", default=None)
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--knowledge-dir", default=None)
    args = parser.parse_args()

    if args.provider:
        os.environ["EMBEDDING_PROVIDER"] = args.provider
    client = get_client(url=args.qdrant_url) if args.qdrant_url else get_client()
    stats = ingest_knowledge(client=client, knowledge_dir=args.knowledge_dir)
    print(stats)


if __name__ == "__main__":
    main()
