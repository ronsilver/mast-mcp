"""Actor-Critic iterative refinement orchestrator."""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from mast.agents.critic import CriticAgent
from mast.agents.judge import JudgeAgent
from mast.agents.protocols import ChatBackend
from mast.config import config
from mast.validation.schemas import (
    ActorCriticResult,
    ActorCriticRound,
    IssueSeverity,
    Verdict,
)

log = structlog.get_logger(__name__)

_ESCALATE_SEVERITIES = {IssueSeverity.HIGH, IssueSeverity.MEDIUM}


@dataclass
class _RoundResult:
    validated_round: ActorCriticRound
    next_thought: str | None = None
    final: bool = False


class ActorCriticOrchestrator:
    """Iterative Critic+Judge refinement loop until convergence."""

    def __init__(self, client: ChatBackend) -> None:
        """Initialize with CriticAgent and JudgeAgent wrapping the given client."""
        self._critic = CriticAgent(client)
        self._judge = JudgeAgent(client)

    async def _run_round(
        self,
        thought: str,
        thought_number: int,
        total_thoughts: int,
        history_summary: str,
        round_idx: int,
        critic_model: str | None = None,
        judge_model: str | None = None,
    ) -> _RoundResult:
        critic_resp, c_lat = await self._critic.critique(
            thought=thought,
            thought_number=thought_number,
            total_thoughts=total_thoughts,
            history_summary=history_summary,
            model=critic_model,
        )
        needs_revision = any(i.severity in _ESCALATE_SEVERITIES for i in critic_resp.issues)
        if not needs_revision:
            return _RoundResult(
                validated_round=ActorCriticRound.model_validate(
                    {
                        "round": round_idx,
                        "thought": thought,
                        "critic": critic_resp,
                        "verdict": "accept",
                        "criticLatencyMs": c_lat,
                        "judgeLatencyMs": 0,
                    }
                ),
                final=True,
            )
        judge_resp, j_lat = await self._judge.judge(
            thought=thought,
            thought_number=thought_number,
            total_thoughts=total_thoughts,
            history_summary=history_summary,
            critique=critic_resp,
            mode="actor_critic",
            model=judge_model,
        )
        next_thought = (
            judge_resp.suggested_revision
            if (judge_resp.suggested_revision and judge_resp.verdict != Verdict.REJECT)
            else None
        )
        return _RoundResult(
            validated_round=ActorCriticRound.model_validate(
                {
                    "round": round_idx,
                    "thought": thought,
                    "critic": critic_resp,
                    "verdict": judge_resp.verdict.value,
                    "suggestedRevision": judge_resp.suggested_revision,
                    "criticLatencyMs": c_lat,
                    "judgeLatencyMs": j_lat,
                }
            ),
            next_thought=next_thought,
            final=next_thought is None,
        )

    async def run(
        self,
        thought: str,
        thought_number: int,
        total_thoughts: int,
        history_summary: str,
        *,
        max_rounds: int | None = None,
        critic_model: str | None = None,
        judge_model: str | None = None,
    ) -> ActorCriticResult:
        effective_max = max_rounds or config.actor_critic_max_rounds
        rounds: list[ActorCriticRound] = []
        current_thought = thought
        for round_idx in range(1, effective_max + 1):
            round_result = await self._run_round(
                thought=current_thought,
                thought_number=thought_number,
                total_thoughts=total_thoughts,
                history_summary=history_summary,
                round_idx=round_idx,
                critic_model=critic_model,
                judge_model=judge_model,
            )
            rounds.append(round_result.validated_round)
            if round_result.final:
                break
            current_thought = round_result.next_thought or current_thought
        final = rounds[-1]
        return ActorCriticResult.model_validate(
            {
                "rounds": rounds,
                "totalRounds": len(rounds),
                "finalThought": final.suggested_revision or final.thought,
                "converged": final.verdict == Verdict.ACCEPT,
            }
        )
