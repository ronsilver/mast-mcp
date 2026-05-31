"""Brainstorm orchestrator — parallel divergence to synthesis convergence."""

from __future__ import annotations

import asyncio

import jinja2
import structlog

from mast.agents._utils import load_prompt
from mast.agents.base import OllamaClient
from mast.config import config
from mast.validation.schemas import BrainstormIdea, BrainstormResult

log = structlog.get_logger(__name__)


class BrainstormOrchestrator:
    """Parallel divergence to synthesis convergence orchestrator."""

    def __init__(self, client: OllamaClient) -> None:
        """Initialize with Ollama client and load prompt templates."""
        self._client = client
        self._idea_tpl = jinja2.Template(
            load_prompt("mast.prompts.brainstorm", "idea_generator.md"),
            undefined=jinja2.Undefined,
        )
        self._synth_tpl = jinja2.Template(
            load_prompt("mast.prompts.brainstorm", "synthesizer.md"),
            undefined=jinja2.Undefined,
        )

    async def _generate_idea(
        self,
        model: str,
        thought: str,
        history_summary: str,
        thought_number: int,
        total_thoughts: int,
    ) -> tuple[BrainstormIdea, int]:
        prompt = self._idea_tpl.render(
            thought=thought,
            history_summary=history_summary,
            thought_number=thought_number,
            total_thoughts=total_thoughts,
        )
        raw, latency = await self._client.chat(
            model=model,
            system_prompt=prompt,
            temperature=0.85,
            num_predict=512,
            fallback={"idea": thought, "rationale": "parse_failed"},
            json_schema=BrainstormIdea.model_json_schema(),
        )
        idea = BrainstormIdea.model_validate(raw)
        idea.model = model
        idea.latency_ms = latency
        return idea, latency

    async def _synthesize(
        self,
        thought: str,
        ideas: list[BrainstormIdea],
        history_summary: str,
        thought_number: int,
        total_thoughts: int,
    ) -> tuple[dict[str, object], int]:
        ideas_text = "\n".join(
            f"[{i + 1}] ({idea.model}): {idea.idea}" for i, idea in enumerate(ideas)
        )
        prompt = self._synth_tpl.render(
            thought=thought,
            ideas_text=ideas_text,
            history_summary=history_summary,
            thought_number=thought_number,
            total_thoughts=total_thoughts,
        )
        return await self._client.chat(
            model=config.brainstorm_synth_model,
            system_prompt=prompt,
            temperature=0.4,
            num_predict=1024,
            fallback={"synthesis": thought, "top_ideas": [], "rationale": "parse_failed"},
        )

    async def run(
        self,
        thought: str,
        thought_number: int,
        total_thoughts: int,
        history_summary: str,
    ) -> BrainstormResult:
        models = config.brainstorm_models

        tasks = [
            self._generate_idea(m, thought, history_summary, thought_number, total_thoughts)
            for m in models
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        ideas: list[BrainstormIdea] = []
        for r in results:
            if isinstance(r, BaseException):
                log.warning("brainstorm_idea_failed", error=str(r))
            else:
                ideas.append(r[0])

        if not ideas:
            return BrainstormResult.model_validate(
                {"ideas": [], "synthesis": "no_ideas_generated", "topIdeas": []}
            )

        raw_synth, synth_lat = await self._synthesize(
            thought,
            ideas,
            history_summary,
            thought_number,
            total_thoughts,
        )

        return BrainstormResult.model_validate(
            {
                "ideas": ideas,
                "synthesis": raw_synth.get("synthesis", thought),
                "topIdeas": raw_synth.get("top_ideas", []),
                "synthLatencyMs": synth_lat,
            }
        )
