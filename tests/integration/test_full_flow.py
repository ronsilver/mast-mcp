"""Integration tests for the full MCP flow with Ollama mocked via respx."""

from __future__ import annotations

import json
from collections.abc import Generator

import httpx
import pytest
import respx

from mast._upstream import SequentialThinkingServer
from mast.agents.base import OllamaClient
from mast.agents.critic import CriticAgent
from mast.agents.judge import JudgeAgent
from mast.config import config
from mast.validation.schemas import Verdict

CRITIC_JSON = json.dumps(
    {
        "issues": [
            {
                "severity": "medium",
                "type": "assumption",
                "detail": "Assumes Redis is always available",
            }
        ],
        "strengths": ["Clear scope definition"],
        "summary": "One assumption issue",
    }
)

JUDGE_JSON = json.dumps(
    {
        "verdict": "revise",
        "confidence": 0.8,
        "rationale": "Assumption about Redis needs to be addressed",
        "suggestedRevision": "Use Redis with fallback to in-memory cache for resilience",
    }
)


@pytest.fixture
def mock_ollama() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url="http://localhost:11434") as mock:
        yield mock


@pytest.fixture
def ollama_client() -> OllamaClient:
    return OllamaClient()


def _mock_chat_response(content: str) -> dict[str, object]:
    return {
        "model": "test-model",
        "message": {"role": "assistant", "content": content},
        "done": True,
    }


@pytest.mark.asyncio
async def test_critic_agent_full_flow(
    mock_ollama: respx.MockRouter, ollama_client: OllamaClient
) -> None:
    mock_ollama.post("/api/chat").mock(
        return_value=httpx.Response(200, json=_mock_chat_response(CRITIC_JSON))
    )

    agent = CriticAgent(ollama_client)
    result, latency_ms = await agent.critique(
        thought="Use Redis for session caching",
        thought_number=2,
        total_thoughts=5,
        history_summary="#1: Define the problem scope",
    )

    assert len(result.issues) == 1
    assert result.issues[0].type.value == "assumption"
    assert latency_ms >= 0
    await ollama_client.aclose()


@pytest.mark.asyncio
async def test_judge_agent_full_flow(
    mock_ollama: respx.MockRouter, ollama_client: OllamaClient
) -> None:
    mock_ollama.post("/api/chat").mock(
        return_value=httpx.Response(200, json=_mock_chat_response(JUDGE_JSON))
    )

    from mast.validation.schemas import CriticIssue, CriticResponse, IssueSeverity, IssueType

    critic_resp = CriticResponse(
        issues=[
            CriticIssue(severity=IssueSeverity.MEDIUM, type=IssueType.ASSUMPTION, detail="...")
        ],
        summary="One issue",
    )

    agent = JudgeAgent(ollama_client)
    result, latency_ms = await agent.judge(
        thought="Use Redis for session caching",
        thought_number=2,
        total_thoughts=5,
        history_summary="#1: Define scope",
        critique=critic_resp,
        mode="debate",
    )

    assert result.verdict == Verdict.REVISE
    assert result.suggested_revision is not None
    await ollama_client.aclose()


@pytest.mark.asyncio
async def test_ollama_timeout_fallback(
    mock_ollama: respx.MockRouter, ollama_client: OllamaClient
) -> None:
    """On timeout, agent should return fallback (not raise)."""
    mock_ollama.post("/api/chat").mock(side_effect=httpx.TimeoutException("timeout"))

    agent = CriticAgent(ollama_client)
    result, _ = await agent.critique(
        thought="Some thought",
        thought_number=1,
        total_thoughts=1,
        history_summary="",
    )
    assert result.issues == []
    await ollama_client.aclose()


@pytest.mark.asyncio
async def test_ollama_invalid_json_fallback(
    mock_ollama: respx.MockRouter, ollama_client: OllamaClient
) -> None:
    """On non-JSON response, agent should return fallback."""
    mock_ollama.post("/api/chat").mock(
        return_value=httpx.Response(200, json=_mock_chat_response("not valid json at all"))
    )

    agent = CriticAgent(ollama_client)
    result, _ = await agent.critique(
        thought="Some thought",
        thought_number=1,
        total_thoughts=1,
        history_summary="",
    )
    assert result.issues == []
    await ollama_client.aclose()


@pytest.mark.asyncio
async def test_ollama_cloud_auth_header() -> None:
    """When OLLAMA_CLOUD_API_KEY is set, Authorization header is sent."""
    saved = config.ollama_cloud_api_key
    config.ollama_cloud_api_key = "sk-test-key-for-auth"

    from mast.agents.base import OllamaClient as CloudClient

    client = CloudClient()

    try:
        with respx.mock(base_url="http://localhost:11434") as mock:
            mock.post("/api/chat").mock(
                return_value=httpx.Response(200, json=_mock_chat_response(CRITIC_JSON))
            )
            agent = CriticAgent(client)
            result, _ = await agent.critique(
                thought="Test cloud auth",
                thought_number=1,
                total_thoughts=1,
                history_summary="",
            )
            assert len(result.issues) == 1
            assert mock.calls.last is not None
            request = mock.calls.last.request
            assert request.headers.get("Authorization") == "Bearer sk-test-key-for-auth"
    finally:
        await client.aclose()
        config.ollama_cloud_api_key = saved


def test_upstream_server_concurrent_thoughts() -> None:
    """Multiple sequential thoughts don't corrupt history."""
    server = SequentialThinkingServer()
    for i in range(1, 6):
        resp = server.process_thought(
            {
                "thought": f"Thought {i}",
                "thoughtNumber": i,
                "totalThoughts": 5,
                "nextThoughtNeeded": i < 5,
            }
        )
    assert resp["thoughtHistoryLength"] == 5
    assert len(server.thought_history) == 5
