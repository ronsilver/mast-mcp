"""Unit tests for CriticAgent prompt rendering."""

from __future__ import annotations

import re

from mast.agents.base import OllamaClient
from mast.agents.critic import CriticAgent, _load_prompt


def _make_agent() -> CriticAgent:
    return CriticAgent(OllamaClient())


def test_prompt_loads_without_frontmatter() -> None:
    """Loaded prompt must not contain YAML frontmatter."""
    text = _load_prompt("critic.md")
    assert not text.startswith("---"), "Frontmatter was not stripped"
    assert "version:" not in text[:50]


def test_template_renders_basic() -> None:
    agent = _make_agent()
    rendered = agent._template.render(
        thought="Use Redis for caching",
        thought_number=1,
        total_thoughts=3,
        history_summary="(no previous thoughts)",
        is_revision=False,
        revises_thought=None,
        branch_id=None,
        branch_from=None,
    )
    assert "Use Redis for caching" in rendered
    assert "Thought 1 of 3" in rendered
    assert "history_summary" not in rendered  # variable was substituted


def test_no_unrendered_variables() -> None:
    """No {{ ... }} placeholders should remain after rendering."""
    agent = _make_agent()
    rendered = agent._template.render(
        thought="Test thought",
        thought_number=2,
        total_thoughts=5,
        history_summary="Some history",
        is_revision=False,
        revises_thought=None,
        branch_id=None,
        branch_from=None,
    )
    unrendered = re.findall(r"\{\{.*?\}\}", rendered)
    assert not unrendered, f"Unrendered variables: {unrendered}"


def test_revision_context_shown() -> None:
    agent = _make_agent()
    rendered = agent._template.render(
        thought="Revised thought",
        thought_number=3,
        total_thoughts=5,
        history_summary="",
        is_revision=True,
        revises_thought=2,
        branch_id=None,
        branch_from=None,
    )
    assert "revises" in rendered.lower() or "#2" in rendered


def test_branch_context_shown() -> None:
    agent = _make_agent()
    rendered = agent._template.render(
        thought="Branch thought",
        thought_number=2,
        total_thoughts=5,
        history_summary="",
        is_revision=False,
        revises_thought=None,
        branch_id="feature-x",
        branch_from=1,
    )
    assert "feature-x" in rendered


def test_long_thought_truncation_note() -> None:
    """Thoughts over 4000 chars should trigger the truncation block."""
    agent = _make_agent()
    long_thought = "A" * 4001
    rendered = agent._template.render(
        thought=long_thought,
        thought_number=1,
        total_thoughts=1,
        history_summary="",
        is_revision=False,
        revises_thought=None,
        branch_id=None,
        branch_from=None,
    )
    assert "truncated" in rendered.lower() or "4000" in rendered


def test_empty_history_summary() -> None:
    agent = _make_agent()
    rendered = agent._template.render(
        thought="Short",
        thought_number=1,
        total_thoughts=1,
        history_summary="",
        is_revision=False,
        revises_thought=None,
        branch_id=None,
        branch_from=None,
    )
    assert rendered  # must not be empty
