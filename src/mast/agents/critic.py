"""Critic agent — challenges a thought and returns structured issues."""

from __future__ import annotations

import jinja2
import structlog
from pydantic import ValidationError

from mast.agents._utils import load_prompt
from mast.agents.base import _CRITIC_FALLBACK, OllamaClient
from mast.config import config
from mast.validation.schemas import CriticResponse

log = structlog.get_logger(__name__)


class CriticAgent:
    def __init__(self, client: OllamaClient) -> None:
        self._client = client
        self._template = jinja2.Template(
            load_prompt("mast.prompts.debate", "critic.md"),
            undefined=jinja2.Undefined,
        )

    async def critique(
        self,
        thought: str,
        thought_number: int,
        total_thoughts: int,
        history_summary: str,
        *,
        is_revision: bool = False,
        revises_thought: int | None = None,
        branch_id: str | None = None,
        branch_from: int | None = None,
        model: str | None = None,
    ) -> tuple[CriticResponse, int]:
        target_model = model or config.critic_model
        prompt = self._template.render(
            thought=thought,
            thought_number=thought_number,
            total_thoughts=total_thoughts,
            history_summary=history_summary,
            is_revision=is_revision,
            revises_thought=revises_thought,
            branch_id=branch_id,
            branch_from=branch_from,
        )

        raw, latency_ms = await self._client.chat(
            model=target_model,
            system_prompt=prompt,
            temperature=0.2,
            num_predict=512,
            fallback=_CRITIC_FALLBACK,
            json_schema=CriticResponse.model_json_schema(),
        )

        try:
            return CriticResponse.model_validate(raw), latency_ms
        except ValidationError as exc:
            log.warning("critic_response_validation_failed", error=str(exc))
            return CriticResponse(), latency_ms
