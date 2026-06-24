"""
Canonical tool contract ported 1:1 from upstream sequential-thinking.

Source: modelcontextprotocol/servers/src/sequentialthinking/index.ts
This module must not contain any MAST-specific logic.
"""

from __future__ import annotations

from typing import Any

SEQUENTIAL_THINKING_TOOL_DESCRIPTION = """\
A tool for dynamic and reflective problem-solving through thoughts.
This tool helps analyze problems through a flexible thinking process that can adapt and \
evolve. Each thought can build on, question, or revise previous insights as understanding \
deepens.

When to use this tool:
- Breaking down complex problems into steps
- Planning and design with room for revision
- Analysis that might need course correction
- Problems where the solution path isn't clear upfront
- Problems that require a multi-step solution
- Tasks that need careful consideration of multiple aspects

Key features:
- You can adjust total_thoughts up or down as you progress
- You can question or revise previous thoughts
- You can add more thoughts even after reaching what seemed like the end
- You can express uncertainty and explore alternative approaches

Parameters explained:
- thought: Your current thinking step
- next_thought_needed: True if you need more thinking, even if at what you thought was the end
- thought_number: Current thought number
- total_thoughts: Current estimate of thoughts needed (can be adjusted)
- is_revision: A boolean indicating if this thought revises previous thinking
- revises_thought: If is_revision is true, which thought number is being reconsidered
- branch_from_thought: Branching point thought number
- branch_id: Branch identifier
- needs_more_thoughts: If you realize you need more thoughts

You should:
1. Start with an initial estimate of needed thoughts
2. Feel free to question or revise previous thoughts
3. Don't hesitate to add more thoughts if needed
4. Use is_revision when reconsidering previous thinking
5. Only set next_thought_needed to false when truly done\
"""

SEQUENTIAL_THINKING_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "thought": {
            "type": "string",
            "description": "Your current thinking step",
        },
        "nextThoughtNeeded": {
            "type": "boolean",
            "description": "Whether another thought step is needed",
        },
        "thoughtNumber": {
            "type": "integer",
            "description": "Current thought number",
            "minimum": 1,
        },
        "totalThoughts": {
            "type": "integer",
            "description": "Estimated total thoughts needed",
            "minimum": 1,
        },
        "isRevision": {
            "type": "boolean",
            "description": "Whether this revises previous thinking",
        },
        "revisesThought": {
            "type": "integer",
            "description": "Which thought is being reconsidered",
            "minimum": 1,
        },
        "branchFromThought": {
            "type": "integer",
            "description": "Branching point thought number",
            "minimum": 1,
        },
        "branchId": {
            "type": "string",
            "description": "Branch identifier",
        },
        "needsMoreThoughts": {
            "type": "boolean",
            "description": "If more thoughts are needed beyond current total",
        },
    },
    "required": ["thought", "nextThoughtNeeded", "thoughtNumber", "totalThoughts"],
}
