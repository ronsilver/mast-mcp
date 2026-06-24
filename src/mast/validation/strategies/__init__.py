"""
Built-in strategy wrappers.

These delegate to existing mode handlers in agents/* and orchestrator.py.
A future refactor (post-foundation) will replace the if/elif chain in
orchestrator.run() with registry.get(mode).run(...).

For now, each built-in exposes the same interface as the Strategy
protocol so they can be registered and looked up. Their `run()` methods
are not directly invoked by the orchestrator — the orchestrator keeps
its current dispatch path until a full-parity migration is verified.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mast.validation.strategy import Strategy

if TYPE_CHECKING:
    from mast._upstream import ThoughtData
    from mast.agents.protocols import ChatBackend
    from mast.validation.cache import ValidationCache
    from mast.validation.schemas import MastOutput


def _make_passthrough(name: str) -> type[Strategy]:
    """
    Create a Strategy subclass with a placeholder run().

    The orchestrator currently owns the per-mode logic. These
    placeholder classes exist to register the 9 built-in names in
    the registry so external plugins can't shadow them. The actual
    orchestrator dispatch remains in `orchestrator.run()` until a
    full parity migration is verified.
    """

    class _BuiltIn:
        def __init__(self) -> None:
            self.name = name

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
        ) -> MastOutput:
            raise NotImplementedError(
                f"Built-in strategy {self.name!r} run() is a placeholder. "
                f"The orchestrator continues to handle this mode directly "
                f"until the registry-based dispatch is migrated."
            )

    _BuiltIn.__name__ = f"BuiltIn_{name.capitalize()}"
    return _BuiltIn


def builtin_strategies() -> list[Strategy]:
    """Return placeholder Strategy instances for the 9 built-in modes."""
    names_list = [
        "passive",
        "validate",
        "debate",
        "debono",
        "actor_critic",
        "brainstorm",
        "tot",
        "kalman",
        "workflow",
    ]
    return [_make_passthrough(n)() for n in names_list]
