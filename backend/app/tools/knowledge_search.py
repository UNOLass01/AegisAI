"""Tool: search_knowledge — semantic search over the incident knowledge base.

Thin wrapper around the Phase 4 RAG retriever so the agent graph has a
uniform tool interface.
"""
from app.rag.retriever import search


def search_knowledge(query: str, k: int = 5, client=None, provider=None) -> dict:
    """Return top-k grounded chunks with source attribution."""
    hits = search(query, k=k, client=client, provider=provider)
    return {
        "tool": "search_knowledge",
        "query": query,
        "hits": [
            {
                "source": hit["source"],
                "title": hit["title"],
                "incident_id": hit["incident_id"],
                "score": round(hit["score"], 4),
                "excerpt": hit["text"][:500],
            }
            for hit in hits
        ],
    }
