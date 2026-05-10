"""Integration tests for the full De Bono pipeline with Ollama mocked via respx."""

from __future__ import annotations

import json
from collections.abc import Generator

import httpx
import pytest
import respx

from mast._upstream import ThoughtData
from mast.agents.base import OllamaClient
from mast.agents.debono import DebonoOrchestrator
from mast.validation.orchestrator import ValidationOrchestrator
from mast.validation.schemas import Verdict

MOCK_HAT_RESPONSES = {
    "blue_open": {
        "working_document": "## Objective\nFind optimal solution for X.\n## Constraints\nMust be fast.",  # noqa: E501
        "objective": "Find optimal solution for X",
        "rationale": "defined scope",
    },
    "white": {  # noqa: E501
        "modified_document": (  # noqa: E501
            "## Objective\nFind optimal solution for X.\n## Constraints\nMust be fast.\n\n"
            "## Facts\n- Fact A\n- Fact B\n\n## Unknowns\n- Missing data Y"
        ),
        "facts_identified": ["Fact A", "Fact B"],
        "unknowns": ["Missing data Y"],
        "rationale": "extracted from context",
    },
    "green": {  # noqa: E501
        "modified_document": (  # noqa: E501
            "## Objective\nFind optimal solution for X.\n\n"
            "## Alternatives\n1. Approach A: use caching\n2. Approach B: async processing\n3. Approach C: batch optimization"  # noqa: E501
        ),
        "alternatives": [  # noqa: E501
            "Approach A: use caching",
            "Approach B: async processing",
            "Approach C: batch optimization",
        ],
        "rationale": "used lateral thinking",
    },
    "yellow": {  # noqa: E501
        "modified_document": (  # noqa: E501
            "## Objective\nFind optimal solution for X.\n\n"
            "## Benefits & Value\n- CERTAIN: caching reduces latency\n"
            "LIKELY: async improves throughput\n- POSSIBLE: batch reduces costs"
        ),
        "benefits": ["CERTAIN: caching reduces latency", "LIKELY: async improves throughput"],
        "rationale": "identified key value drivers",
    },
    "black": {  # noqa: E501
        "modified_document": (  # noqa: E501
            "## Objective\nFind optimal solution for X.\n\n"
            "## Risks & Mitigations\n- HIGH: cache invalidation complexity\n"
            "- MEDIUM: async increases debugging difficulty"
        ),
        "risks": ["HIGH: cache invalidation", "MEDIUM: async debugging"],
        "mitigations": ["TTL-based expiry", "structured logging"],
        "rationale": "found critical risks",
    },
    "red": {  # noqa: E501
        "modified_document": (  # noqa: E501
            "## Objective\nFind optimal solution for X.\n\n"
            "## Intuition Check\nThis feels solid but the async approach needs careful error handling."  # noqa: E501
        ),
        "gut_feeling": "This feels solid but needs careful error handling.",
        "rationale": "intuition check",
    },
    "blue_close": {
        "verdict": "accept",
        "confidence": 0.85,
        "rationale": "All risks have mitigations, benefits are clear.",
        "suggested_revision": None,
        "suggested_revision_mode": None,
        "final_document": "## Final Solution\nUse caching with TTL + async processing.",
        "evidence_seen": ["CERTAIN: caching reduces latency", "HIGH: cache invalidation"],
    },
}

HAT_NAMES = ["blue_open", "white", "green", "yellow", "black", "red", "blue_close"]
HAT_NAMES_NO_RED = ["blue_open", "white", "green", "yellow", "black", "blue_close"]


@pytest.fixture
def mock_ollama() -> Generator[respx.MockRouter, None, None]:
    with respx.mock(base_url="http://localhost:11434") as mock:
        yield mock


def _mock_ollama_chat(content: str) -> dict[str, object]:
    return {
        "model": "test-model",
        "message": {"role": "assistant", "content": content},
        "done": True,
    }


def _setup_sequential_mocks(mock_ollama: respx.MockRouter, hat_names: list[str]) -> None:
    call_count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        idx = call_count[0]
        call_count[0] += 1
        if idx >= len(hat_names):
            return httpx.Response(500)
        hat = hat_names[idx]
        content = json.dumps(MOCK_HAT_RESPONSES[hat])
        return httpx.Response(200, json=_mock_ollama_chat(content))

    mock_ollama.post("/api/chat").mock(side_effect=handler)


