"""Validation orchestrator — assembles Critic + Judge based on mode."""
from __future__ import annotations

import hashlib

import structlog

from mast._upstream import ThoughtData
from mast.agents.base import OllamaClient
from mast.agents.critic import CriticAgent
from mast.agents.judge import JudgeAgent
from mast.config import config
from mast.validation.cache import ValidationCache
from mast.validation.schemas import (
    MastOutput,
    ValidationResult,
)

log = structlog.get_logger(__name__)

_SKIP_THRESHOLD_CHARS = 20  # thoughts shorter than this are skipped


def _build_history_summary(
    history: list[ThoughtData],
    window: int,
    max_tokens: int,
) -> str:
    """
    Compress history to a string:
    - Last `window` thoughts shown in full.
    - Older ones compressed to one line each.
    Total capped at ~max_tokens (estimated by chars/4).
    """
    max_chars = max_tokens * 4
    if not history:
        return "(no previous thoughts)"

    recent = history[-window:]
    older = history[:-window]

    lines: list[str] = []

    for t in older:
        lines.append(f"#{t.thought_number}: {t.thought[:80]}{'...' if len(t.thought) > 80 else ''}")

    for t in recent:
        lines.append(f"#{t.thought_number} (full):\n{t.thought}")

    summary = "\n".join(lines)
    if len(summary) > max_chars:
        summary = summary[-max_chars:]
    return summary


def _cache_key(thought: str, critic_model: str, judge_model: str, mode: str) -> str:
    payload = f"{thought}|{critic_model}|{judge_model}|{mode}"
    return hashlib.sha256(payload.encode()).hexdigest()


class ValidationOrchestrator:
    """Coordinates Critic and Judge according to the active mode."""

    def __init__(self) -> None:
        self._client = OllamaClient()
        self._critic = CriticAgent(self._client)
        self._judge = JudgeAgent(self._client)
        self._cache: ValidationCache[MastOutput] = ValidationCache(
            ttl_seconds=config.mast_cache_ttl_s
        )

    async def run(
        self,
        thought: ThoughtData,
        history: list[ThoughtData],
        upstream_response: dict[str, object],
        mode: str,
        trace_id: str,
    ) -> MastOutput:
        base = MastOutput(
            thought_number=upstream_response["thoughtNumber"],  # type: ignore[arg-type]
            total_thoughts=upstream_response["totalThoughts"],  # type: ignore[arg-type]
            next_thought_needed=upstream_response["nextThoughtNeeded"],  # type: ignore[arg-type]
            branches=upstream_response.get("branches", []),  # type: ignore[arg-type]
            thought_history_length=upstream_response["thoughtHistoryLength"],  # type: ignore[arg-type]
        )

        if mode == "passive":
            return base

        # Skip very short / meta thoughts
        if len(thought.thought.strip()) < _SKIP_THRESHOLD_CHARS:
            log.info("validation_skipped_short_thought", trace_id=trace_id)
            return base

        cache_key = _cache_key(
            thought.thought, config.critic_model, config.judge_model, mode
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            log.info("validation_cache_hit", trace_id=trace_id)
            return cached

        history_summary = _build_history_summary(
            history,
            window=config.mast_history_window,
            max_tokens=config.mast_history_max_tokens,
        )

        # --- Critic ---
        critic_response, critic_latency = await self._critic.critique(
            thought=thought.thought,
            thought_number=thought.thought_number,
            total_thoughts=thought.total_thoughts,
            history_summary=history_summary,
            is_revision=thought.is_revision,
            revises_thought=thought.revises_thought,
            branch_id=thought.branch_id,
            branch_from=thought.branch_from_thought,
        )

        log.info(
            "critic_done",
            trace_id=trace_id,
            thought_number=thought.thought_number,
            issues=len(critic_response.issues),
            latency_ms=critic_latency,
        )

        validation = ValidationResult(
            issues=critic_response.issues,
            strengths=critic_response.strengths,
            critic_model=config.critic_model,
            critic_latency_ms=critic_latency,
        )
        base.validation = validation

        if mode == "validate":
            self._cache.set(cache_key, base)
            return base

        # --- Judge ---
        judge_response, judge_latency = await self._judge.judge(
            thought=thought.thought,
            thought_number=thought.thought_number,
            total_thoughts=thought.total_thoughts,
            history_summary=history_summary,
            critique=critic_response,
            mode=mode,
        )

        log.info(
            "judge_done",
            trace_id=trace_id,
            thought_number=thought.thought_number,
            verdict=judge_response.verdict,
            confidence=judge_response.confidence,
            latency_ms=judge_latency,
        )

        base.verdict = judge_response.verdict
        base.confidence = judge_response.confidence
        base.suggested_revision = judge_response.suggested_revision
        base.judge_model = config.judge_model
        base.judge_latency_ms = judge_latency

        self._cache.set(cache_key, base)
        return base

    async def aclose(self) -> None:
        await self._client.aclose()
