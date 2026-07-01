"""Ollama backend — implements ChatBackend for Ollama /api/chat + /api/tags."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from mast.agents._json_utils import CRITIC_FALLBACK, JUDGE_FALLBACK, extract_json
from mast.agents.protocols import ChatBackend, ChatResult
from mast.config import config

log = structlog.get_logger(__name__)

# Re-exports for backwards compatibility with existing imports.
# Existing callers (critic.py, judge.py, tests) import these names from base.
# Will be removed in T13 when call sites migrate to _json_utils directly.
_extract_json = extract_json
_CRITIC_FALLBACK = CRITIC_FALLBACK
_JUDGE_FALLBACK = JUDGE_FALLBACK


def _build_format(json_schema: dict[str, Any] | None) -> dict[str, Any] | str | None:
    """Return the Ollama `format` value based on config and schema availability."""
    mode = config.mast_format_mode
    if mode == "schema" and json_schema is not None:
        return json_schema
    if mode == "text":
        return None
    return "json"


class OllamaBackend(ChatBackend):
    """Async client for Ollama /api/chat endpoint."""

    def __init__(self) -> None:
        """Initialize Ollama backend with cloud auth if configured."""
        headers: dict[str, str] = {}
        if config.ollama_cloud_api_key:
            headers["Authorization"] = f"Bearer {config.ollama_cloud_api_key}"
        self._http = httpx.AsyncClient(
            base_url=config.ollama_base_url,
            timeout=config.ollama_timeout,
            headers=headers,
        )

    async def chat(
        self,
        model: str,
        system_prompt: str,
        *,
        temperature: float = 0.2,
        num_predict: int = 512,
        fallback: dict[str, Any],
        json_schema: dict[str, Any] | None = None,
    ) -> ChatResult:
        """Call /api/chat and return (parsed_json, latency_ms)."""
        fmt = _build_format(json_schema)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                "top_p": config.ollama_top_p,
            },
        }
        if fmt is not None:
            payload["format"] = fmt

        from mast.agents._utils import _retry_parse

        return await _retry_parse(
            self._http,
            "/api/chat",
            payload,
            None,
            lambda raw: raw["message"]["content"],
            fallback,
            model,
            "ollama",
        )

    async def list_models(self) -> list[str]:
        """Return list of locally available model names."""
        try:
            response = await self._http.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except httpx.HTTPError:
            return []

    async def aclose(self) -> None:
        await self._http.aclose()


# Backwards-compatible alias for existing imports.
# Will be removed once all call sites migrate to OllamaBackend.
OllamaClient = OllamaBackend
