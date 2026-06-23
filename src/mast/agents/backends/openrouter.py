"""OpenRouter backend — extends OpenAICompatBackend with routing headers."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from mast.agents.backends.openai import (
    OpenAICompatBackend,  # noqa: F401  # parent class for type-checking
)
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
        import json as _json
        import time as _time

        from mast.agents._json_utils import extract_json

        payload: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": [{"role": "system", "content": system_prompt}],
            "temperature": temperature,
            "max_tokens": num_predict,
        }
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "mast_response", "schema": json_schema},
            }
        else:
            payload["response_format"] = {"type": "json_object"}

        content = ""
        last_latency_ms = 0
        for attempt in range(2):
            t0 = _time.monotonic()
            try:
                response = await self._http.post(
                    "/chat/completions", json=payload, headers=self._headers()
                )
                latency_ms = int((_time.monotonic() - t0) * 1000)
                last_latency_ms = latency_ms
                response.raise_for_status()
                raw = response.json()
                content = raw["choices"][0]["message"]["content"]
                parsed: dict[str, Any] = _json.loads(content)
                return parsed, latency_ms
            except _json.JSONDecodeError as exc:
                latency_ms = int((_time.monotonic() - t0) * 1000)
                last_latency_ms = latency_ms
                log.warning(
                    "openrouter_json_parse_failed",
                    attempt=attempt,
                    error=str(exc),
                    model=model,
                )
                extracted = extract_json(content)
                if extracted is not None:
                    return extracted, latency_ms
                if attempt == 0:
                    payload["messages"] = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "Respond with JSON only, no prose."},
                    ]
                    continue
            except (KeyError, IndexError) as exc:
                latency_ms = int((_time.monotonic() - t0) * 1000)
                last_latency_ms = latency_ms
                log.warning("openrouter_response_key_missing", error=str(exc), model=model)
                if attempt == 0:
                    continue
            except httpx.HTTPError as exc:
                latency_ms = int((_time.monotonic() - t0) * 1000)
                last_latency_ms = latency_ms
                log.error("openrouter_http_error", error=str(exc), model=model)
                return fallback, latency_ms

        log.warning("openrouter_validation_failed_using_fallback", model=model)
        return fallback, last_latency_ms

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
