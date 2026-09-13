"""LLM provider abstraction (OpenAI-compatible API + Ollama + stub).

- ``LLM_PROVIDER=openai`` (default): ``{OPENAI_BASE_URL}/chat/completions``
  with ``OPENAI_API_KEY`` and ``LLM_MODEL`` (default ``gpt-4o-mini``).
  Any OpenAI-compatible gateway works by pointing ``OPENAI_BASE_URL`` at it.
- ``LLM_PROVIDER=ollama``: local Ollama ``{OLLAMA_BASE_URL}/chat/completions``
  (default ``http://localhost:11434/v1``), model via ``LLM_MODEL``.
- ``LLM_PROVIDER=stub``: deterministic, no network. Used for tests, offline
  demos, and as automatic fallback when no API key is configured.

Only httpx is required; no vendor SDKs.
"""
import json
import logging
import os

import httpx

logger = logging.getLogger("aegis")

REQUEST_TIMEOUT_S = 60.0


class LLMConfig:
    def __init__(self, kind: str, base_url: str | None, api_key: str | None,
                 model: str):
        self.kind = kind
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def __repr__(self) -> str:  # pragma: no cover
        return f"LLMConfig(kind={self.kind}, model={self.model})"


def resolve_llm() -> LLMConfig:
    """Resolve the effective LLM from environment (never raises)."""
    provider = os.getenv("LLM_PROVIDER", "auto").lower()
    if provider == "stub":
        return LLMConfig("stub", None, None, "stub")
    if provider == "ollama":
        return LLMConfig(
            "ollama",
            os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/"),
            None,
            os.getenv("LLM_MODEL", "llama3.1:8b"),
        )
    # "openai" or "auto": real API only when a key is present.
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        return LLMConfig(
            "openai",
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            api_key,
            os.getenv("LLM_MODEL", "gpt-4o-mini"),
        )
    if provider == "openai":
        logger.warning("LLM_PROVIDER=openai without OPENAI_API_KEY; using stub")
    return LLMConfig("stub", None, None, "stub")


def complete(config: LLMConfig, messages: list[dict], json_mode: bool = False) -> str:
    """One chat completion; raises on transport/API errors."""
    if config.kind == "stub":
        raise RuntimeError("stub LLM cannot complete prompts")
    body: dict = {
        "model": config.model,
        "messages": messages,
        "temperature": 0.2,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    resp = httpx.post(
        f"{config.base_url}/chat/completions",
        headers=headers,
        json=body,
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def try_complete_json(config: LLMConfig, messages: list[dict]) -> dict | None:
    """Best-effort JSON completion; returns None on any failure (fallback path)."""
    try:
        return json.loads(complete(config, messages, json_mode=True))
    except Exception as exc:
        logger.warning(f"LLM completion failed ({config.kind}/{config.model}): {exc}")
        return None
