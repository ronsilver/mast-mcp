"""Shared utilities for agent prompt loading and backend retry logic."""

from __future__ import annotations

import importlib.resources
import json
import re
import time
from collections.abc import Callable
from typing import Any

import httpx
import structlog

from mast.agents._json_utils import extract_json

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)
log = structlog.get_logger(__name__)


def load_prompt(base_pkg: str, filename: str) -> str:
    """Read a prompt template and strip its YAML frontmatter."""
    text = importlib.resources.files(base_pkg).joinpath(filename).read_text(encoding="utf-8")
    return _FRONTMATTER_RE.sub("", text, count=1)


async def _retry_parse(
    http: httpx.AsyncClient,
    url_path: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None,
    response_extractor: Callable[[dict[str, Any]], str],
    fallback: dict[str, Any],
    model: str,
    backend_name: str,
) -> tuple[dict[str, Any], int]:
    """Retry loop: POST, parse JSON, fallback on failure."""
    content = ""
    last_latency_ms = 0
    for attempt in range(2):
        t0 = time.monotonic()
        try:
            response = await http.post(url_path, json=payload, headers=headers)
            latency_ms = int((time.monotonic() - t0) * 1000)
            last_latency_ms = latency_ms
            response.raise_for_status()
            content = response_extractor(response.json())
            return json.loads(content), latency_ms
        except json.JSONDecodeError as exc:
            result = _handle_json_error(exc, content, attempt, model, backend_name)
            if result is not None:
                return result, last_latency_ms
            _nudge_payload(payload)
        except (KeyError, IndexError) as exc:
            log.warning(f"{backend_name}_response_key_missing", error=str(exc), model=model)
            if attempt == 0:
                continue
        except httpx.HTTPError as exc:
            log.error(f"{backend_name}_http_error", error=str(exc), model=model)
            return fallback, last_latency_ms
    log.warning(f"{backend_name}_validation_failed_using_fallback", model=model)
    return fallback, last_latency_ms


def _handle_json_error(
    exc: json.JSONDecodeError, content: str, attempt: int, model: str, backend_name: str
) -> dict[str, Any] | None:
    log.warning(f"{backend_name}_json_parse_failed", attempt=attempt, error=str(exc), model=model)
    extracted = extract_json(content)
    return extracted


def _nudge_payload(payload: dict[str, Any]) -> None:
    if "messages" not in payload:
        return
    payload["messages"] = [
        payload["messages"][0],
        {"role": "user", "content": "Respond with JSON only, no prose."},
    ]
