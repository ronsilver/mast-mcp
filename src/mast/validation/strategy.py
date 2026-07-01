"""Strategy interface — pluggable reasoning modes for ValidationOrchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from mast._upstream import ThoughtData
    from mast.agents.protocols import ChatBackend
    from mast.validation.cache import ValidationCache
    from mast.validation.schemas import MastOutput


class Strategy(Protocol):
    """
    Pluggable reasoning mode.

    A strategy encapsulates one of the 9 reasoning modes (validate, debate,
    debono, actor_critic, brainstorm, tot, kalman, workflow, passive).
    """

    name: str

    async def run(
        self,
        thought: ThoughtData,
        history: list[ThoughtData],
        upstream_response: dict[str, Any],
        *,
        critic_model: str | None = None,
        judge_model: str | None = None,
        backend: ChatBackend,
        cache: ValidationCache[MastOutput],
    ) -> MastOutput: ...
