"""MCP server — low-level mcp.server.Server; registers sequentialthinking and mast_debate."""

from __future__ import annotations

import json
import sys
import uuid
from typing import Any

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from mast._mast_debate_tool import MAST_DEBATE_INPUT_SCHEMA, MAST_DEBATE_TOOL_DESCRIPTION
from mast._upstream import SequentialThinkingServer, ThoughtData
from mast._upstream_tool import (
    SEQUENTIAL_THINKING_INPUT_SCHEMA,
    SEQUENTIAL_THINKING_TOOL_DESCRIPTION,
)
from mast.config import config
from mast.validation.orchestrator import ValidationOrchestrator
from mast.validation.schemas import SequentialThinkingInput

log = structlog.get_logger(__name__)

server = Server("mast-mcp")


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


@server.list_tools()  # type: ignore[no-untyped-call, untyped-decorator]
async def _list_tools() -> list[Tool]:
    return [
        Tool(
            name="sequentialthinking",
            description=SEQUENTIAL_THINKING_TOOL_DESCRIPTION,
            inputSchema=SEQUENTIAL_THINKING_INPUT_SCHEMA,
        ),
        Tool(
            name="mast_debate",
            description=MAST_DEBATE_TOOL_DESCRIPTION,
            inputSchema=MAST_DEBATE_INPUT_SCHEMA,
        ),
    ]


@server.call_tool()  # type: ignore[untyped-decorator]
async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    upstream = _get_upstream()
    orchestrator = _get_orchestrator()

    if name == "sequentialthinking":
        result = await _handle_thought(arguments, upstream=upstream, orchestrator=orchestrator)
    elif name == "mast_debate":
        critic_model = arguments.pop("criticModel", None)
        judge_model = arguments.pop("judgeModel", None)
        debono_primary = arguments.pop("debonoPrimaryModel", None)
        debono_creative = arguments.pop("debonoCreativeModel", None)
        # mast_debate defaults to "debate" if the client did not pass mode,
        # unlike sequentialthinking which uses config.mast_mode.
        user_mode = arguments.get("mode") or "debate"
        result = await _handle_thought(
            arguments,
            upstream=upstream,
            orchestrator=orchestrator,
            force_mode=user_mode,
            critic_model=critic_model or debono_primary,
            judge_model=judge_model or debono_creative,
        )
    else:
        raise ValueError(f"Unknown tool: {name!r}")

    return [TextContent(type="text", text=result)]


# ---------------------------------------------------------------------------
# Shared state accessors (set during run_server, safe for single-process MCP)
# ---------------------------------------------------------------------------

_upstream_state: SequentialThinkingServer | None = None
_orchestrator_state: ValidationOrchestrator | None = None


def _get_upstream() -> SequentialThinkingServer:
    if _upstream_state is None:
        raise RuntimeError("Server not initialized — call run_server()")
    return _upstream_state


def _get_orchestrator() -> ValidationOrchestrator:
    if _orchestrator_state is None:
        raise RuntimeError("Server not initialized — call run_server()")
    return _orchestrator_state


# ---------------------------------------------------------------------------
# Core handler
# ---------------------------------------------------------------------------


async def _handle_thought(
    raw_input: dict[str, Any],
    *,
    upstream: SequentialThinkingServer,
    orchestrator: ValidationOrchestrator,
    force_mode: str | None = None,
    critic_model: str | None = None,
    judge_model: str | None = None,
) -> str:
    trace_id = str(uuid.uuid4())[:8]

    parsed = SequentialThinkingInput.model_validate(raw_input)
    mode = force_mode or parsed.mode or config.mast_mode

    upstream_response = upstream.process_thought(raw_input)

    thought_obj = ThoughtData(
        thought=parsed.thought,
        thought_number=parsed.thought_number,
        total_thoughts=parsed.total_thoughts,
        next_thought_needed=parsed.next_thought_needed,
        is_revision=parsed.is_revision or False,
        revises_thought=parsed.revises_thought,
        branch_from_thought=parsed.branch_from_thought,
        branch_id=parsed.branch_id,
        needs_more_thoughts=parsed.needs_more_thoughts or False,
    )

    if not config.disable_thought_logging:
        formatted = upstream.format_thought(thought_obj)
        if formatted:
            print(formatted, file=sys.stderr, flush=True)

    if parsed.skip_validation or mode == "passive":
        return json.dumps(upstream_response)

    result = await orchestrator.run(
        thought=thought_obj,
        history=upstream.get_history_for_branch(parsed.branch_id),
        upstream_response=upstream_response,
        mode=mode,
        trace_id=trace_id,
        critic_model=critic_model,
        judge_model=judge_model,
    )

    return json.dumps(result.to_dict())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_server() -> None:
    global _upstream_state, _orchestrator_state

    _upstream_state = SequentialThinkingServer()
    _orchestrator_state = ValidationOrchestrator()

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        await _orchestrator_state.aclose()
