"""Unit tests for upstream parity (passive mode = identical to upstream)."""
from __future__ import annotations

import pytest

from mast._upstream import SequentialThinkingServer


@pytest.fixture
def server() -> SequentialThinkingServer:
    return SequentialThinkingServer()


def test_basic_thought(server: SequentialThinkingServer) -> None:
    resp = server.process_thought(
        {
            "thought": "Analyzing the problem",
            "thoughtNumber": 1,
            "totalThoughts": 3,
            "nextThoughtNeeded": True,
        }
    )
    assert resp["thoughtNumber"] == 1
    assert resp["totalThoughts"] == 3
    assert resp["nextThoughtNeeded"] is True
    assert resp["thoughtHistoryLength"] == 1
    assert resp["branches"] == []


def test_sequential_thoughts(server: SequentialThinkingServer) -> None:
    for i in range(1, 4):
        server.process_thought(
            {
                "thought": f"Thought {i}",
                "thoughtNumber": i,
                "totalThoughts": 3,
                "nextThoughtNeeded": i < 3,
            }
        )
    assert len(server.thought_history) == 3


def test_revision_thought(server: SequentialThinkingServer) -> None:
    server.process_thought(
        {
            "thought": "First attempt",
            "thoughtNumber": 1,
            "totalThoughts": 2,
            "nextThoughtNeeded": True,
        }
    )
    resp = server.process_thought(
        {
            "thought": "Revised first attempt",
            "thoughtNumber": 2,
            "totalThoughts": 2,
            "nextThoughtNeeded": False,
            "isRevision": True,
            "revisesThought": 1,
        }
    )
    assert resp["thoughtHistoryLength"] == 2


def test_branch_thought(server: SequentialThinkingServer) -> None:
    server.process_thought(
        {"thought": "Main", "thoughtNumber": 1, "totalThoughts": 2, "nextThoughtNeeded": True}
    )
    resp = server.process_thought(
        {
            "thought": "Branch thought",
            "thoughtNumber": 2,
            "totalThoughts": 2,
            "nextThoughtNeeded": False,
            "branchFromThought": 1,
            "branchId": "branch-a",
        }
    )
    assert "branch-a" in resp["branches"]
    # branch thoughts don't increment main history
    assert resp["thoughtHistoryLength"] == 1


def test_missing_required_fields(server: SequentialThinkingServer) -> None:
    with pytest.raises(ValueError):
        server.process_thought({"thought": "Missing fields"})


def test_format_thought_regular(server: SequentialThinkingServer) -> None:
    server.process_thought(
        {"thought": "Hello", "thoughtNumber": 1, "totalThoughts": 1, "nextThoughtNeeded": False}
    )
    thought = server.thought_history[0]
    formatted = server.format_thought(thought)
    assert "💭" in formatted
    assert "Hello" in formatted


def test_format_thought_disabled_logging(server: SequentialThinkingServer) -> None:
    server.process_thought(
        {"thought": "Hello", "thoughtNumber": 1, "totalThoughts": 1, "nextThoughtNeeded": False}
    )
    thought = server.thought_history[0]
    assert server.format_thought(thought, disable_logging=True) == ""


def test_passive_output_shape(server: SequentialThinkingServer) -> None:
    """Golden test: output must match upstream JSON shape exactly."""
    resp = server.process_thought(
        {
            "thought": "Starting analysis",
            "thoughtNumber": 1,
            "totalThoughts": 5,
            "nextThoughtNeeded": True,
        }
    )
    required_keys = {
        "thoughtNumber",
        "totalThoughts",
        "nextThoughtNeeded",
        "branches",
        "thoughtHistoryLength",
    }
    assert required_keys.issubset(resp.keys()), f"Missing keys: {required_keys - resp.keys()}"
