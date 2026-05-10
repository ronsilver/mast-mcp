"""Validation orchestrator — assembles Critic + Judge or debono pipeline based on mode."""

from __future__ import annotations

import hashlib

import structlog

from mast._upstream import ThoughtData
from mast.agents.base import OllamaClient
from mast.agents.critic import CriticAgent
from mast.agents.debono import DebonoContext, DebonoOrchestrator
from mast.agents.judge import JudgeAgent
from mast.config import config
from mast.validation.cache import ValidationCache
from mast.validation.schemas import (
    MastOutput,
    ValidationResult,
    Verdict,
)

log = structlog.get_logger(__name__)


def _build_history_summary(
    history: list[ThoughtData],
    window: int,
    max_tokens: int,
) -> str:
    """Compress history to a string for the prompt context.

    Last `window` thoughts shown in full; older ones compressed to one line each.
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


def _cache_key(
    thought: str,
    critic_model: str,
    judge_model: str,
    mode: str,
    history_summary: str,
    branch_id: str | None,
) -> str:
    payload = f"{thought}|{critic_model}|{judge_model}|{mode}|{history_summary}|{branch_id}"
    return hashlib.sha256(payload.encode()).hexdigest()


class ValidationOrchestrator:
    """Coordinates Critic and Judge according to the active mode."""

    def __init__(self) -> None:
        self._client = OllamaClient()
        self._critic = CriticAgent(self._client)
        self._judge = JudgeAgent(self._client)
        self._debono: DebonoOrchestrator | None = None
        self._cache: ValidationCache[MastOutput] = ValidationCache(
            ttl_seconds=config.mast_cache_ttl_s
        )

    async def _run_debono(
        self,
        thought: ThoughtData,
        history_summary: str,
        critic_model: str | None,
        judge_model: str | None,
    ) -> None:
        if self._debono is None:
            self._debono = DebonoOrchestrator(self._client)
        debono_result, blue_close = await self._debono.run(
            thought=thought.thought,
            ctx=DebonoContext(
                thought_number=thought.thought_number,
                total_thoughts=thought.total_thoughts,
                history_summary=history_summary,
                is_revision=thought.is_revision,
                revises_thought=thought.revises_thought,
                branch_id=thought.branch_id,
                branch_from=thought.branch_from_thought,
            ),
            primary_model=critic_model,
            creative_model=judge_model,
        )
        self._debono_result = debono_result
        self._debono_blue_close = blue_close

    async def _run_critic(
        self,
        thought: ThoughtData,
        history_summary: str,
        effective_critic: str,
    ) -> None:
        critic_response, critic_latency = await self._critic.critique(
            thought=thought.thought,
            thought_number=thought.thought_number,
            total_thoughts=thought.total_thoughts,
            history_summary=history_summary,
            is_revision=thought.is_revision,
            revises_thought=thought.revises_thought,
            branch_id=thought.branch_id,
            branch_from=thought.branch_from_thought,
            model=effective_critic,
        )
        self._critic_response = critic_response
        self._critic_latency = critic_latency

    async def _run_judge(
        self,
        thought: ThoughtData,
        history_summary: str,
        mode: str,
        effective_judge: str,
    ) -> None:
        judge_response, judge_latency = await self._judge.judge(
            thought=thought.thought,
            thought_number=thought.thought_number,
            total_thoughts=thought.total_thoughts,
            history_summary=history_summary,
            critique=self._critic_response,
            mode=mode,
            is_revision=thought.is_revision,
            model=effective_judge,
        )
        self._judge_response = judge_response
        self._judge_latency = judge_latency

    async def run(
        self,
        thought: ThoughtData,
        history: list[ThoughtData],
        upstream_response: dict[str, object],
        mode: str,
        trace_id: str,
        *,
        critic_model: str | None = None,
        judge_model: str | None = None,
    ) -> MastOutput:
        effective_critic = critic_model or config.critic_model
        effective_judge = judge_model or config.judge_model

        base = MastOutput(
            thought_number=upstream_response["thoughtNumber"],  # type: ignore[arg-type]
            total_thoughts=upstream_response["totalThoughts"],  # type: ignore[arg-type]
            next_thought_needed=upstream_response["nextThoughtNeeded"],  # type: ignore[arg-type]
            branches=upstream_response.get("branches", []),  # type: ignore[arg-type]
            thought_history_length=upstream_response["thoughtHistoryLength"],  # type: ignore[arg-type]
        )

        if mode == "passive":
            return base

        if len(thought.thought.strip()) < config.mast_skip_threshold_chars:
            log.info("validation_skipped_short_thought", trace_id=trace_id)
            return base

        history_summary = _build_history_summary(
            history,
            window=config.mast_history_window,
            max_tokens=config.mast_history_max_tokens,
        )

        cache_key = _cache_key(
            thought.thought,
            effective_critic,
            effective_judge,
            mode,
            history_summary,
            thought.branch_id,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            log.info("validation_cache_hit", trace_id=trace_id)
            return cached

        # --- De Bono mode ---
        if mode == "debono":
            await self._run_debono(thought, history_summary, critic_model, judge_model)
            debono_result = self._debono_result
            blue_close = self._debono_blue_close

            base.debono = debono_result
            verdict_raw = blue_close.get("verdict", "accept")
            try:
                base.verdict = Verdict(verdict_raw)
            except ValueError:
                base.verdict = Verdict.ACCEPT
            base.confidence = float(blue_close.get("confidence", 0.5))
            base.suggested_revision = blue_close.get("suggested_revision")
            base.judge_model = debono_result.hats[-1].model if debono_result.hats else None
            base.judge_latency_ms = debono_result.total_latency_ms

            log.info(
                "debono_done",
                trace_id=trace_id,
                thought_number=thought.thought_number,
                hats=len(debono_result.hats),
                verdict=base.verdict.value if base.verdict else None,
                total_latency_ms=debono_result.total_latency_ms,
            )
            self._cache.set(cache_key, base)
            return base

        # --- Critic ---
        await self._run_critic(thought, history_summary, effective_critic)
        critic_response = self._critic_response
        critic_latency = self._critic_latency

        log.info(
            "critic_done",
            trace_id=trace_id,
            thought_number=thought.thought_number,
            issues=len(critic_response.issues),
            latency_ms=critic_latency,
            model=effective_critic,
        )

        validation = ValidationResult(
            issues=critic_response.issues,
            strengths=critic_response.strengths,
            critic_model=effective_critic,
            critic_latency_ms=critic_latency,
        )
        base.validation = validation

        if mode == "validate":
            self._cache.set(cache_key, base)
            return base

        # --- Judge ---
        await self._run_judge(thought, history_summary, mode, effective_judge)
        judge_response = self._judge_response
        judge_latency = self._judge_latency

        log.info(
            "judge_done",
            trace_id=trace_id,
            thought_number=thought.thought_number,
            verdict=judge_response.verdict,
            confidence=judge_response.confidence,
            latency_ms=judge_latency,
            model=effective_judge,
        )

        base.verdict = judge_response.verdict
        base.confidence = judge_response.confidence
        base.suggested_revision = judge_response.suggested_revision
        base.judge_model = effective_judge
        base.judge_latency_ms = judge_latency

        self._cache.set(cache_key, base)
        return base

    async def aclose(self) -> None:
        await self._client.aclose()
