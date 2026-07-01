"""Per-mode validation runners extracted from orchestrator.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from mast.config import config
from mast.validation.schemas import (
    MastOutput,
    ValidationResult,
    Verdict,
)

if TYPE_CHECKING:
    from mast.validation.orchestrator import ValidationOrchestrator, _RunCtx

log = structlog.get_logger(__name__)


async def run_debono_mode(orch: ValidationOrchestrator, ctx: _RunCtx) -> MastOutput:
    debono_result, blue_close = await orch._run_debono(
        ctx.thought, ctx.history_summary, ctx.critic_model, ctx.judge_model
    )
    ctx.base.debono = debono_result
    verdict_raw = str(blue_close.get("verdict", "accept"))
    try:
        ctx.base.verdict = Verdict(verdict_raw)
    except ValueError:
        ctx.base.verdict = Verdict.ACCEPT
    confidence_val = blue_close.get("confidence", 0.5)
    ctx.base.confidence = float(confidence_val) if isinstance(confidence_val, int | float) else 0.5
    revision_val = blue_close.get("suggested_revision")
    ctx.base.suggested_revision = (
        str(revision_val) if revision_val is not None and isinstance(revision_val, str) else None
    )
    ctx.base.judge_model = debono_result.hats[-1].model if debono_result.hats else None
    ctx.base.judge_latency_ms = debono_result.total_latency_ms
    log.info(
        "debono_done",
        trace_id=ctx.trace_id,
        thought_number=ctx.thought.thought_number,
        hats=len(debono_result.hats),
        verdict=ctx.base.verdict.value if ctx.base.verdict else None,
        total_latency_ms=debono_result.total_latency_ms,
    )
    return ctx.base


async def run_actor_critic_mode(orch: ValidationOrchestrator, ctx: _RunCtx) -> MastOutput:
    ac_result = await orch._actor_critic.run(
        thought=ctx.thought.thought,
        thought_number=ctx.thought.thought_number,
        total_thoughts=ctx.thought.total_thoughts,
        history_summary=ctx.history_summary,
        critic_model=ctx.critic_model,
        judge_model=ctx.judge_model,
    )
    ctx.base.actor_critic = ac_result
    ctx.base.verdict = Verdict.ACCEPT if ac_result.converged else Verdict.REVISE
    ctx.base.confidence = 1.0 if ac_result.converged else 0.5
    ctx.base.suggested_revision = ac_result.final_thought
    log.info(
        "actor_critic_done",
        trace_id=ctx.trace_id,
        thought_number=ctx.thought.thought_number,
        total_rounds=ac_result.total_rounds,
        converged=ac_result.converged,
    )
    return ctx.base


async def run_brainstorm_mode(orch: ValidationOrchestrator, ctx: _RunCtx) -> MastOutput:
    bs_result = await orch._brainstorm.run(
        thought=ctx.thought.thought,
        thought_number=ctx.thought.thought_number,
        total_thoughts=ctx.thought.total_thoughts,
        history_summary=ctx.history_summary,
    )
    ctx.base.brainstorm = bs_result
    ctx.base.verdict = Verdict.REVISE
    ctx.base.suggested_revision = bs_result.synthesis
    log.info(
        "brainstorm_done",
        trace_id=ctx.trace_id,
        thought_number=ctx.thought.thought_number,
        ideas=len(bs_result.ideas),
    )
    return ctx.base


async def run_tot_mode(orch: ValidationOrchestrator, ctx: _RunCtx) -> MastOutput:
    tot_result = await orch._tot.run(
        thought=ctx.thought.thought,
        thought_number=ctx.thought.thought_number,
        total_thoughts=ctx.thought.total_thoughts,
        history_summary=ctx.history_summary,
    )
    ctx.base.tot = tot_result
    if tot_result.selected_branch:
        ctx.base.verdict = Verdict.REVISE
        ctx.base.suggested_revision = tot_result.selected_branch.next_step
    log.info(
        "tot_done",
        trace_id=ctx.trace_id,
        thought_number=ctx.thought.thought_number,
        branches=len(tot_result.branches),
        selected=tot_result.selected_branch is not None,
    )
    return ctx.base


async def run_kalman_mode(orch: ValidationOrchestrator, ctx: _RunCtx) -> MastOutput:
    k_result = await orch._kalman.run(
        thought=ctx.thought.thought,
        thought_number=ctx.thought.thought_number,
        total_thoughts=ctx.thought.total_thoughts,
        history_summary=ctx.history_summary,
    )
    ctx.base.kalman = k_result
    ctx.base.verdict = k_result.verdict
    ctx.base.confidence = k_result.confidence
    log.info(
        "kalman_done",
        trace_id=ctx.trace_id,
        thought_number=ctx.thought.thought_number,
        x=round(k_result.x_final, 3),
        converged=k_result.converged,
        verdict=k_result.verdict.value,
    )
    return ctx.base


async def run_workflow_mode(orch: ValidationOrchestrator, ctx: _RunCtx) -> MastOutput:
    stages = config.workflow_stages
    workflow_result = await orch._run_workflow(
        ctx.thought,
        ctx.history,
        ctx.upstream_response,
        stages,
        ctx.trace_id,
        critic_model=ctx.critic_model,
        judge_model=ctx.judge_model,
    )
    ctx.base.workflow = workflow_result
    if workflow_result.stages:
        last = workflow_result.stages[-1]
        ctx.base.verdict = last.verdict
        ctx.base.confidence = last.confidence
        ctx.base.suggested_revision = last.suggested_revision
    log.info(
        "workflow_done",
        trace_id=ctx.trace_id,
        thought_number=ctx.thought.thought_number,
        stages=len(workflow_result.stages),
        final_verdict=workflow_result.stages[-1].verdict.value if workflow_result.stages else None,
    )
    return ctx.base


async def run_critic_judge_mode(orch: ValidationOrchestrator, ctx: _RunCtx) -> MastOutput:
    critic_response, critic_latency = await orch._run_critic(
        ctx.thought, ctx.history_summary, ctx.effective_critic
    )
    log.info(
        "critic_done",
        trace_id=ctx.trace_id,
        thought_number=ctx.thought.thought_number,
        issues=len(critic_response.issues),
        latency_ms=critic_latency,
        model=ctx.effective_critic,
    )
    ctx.base.validation = ValidationResult(
        issues=critic_response.issues,
        strengths=critic_response.strengths,
        critic_model=ctx.effective_critic,
        critic_latency_ms=critic_latency,
    )
    if ctx.mode == "validate":
        return ctx.base

    judge_response, judge_latency = await orch._run_judge(
        ctx.thought, ctx.history_summary, ctx.mode, ctx.effective_judge, critic_response
    )
    log.info(
        "judge_done",
        trace_id=ctx.trace_id,
        thought_number=ctx.thought.thought_number,
        verdict=judge_response.verdict,
        confidence=judge_response.confidence,
        latency_ms=judge_latency,
        model=ctx.effective_judge,
    )
    ctx.base.verdict = judge_response.verdict
    ctx.base.confidence = judge_response.confidence
    ctx.base.suggested_revision = judge_response.suggested_revision
    ctx.base.judge_model = ctx.effective_judge
    ctx.base.judge_latency_ms = judge_latency
    return ctx.base
