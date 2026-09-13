"""Embedding providers, selected via EMBEDDING_PROVIDER.

- ``local`` (default): sentence-transformers ``all-MiniLM-L6-v2`` on CPU.
  Real semantic search; downloads ~90MB on first use (cached via HF_HOME).
- ``openai``: ``text-embedding-3-small`` API. Needs ``OPENAI_API_KEY``.
- ``hash``: deterministic dependency-free fallback (signed word/bigram
  hashing, L2-normalized). Used for fast hermetic tests, not for quality.

Heavy third-party imports are lazy so the backend boots and tests run
without torch / API keys installed.
"""
import hashlib
import math
import os
import re

TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    words = TOKEN_RE.findall(text.lower())
    return words + [f"{a} {b}" for a, b in zip(words, words[1:])]


class EmbeddingProvider:
    slug: str = "base"
    dim: int = 0

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic keyword-ish embeddings for tests and offline use."""

    slug = "hash-384"
    dim = 384

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self.dim
            for token in _tokens(text):
                digest = hashlib.md5(token.encode()).digest()
                index = int.from_bytes(digest[:4], "big") % self.dim
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vec[index] += sign
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors


class LocalEmbeddingProvider(EmbeddingProvider):
    slug = "minilm-l6-v2"
    dim = 384
    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.MODEL_NAME)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        ).tolist()


class OpenAIEmbeddingProvider(EmbeddingProvider):
    slug = "openai-small"
    dim = 1536
    MODEL_NAME = "text-embedding-3-small"

    def __init__(self) -> None:
        import httpx

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for EMBEDDING_PROVIDER=openai")
        self._httpx = httpx
        self._api_key = api_key

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 100):
            batch = texts[start : start + 100]
            resp = self._httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self.MODEL_NAME, "input": batch},
                timeout=60.0,
            )
            resp.raise_for_status()
            vectors.extend(item["embedding"] for item in resp.json()["data"])
        return vectors


_PROVIDERS: dict[str, EmbeddingProvider] = {}


def get_provider(name: str | None = None) -> EmbeddingProvider:
    key = (name or os.getenv("EMBEDDING_PROVIDER", "local")).lower()
    if key not in _PROVIDERS:
        if key in ("local", "sentence-transformers", "minilm"):
            _PROVIDERS[key] = LocalEmbeddingProvider()
        elif key == "openai":
            _PROVIDERS[key] = OpenAIEmbeddingProvider()
        elif key in ("hash", "hashing", "test", "deterministic"):
            _PROVIDERS[key] = HashEmbeddingProvider()
        else:
            raise ValueError(
                f"Unknown EMBEDDING_PROVIDER {key!r}. Choose local, openai, or hash."
            )
    return _PROVIDERS[key]


def clear_provider_cache() -> None:
    _PROVIDERS.clear()
