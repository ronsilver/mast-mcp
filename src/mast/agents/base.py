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

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(text: str) -> dict[str, Any] | None:
    """Defensively extract first balanced JSON object from arbitrary model output.

    Tolerates: <think> blocks, code fences, prose prefixes/suffixes.
    Uses raw_decode so it stops at the first complete JSON object.
    """
    # 1. Strip reasoning blocks emitted by some models.
    text = _THINK_RE.sub("", text)

    # 2. If code fence present, extract only its content.
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1)

    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text, i)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _build_format(json_schema: dict[str, Any] | None) -> dict[str, Any] | str | None:
    """Return the Ollama `format` value based on config and schema availability."""
    mode = config.mast_format_mode
    if mode == "schema" and json_schema is not None:
        return json_schema
    if mode == "text":
        return None
    return "json"


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
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], int]:
        """Call /api/chat and return (parsed_json, latency_ms).

        On parse failure after one retry, returns (fallback, latency_ms).
        Accepts an optional json_schema to pass as Ollama format (0.5+).
        """
        fmt = _build_format(json_schema)
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                "top_p": 0.9,
            },
        }
        if fmt is not None:
            payload["format"] = fmt

        content = ""
        for attempt in range(2):
            t0 = time.monotonic()
            try:
                response = await self._http.post("/api/chat", json=payload)
                latency_ms = int((time.monotonic() - t0) * 1000)
                response.raise_for_status()
                raw = response.json()
                content = raw["message"]["content"]
                # Fast path: model returned clean JSON.
                parsed: dict[str, Any] = json.loads(content)
                return parsed, latency_ms
            except json.JSONDecodeError as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                log.warning(
                    "ollama_json_parse_failed",
                    attempt=attempt,
                    error=str(exc),
                    model=model,
                )
                extracted = _extract_json(content)
                if extracted is not None:
                    return extracted, latency_ms
                if attempt == 0:
                    continue
            except KeyError as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                log.warning("ollama_response_key_missing", error=str(exc), model=model)
                if attempt == 0:
                    continue
            except httpx.HTTPError as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                log.error("ollama_http_error", error=str(exc), model=model)
                return fallback, latency_ms

        log.warning("ollama_validation_failed_using_fallback", model=model)
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
