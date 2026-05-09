"""MAST-specific tool definition — superset of upstream sequential-thinking."""

from __future__ import annotations

import copy
from typing import Any

from mast._upstream_tool import SEQUENTIAL_THINKING_INPUT_SCHEMA

MAST_DEBATE_TOOL_DESCRIPTION = """\
Forces debate mode (Critic + Judge) or debono mode (Six Thinking Hats) regardless of
server defaults. Use for maximum validation quality on critical reasoning steps.

In debate mode: the thought is evaluated by two local Ollama models: a Critic identifies
flaws, and a Judge synthesizes a final verdict (accept / revise / reject) with optional
suggested revision.

In debono mode: the thought passes through 7 sequential De Bono hats (Blue Open, White,
Green, Yellow, Black, Red, Blue Close) that progressively refine a working document and
produce a verdict.

Accepts optional model overrides per call.
All other parameters are identical to the sequentialthinking tool.\
"""

# Superset schema: all upstream fields + MAST-specific overrides
_base: dict[str, Any] = copy.deepcopy(SEQUENTIAL_THINKING_INPUT_SCHEMA)
_props: dict[str, Any] = dict(_base["properties"])
_props["criticModel"] = {
    "type": "string",
    "description": "Override the Critic model for this call (e.g. 'mistral:7b-instruct')",
}
_props["judgeModel"] = {
    "type": "string",
    "description": "Override the Judge model for this call (e.g. 'deepseek-r1:8b')",
}
_props["debonoPrimaryModel"] = {
    "type": "string",
    "description": "Override main De Bono model (qwen2.5:3b) for white/yellow/black/blue",
}
_props["debonoCreativeModel"] = {
    "type": "string",
    "description": "Override the creative De Bono model (default: qwen2.5:1.5b) for green/red hats",
}
_base["properties"] = _props

MAST_DEBATE_INPUT_SCHEMA: dict[str, Any] = _base
