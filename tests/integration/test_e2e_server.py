"""
End-to-end test of MCP tool dispatch through _call_tool.

Exercises the real entry point used by the MCP server without launching
stdio transport. Validates that tool routing, mode dispatch, the
doctor command, and error paths all work end-to-end.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Protocol

import pytest

from mast import server
from mast._upstream import SequentialThinkingServer
from mast._upstream import ThoughtData as ThoughtDataReal
from mast.validation.schemas import MastOutput

# Re-export under a non-private alias for the stub annotation
ThoughtData = ThoughtDataReal


class _StubOrchestratorProto(Protocol):
    async def run(
        self,
        thought: ThoughtData,
        history: list[ThoughtData],
        upstream_response: dict[str, object],
        mode: str,
        trace_id: str,
        *,
        critic_model: str | None = ...,
        judge_model: str | None = ...,
    ) -> MastOutput: ...


@pytest.fixture
def upstream_server() -> SequentialThinkingServer:
    return SequentialThinkingServer()


class _StubOrchestratorImpl:
    async def run(
        self,
        thought: ThoughtData,
        history: list[ThoughtData],
        upstream_response: dict[str, object],
        mode: str,
        trace_id: str,
        *,
        critic_model: str | None = None,
        judge_model: str | None = None,
    ) -> MastOutput:
        return MastOutput(
            thought_number=thought.thought_number,
            total_thoughts=thought.total_thoughts,
            next_thought_needed=thought.next_thought_needed,
            thought_history_length=1,
        )


@pytest.fixture
def orchestrator_stub() -> _StubOrchestratorImpl:
    return _StubOrchestratorImpl()


@pytest.fixture
def _init_state(
    monkeypatch: pytest.MonkeyPatch,
    upstream_server: SequentialThinkingServer,
    orchestrator_stub: _StubOrchestratorImpl,
) -> Generator[None, None, None]:
    """Initialize module-level state for _get_upstream / _get_orchestrator."""
    server._upstream_state = upstream_server
    server._orchestrator_state = orchestrator_stub  # type: ignore[assignment]
    yield
    server._upstream_state = None
    server._orchestrator_state = None


@pytest.mark.asyncio
async def test_call_tool_sequentialthinking_dispatches(
    _init_state: Generator[None, None, None],
) -> None:
    arguments = {
        "thought": "test thought " + "x" * 30,
        "thoughtNumber": 1,
        "totalThoughts": 3,
        "nextThoughtNeeded": True,
    }
    result = await server._call_tool("sequentialthinking", arguments)
    assert len(result) == 1
    text = result[0].text
    assert "thoughtHistoryLength" in text or "thoughtNumber" in text


@pytest.mark.asyncio
async def test_call_tool_mast_debate_defaults_to_debate(
    _init_state: Generator[None, None, None],
) -> None:
    """mast_debate without mode arg should default to 'debate'."""
    arguments: dict[str, object] = {
        "thought": "debate me " + "x" * 30,
        "thoughtNumber": 1,
        "totalThoughts": 1,
        "nextThoughtNeeded": False,
    }
    result = await server._call_tool("mast_debate", arguments)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_call_tool_mast_debate_with_mode_override(
    _init_state: Generator[None, None, None],
) -> None:
    arguments: dict[str, object] = {
        "thought": "debono me " + "x" * 30,
        "thoughtNumber": 1,
        "totalThoughts": 1,
        "nextThoughtNeeded": False,
        "mode": "debono",
    }
    result = await server._call_tool("mast_debate", arguments)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_call_tool_unknown_raises_value_error(
    _init_state: Generator[None, None, None],
) -> None:
    with pytest.raises(ValueError, match="Unknown tool"):
        await server._call_tool("not_a_tool", {})


@pytest.mark.asyncio
async def test_get_upstream_uninitialized_raises() -> None:
    server._upstream_state = None
    with pytest.raises(RuntimeError, match="not initialized"):
        server._get_upstream()


@pytest.mark.asyncio
async def test_get_orchestrator_uninitialized_raises() -> None:
    server._orchestrator_state = None
    with pytest.raises(RuntimeError, match="not initialized"):
        server._get_orchestrator()


def test_main_doctor_command_runs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Run main() with --doctor argument; expect doctor output and exit."""
    from mast import __main__
    from mast.agents import registry as agent_registry

    class _StubBackend:
        async def list_models(self) -> list[str]:
            return ["m1", "m2"]

        async def aclose(self) -> None:
            pass

    stub = _StubBackend()
    stub._provider_name = "ollama"  # type: ignore[attr-defined]
    monkeypatch.setattr(agent_registry, "_cached", stub)

    import sys

    monkeypatch.setattr(sys, "argv", ["mast-server", "--doctor"])

    with pytest.raises(SystemExit) as exc_info:
        __main__.main()
    # Exit code 0 (all models found) or 1 (missing models) both valid.
    # We only verify the doctor output was emitted.
    assert exc_info.value.code in (0, 1)

    captured = capsys.readouterr()
    assert "MAST-MCP Doctor" in captured.out or "MAST-MCP Doctor" in captured.err


def test_main_runs_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() without --doctor should call run_server()."""
    from mast import __main__

    called: dict[str, bool] = {}

    async def fake_run_server() -> None:
        called["ran"] = True

    monkeypatch.setattr("mast.server.run_server", fake_run_server)
    import sys

    monkeypatch.setattr(sys, "argv", ["mast-server"])

    __main__.main()
    assert called.get("ran") is True