@pytest.mark.asyncio
async def test_debono_orchestrator_full_flow(mock_ollama: respx.MockRouter) -> None:
    _setup_sequential_mocks(mock_ollama, HAT_NAMES)

    client = OllamaClient()
    orchestrator = DebonoOrchestrator(client)
    result, blue_close = await orchestrator.run(
        thought="We should implement feature X using caching.",
        thought_number=1,
        total_thoughts=5,
        history_summary="#1: Initial thought",
    )

    assert len(result.hats) == 7
    assert [h.hat.value for h in result.hats] == HAT_NAMES
    assert result.total_latency_ms > 0
    assert blue_close["verdict"] == "accept"
    assert blue_close["confidence"] == 0.85

    await client.aclose()


@pytest.mark.asyncio
async def test_debono_orchestrator_with_skip_red(mock_ollama: respx.MockRouter) -> None:
    _setup_sequential_mocks(mock_ollama, HAT_NAMES_NO_RED)

    client = OllamaClient()
    orchestrator = DebonoOrchestrator(client)
    result, blue_close = await orchestrator.run(
        thought="Implement feature X.",
        thought_number=1,
        total_thoughts=3,
        history_summary="",
        skip_red=True,
    )

    assert len(result.hats) == 6
    assert [h.hat.value for h in result.hats] == HAT_NAMES_NO_RED

    await client.aclose()


@pytest.mark.asyncio
async def test_debono_hats_progressive_document(mock_ollama: respx.MockRouter) -> None:
    _setup_sequential_mocks(mock_ollama, HAT_NAMES)

    client = OllamaClient()
    orchestrator = DebonoOrchestrator(client)
    result, _ = await orchestrator.run(
        thought="Feature X with caching.",
        thought_number=1,
        total_thoughts=3,
        history_summary="",
    )

    assert len(result.hats) == 7
    assert result.total_latency_ms > 0

    await client.aclose()


@pytest.mark.asyncio
async def test_debono_orchestrator_timeout_fallback(mock_ollama: respx.MockRouter) -> None:
    mock_ollama.post("/api/chat").mock(side_effect=httpx.TimeoutException("timeout"))

    client = OllamaClient()
    orchestrator = DebonoOrchestrator(client)
    result, blue_close = await orchestrator.run(
        thought="Test thought that times out.",
        thought_number=1,
        total_thoughts=3,
        history_summary="",
    )

    assert len(result.hats) == 7
    for hat in result.hats:
        assert hat.rationale == "parse_failed"

    await client.aclose()


@pytest.mark.asyncio
async def test_debono_full_pipeline_through_orchestrator(mock_ollama: respx.MockRouter) -> None:
    _setup_sequential_mocks(mock_ollama, HAT_NAMES)

    orchestrator = ValidationOrchestrator()
    thought = ThoughtData(
        thought="Implement feature X using caching.",
        thought_number=1,
        total_thoughts=5,
        next_thought_needed=True,
    )
    upstream_response = {
        "thoughtNumber": 1,
        "totalThoughts": 5,
        "nextThoughtNeeded": True,
        "branches": [],
        "thoughtHistoryLength": 1,
    }

    result = await orchestrator.run(
        thought=thought,
        history=[],
        upstream_response=upstream_response,
        mode="debono",
        trace_id="test-debono",
    )

    assert result.debono is not None
    assert len(result.debono.hats) == 7
    assert result.debono.hats[0].hat.value == "blue_open"
    assert result.debono.hats[1].hat.value == "white"
    assert result.debono.hats[3].hat.value == "yellow"
    assert result.debono.hats[6].hat.value == "blue_close"
    assert result.verdict == Verdict.ACCEPT
    assert result.confidence == 0.85

    result_dict = result.to_dict()
    assert "debono" in result_dict
    assert result_dict["verdict"] == "accept"

    await orchestrator.aclose()


@pytest.mark.asyncio
async def test_debono_skip_validation_on_short_thought(mock_ollama: respx.MockRouter) -> None:
    orchestrator = ValidationOrchestrator()
    thought = ThoughtData(
        thought="OK",  # shorter than MAST_SKIP_THRESHOLD_CHARS=20
        thought_number=1,
        total_thoughts=1,
        next_thought_needed=False,
    )
    upstream_response = {
        "thoughtNumber": 1,
        "totalThoughts": 1,
        "nextThoughtNeeded": False,
        "branches": [],
        "thoughtHistoryLength": 1,
    }

    result = await orchestrator.run(
        thought=thought,
        history=[],
        upstream_response=upstream_response,
        mode="debono",
        trace_id="test-short",
    )

    # Short thought: should skip validation
    assert result.debono is None
    assert result.verdict is None

    await orchestrator.aclose()
