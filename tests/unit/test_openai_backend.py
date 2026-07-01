"""Tests for OpenAICompatBackend."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from mast.agents.backends.openai import OpenAICompatBackend


@pytest.fixture
def backend() -> OpenAICompatBackend:
    return OpenAICompatBackend(
        base_url="https://api.example.com",
        api_key="sk-test",
        default_model="gpt-4o-mini",
    )


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer sk-test"}


@pytest.mark.asyncio
async def test_chat_successful_json_response(
    backend: OpenAICompatBackend,
) -> None:
    with respx.mock(base_url="https://api.example.com/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": '{"verdict": "accept", "confidence": 0.9}'}}
                    ]
                },
            )
        )
        payload, latency = await backend.chat(
            model="gpt-4o-mini",
            system_prompt="Evaluate this",
            temperature=0.2,
            num_predict=512,
            fallback={"verdict": "accept", "confidence": 0.0},
        )
    assert payload == {"verdict": "accept", "confidence": 0.9}
    assert latency >= 0


@pytest.mark.asyncio
async def test_chat_with_json_schema_uses_response_format(
    backend: OpenAICompatBackend,
) -> None:
    with respx.mock(base_url="https://api.example.com/v1") as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": '{"x": 1}'}}]}
            )
        )
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        await backend.chat(
            model="gpt-4o-mini",
            system_prompt="s",
            fallback={"x": 0},
            json_schema=schema,
        )
        sent = route.calls.last.request
        body = json.loads(sent.content)
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["schema"] == schema


@pytest.mark.asyncio
async def test_chat_extracts_json_from_prose(
    backend: OpenAICompatBackend,
) -> None:
    """Model returns prose with embedded JSON — fallback to extract_json."""
    prose = '```json\n{"answer": 42}\n```'
    with respx.mock(base_url="https://api.example.com/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": prose}}]})
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"answer": 0})
    assert payload == {"answer": 42}


@pytest.mark.asyncio
async def test_chat_fallback_on_http_error(backend: OpenAICompatBackend) -> None:
    with respx.mock(base_url="https://api.example.com/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        payload, latency = await backend.chat(
            model="m", system_prompt="s", fallback={"err": "auth"}
        )
    assert payload == {"err": "auth"}
    assert latency >= 0


@pytest.mark.asyncio
async def test_chat_fallback_after_two_parse_failures(
    backend: OpenAICompatBackend,
) -> None:
    with respx.mock(base_url="https://api.example.com/v1") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": "not json at all"}}]}
            )
        )
        payload, latency = await backend.chat(model="m", system_prompt="s", fallback={"fb": True})
    assert payload == {"fb": True}
    assert latency >= 0


@pytest.mark.asyncio
async def test_chat_sends_authorization_header(
    backend: OpenAICompatBackend,
) -> None:
    with respx.mock(base_url="https://api.example.com/v1") as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        )
        await backend.chat(model="m", system_prompt="s", fallback={})
        sent = route.calls.last.request
        assert sent.headers.get("Authorization") == "Bearer sk-test"


@pytest.mark.asyncio
async def test_chat_sends_num_predict_as_max_tokens(
    backend: OpenAICompatBackend,
) -> None:
    with respx.mock(base_url="https://api.example.com/v1") as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        )
        await backend.chat(model="m", system_prompt="s", fallback={}, num_predict=1024)
        body = json.loads(route.calls.last.request.content)
        assert body["max_tokens"] == 1024


@pytest.mark.asyncio
async def test_list_models_returns_ids(backend: OpenAICompatBackend) -> None:
    with respx.mock(base_url="https://api.example.com/v1") as mock:
        mock.get("/models").mock(
            return_value=httpx.Response(
                200, json={"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4o"}]}
            )
        )
        models = await backend.list_models()
    assert models == ["gpt-4o-mini", "gpt-4o"]


@pytest.mark.asyncio
async def test_list_models_returns_empty_on_error(
    backend: OpenAICompatBackend,
) -> None:
    with respx.mock(base_url="https://api.example.com/v1") as mock:
        mock.get("/models").mock(return_value=httpx.Response(500, json={"error": "fail"}))
        models = await backend.list_models()
    assert models == []


@pytest.mark.asyncio
async def test_aclose_closes_http(backend: OpenAICompatBackend) -> None:
    await backend.aclose()


def test_backend_url_normalization() -> None:
    b1 = OpenAICompatBackend(base_url="https://api.example.com/", api_key="x", default_model="m")
    assert b1._base_url == "https://api.example.com/v1"
    b2 = OpenAICompatBackend(base_url="https://api.example.com/v1", api_key="x", default_model="m")
    assert b2._base_url == "https://api.example.com/v1"
    b3 = OpenAICompatBackend(
        base_url="https://api.example.com/openai", api_key="x", default_model="m"
    )
    assert b3._base_url == "https://api.example.com/openai/v1"


def test_backend_is_chat_backend() -> None:
    b = OpenAICompatBackend(base_url="https://x", api_key="y", default_model="m")
    from mast.agents.protocols import ChatBackend

    assert isinstance(b, ChatBackend)
