"""Tree of Thoughts — parallel branch generation and voting."""

from __future__ import annotations

import asyncio

import jinja2
import structlog

from mast.agents._utils import load_prompt
from mast.agents.protocols import ChatBackend
from mast.config import config
from mast.validation.schemas import ToTBranch, ToTResult

log = structlog.get_logger(__name__)


class TreeOfThoughtsOrchestrator:
    """Parallel branch generation and voting orchestrator."""

    def __init__(self, client: ChatBackend) -> None:
        """Initialize with Ollama client and load prompt templates."""
        self._client = client
        self._branch_tpl = jinja2.Template(
            load_prompt("mast.prompts.tot", "branch_generator.md"),
            undefined=jinja2.Undefined,
        )
        self._voter_tpl = jinja2.Template(
            load_prompt("mast.prompts.tot", "voter.md"),
            undefined=jinja2.Undefined,
        )

    async def _generate_branch(
        self,
        model: str,
        thought: str,
        history_summary: str,
        thought_number: int,
        total_thoughts: int,
    ) -> tuple[ToTBranch, int]:
        prompt = self._branch_tpl.render(
            thought=thought,
            history_summary=history_summary,
            thought_number=thought_number,
            total_thoughts=total_thoughts,
        )
        raw, lat = await self._client.chat(
            model=model,
            system_prompt=prompt,
            temperature=0.75,
            num_predict=512,
            fallback={"next_step": thought, "rationale": "parse_failed"},
            json_schema=ToTBranch.model_json_schema(),
        )
        branch = ToTBranch.model_validate(raw)
        branch.model = model
        return branch, lat

    async def _vote(
        self,
        thought: str,
        branches: list[ToTBranch],
        history_summary: str,
    ) -> list[dict[str, object]]:
        branches_text = "\n".join(f"[{i}] {b.next_step}" for i, b in enumerate(branches))
        prompt = self._voter_tpl.render(
            thought=thought,
            branches_text=branches_text,
            history_summary=history_summary,
        )
        raw, _ = await self._client.chat(
            model=config.tot_voter_model,
            system_prompt=prompt,
            temperature=0.2,
            num_predict=512,
            fallback={"scores": []},
        )
        scores = raw.get("scores", [])
        if isinstance(scores, list):
            return [dict(s) for s in scores]
        return []

    async def run(
        self,
        thought: str,
        thought_number: int,
        total_thoughts: int,
        history_summary: str,
    ) -> ToTResult:
        models = config.tot_branch_models

        tasks = [
            self._generate_branch(m, thought, history_summary, thought_number, total_thoughts)
            for m in models
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        branches: list[ToTBranch] = []
        for r in results:
            if isinstance(r, BaseException):
                continue
            branches.append(r[0])

        if not branches:
            return ToTResult.model_validate(
                {"branches": [], "selectedBranch": None, "voterScores": []}
            )

        scores = await self._vote(thought, branches, history_summary)
        self._apply_voter_scores(branches, scores)

        branches.sort(key=lambda b: b.voter_score or 0, reverse=True)
        selected = branches[0] if branches else None

        return ToTResult.model_validate(
            {
                "branches": branches,
                "selectedBranch": selected,
                "voterScores": scores,
            }
        )

    @staticmethod
    def _apply_voter_scores(
        branches: list[ToTBranch],
        scores: list[dict[str, object]],
    ) -> None:
        """
        Map voter scores to branches by explicit `index` field.

        Branches are addressed via their declared `index` rather than
        positional ordering. Scores with an `index` outside the valid
        range or missing `index` are ignored (unscored branches sort
        to the bottom by default sort with `or 0`).
        """
        for score_data in scores:
            raw_index = score_data.get("index")
            if not isinstance(raw_index, int) or raw_index < 0 or raw_index >= len(branches):
                continue
            raw_score = score_data.get("score", 0.0)
            branches[raw_index].voter_score = (
                raw_score if isinstance(raw_score, int | float) else 0.0
            )
            raw_rationale = score_data.get("rationale", "")
            branches[raw_index].voter_rationale = (
                str(raw_rationale) if raw_rationale is not None else ""
            )
