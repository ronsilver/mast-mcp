"""Tests for GitHubBackend."""

from __future__ import annotations

import httpx
import pytest
import respx

from mast.agents.backends.github import GitHubBackend


@pytest.fixture
def backend() -> GitHubBackend:
    return GitHubBackend(api_key="ghp-test")


@pytest.mark.asyncio
async def test_chat_uses_github_endpoint(backend: GitHubBackend) -> None:
    with respx.mock(base_url="https://models.inference.ai.azure.com") as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        )
        await backend.chat(model="gpt-4o-mini", system_prompt="s", fallback={})
        sent = route.calls.last.request
        assert "models.inference.ai.azure.com" in str(sent.url)


@pytest.mark.asyncio
async def test_chat_sends_bearer_token(backend: GitHubBackend) -> None:
    with respx.mock(base_url="https://models.inference.ai.azure.com") as mock:
        route = mock.post("/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})
        )
        await backend.chat(model="m", system_prompt="s", fallback={})
        assert route.calls.last.request.headers.get("Authorization") == "Bearer ghp-test"


@pytest.mark.asyncio
async def test_chat_successful_response(backend: GitHubBackend) -> None:
    with respx.mock(base_url="https://models.inference.ai.azure.com") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": '{"v": 1}'}}]}
            )
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"v": 0})
    assert payload == {"v": 1}


@pytest.mark.asyncio
async def test_chat_http_error(backend: GitHubBackend) -> None:
    with respx.mock(base_url="https://models.inference.ai.azure.com") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(403, json={"error": "forbidden"})
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"fb": True})
    assert payload == {"fb": True}


@pytest.mark.asyncio
async def test_chat_extracts_json_from_code_fence(backend: GitHubBackend) -> None:
    with respx.mock(base_url="https://models.inference.ai.azure.com") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": '```json\n{"r": 7}\n```'}}]}
            )
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"r": 0})
    assert payload == {"r": 7}


@pytest.mark.asyncio
async def test_chat_two_parse_failures_use_fallback(backend: GitHubBackend) -> None:
    with respx.mock(base_url="https://models.inference.ai.azure.com") as mock:
        mock.post("/chat/completions").mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": "not json"}}]}
            )
        )
        payload, _ = await backend.chat(model="m", system_prompt="s", fallback={"fb": True})
    assert payload == {"fb": True}


@pytest.mark.asyncio
async def test_list_models_returns_catalog(backend: GitHubBackend) -> None:
    models = await backend.list_models()
    assert "gpt-4o-mini" in models
    assert "claude-3-5-sonnet" in models
    assert len(models) > 5


@pytest.mark.asyncio
async def test_aclose(backend: GitHubBackend) -> None:
    await backend.aclose()


def test_default_endpoint() -> None:
    b = GitHubBackend(api_key="x")
    assert "models.inference.ai.azure.com" in str(b._http.base_url)


def test_is_chat_backend() -> None:
    from mast.agents.protocols import ChatBackend

    b = GitHubBackend(api_key="x")
    assert isinstance(b, ChatBackend)
