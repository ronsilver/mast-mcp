"""Google Gemini backend — generateContent with response_mime_type JSON."""

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

_DEFAULT_MODELS: list[str] = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]


class GeminiBackend(ChatBackend):
    """Async client for Google Gemini generateContent API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        """Initialize Gemini backend with optional overrides."""
        resolved_base = base_url or "https://generativelanguage.googleapis.com/v1beta"
        resolved_key = api_key or config.gemini_api_key or config.mast_api_key
        self._api_key = resolved_key
        self._default_model = default_model or "gemini-2.0-flash"
        self._http = httpx.AsyncClient(
            base_url=resolved_base,
            timeout=config.mast_timeout_ms / 1000.0,
        )

    def _endpoint(self, model: str) -> str:
        m = model or self._default_model
        return f"/models/{m}:generateContent"

    def _query_string(self) -> str:
        return f"?key={self._api_key}" if self._api_key else ""

    def _build_payload(
        self,
        system_prompt: str,
        temperature: float,
        num_predict: int,
        json_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        gen_config: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": num_predict,
        }
        if json_schema is not None:
            gen_config["response_mime_type"] = "application/json"
            gen_config["response_schema"] = json_schema
        return {
            "contents": [{"role": "user", "parts": [{"text": system_prompt}]}],
            "generationConfig": gen_config,
        }

    @staticmethod
    def _extract_text(raw: dict[str, Any]) -> str:
        candidates = raw.get("candidates", [])
        if not candidates:
            return ""
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        texts: list[str] = []
        for part in parts:
            text = part.get("text")
            if isinstance(text, str):
                texts.append(text)
        return "\n".join(texts)

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
        url = self._endpoint(model) + self._query_string()
        payload = self._build_payload(system_prompt, temperature, num_predict, json_schema)

        content = ""
        last_latency_ms = 0
        for attempt in range(2):
            t0 = _time.monotonic()
            try:
                response = await self._http.post(url, json=payload)
                latency_ms = int((_time.monotonic() - t0) * 1000)
                last_latency_ms = latency_ms
                response.raise_for_status()
                raw = response.json()
                content = self._extract_text(raw)
                if not content:
                    if attempt == 0:
                        continue
                    break
                try:
                    parsed_dict: dict[str, Any] = _json.loads(content)
                    return parsed_dict, latency_ms
                except _json.JSONDecodeError:
                    extracted = extract_json(content)
                    if extracted is not None:
                        return extracted, latency_ms
                    if attempt == 0:
                        continue
            except (KeyError, IndexError) as exc:
                latency_ms = int((_time.monotonic() - t0) * 1000)
                last_latency_ms = latency_ms
                log.warning("gemini_response_key_missing", error=str(exc), model=model)
                if attempt == 0:
                    continue
            except httpx.HTTPError as exc:
                latency_ms = int((_time.monotonic() - t0) * 1000)
                last_latency_ms = latency_ms
                log.error("gemini_http_error", error=str(exc), model=model)
                return fallback, latency_ms

        log.warning("gemini_validation_failed_using_fallback", model=model)
        return fallback, last_latency_ms

    async def list_models(self) -> list[str]:
        """Fetch available models from the v1beta/models endpoint."""
        if not self._api_key:
            return list(_DEFAULT_MODELS)
        try:
            response = await self._http.get(f"/models?key={self._api_key}")
            response.raise_for_status()
            data = response.json()
            models: list[str] = []
            for m in data.get("models", []):
                name = m.get("name", "")
                if name.startswith("models/"):
                    name = name[len("models/") :]
                models.append(name)
            return models or list(_DEFAULT_MODELS)
        except httpx.HTTPError:
            return list(_DEFAULT_MODELS)

    async def aclose(self) -> None:
        await self._http.aclose()
