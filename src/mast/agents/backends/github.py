"""GitHub Models backend — OpenAI-compatible endpoint at models.inference.ai.azure.com."""

from __future__ import annotations

import json as _json
import time as _time
from typing import Any

import httpx
import structlog

from mast.agents._json_utils import extract_json
from mast.agents.protocols import ChatBackend, ChatResult
from mast.config import config

log = structlog.get_logger(__name__)


class GitHubBackend(ChatBackend):
    """Async client for GitHub Models inference endpoint."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        resolved_base = base_url or "https://models.inference.ai.azure.com"
        resolved_key = api_key or config.github_token or config.mast_api_key
        self._api_key = resolved_key
        self._default_model = default_model or "gpt-4o-mini"
        self._http = httpx.AsyncClient(
            base_url=resolved_base,
            timeout=config.mast_timeout_ms / 1000.0,
        )

    def _headers(self) -> dict[str, str]:
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
                    "github_json_parse_failed",
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
                log.warning("github_response_key_missing", error=str(exc), model=model)
                if attempt == 0:
                    continue
            except httpx.HTTPError as exc:
                latency_ms = int((_time.monotonic() - t0) * 1000)
                last_latency_ms = latency_ms
                log.error("github_http_error", error=str(exc), model=model)
                return fallback, latency_ms

        log.warning("github_validation_failed_using_fallback", model=model)
        return fallback, last_latency_ms

    async def list_models(self) -> list[str]:
        """Return hardcoded catalog (GitHub Models API doesn't have a /models endpoint)."""
        return [
            "gpt-4o",
            "gpt-4o-mini",
            "o1-preview",
            "o1-mini",
            "claude-3-5-sonnet",
            "claude-3-7-sonnet",
            "gemini-2.0-flash",
            "mistral-large",
            "phi-4",
            "llama-3.3-70b-instruct",
        ]

    async def aclose(self) -> None:
        await self._http.aclose()
