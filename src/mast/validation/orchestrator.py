"""Validation orchestrator — assembles Critic + Judge or debono pipeline based on mode."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import structlog

from mast._upstream import ThoughtData
from mast.agents.actor_critic import ActorCriticOrchestrator
from mast.agents.brainstorm import BrainstormOrchestrator
from mast.agents.critic import CriticAgent
from mast.agents.debono import DebonoContext, DebonoOrchestrator
from mast.agents.judge import JudgeAgent
from mast.agents.kalman import KalmanConvergenceLayer
from mast.agents.registry import get_backend
from mast.agents.tot import TreeOfThoughtsOrchestrator
from mast.config import config
from mast.validation.cache import ValidationCache
from mast.validation.schemas import (
    CriticResponse,
    DebonoResult,
    JudgeResponse,
    MastOutput,
    ValidationResult,
    Verdict,
    WorkflowResult,
    WorkflowStageResult,
)

log = structlog.get_logger(__name__)


@dataclass
class _WorkflowStageCtx:
    stage_mode: str
    current_thought: str
    thought: ThoughtData
    history: list[ThoughtData]
    upstream_response: dict[str, object]
    trace_id: str
    critic_model: str | None = None
    judge_model: str | None = None


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
    """Coordinates Critic, Judge, and new reasoning modes."""

    def __init__(self) -> None:
        """Initialize orchestrator with backend and all agent instances."""
        self._client = get_backend(config.mast_provider)
        self._critic = CriticAgent(self._client)
        self._judge = JudgeAgent(self._client)
        self._debono: DebonoOrchestrator | None = None
        self._actor_critic = ActorCriticOrchestrator(self._client)
        self._brainstorm = BrainstormOrchestrator(self._client)
        self._tot = TreeOfThoughtsOrchestrator(self._client)
        self._kalman = KalmanConvergenceLayer(self._client)
        self._cache: ValidationCache[MastOutput] = ValidationCache(
            ttl_seconds=config.mast_cache_ttl_s
        )

    async def _run_debono(
        self,
        thought: ThoughtData,
        history_summary: str,
        critic_model: str | None,
        judge_model: str | None,
    ) -> tuple[DebonoResult, dict[str, object]]:
        if self._debono is None:
            self._debono = DebonoOrchestrator(self._client)
        return await self._debono.run(
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

    async def _run_critic(
        self,
        thought: ThoughtData,
        history_summary: str,
        effective_critic: str,
    ) -> tuple[CriticResponse, int]:
        from mast.agents.critic import CritiqueRequest

        return await self._critic.critique(
            CritiqueRequest(
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
        )

    async def _run_judge(
        self,
        thought: ThoughtData,
        history_summary: str,
        mode: str,
        effective_judge: str,
        critique: CriticResponse,
    ) -> tuple[JudgeResponse, int]:
        from mast.agents.judge import JudgeRequest

        return await self._judge.judge(
            JudgeRequest(
                thought=thought.thought,
                thought_number=thought.thought_number,
                total_thoughts=thought.total_thoughts,
                history_summary=history_summary,
                critique=critique,
                mode=mode,
                is_revision=thought.is_revision,
                model=effective_judge,
            )
        )

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
        bypass_cache = mode in ("brainstorm", "tot")
        if not bypass_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                log.info("validation_cache_hit", trace_id=trace_id)
                return cached

        result = await self._dispatch_mode(
            mode=mode,
            thought=thought,
            history=history,
            history_summary=history_summary,
            upstream_response=upstream_response,
            trace_id=trace_id,
            base=base,
            cache_key=cache_key,
            bypass_cache=bypass_cache,
            effective_critic=effective_critic,
            effective_judge=effective_judge,
            critic_model=critic_model,
            judge_model=judge_model,
        )
        if not bypass_cache:
            self._cache.set(cache_key, result)
        return result

    async def _dispatch_mode(
        self,
        mode: str,
        thought: ThoughtData,
        history: list[ThoughtData],
        history_summary: str,
        upstream_response: dict[str, object],
        trace_id: str,
        base: MastOutput,
        cache_key: str,
        bypass_cache: bool,
        effective_critic: str,
        effective_judge: str,
        critic_model: str | None,
        judge_model: str | None,
    ) -> MastOutput:
        if mode == "debono":
            return await self._run_debono_mode(
                thought, history_summary, critic_model, judge_model, base, trace_id
            )
        if mode == "actor_critic":
            return await self._run_actor_critic_mode(
                thought, history_summary, critic_model, judge_model, base, trace_id
            )
        if mode == "brainstorm":
            return await self._run_brainstorm_mode(thought, history_summary, base, trace_id)
        if mode == "tot":
            return await self._run_tot_mode(thought, history_summary, base, trace_id)
        if mode == "kalman":
            return await self._run_kalman_mode(thought, history_summary, base, trace_id)
        if mode == "workflow":
            return await self._run_workflow_mode(
                thought, history, upstream_response, trace_id, base, critic_model, judge_model
            )
        return await self._run_critic_judge_mode(
            thought, history_summary, mode, trace_id, base, effective_critic, effective_judge
        )

    async def _run_debono_mode(
        self,
        thought: ThoughtData,
        history_summary: str,
        critic_model: str | None,
        judge_model: str | None,
        base: MastOutput,
        trace_id: str,
    ) -> MastOutput:
        debono_result, blue_close = await self._run_debono(
            thought, history_summary, critic_model, judge_model
        )
        base.debono = debono_result
        verdict_raw = str(blue_close.get("verdict", "accept"))
        try:
            base.verdict = Verdict(verdict_raw)
        except ValueError:
            base.verdict = Verdict.ACCEPT
        confidence_val = blue_close.get("confidence", 0.5)
        base.confidence = float(confidence_val) if isinstance(confidence_val, (int, float)) else 0.5
        revision_val = blue_close.get("suggested_revision")
        base.suggested_revision = (
            str(revision_val)
            if revision_val is not None and isinstance(revision_val, str)
            else None
        )
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
        return base

    async def _run_actor_critic_mode(
        self,
        thought: ThoughtData,
        history_summary: str,
        critic_model: str | None,
        judge_model: str | None,
        base: MastOutput,
        trace_id: str,
    ) -> MastOutput:
        ac_result = await self._actor_critic.run(
            thought=thought.thought,
            thought_number=thought.thought_number,
            total_thoughts=thought.total_thoughts,
            history_summary=history_summary,
            critic_model=critic_model,
            judge_model=judge_model,
        )
        base.actor_critic = ac_result
        base.verdict = Verdict.ACCEPT if ac_result.converged else Verdict.REVISE
        base.confidence = 1.0 if ac_result.converged else 0.5
        base.suggested_revision = ac_result.final_thought
        log.info(
            "actor_critic_done",
            trace_id=trace_id,
            thought_number=thought.thought_number,
            total_rounds=ac_result.total_rounds,
            converged=ac_result.converged,
        )
        return base

    async def _run_brainstorm_mode(
        self,
        thought: ThoughtData,
        history_summary: str,
        base: MastOutput,
        trace_id: str,
    ) -> MastOutput:
        bs_result = await self._brainstorm.run(
            thought=thought.thought,
            thought_number=thought.thought_number,
            total_thoughts=thought.total_thoughts,
            history_summary=history_summary,
        )
        base.brainstorm = bs_result
        base.verdict = Verdict.REVISE
        base.suggested_revision = bs_result.synthesis
        log.info(
            "brainstorm_done",
            trace_id=trace_id,
            thought_number=thought.thought_number,
            ideas=len(bs_result.ideas),
        )
        return base

    async def _run_tot_mode(
        self,
        thought: ThoughtData,
        history_summary: str,
        base: MastOutput,
        trace_id: str,
    ) -> MastOutput:
        tot_result = await self._tot.run(
            thought=thought.thought,
            thought_number=thought.thought_number,
            total_thoughts=thought.total_thoughts,
            history_summary=history_summary,
        )
        base.tot = tot_result
        if tot_result.selected_branch:
            base.verdict = Verdict.REVISE
            base.suggested_revision = tot_result.selected_branch.next_step
        log.info(
            "tot_done",
            trace_id=trace_id,
            thought_number=thought.thought_number,
            branches=len(tot_result.branches),
            selected=tot_result.selected_branch is not None,
        )
        return base

    async def _run_kalman_mode(
        self,
        thought: ThoughtData,
        history_summary: str,
        base: MastOutput,
        trace_id: str,
    ) -> MastOutput:
        k_result = await self._kalman.run(
            thought=thought.thought,
            thought_number=thought.thought_number,
            total_thoughts=thought.total_thoughts,
            history_summary=history_summary,
        )
        base.kalman = k_result
        base.verdict = k_result.verdict
        base.confidence = k_result.confidence
        log.info(
            "kalman_done",
            trace_id=trace_id,
            thought_number=thought.thought_number,
            x=round(k_result.x_final, 3),
            converged=k_result.converged,
            verdict=k_result.verdict.value,
        )
        return base

    async def _run_workflow_mode(
        self,
        thought: ThoughtData,
        history: list[ThoughtData],
        upstream_response: dict[str, object],
        trace_id: str,
        base: MastOutput,
        critic_model: str | None,
        judge_model: str | None,
    ) -> MastOutput:
        stages = config.workflow_stages
        workflow_result = await self._run_workflow(
            thought,
            history,
            upstream_response,
            stages,
            trace_id,
            critic_model=critic_model,
            judge_model=judge_model,
        )
        base.workflow = workflow_result
        if workflow_result.stages:
            last = workflow_result.stages[-1]
            base.verdict = last.verdict
            base.confidence = last.confidence
            base.suggested_revision = last.suggested_revision
        log.info(
            "workflow_done",
            trace_id=trace_id,
            thought_number=thought.thought_number,
            stages=len(workflow_result.stages),
            final_verdict=workflow_result.stages[-1].verdict.value
            if workflow_result.stages
            else None,
        )
        return base

    async def _run_critic_judge_mode(
        self,
        thought: ThoughtData,
        history_summary: str,
        mode: str,
        trace_id: str,
        base: MastOutput,
        effective_critic: str,
        effective_judge: str,
    ) -> MastOutput:
        critic_response, critic_latency = await self._run_critic(
            thought, history_summary, effective_critic
        )
        log.info(
            "critic_done",
            trace_id=trace_id,
            thought_number=thought.thought_number,
            issues=len(critic_response.issues),
            latency_ms=critic_latency,
            model=effective_critic,
        )
        base.validation = ValidationResult(
            issues=critic_response.issues,
            strengths=critic_response.strengths,
            critic_model=effective_critic,
            critic_latency_ms=critic_latency,
        )
        if mode == "validate":
            return base

        judge_response, judge_latency = await self._run_judge(
            thought, history_summary, mode, effective_judge, critic_response
        )
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
        return base

    async def _run_workflow(
        self,
        thought: ThoughtData,
        history: list[ThoughtData],
        upstream_response: dict[str, object],
        stages: list[str],
        trace_id: str,
        *,
        critic_model: str | None = None,
        judge_model: str | None = None,
    ) -> WorkflowResult:
        current_thought = thought.thought
        stage_results: list[WorkflowStageResult] = []

        for stage_mode in stages:
            ctx = _WorkflowStageCtx(
                stage_mode=stage_mode,
                current_thought=current_thought,
                thought=thought,
                history=history,
                upstream_response=upstream_response,
                trace_id=trace_id,
                critic_model=critic_model,
                judge_model=judge_model,
            )
            result = await self._run_workflow_stage(ctx)
            stage_results.append(result)
            current_thought = result.output_thought

        return WorkflowResult.model_validate(
            {
                "stages": stage_results,
                "finalThought": current_thought,
                "totalStages": len(stages),
            }
        )

    async def _run_workflow_stage(self, ctx: _WorkflowStageCtx) -> WorkflowStageResult:
        log.info("workflow_stage_start", stage=ctx.stage_mode, trace_id=ctx.trace_id)

        stage_thought = ThoughtData(
            thought=ctx.current_thought,
            thought_number=ctx.thought.thought_number,
            total_thoughts=ctx.thought.total_thoughts,
            next_thought_needed=ctx.thought.next_thought_needed,
        )

        try:
            stage_output = await self.run(
                thought=stage_thought,
                history=ctx.history,
                upstream_response=ctx.upstream_response,
                mode=ctx.stage_mode,
                trace_id=f"{ctx.trace_id}:{ctx.stage_mode}",
                critic_model=ctx.critic_model,
                judge_model=ctx.judge_model,
            )
        except Exception as exc:
            log.error("workflow_stage_failed", stage=ctx.stage_mode, error=str(exc))
            return WorkflowStageResult.model_validate(
                {
                    "stage": ctx.stage_mode,
                    "verdict": "accept",
                    "confidence": 0.0,
                    "error": str(exc),
                    "inputThought": ctx.current_thought,
                    "outputThought": ctx.current_thought,
                }
            )

        output_thought = self._extract_workflow_output(stage_output, ctx.current_thought)

        log.info(
            "workflow_stage_done",
            stage=ctx.stage_mode,
            verdict=stage_output.verdict,
            trace_id=ctx.trace_id,
        )
        return WorkflowStageResult.model_validate(
            {
                "stage": ctx.stage_mode,
                "verdict": stage_output.verdict.value if stage_output.verdict else "accept",
                "confidence": stage_output.confidence or 0.0,
                "suggestedRevision": stage_output.suggested_revision,
                "inputThought": ctx.current_thought,
                "outputThought": output_thought,
            }
        )

    @staticmethod
    def _extract_workflow_output(
        stage_output: MastOutput,
        fallback: str,
    ) -> str:
        if stage_output.suggested_revision:
            return stage_output.suggested_revision
        if stage_output.actor_critic and stage_output.actor_critic.final_thought:
            return stage_output.actor_critic.final_thought
        if stage_output.brainstorm and stage_output.brainstorm.synthesis:
            return stage_output.brainstorm.synthesis
        if stage_output.tot and stage_output.tot.selected_branch:
            return stage_output.tot.selected_branch.next_step
        return fallback

    async def aclose(self) -> None:
        await self._client.aclose()
