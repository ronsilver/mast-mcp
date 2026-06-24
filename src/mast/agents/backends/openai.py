"""
OpenAI-compatible backend.

Targets `/v1/chat/completions`. Works with OpenAI, vLLM, LM Studio,
TGI, llama.cpp server, and any other OpenAI-compatible endpoint.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from mast.agents.protocols import ChatBackend, ChatResult
from mast.config import config

log = structlog.get_logger(__name__)


class OpenAICompatBackend(ChatBackend):
    """Async client for OpenAI-compatible /v1/chat/completions."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        """Initialize OpenAI-compatible backend with optional overrides."""
        resolved_base = base_url or config.openai_base_url or config.effective_base_url
        if resolved_base.endswith("/"):
            resolved_base = resolved_base[:-1]
        if not resolved_base.endswith("/v1"):
            resolved_base = resolved_base + "/v1"
        resolved_key = api_key or config.openai_api_key or config.mast_api_key
        self._base_url = resolved_base
        self._api_key = resolved_key
        self._default_model = default_model or "gpt-4o-mini"
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=config.mast_timeout_ms / 1000.0,
        )

    def _auth_headers(self) -> dict[str, str]:
        if not self._api_key:
            return {}
        return {"Authorization": f"Bearer {self._api_key}"}

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
        payload: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": [{"role": "system", "content": system_prompt}],
            "temperature": temperature,
            "max_tokens": num_predict,
        }
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "mast_response",
                    "schema": json_schema,
                    "strict": False,
                },
            }
        else:
            payload["response_format"] = {"type": "json_object"}

        from mast.agents._utils import _retry_parse

        return await _retry_parse(
            self._http,
            "/chat/completions",
            payload,
            self._auth_headers(),
            lambda raw: raw["choices"][0]["message"]["content"],
            fallback,
            model,
            "openai",
        )

    async def list_models(self) -> list[str]:
        """Return list of model IDs from /v1/models."""
        try:
            response = await self._http.get("/models", headers=self._auth_headers())
            response.raise_for_status()
            data = response.json()
            return [m["id"] for m in data.get("data", [])]
        except httpx.HTTPError:
            return []

    async def aclose(self) -> None:
        await self._http.aclose()
