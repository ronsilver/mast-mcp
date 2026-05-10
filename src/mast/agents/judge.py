"""Judge agent — synthesizes thought + critique into a verdict."""

from __future__ import annotations

import json

import jinja2
import structlog
from pydantic import ValidationError

from mast.agents._utils import load_prompt
from mast.agents.base import _JUDGE_FALLBACK, OllamaClient
from mast.config import config
from mast.validation.schemas import CriticResponse, JudgeResponse, Verdict

log = structlog.get_logger(__name__)


class JudgeAgent:
    def __init__(self, client: OllamaClient) -> None:
        self._client = client
        self._template = jinja2.Template(
            load_prompt("mast.prompts.debate", "judge.md"),
            undefined=jinja2.Undefined,
        )

    async def judge(
        self,
        thought: str,
        thought_number: int,
        total_thoughts: int,
        history_summary: str,
        critique: CriticResponse,
        mode: str,
        *,
        is_revision: bool = False,
        model: str | None = None,
    ) -> tuple[JudgeResponse, int]:
        target_model = model or config.judge_model
        prompt = self._template.render(
            thought=thought,
            thought_number=thought_number,
            total_thoughts=total_thoughts,
            history_summary=history_summary,
            critique_json=json.dumps(critique.model_dump(), ensure_ascii=False),
            mode=mode,
            is_revision=is_revision,
        )

        raw, latency_ms = await self._client.chat(
            model=target_model,
            system_prompt=prompt,
            temperature=0.4,
            num_predict=1024,
            fallback=_JUDGE_FALLBACK,
            json_schema=JudgeResponse.model_json_schema(),
        )

        try:
            return JudgeResponse.model_validate(raw), latency_ms
        except ValidationError as exc:
            log.warning("judge_response_validation_failed", error=str(exc))
            return JudgeResponse(
                verdict=Verdict.ACCEPT,
                confidence=0.0,
                rationale="validation_failed",
            ), latency_ms
