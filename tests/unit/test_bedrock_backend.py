"""Tests for BedrockBackend — dual auth (iam via boto3, token via httpx)."""

from __future__ import annotations

import httpx
import pytest
import respx

from mast.agents.backends.bedrock import BedrockBackend
from mast.agents.protocols import ChatBackend

# ---------------------------------------------------------------------------
# Token auth tests (no boto3 required)
# ---------------------------------------------------------------------------


@pytest.fixture
def token_backend() -> BedrockBackend:
    return BedrockBackend(
        region="us-east-1",
        auth_method="token",
        token="bedrock-tok-test",
    )


@pytest.mark.asyncio
async def test_token_auth_uses_bearer_header(token_backend: BedrockBackend) -> None:
    with respx.mock(base_url="https://bedrock-runtime.us-east-1.amazonaws.com") as mock:
        route = mock.post("/model/anthropic.claude-3-5-sonnet-20241022-v2:0/invoke").mock(
            return_value=httpx.Response(
                200,
                json={"content": [{"type": "text", "text": '{"v": 1}'}]},
            )
        )
        payload, _ = await token_backend.chat(
            model="anthropic.claude-3-5-sonnet-20241022-v2:0",
            system_prompt="s",
            fallback={"v": 0},
        )
        sent = route.calls.last.request
        assert sent.headers.get("Authorization") == "Bearer bedrock-tok-test"
        assert payload == {"v": 1}


@pytest.mark.asyncio
async def test_token_auth_tool_use_json(token_backend: BedrockBackend) -> None:
    schema = {"type": "object", "properties": {"verdict": {"type": "string"}}}
    with respx.mock(base_url="https://bedrock-runtime.us-east-1.amazonaws.com") as mock:
        route = mock.post("/model/anthropic.claude-3-5-sonnet-20241022-v2:0/invoke").mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": [
                        {"type": "tool_use", "name": "respond", "input": {"verdict": "accept"}}
                    ]
                },
            )
        )
        payload, _ = await token_backend.chat(
            model="anthropic.claude-3-5-sonnet-20241022-v2:0",
            system_prompt="s",
            fallback={"verdict": "reject"},
            json_schema=schema,
        )
        body = _read_body(route.calls.last.request)
        tools = body.get("tools")
        assert isinstance(tools, list)
        assert tools[0].get("name") == "respond"
        assert body.get("tool_choice") == {"type": "tool", "name": "respond"}
        assert payload == {"verdict": "accept"}


@pytest.mark.asyncio
async def test_token_auth_http_error(token_backend: BedrockBackend) -> None:
    with respx.mock(base_url="https://bedrock-runtime.us-east-1.amazonaws.com") as mock:
        mock.post("/model/anthropic.claude-3-5-sonnet-20241022-v2:0/invoke").mock(
            return_value=httpx.Response(403, text="forbidden")
        )
        payload, _ = await token_backend.chat(
            model="anthropic.claude-3-5-sonnet-20241022-v2:0",
            system_prompt="s",
            fallback={"fb": True},
        )
    assert payload == {"fb": True}


@pytest.mark.asyncio
async def test_token_auth_two_parse_failures(token_backend: BedrockBackend) -> None:
    with respx.mock(base_url="https://bedrock-runtime.us-east-1.amazonaws.com") as mock:
        mock.post("/model/anthropic.claude-3-5-sonnet-20241022-v2:0/invoke").mock(
            return_value=httpx.Response(
                200,
                json={"content": [{"type": "text", "text": "not json"}]},
            )
        )
        payload, _ = await token_backend.chat(
            model="anthropic.claude-3-5-sonnet-20241022-v2:0",
            system_prompt="s",
            fallback={"fb": True},
        )
    assert payload == {"fb": True}


@pytest.mark.asyncio
async def test_token_auth_max_tokens(token_backend: BedrockBackend) -> None:
    with respx.mock(base_url="https://bedrock-runtime.us-east-1.amazonaws.com") as mock:
        route = mock.post("/model/anthropic.claude-3-5-sonnet-20241022-v2:0/invoke").mock(
            return_value=httpx.Response(
                200,
                json={"content": [{"type": "text", "text": "{}"}]},
            )
        )
        await token_backend.chat(
            model="anthropic.claude-3-5-sonnet-20241022-v2:0",
            system_prompt="s",
            fallback={},
            num_predict=1024,
        )
        body = _read_body(route.calls.last.request)
        assert body.get("max_tokens") == 1024


@pytest.mark.asyncio
async def test_token_auth_list_models_returns_catalog(
    token_backend: BedrockBackend,
) -> None:
    models = await token_backend.list_models()
    assert "anthropic.claude-3-5-sonnet-20241022-v2:0" in models


@pytest.mark.asyncio
async def test_token_auth_aclose(token_backend: BedrockBackend) -> None:
    await token_backend.aclose()


# ---------------------------------------------------------------------------
# IAM auth — boto3 unavailable (testing graceful degradation)
# ---------------------------------------------------------------------------


def test_iam_auth_without_boto3_marks_unavailable() -> None:
    """When boto3 import fails, backend marks itself unavailable but instantiates."""
    backend = BedrockBackend(
        region="us-east-1",
        auth_method="iam",
    )
    assert backend._boto3_unavailable is True
    assert backend._boto3_client is None


def test_unknown_auth_method_raises() -> None:
    with pytest.raises(ValueError, match="BEDROCK_AUTH_METHOD"):
        BedrockBackend(region="us-east-1", auth_method="oauth")


def test_token_auth_without_token_succeeds_init() -> None:
    """Init succeeds; token error raised on chat when invoke attempts."""
    backend = BedrockBackend(region="us-east-1", auth_method="token")
    assert backend._token is None
    assert backend._http is not None


def test_is_chat_backend() -> None:
    b = BedrockBackend(region="us-east-1", auth_method="token", token="x")
    assert isinstance(b, ChatBackend)


def test_default_model_anthropic() -> None:
    b = BedrockBackend(region="us-east-1", auth_method="token", token="x")
    assert "anthropic.claude-3-5-sonnet" in b._default_model


def _read_body(req: httpx.Request) -> dict[str, object]:
    import json

    result: dict[str, object] = json.loads(req.content)
    return result
