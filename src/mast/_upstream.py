"""Port 1:1 of upstream sequential-thinking TypeScript server logic.

Reference: https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking
This module must not contain any MAST-specific logic. Keep it as a faithful
translation so upstream changes can be ported here in isolation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ThoughtData:
    thought: str
    thought_number: int
    total_thoughts: int
    next_thought_needed: bool
    is_revision: bool = False
    revises_thought: int | None = None
    branch_from_thought: int | None = None
    branch_id: str | None = None
    needs_more_thoughts: bool = False


@dataclass
class SequentialThinkingServer:
    """Pure port of upstream SequentialThinkingServer (lib.ts)."""

    thought_history: list[ThoughtData] = field(default_factory=list)
    branches: dict[str, list[ThoughtData]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_thought(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Process a single thought and return the upstream-compatible response."""
        thought = self._validate_input(input_data)
        self._store_thought(thought)
        return self._build_response(thought)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_input(self, data: dict[str, Any]) -> ThoughtData:
        if not isinstance(data.get("thought"), str):
            raise ValueError("'thought' must be a string")
        if not isinstance(data.get("thoughtNumber"), int):
            raise ValueError("'thoughtNumber' must be an integer")
        if not isinstance(data.get("totalThoughts"), int):
            raise ValueError("'totalThoughts' must be an integer")
        if not isinstance(data.get("nextThoughtNeeded"), bool):
            raise ValueError("'nextThoughtNeeded' must be a boolean")

        revises_thought: int | None = data.get("revisesThought")
        branch_from_thought: int | None = data.get("branchFromThought")
        branch_id: str | None = data.get("branchId")

        # Validate that revisesThought references an existing thought
        if revises_thought is not None:
            existing = {t.thought_number for t in self.thought_history}
            if revises_thought not in existing:
                raise ValueError(
                    f"'revisesThought' #{revises_thought} does not reference an existing thought"
                )

        # branchId and branchFromThought must appear together
        if (branch_id is None) != (branch_from_thought is None):
            raise ValueError(
                "'branchId' and 'branchFromThought' must both be present or both absent"
            )

        # branchFromThought must reference an existing thought
        if branch_from_thought is not None:
            existing = {t.thought_number for t in self.thought_history}
            if branch_from_thought not in existing:
                raise ValueError(
                    f"'branchFromThought' #{branch_from_thought} does not reference an existing thought"  # noqa: E501
                )

        thought_number: int = data["thoughtNumber"]
        total_thoughts: int = data["totalThoughts"]

        # Auto-extend totalThoughts when thoughtNumber exceeds it (mirrors upstream)
        if thought_number > total_thoughts:
            total_thoughts = thought_number

        return ThoughtData(
            thought=data["thought"],
            thought_number=thought_number,
            total_thoughts=total_thoughts,
            next_thought_needed=data["nextThoughtNeeded"],
            is_revision=bool(data.get("isRevision", False)),
            revises_thought=revises_thought,
            branch_from_thought=branch_from_thought,
            branch_id=branch_id,
            needs_more_thoughts=bool(data.get("needsMoreThoughts", False)),
        )

    def _store_thought(self, thought: ThoughtData) -> None:
        if thought.branch_id:
            if thought.branch_id not in self.branches:
                self.branches[thought.branch_id] = []
            self.branches[thought.branch_id].append(thought)
        else:
            self.thought_history.append(thought)

    def _build_response(self, thought: ThoughtData) -> dict[str, Any]:
        return {
            "thoughtNumber": thought.thought_number,
            "totalThoughts": thought.total_thoughts,
            "nextThoughtNeeded": thought.next_thought_needed,
            "branches": list(self.branches.keys()),
            "thoughtHistoryLength": len(self.thought_history),
        }

    def format_thought(self, thought: ThoughtData, disable_logging: bool = False) -> str:
        """Format a thought for console output (mirrors formatThought in lib.ts)."""
        if disable_logging:
            return ""

        prefix = ""
        context = ""

        if thought.is_revision:
            prefix = "🔄 Revision"
            context = f" (revises #{thought.revises_thought})"
        elif thought.branch_from_thought is not None:
            prefix = "🌿 Branch"
            context = f" (from #{thought.branch_from_thought}, id: {thought.branch_id})"
        else:
            prefix = "💭 Thought"

        header = f"{prefix} {thought.thought_number}/{thought.total_thoughts}{context}"
        border = "─" * max(len(header), 4)
        return f"\n┌─ {header}\n│\n│ {thought.thought}\n│\n└─{border}\n"

    def get_history_for_branch(self, branch_id: str | None) -> list[ThoughtData]:
        if branch_id:
            return self.branches.get(branch_id, [])
        return self.thought_history

    def to_json(self) -> str:
        return json.dumps(
            {
                "thoughtHistory": [
                    {
                        "thought": t.thought,
                        "thoughtNumber": t.thought_number,
                        "totalThoughts": t.total_thoughts,
                        "nextThoughtNeeded": t.next_thought_needed,
                        "isRevision": t.is_revision,
                        "revisesThought": t.revises_thought,
                        "branchFromThought": t.branch_from_thought,
                        "branchId": t.branch_id,
                        "needsMoreThoughts": t.needs_more_thoughts,
                    }
                    for t in self.thought_history
                ],
                "branches": {
                    bid: [
                        {"thought": t.thought, "thoughtNumber": t.thought_number} for t in thoughts
                    ]
                    for bid, thoughts in self.branches.items()
                },
            }
        )
