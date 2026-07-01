"""Tests for OpenRouterBackend."""

from __future__ import annotations

import httpx
import pytest
import respx

from mast.agents.backends.openrouter import OpenRouterBackend


@pytest.fixture
def backend() -> OpenRouterBackend:
    return OpenRouterBackend(api_key="sk-or-test")


@pytest.mark.asyncio
async def test_chat_sends_routing_headers(backend: OpenRouterBackend) -> None:
    with respx.mock(base_url="https://openrouter.ai/api/v1") as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        )
        await backend.chat(model="anthropic/claude-3.5-sonnet", system_prompt="s", fallback={})
        sent = route.calls.last.request
        assert sent.headers.get("Authorization") == "Bearer sk-or-test"
        assert sent.headers.get("HTTP-Referer") == "https://github.com/ronsilver/mast-mcp"
        assert sent.headers.get("X-Title") == "MAST-MCP"


@pytest.mark.asyncio
async def test_chat_successful_response(backend: OpenRouterBackend) -> None:
    with respx.mock(base_url="https://openrouter.ai/api/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": '{"x": 1}'}}]}
            )
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"x": 0})
    assert payload == {"x": 1}


@pytest.mark.asyncio
async def test_chat_http_error_returns_fallback(backend: OpenRouterBackend) -> None:
    with respx.mock(base_url="https://openrouter.ai/api/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(500, json={"error": "fail"})
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"fb": True})
    assert payload == {"fb": True}


@pytest.mark.asyncio
async def test_chat_parse_failure_extracts_json(backend: OpenRouterBackend) -> None:
    with respx.mock(base_url="https://openrouter.ai/api/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": '```json\n{"v": 99}\n```'}}]}
            )
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"v": 0})
    assert payload == {"v": 99}


@pytest.mark.asyncio
async def test_chat_two_parse_failures_use_fallback(backend: OpenRouterBackend) -> None:
    with respx.mock(base_url="https://openrouter.ai/api/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": "definitely not json"}}]}
            )
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"fb": True})
    assert payload == {"fb": True}


@pytest.mark.asyncio
async def test_list_models_returns_ids(backend: OpenRouterBackend) -> None:
    with respx.mock(base_url="https://openrouter.ai/api/v1") as mock:
        mock.get("/models").mock(
            return_value=httpx.Response(
                200, json={"data": [{"id": "anthropic/claude-3.5-sonnet"}, {"id": "openai/gpt-4o"}]}
            )
        )
        models = await backend.list_models()
    assert "anthropic/claude-3.5-sonnet" in models


@pytest.mark.asyncio
async def test_list_models_empty_on_error(backend: OpenRouterBackend) -> None:
    with respx.mock(base_url="https://openrouter.ai/api/v1") as mock:
        mock.get("/models").mock(return_value=httpx.Response(503, text="down"))
        models = await backend.list_models()
    assert models == []


@pytest.mark.asyncio
async def test_aclose(backend: OpenRouterBackend) -> None:
    await backend.aclose()


def test_default_base_url() -> None:
    b = OpenRouterBackend(api_key="x")
    assert b._http.base_url.host == "openrouter.ai"


def test_default_model() -> None:
    b = OpenRouterBackend(api_key="x")
    assert "claude" in b._default_model


def test_is_chat_backend() -> None:
    from mast.agents.protocols import ChatBackend

    b = OpenRouterBackend(api_key="x")
    assert isinstance(b, ChatBackend)
