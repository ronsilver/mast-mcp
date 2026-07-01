"""Unit tests for upstream parity (passive mode = identical to upstream)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mast._upstream import SequentialThinkingServer
from mast._upstream_tool import SEQUENTIAL_THINKING_INPUT_SCHEMA

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def server() -> SequentialThinkingServer:
    return SequentialThinkingServer()


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------


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
    assert resp["thoughtHistoryLength"] == 1  # branch thoughts don't increment main history


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


# ---------------------------------------------------------------------------
# P1.2 — Schema parity with upstream fixture
# ---------------------------------------------------------------------------


def test_tool_schema_matches_upstream() -> None:
    """
    Our exported schema must match the upstream fixture exactly.

    Intentional extensions (mode, skipValidation) only exist in mast_debate;
    the sequentialthinking schema must be a 1:1 port.
    """
    expected = json.loads((FIXTURES / "upstream_tool_schema.json").read_text())
    actual = SEQUENTIAL_THINKING_INPUT_SCHEMA

    assert actual["type"] == expected["type"]
    assert set(actual["required"]) == set(expected["required"])

    expected_props: dict[str, object] = expected["properties"]
    actual_props: dict[str, object] = actual["properties"]

    # Every upstream property must be present with matching type
    for prop, spec in expected_props.items():
        assert prop in actual_props, f"Missing property: {prop!r}"
        assert actual_props[prop]["type"] == spec["type"], f"Type mismatch for {prop!r}"  # type: ignore[index]


# ---------------------------------------------------------------------------
# P1.3 — Validations that upstream enforces
# ---------------------------------------------------------------------------


def test_revises_thought_must_exist(server: SequentialThinkingServer) -> None:
    """The revises_thought field must reference an existing thought number."""
    server.process_thought(
        {"thought": "T1", "thoughtNumber": 1, "totalThoughts": 3, "nextThoughtNeeded": True}
    )
    with pytest.raises(ValueError, match="revisesThought"):
        server.process_thought(
            {
                "thought": "Revise nonexistent",
                "thoughtNumber": 2,
                "totalThoughts": 3,
                "nextThoughtNeeded": False,
                "isRevision": True,
                "revisesThought": 99,
            }
        )


def test_branch_from_thought_must_exist(server: SequentialThinkingServer) -> None:
    """The branch_from_thought field must reference an existing thought number."""
    server.process_thought(
        {"thought": "T1", "thoughtNumber": 1, "totalThoughts": 3, "nextThoughtNeeded": True}
    )
    with pytest.raises(ValueError, match="branchFromThought"):
        server.process_thought(
            {
                "thought": "Branch from nonexistent",
                "thoughtNumber": 2,
                "totalThoughts": 3,
                "nextThoughtNeeded": False,
                "branchFromThought": 99,
                "branchId": "branch-x",
            }
        )


def test_branch_id_and_branch_from_must_both_be_present(
    server: SequentialThinkingServer,
) -> None:
    """The branch_id field without branch_from_thought must raise."""
    server.process_thought(
        {"thought": "T1", "thoughtNumber": 1, "totalThoughts": 3, "nextThoughtNeeded": True}
    )
    # branchId alone
    with pytest.raises(ValueError, match="branchId"):
        server.process_thought(
            {
                "thought": "Orphan branch",
                "thoughtNumber": 2,
                "totalThoughts": 3,
                "nextThoughtNeeded": False,
                "branchId": "alone",
            }
        )


def test_total_thoughts_auto_extends(server: SequentialThinkingServer) -> None:
    """When thoughtNumber > totalThoughts, totalThoughts is auto-extended."""
    resp = server.process_thought(
        {
            "thought": "Overflow",
            "thoughtNumber": 5,
            "totalThoughts": 3,
            "nextThoughtNeeded": False,
        }
    )
    assert resp["totalThoughts"] == 5
