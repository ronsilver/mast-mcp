"""Async Ollama HTTP client."""
from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx
import structlog

from mast.config import config

log = structlog.get_logger(__name__)

# Minimum valid fallback shape for Critic responses
_CRITIC_FALLBACK: dict[str, Any] = {
    "issues": [],
    "strengths": [],
    "summary": "validation_failed",
}

# Minimum valid fallback shape for Judge responses
_JUDGE_FALLBACK: dict[str, Any] = {
    "verdict": "accept",
    "confidence": 0.0,
    "rationale": "validation_failed",
    "suggestedRevision": None,
}


def _extract_json(text: str) -> dict[str, Any] | None:
    """Try to extract first valid JSON object from text via regex."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return None
    return None


class OllamaClient:
    """Async client for Ollama /api/chat endpoint."""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            base_url=config.ollama_base_url,
            timeout=config.ollama_timeout,
        )

    async def chat(
        self,
        model: str,
        system_prompt: str,
        *,
        temperature: float = 0.2,
        num_predict: int = 512,
        fallback: dict[str, Any],
    ) -> tuple[dict[str, Any], int]:
        """
        Call /api/chat and return (parsed_json, latency_ms).
        On parse failure after one retry, returns (fallback, latency_ms).
        """
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                "top_p": 0.9,
            },
        }

        for attempt in range(2):
            t0 = time.monotonic()
            try:
                response = await self._http.post("/api/chat", json=payload)
                latency_ms = int((time.monotonic() - t0) * 1000)
                response.raise_for_status()
                raw = response.json()
                content: str = raw["message"]["content"]
                parsed = json.loads(content)
                return parsed, latency_ms
            except (json.JSONDecodeError, KeyError) as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                if attempt == 0:
                    log.warning(
                        "ollama_json_parse_failed",
                        attempt=attempt,
                        error=str(exc),
                        model=model,
                    )
                    # Try regex extraction before retry
                    if "content" in locals():
                        extracted = _extract_json(content)
                        if extracted is not None:
                            return extracted, latency_ms
                    continue
                log.warning(
                    "ollama_validation_failed_using_fallback",
                    model=model,
                    latency_ms=latency_ms,
                )
                return fallback, latency_ms
            except httpx.HTTPError as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                log.error("ollama_http_error", error=str(exc), model=model)
                return fallback, latency_ms

        return fallback, 0

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
