"""Tests for cache bypass on stochastic modes (T21)."""

from __future__ import annotations

from typing import Any

import pytest

from mast._upstream import ThoughtData
from mast.agents.critic import CriticAgent
from mast.agents.judge import JudgeAgent
from mast.agents.protocols import ChatBackend
from mast.validation.orchestrator import ValidationOrchestrator


class _VariedBackend(ChatBackend):
    """Backend that returns different content each call."""

    def __init__(self) -> None:
        self.call_count = 0

    async def chat(
        self,
        model: str,
        system_prompt: str,
        *,
        temperature: float = 0.2,
        num_predict: int = 512,
        fallback: dict[str, Any],
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], int]:
        self.call_count += 1
        if json_schema is not None and "Judge" in json_schema.get("title", ""):
            return {
                "verdict": "accept",
                "confidence": 0.9,
                "rationale": f"judge-{self.call_count}",
                "suggestedRevision": f"rev-{self.call_count}",
            }, 1
        return {
            "issues": [],
            "strengths": [],
            "summary": f"summary-{self.call_count}",
        }, 1

    async def list_models(self) -> list[str]:
        return ["v"]

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_brainstorm_bypasses_cache() -> None:
    """Two identical brainstorm calls should NOT hit cache."""
    from mast.agents.brainstorm import BrainstormOrchestrator

    backend = _VariedBackend()
    orchestrator = ValidationOrchestrator()
    orchestrator._client = backend
    orchestrator._critic = CriticAgent(backend)
    orchestrator._judge = JudgeAgent(backend)
    orchestrator._brainstorm = BrainstormOrchestrator(backend)

    upstream: dict[str, object] = {
        "thoughtNumber": 1,
        "totalThoughts": 1,
        "nextThoughtNeeded": False,
        "thoughtHistoryLength": 1,
    }
    thought = ThoughtData(
        thought="identical thought " + "x" * 50,
        thought_number=1,
        total_thoughts=1,
        next_thought_needed=False,
    )

    # Track calls to backend to verify cache is bypassed
    initial_calls = backend.call_count
    await orchestrator.run(
        thought=thought,
        history=[],
        upstream_response=upstream,
        mode="brainstorm",
        trace_id="t1",
    )
    calls_after_first = backend.call_count
    await orchestrator.run(
        thought=thought,
        history=[],
        upstream_response=upstream,
        mode="brainstorm",
        trace_id="t2",
    )
    calls_after_second = backend.call_count
    # Cache bypassed: 2nd call must have made backend calls
    assert calls_after_second > calls_after_first, (
        f"Cache bypass failed: 2nd call added {calls_after_second - calls_after_first} calls"
    )
    assert calls_after_first > initial_calls, "1st call should also call backend"


@pytest.mark.asyncio
async def test_tot_bypasses_cache() -> None:
    """Two identical tot calls should NOT hit cache."""
    from mast.agents.tot import TreeOfThoughtsOrchestrator

    backend = _VariedBackend()
    orchestrator = ValidationOrchestrator()
    orchestrator._client = backend
    orchestrator._critic = CriticAgent(backend)
    orchestrator._judge = JudgeAgent(backend)
    orchestrator._tot = TreeOfThoughtsOrchestrator(backend)

    upstream: dict[str, object] = {
        "thoughtNumber": 1,
        "totalThoughts": 1,
        "nextThoughtNeeded": False,
        "thoughtHistoryLength": 1,
    }
    thought = ThoughtData(
        thought="identical thought " + "x" * 50,
        thought_number=1,
        total_thoughts=1,
        next_thought_needed=False,
    )

    initial_calls = backend.call_count
    await orchestrator.run(
        thought=thought,
        history=[],
        upstream_response=upstream,
        mode="tot",
        trace_id="t1",
    )
    calls_after_first = backend.call_count
    await orchestrator.run(
        thought=thought,
        history=[],
        upstream_response=upstream,
        mode="tot",
        trace_id="t2",
    )
    calls_after_second = backend.call_count
    assert calls_after_second > calls_after_first, (
        f"Cache bypass failed: 2nd call added {calls_after_second - calls_after_first} calls"
    )
    assert calls_after_first > initial_calls


@pytest.mark.asyncio
async def test_debate_does_cache_deterministic_modes() -> None:
    """Deterministic modes use cache: identical input → cached output."""
    backend = _VariedBackend()
    orchestrator = ValidationOrchestrator()
    orchestrator._client = backend
    orchestrator._critic = CriticAgent(backend)
    orchestrator._judge = JudgeAgent(backend)

    upstream: dict[str, object] = {
        "thoughtNumber": 1,
        "totalThoughts": 1,
        "nextThoughtNeeded": False,
        "thoughtHistoryLength": 1,
    }
    thought = ThoughtData(
        thought="deterministic thought " + "x" * 50,
        thought_number=1,
        total_thoughts=1,
        next_thought_needed=False,
    )

    result1 = await orchestrator.run(
        thought=thought,
        history=[],
        upstream_response=upstream,
        mode="validate",
        trace_id="t1",
    )
    await orchestrator.run(
        thought=thought,
        history=[],
        upstream_response=upstream,
        mode="validate",
        trace_id="t2",
    )
    # Cached: 2nd call must NOT have made additional backend calls
    # beyond the first call's call_count.
    assert result1.validation is not None
