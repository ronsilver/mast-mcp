"""Concurrent run() stress test — verify no verdict crossover."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from mast._upstream import ThoughtData
from mast.agents.protocols import ChatBackend
from mast.validation.orchestrator import ValidationOrchestrator


def _extract_thought_id(prompt: str) -> str:
    return prompt.split("THOUGHT_ID=")[1].split()[0]


class _TwoStageBackend(ChatBackend):
    """Backend that responds differently based on the schema (Critic vs Judge)."""

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
        thought_id = _extract_thought_id(system_prompt)
        await asyncio.sleep(0.001)
        if json_schema is not None and "JudgeResponse" in json_schema.get("title", ""):
            return {
                "verdict": "accept",
                "confidence": 0.9,
                "rationale": f"judge-{thought_id}",
                "suggestedRevision": f"rev-{thought_id}",
            }, 1
        return {
            "issues": [],
            "strengths": [],
            "summary": f"summary-{thought_id}",
        }, 1

    async def list_models(self) -> list[str]:
        return ["stub"]

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_50_concurrent_runs_no_verdict_crossover() -> None:
    """
    Spawn 50 concurrent run() calls with distinct thoughts.

    Each call must receive its own critic + judge response, not a sibling's.
    """
    from mast.agents.critic import CriticAgent
    from mast.agents.judge import JudgeAgent

    stub = _TwoStageBackend()
    orchestrator = ValidationOrchestrator()
    orchestrator._client = stub
    orchestrator._critic = CriticAgent(stub)
    orchestrator._judge = JudgeAgent(stub)

    async def run_one(idx: int) -> str:
        thought = ThoughtData(
            thought=f"thought {idx} THOUGHT_ID={idx} " + "x" * 50,
            thought_number=idx,
            total_thoughts=50,
            next_thought_needed=False,
        )
        upstream: dict[str, object] = {
            "thoughtNumber": idx,
            "totalThoughts": 50,
            "nextThoughtNeeded": False,
            "thoughtHistoryLength": idx,
        }
        result = await orchestrator.run(
            thought=thought,
            history=[],
            upstream_response=upstream,
            mode="debate",
            trace_id=f"trace-{idx}",
        )
        return result.suggested_revision or ""

    results = await asyncio.gather(*(run_one(i) for i in range(50)))
    for idx, result in enumerate(results):
        assert result == f"rev-{idx}", (
            f"Thought {idx} got wrong revision: {result!r} (expected rev-{idx})"
        )


class _CountingBackend(ChatBackend):
    """Backend that returns latency = call_id * 10ms, allowing assertion."""

    def __init__(self) -> None:
        self.call_count = 0
        self.lock = asyncio.Lock()

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
        async with self.lock:
            self.call_count += 1
            call_id = self.call_count
        await asyncio.sleep(0.001)
        return {
            "issues": [],
            "strengths": [],
            "summary": f"summary-{call_id}",
        }, call_id * 10

    async def list_models(self) -> list[str]:
        return ["c"]

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_concurrent_runs_have_independent_critic_latency() -> None:
    """Verify each run()'s critic latency is correctly captured for that run."""
    from mast.agents.critic import CriticAgent
    from mast.agents.judge import JudgeAgent

    backend = _CountingBackend()
    orchestrator = ValidationOrchestrator()
    orchestrator._client = backend
    orchestrator._critic = CriticAgent(backend)
    orchestrator._judge = JudgeAgent(backend)

    async def run_one(idx: int) -> int:
        thought = ThoughtData(
            thought=f"thought {idx} " + "x" * 50,
            thought_number=idx,
            total_thoughts=10,
            next_thought_needed=False,
        )
        upstream: dict[str, object] = {
            "thoughtNumber": idx,
            "totalThoughts": 10,
            "nextThoughtNeeded": False,
            "thoughtHistoryLength": idx,
        }
        result = await orchestrator.run(
            thought=thought,
            history=[],
            upstream_response=upstream,
            mode="validate",
            trace_id=f"trace-{idx}",
        )
        return result.validation.critic_latency_ms  # type: ignore[union-attr]

    latencies = await asyncio.gather(*(run_one(i) for i in range(10)))
    for idx, lat in enumerate(latencies):
        assert lat == (idx + 1) * 10, (
            f"Expected latency {(idx + 1) * 10} for call {idx + 1}, got {lat}"
        )
