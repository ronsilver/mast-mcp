"""Tests for GeminiBackend."""

from __future__ import annotations

import httpx
import pytest
import respx

from mast.agents.backends.gemini import GeminiBackend


@pytest.fixture
def backend() -> GeminiBackend:
    return GeminiBackend(api_key="gem-test-key")


@pytest.mark.asyncio
async def test_chat_uses_response_mime_type(backend: GeminiBackend) -> None:
    with respx.mock(base_url="https://generativelanguage.googleapis.com/v1beta") as mock:
        route = mock.post("/models/gemini-2.0-flash:generateContent").mock(
            return_value=httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": '{"verdict": "accept"}'}]}}]},
            )
        )
        schema = {"type": "object", "properties": {"verdict": {"type": "string"}}}
        payload, _ = await backend.chat(
            model="gemini-2.0-flash",
            system_prompt="s",
            fallback={"verdict": "reject"},
            json_schema=schema,
        )
        sent = route.calls.last.request
        assert "?key=gem-test-key" in str(sent.url)
        body = _body(sent)
        gen_cfg = body.get("generationConfig")
        assert isinstance(gen_cfg, dict)
        assert gen_cfg.get("response_mime_type") == "application/json"
        assert gen_cfg.get("response_schema") == schema
        assert payload == {"verdict": "accept"}


@pytest.mark.asyncio
async def test_chat_extracts_json_from_code_fence(backend: GeminiBackend) -> None:
    with respx.mock(base_url="https://generativelanguage.googleapis.com/v1beta") as mock:
        mock.post("/models/gemini-2.0-flash:generateContent").mock(
            return_value=httpx.Response(
                200,
                json={
                    "candidates": [{"content": {"parts": [{"text": '```json\n{"v": 99}\n```'}]}}]
                },
            )
        )
        payload, _ = await backend.chat(
            model="gemini-2.0-flash", system_prompt="s", fallback={"v": 0}
        )
    assert payload == {"v": 99}


@pytest.mark.asyncio
async def test_chat_http_error(backend: GeminiBackend) -> None:
    with respx.mock(base_url="https://generativelanguage.googleapis.com/v1beta") as mock:
        mock.post("/models/gemini-2.0-flash:generateContent").mock(
            return_value=httpx.Response(403, json={"error": "forbidden"})
        )
        payload, _ = await backend.chat(
            model="gemini-2.0-flash", system_prompt="s", fallback={"fb": True}
        )
    assert payload == {"fb": True}


@pytest.mark.asyncio
async def test_chat_empty_response_uses_fallback(backend: GeminiBackend) -> None:
    with respx.mock(base_url="https://generativelanguage.googleapis.com/v1beta") as mock:
        mock.post("/models/gemini-2.0-flash:generateContent").mock(
            return_value=httpx.Response(200, json={"candidates": []})
        )
        payload, _ = await backend.chat(
            model="gemini-2.0-flash", system_prompt="s", fallback={"fb": True}
        )
    assert payload == {"fb": True}


@pytest.mark.asyncio
async def test_chat_two_parse_failures_use_fallback(backend: GeminiBackend) -> None:
    with respx.mock(base_url="https://generativelanguage.googleapis.com/v1beta") as mock:
        mock.post("/models/gemini-2.0-flash:generateContent").mock(
            return_value=httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": "not json"}]}}]},
            )
        )
        payload, _ = await backend.chat(
            model="gemini-2.0-flash", system_prompt="s", fallback={"fb": True}
        )
    assert payload == {"fb": True}


@pytest.mark.asyncio
async def test_chat_sends_num_predict_as_max_output_tokens(
    backend: GeminiBackend,
) -> None:
    with respx.mock(base_url="https://generativelanguage.googleapis.com/v1beta") as mock:
        route = mock.post("/models/gemini-2.0-flash:generateContent").mock(
            return_value=httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]},
            )
        )
        await backend.chat(
            model="gemini-2.0-flash",
            system_prompt="s",
            fallback={},
            num_predict=2048,
        )
        body = _body(route.calls.last.request)
        gen_cfg = body.get("generationConfig")
        assert isinstance(gen_cfg, dict)
        assert gen_cfg.get("max_output_tokens") == 2048


@pytest.mark.asyncio
async def test_list_models_fetches_catalog(backend: GeminiBackend) -> None:
    with respx.mock(base_url="https://generativelanguage.googleapis.com/v1beta") as mock:
        mock.get("/models").mock(
            return_value=httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "models/gemini-2.0-flash"},
                        {"name": "models/gemini-1.5-pro"},
                    ]
                },
            )
        )
        models = await backend.list_models()
    assert "gemini-2.0-flash" in models
    assert "gemini-1.5-pro" in models


@pytest.mark.asyncio
async def test_list_models_falls_back_on_error(backend: GeminiBackend) -> None:
    with respx.mock(base_url="https://generativelanguage.googleapis.com/v1beta") as mock:
        mock.get("/models").mock(return_value=httpx.Response(500, text="down"))
        models = await backend.list_models()
    assert "gemini-2.0-flash" in models


@pytest.mark.asyncio
async def test_aclose(backend: GeminiBackend) -> None:
    await backend.aclose()


def test_default_endpoint() -> None:
    b = GeminiBackend(api_key="x")
    assert "generativelanguage" in str(b._http.base_url)


def test_is_chat_backend() -> None:
    from mast.agents.protocols import ChatBackend

    b = GeminiBackend(api_key="x")
    assert isinstance(b, ChatBackend)


def _body(req: httpx.Request) -> dict[str, object]:
    import json

    result: dict[str, object] = json.loads(req.content)
    return result
