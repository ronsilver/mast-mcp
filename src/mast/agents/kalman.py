"""Kalman Convergence Layer — Bayesian fusion of multi-agent quality scores."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import jinja2
import structlog

from mast.agents._utils import load_prompt
from mast.agents.protocols import ChatBackend
from mast.config import config
from mast.validation.schemas import KalmanResult, KalmanScoreEntry, Verdict

log = structlog.get_logger(__name__)


@dataclass
class _KFState:
    x: float = 0.5
    P: float = 1.0
    Q: float = 0.01
    innovations: list[float] = field(default_factory=list)

    def update(self, z: float, confidence: float) -> None:
        R = max(1.0 - confidence, 1e-6)
        x_pred = self.x
        P_pred = self.P + self.Q
        innovation = z - x_pred
        self.innovations.append(abs(innovation))
        S = P_pred + R
        K = P_pred / S
        self.x = x_pred + K * innovation
        self.P = (1 - K) * P_pred * (1 - K) + K * R * K
        self.x = max(0.0, min(1.0, self.x))
        self.P = max(0.0, self.P)


def _detect_kalman_triggers(state: _KFState, entry_count: int) -> list[str]:
    triggers: list[str] = []
    if state.P > 0.5 and entry_count >= 2:
        triggers.append("K1:high_divergence")
    if state.P < 1e-15:
        triggers.append("K2:covariance_collapse")
    if any(abs(i) > 0.5 for i in state.innovations):
        triggers.append("K4:large_innovation")
    if (
        len(state.innovations) >= 3
        and max(state.innovations[-3:]) - min(state.innovations[-3:]) < 0.02
        and state.P > 0.20
    ):
        triggers.append("K5:no_new_information")
    return triggers


class KalmanConvergenceLayer:
    """Bayesian fusion of multi-agent quality scores via Kalman filter."""

    def __init__(self, client: ChatBackend) -> None:
        """Initialize with Ollama client and load scorer prompt template."""
        self._client = client
        self._scorer_tpl = jinja2.Template(
            load_prompt("mast.prompts.kalman", "scorer.md"),
            undefined=jinja2.Undefined,
        )

    async def _score_thought(
        self,
        model: str,
        thought: str,
        history_summary: str,
        thought_number: int,
        total_thoughts: int,
    ) -> tuple[KalmanScoreEntry, int]:
        prompt = self._scorer_tpl.render(
            thought=thought,
            history_summary=history_summary,
            thought_number=thought_number,
            total_thoughts=total_thoughts,
        )
        raw, lat = await self._client.chat(
            model=model,
            system_prompt=prompt,
            temperature=0.1,
            num_predict=128,
            fallback={"score": 0.5, "confidence": 0.5, "rationale": "parse_failed"},
            json_schema=KalmanScoreEntry.model_json_schema(),
        )
        entry = KalmanScoreEntry.model_validate(raw)
        entry.model = model
        entry.latency_ms = lat
        return entry, lat

    async def run(
        self,
        thought: str,
        thought_number: int,
        total_thoughts: int,
        history_summary: str,
    ) -> KalmanResult:
        models = config.kalman_scorer_models
        accept_threshold = config.kalman_accept_threshold
        p_threshold = config.kalman_p_threshold

        tasks = [
            self._score_thought(m, thought, history_summary, thought_number, total_thoughts)
            for m in models
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        state = _KFState()
        entries: list[KalmanScoreEntry] = []
        for r in results:
            if isinstance(r, BaseException):
                log.warning("kalman_scorer_failed", error=str(r))
                continue
            entry = r[0]
            entries.append(entry)
            state.update(z=entry.score, confidence=entry.confidence)

        triggers = _detect_kalman_triggers(state, len(entries))
        converged = p_threshold > state.P
        verdict = Verdict.ACCEPT if state.x >= accept_threshold else Verdict.REVISE

        log.info(
            "kalman_done",
            thought_number=thought_number,
            x=round(state.x, 3),
            P=round(state.P, 4),
            converged=converged,
            triggers=triggers,
        )
        return KalmanResult.model_validate(
            {
                "scorers": entries,
                "xFinal": state.x,
                "PFinal": state.P,
                "converged": converged,
                "triggers": triggers,
                "verdict": verdict,
                "confidence": 1.0 - state.P,
            }
        )
