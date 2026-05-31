"""Validation orchestrator — assembles Critic + Judge or debono pipeline based on mode."""

from __future__ import annotations

import hashlib

import structlog

from mast._upstream import ThoughtData
from mast.agents.actor_critic import ActorCriticOrchestrator
from mast.agents.base import OllamaClient
from mast.agents.brainstorm import BrainstormOrchestrator
from mast.agents.critic import CriticAgent
from mast.agents.debono import DebonoContext, DebonoOrchestrator
from mast.agents.judge import JudgeAgent
from mast.agents.kalman import KalmanConvergenceLayer
from mast.agents.tot import TreeOfThoughtsOrchestrator
from mast.config import config
from mast.validation.cache import ValidationCache
from mast.validation.schemas import (
    MastOutput,
    ValidationResult,
    Verdict,
    WorkflowResult,
    WorkflowStageResult,
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
    """Coordinates Critic, Judge, and new reasoning modes."""

    def __init__(self) -> None:
        self._client = OllamaClient()
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

        # --- Actor-Critic (self-contained loop, no external critic needed) ---
        if mode == "actor_critic":
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
            self._cache.set(cache_key, base)
            return base

        # --- Brainstorm ---
        if mode == "brainstorm":
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
            self._cache.set(cache_key, base)
            return base

        # --- Tree of Thoughts ---
        if mode == "tot":
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
            self._cache.set(cache_key, base)
            return base

        # --- Kalman Convergence ---
        if mode == "kalman":
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
            self._cache.set(cache_key, base)
            return base

        # --- Workflow (chains multiple modes in sequence) ---
        if mode == "workflow":
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
                final_verdict=last.verdict.value if workflow_result.stages else None,
            )
            self._cache.set(cache_key, base)
            return base

        # --- Critic (runs for validate and debate) ---
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
            log.info("workflow_stage_start", stage=stage_mode, trace_id=trace_id)

            stage_thought = ThoughtData(
                thought=current_thought,
                thought_number=thought.thought_number,
                total_thoughts=thought.total_thoughts,
                next_thought_needed=thought.next_thought_needed,
            )

            try:
                stage_output = await self.run(
                    thought=stage_thought,
                    history=history,
                    upstream_response=upstream_response,
                    mode=stage_mode,
                    trace_id=f"{trace_id}:{stage_mode}",
                    critic_model=critic_model,
                    judge_model=judge_model,
                )
            except Exception as exc:
                log.error("workflow_stage_failed", stage=stage_mode, error=str(exc))
                stage_results.append(
                    WorkflowStageResult.model_validate(
                        {
                            "stage": stage_mode,
                            "verdict": "accept",
                            "confidence": 0.0,
                            "error": str(exc),
                            "inputThought": current_thought,
                            "outputThought": current_thought,
                        }
                    )
                )
                continue

            output_thought = (
                stage_output.suggested_revision
                or (stage_output.actor_critic.final_thought if stage_output.actor_critic else None)
                or (stage_output.brainstorm.synthesis if stage_output.brainstorm else None)
                or (
                    stage_output.tot.selected_branch.next_step
                    if stage_output.tot and stage_output.tot.selected_branch
                    else None
                )
                or current_thought
            )

            stage_results.append(
                WorkflowStageResult.model_validate(
                    {
                        "stage": stage_mode,
                        "verdict": stage_output.verdict.value if stage_output.verdict else "accept",
                        "confidence": stage_output.confidence or 0.0,
                        "suggestedRevision": stage_output.suggested_revision,
                        "inputThought": current_thought,
                        "outputThought": output_thought,
                    }
                )
            )

            current_thought = output_thought

            log.info(
                "workflow_stage_done",
                stage=stage_mode,
                verdict=stage_results[-1].verdict,
                trace_id=trace_id,
            )

        return WorkflowResult.model_validate(
            {
                "stages": stage_results,
                "finalThought": current_thought,
                "totalStages": len(stages),
            }
        )

    async def aclose(self) -> None:
        await self._client.aclose()
