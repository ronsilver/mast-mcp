"""MAST-specific tool definition — superset of upstream sequential-thinking."""

from __future__ import annotations

import copy
from typing import Any

from mast._upstream_tool import SEQUENTIAL_THINKING_INPUT_SCHEMA

MAST_DEBATE_TOOL_DESCRIPTION = """\
Forces a specific reasoning strategy (Critic+Judge debate, De Bono Six Hats, Actor-Critic,
Brainstorm, Tree of Thoughts, Kalman Convergence, or Workflow) regardless of server defaults.
Use for maximum validation quality on critical reasoning steps.

In debate mode: thought evaluated by Critic (identifies flaws) and Judge (verdict + revision).
In debono mode: 7 sequential De Bono hats refine a working document.
In actor_critic mode: iterative Critic+Judge loop up to ACTOR_CRITIC_MAX_ROUNDS.
In brainstorm mode: N parallel generators produce ideas, Synthesizer merges top picks.
In tot mode (Tree of Thoughts): N parallel branch generators, Voter scores them.
In kalman mode: N scorers evaluate quality, Kalman filter fuses scores optimally.
In workflow mode: chains multiple modes in sequence defined by MAST_WORKFLOW_STAGES.

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
