"""OpenRouter backend — extends OpenAICompatBackend with routing headers."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from mast.agents.protocols import ChatBackend, ChatResult
from mast.config import config

log = structlog.get_logger(__name__)


class OpenRouterBackend(ChatBackend):
    """Async client for OpenRouter's OpenAI-compatible API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        """Initialize OpenRouter backend with optional overrides."""
        resolved_base = base_url or "https://openrouter.ai/api/v1"
        resolved_key = api_key or config.openrouter_api_key or config.mast_api_key
        self._default_model = default_model or "anthropic/claude-3.5-sonnet"
        self._http = httpx.AsyncClient(
            base_url=resolved_base,
            timeout=config.mast_timeout_ms / 1000.0,
        )
        self._api_key = resolved_key

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "HTTP-Referer": "https://github.com/ronsilver/mast-mcp",
            "X-Title": "MAST-MCP",
        }
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

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
        """Delegate to a one-shot OpenAI-compat request via httpx."""
        from mast.agents._utils import _build_openai_payload, _retry_parse

        payload = _build_openai_payload(
            model, system_prompt, temperature, num_predict, self._default_model, json_schema
        )
        return await _retry_parse(
            self._http,
            "/chat/completions",
            payload,
            self._headers(),
            lambda raw: raw["choices"][0]["message"]["content"],
            fallback,
            model,
            "openrouter",
        )

    async def list_models(self) -> list[str]:
        try:
            response = await self._http.get("/models", headers=self._headers())
            response.raise_for_status()
            data = response.json()
            return [m["id"] for m in data.get("data", [])]
        except httpx.HTTPError:
            return []

    async def aclose(self) -> None:
        await self._http.aclose()
