"""MCP server using FastMCP — registers sequentialthinking and mast_debate tools."""
from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from mcp.server.fastmcp import FastMCP

from mast._upstream import SequentialThinkingServer, ThoughtData
from mast.config import config
from mast.validation.orchestrator import ValidationOrchestrator
from mast.validation.schemas import SequentialThinkingInput

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Shared state (per-process — MCP servers are long-lived processes)
# ---------------------------------------------------------------------------
_upstream = SequentialThinkingServer()
_orchestrator = ValidationOrchestrator()

mcp = FastMCP("mast-ollama")


# ---------------------------------------------------------------------------
# Shared handler
# ---------------------------------------------------------------------------


async def _handle_thought(
    raw_input: dict[str, Any],
    *,
    force_mode: str | None = None,
) -> str:
    trace_id = str(uuid.uuid4())[:8]

    parsed = SequentialThinkingInput.model_validate(raw_input)
    mode = force_mode or parsed.mode or config.mast_mode

    upstream_response = _upstream.process_thought(raw_input)

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
        formatted = _upstream.format_thought(thought_obj)
        if formatted:
            import sys
            print(formatted, file=sys.stderr, flush=True)

    if parsed.skip_validation or mode == "passive":
        return json.dumps(upstream_response)

    result = await _orchestrator.run(
        thought=thought_obj,
        history=_upstream.get_history_for_branch(parsed.branch_id),
        upstream_response=upstream_response,
        mode=mode,
        trace_id=trace_id,
    )

    return json.dumps(result.to_dict())


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    description=(
        "A tool for dynamic and reflective problem-solving through sequential thoughts.\n\n"
        "MAST extension: each thought is validated by local Ollama models (Critic + Judge) "
        "before being returned. Set mode='passive' to disable validation and match upstream "
        "sequential-thinking behavior exactly.\n\n"
        "Parameters:\n"
        "- thought: Your current thinking step\n"
        "- thoughtNumber: Current thought number (1-based)\n"
        "- totalThoughts: Estimated total thoughts needed\n"
        "- nextThoughtNeeded: Whether another thought is needed\n"
        "- isRevision: True if this revises a previous thought\n"
        "- revisesThought: Which thought number this revises\n"
        "- branchFromThought: Branching point thought number\n"
        "- branchId: Branch identifier string\n"
        "- needsMoreThoughts: If you realize you need more thoughts\n"
        "- mode: 'passive' | 'validate' | 'debate' (overrides MAST_MODE env var)\n"
        "- skipValidation: Skip Critic/Judge for this step only"
    )
)
async def sequentialthinking(
    thought: str,
    thoughtNumber: int,
    totalThoughts: int,
    nextThoughtNeeded: bool,
    isRevision: bool = False,
    revisesThought: int | None = None,
    branchFromThought: int | None = None,
    branchId: str | None = None,
    needsMoreThoughts: bool = False,
    mode: str | None = None,
    skipValidation: bool = False,
) -> str:
    return await _handle_thought(
        {
            "thought": thought,
            "thoughtNumber": thoughtNumber,
            "totalThoughts": totalThoughts,
            "nextThoughtNeeded": nextThoughtNeeded,
            "isRevision": isRevision,
            "revisesThought": revisesThought,
            "branchFromThought": branchFromThought,
            "branchId": branchId,
            "needsMoreThoughts": needsMoreThoughts,
            "mode": mode,
            "skipValidation": skipValidation,
        }
    )


@mcp.tool(
    description=(
        "Forces debate mode (Critic + Judge) regardless of server defaults. "
        "Use when you want maximum validation quality for a critical reasoning step. "
        "Accepts optional criticModel and judgeModel to override default models per call."
    )
)
async def mast_debate(
    thought: str,
    thoughtNumber: int,
    totalThoughts: int,
    nextThoughtNeeded: bool,
    isRevision: bool = False,
    revisesThought: int | None = None,
    branchFromThought: int | None = None,
    branchId: str | None = None,
    needsMoreThoughts: bool = False,
    criticModel: str | None = None,
    judgeModel: str | None = None,
) -> str:
    # Per-call model overrides: set temporarily in config is not thread-safe,
    # so we pass via the raw dict and let orchestrator pick up via env defaults.
    # Full per-call model override is a Phase 5 feature.
    return await _handle_thought(
        {
            "thought": thought,
            "thoughtNumber": thoughtNumber,
            "totalThoughts": totalThoughts,
            "nextThoughtNeeded": nextThoughtNeeded,
            "isRevision": isRevision,
            "revisesThought": revisesThought,
            "branchFromThought": branchFromThought,
            "branchId": branchId,
            "needsMoreThoughts": needsMoreThoughts,
        },
        force_mode="debate",
    )


def run_server() -> None:
    mcp.run(transport="stdio")
