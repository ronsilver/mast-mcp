"""Critic agent — challenges a thought and returns structured issues."""

from __future__ import annotations

from dataclasses import dataclass

import jinja2
import structlog
from pydantic import ValidationError

from mast.agents._json_utils import CRITIC_FALLBACK
from mast.agents._utils import load_prompt
from mast.agents.protocols import ChatBackend
from mast.config import config
from mast.validation.schemas import CriticResponse

log = structlog.get_logger(__name__)


@dataclass
class CritiqueRequest:
    thought: str
    thought_number: int
    total_thoughts: int
    history_summary: str
    is_revision: bool = False
    revises_thought: int | None = None
    branch_id: str | None = None
    branch_from: int | None = None
    model: str | None = None


class CriticAgent:
    def __init__(self, client: ChatBackend) -> None:
        """Initialize critic agent with backend client."""
        self._client = client
        self._template = jinja2.Template(
            load_prompt("mast.prompts.debate", "critic.md"),
            undefined=jinja2.Undefined,
        )

    async def critique(self, req: CritiqueRequest) -> tuple[CriticResponse, int]:
        target_model = req.model or config.critic_model
        prompt = self._template.render(
            thought=req.thought,
            thought_number=req.thought_number,
            total_thoughts=req.total_thoughts,
            history_summary=req.history_summary,
            is_revision=req.is_revision,
            revises_thought=req.revises_thought,
            branch_id=req.branch_id,
            branch_from=req.branch_from,
        )

        raw, latency_ms = await self._client.chat(
            model=target_model,
            system_prompt=prompt,
            temperature=0.2,
            num_predict=512,
            fallback=CRITIC_FALLBACK,
            json_schema=CriticResponse.model_json_schema(),
        )

        try:
            return CriticResponse.model_validate(raw), latency_ms
        except ValidationError as exc:
            log.warning("critic_response_validation_failed", error=str(exc))
            return CriticResponse(), latency_ms
