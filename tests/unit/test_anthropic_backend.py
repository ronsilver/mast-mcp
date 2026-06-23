"""Tests for AnthropicBackend."""

from __future__ import annotations

import httpx
import pytest
import respx

from mast.agents.backends.anthropic import AnthropicBackend


@pytest.fixture
def backend() -> AnthropicBackend:
    return AnthropicBackend(api_key="sk-ant-test")


@pytest.mark.asyncio
async def test_chat_uses_tool_use_for_json_schema(backend: AnthropicBackend) -> None:
    with respx.mock(base_url="https://api.anthropic.com") as mock:
        route = mock.post("/v1/messages").mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": [
                        {"type": "tool_use", "name": "respond", "input": {"verdict": "accept"}}
                    ]
                },
            )
        )
        schema = {"type": "object", "properties": {"verdict": {"type": "string"}}}
        payload, _ = await backend.chat(
            model="claude-3-5-sonnet-20241022",
            system_prompt="s",
            fallback={"verdict": "reject"},
            json_schema=schema,
        )
        sent = route.calls.last.request
        body = _read_body(sent)
        tools = body.get("tools")
        assert isinstance(tools, list)
        assert tools[0]["name"] == "respond"
        assert tools[0]["input_schema"] == schema
        assert body.get("tool_choice") == {"type": "tool", "name": "respond"}
        assert payload == {"verdict": "accept"}


@pytest.mark.asyncio
async def test_chat_extracts_json_from_text(backend: AnthropicBackend) -> None:
    """No schema provided: parse JSON from text block."""
    with respx.mock(base_url="https://api.anthropic.com") as mock:
        mock.post("/v1/messages").mock(
            return_value=httpx.Response(
                200, json={"content": [{"type": "text", "text": '{"v": 42}'}]}
            )
        )
        payload, _ = await backend.chat(
            model="claude-3-5-sonnet-20241022",
            system_prompt="s",
            fallback={"v": 0},
        )
    assert payload == {"v": 42}


@pytest.mark.asyncio
async def test_chat_extracts_json_from_text_code_fence(
    backend: AnthropicBackend,
) -> None:
    with respx.mock(base_url="https://api.anthropic.com") as mock:
        mock.post("/v1/messages").mock(
            return_value=httpx.Response(
                200, json={"content": [{"type": "text", "text": '```json\n{"a": 1}\n```'}]}
            )
        )
        payload, _ = await backend.chat(
            model="claude-3-5-sonnet-20241022",
            system_prompt="s",
            fallback={"a": 0},
        )
    assert payload == {"a": 1}


@pytest.mark.asyncio
async def test_chat_http_error_returns_fallback(backend: AnthropicBackend) -> None:
    with respx.mock(base_url="https://api.anthropic.com") as mock:
        mock.post("/v1/messages").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"fb": True})
    assert payload == {"fb": True}


@pytest.mark.asyncio
async def test_chat_two_parse_failures_use_fallback(backend: AnthropicBackend) -> None:
    with respx.mock(base_url="https://api.anthropic.com") as mock:
        mock.post("/v1/messages").mock(
            return_value=httpx.Response(
                200, json={"content": [{"type": "text", "text": "not json"}]}
            )
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"fb": True})
    assert payload == {"fb": True}


@pytest.mark.asyncio
async def test_chat_sends_anthropic_headers(backend: AnthropicBackend) -> None:
    with respx.mock(base_url="https://api.anthropic.com") as mock:
        route = mock.post("/v1/messages").mock(
            return_value=httpx.Response(200, json={"content": []})
        )
        await backend.chat(model="m", system_prompt="s", fallback={})
        sent = route.calls.last.request
        assert sent.headers.get("x-api-key") == "sk-ant-test"
        assert sent.headers.get("anthropic-version") == "2023-06-01"


@pytest.mark.asyncio
async def test_chat_num_predict_as_max_tokens(backend: AnthropicBackend) -> None:
    with respx.mock(base_url="https://api.anthropic.com") as mock:
        route = mock.post("/v1/messages").mock(
            return_value=httpx.Response(200, json={"content": []})
        )
        await backend.chat(model="m", system_prompt="s", fallback={}, num_predict=2048)
        body = _read_body(route.calls.last.request)
        assert body["max_tokens"] == 2048


@pytest.mark.asyncio
async def test_list_models_returns_catalog(backend: AnthropicBackend) -> None:
    models = await backend.list_models()
    assert "claude-3-5-sonnet-20241022" in models
    assert "claude-3-opus-20240229" in models


@pytest.mark.asyncio
async def test_aclose(backend: AnthropicBackend) -> None:
    await backend.aclose()


def test_is_chat_backend() -> None:
    from mast.agents.protocols import ChatBackend

    b = AnthropicBackend(api_key="x")
    assert isinstance(b, ChatBackend)


def _read_body(req: httpx.Request) -> dict[str, object]:
    import json

    result: dict[str, object] = json.loads(req.content)
    return result
