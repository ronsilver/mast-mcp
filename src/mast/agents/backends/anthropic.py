"""Anthropic backend — Claude API at api.anthropic.com with tool-use JSON mode."""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from mast.agents.protocols import ChatBackend, ChatResult
from mast.config import config

log = structlog.get_logger(__name__)

# Default model catalog (Anthropic does not expose /v1/models publicly).
_DEFAULT_MODELS: list[str] = [
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-latest",
    "claude-3-5-haiku-20241022",
    "claude-3-5-haiku-latest",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
]


class AnthropicBackend(ChatBackend):
    """Async client for Anthropic's /v1/messages endpoint."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        """Initialize Anthropic backend with optional overrides."""
        resolved_base = base_url or "https://api.anthropic.com"
        resolved_key = api_key or config.anthropic_api_key or config.mast_api_key
        self._api_key = resolved_key
        self._default_model = default_model or "claude-3-5-sonnet-20241022"
        self._http = httpx.AsyncClient(
            base_url=resolved_base,
            timeout=config.mast_timeout_ms / 1000.0,
        )

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        if self._api_key:
            h["x-api-key"] = self._api_key
        return h

    def _build_payload(
        self,
        model: str,
        system_prompt: str,
        temperature: float,
        num_predict: int,
        json_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or self._default_model,
            "max_tokens": num_predict,
            "temperature": temperature,
            "messages": [{"role": "user", "content": system_prompt}],
        }
        if json_schema is not None:
            payload["tools"] = [
                {
                    "name": "respond",
                    "description": "Emit a JSON response matching the schema.",
                    "input_schema": json_schema,
                }
            ]
            payload["tool_choice"] = {"type": "tool", "name": "respond"}
        return payload

    @staticmethod
    def _extract_tool_input(raw: dict[str, Any]) -> dict[str, Any] | None:
        for block in raw.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                inner = block.get("input")
                if isinstance(inner, dict):
                    return inner
        return None

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
        payload = self._build_payload(model, system_prompt, temperature, num_predict, json_schema)
        from mast.agents._utils import _retry_parse

        def extractor(raw: dict[str, Any]) -> str:
            if json_schema is not None:
                parsed = self._extract_tool_input(raw)
                if parsed is not None:
                    return json.dumps(parsed)
            return self._extract_content(raw)

        return await _retry_parse(
            self._http,
            "/v1/messages",
            payload,
            self._headers(),
            extractor,
            fallback,
            model,
            "anthropic",
        )

    def _extract_content(self, raw: dict[str, Any]) -> str:
        text_blocks: list[str] = []
        for block in raw.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                text_blocks.append(str(block.get("text", "")))
        return "\n".join(text_blocks)

    async def list_models(self) -> list[str]:
        return list(_DEFAULT_MODELS)

    async def aclose(self) -> None:
        await self._http.aclose()
