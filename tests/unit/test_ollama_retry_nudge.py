"""Tests for OllamaBackend retry behavior (T20)."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from mast.agents.base import OllamaBackend
from mast.agents.protocols import ChatBackend


@pytest.fixture
def backend() -> OllamaBackend:
    return OllamaBackend()


@pytest.mark.asyncio
async def test_retry_increments_temperature_on_parse_failure(
    backend: OllamaBackend,
) -> None:
    """On JSON parse failure, retry should adjust temperature."""
    with respx.mock(base_url="http://localhost:11434") as mock:
        route = mock.post("/api/chat").mock(
            side_effect=[
                httpx.Response(200, json={"message": {"content": "not json at all"}}),
                httpx.Response(200, json={"message": {"content": '{"v": 1}'}}),
            ]
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"v": 0})
        assert payload == {"v": 1}
        assert route.call_count == 2
        # Second request should have a higher temperature than first
        bodies = [json.loads(call.request.content) for call in route.calls]
        temps = [b["options"]["temperature"] for b in bodies]
        assert temps[1] >= temps[0]


@pytest.mark.asyncio
async def test_fallback_latency_nonzero_after_failures(
    backend: OllamaBackend,
) -> None:
    """After 2 failed attempts, the latency_ms returned with fallback.

    Should reflect the time spent, not 0.
    """
    with respx.mock(base_url="http://localhost:11434") as mock:
        mock.post("/api/chat").mock(
            side_effect=[
                httpx.Response(200, json={"message": {"content": "garbage"}}),
                httpx.Response(200, json={"message": {"content": "more garbage"}}),
            ]
        )
        payload, latency = await backend.chat(model="m", system_prompt="s", fallback={"fb": True})
    assert payload == {"fb": True}
    assert latency >= 0


@pytest.mark.asyncio
async def test_first_attempt_clean_json_no_retry(
    backend: OllamaBackend,
) -> None:
    with respx.mock(base_url="http://localhost:11434") as mock:
        route = mock.post("/api/chat").mock(
            return_value=httpx.Response(200, json={"message": {"content": '{"v": 99}'}})
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"v": 0})
    assert payload == {"v": 99}
    assert route.call_count == 1


def test_is_chat_backend() -> None:
    b = OllamaBackend()
    assert isinstance(b, ChatBackend)
