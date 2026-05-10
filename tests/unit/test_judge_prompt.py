"""Unit tests for JudgeAgent prompt rendering."""

from __future__ import annotations

import json
import re

from mast.agents._utils import load_prompt as _load_prompt
from mast.agents.base import OllamaClient
from mast.agents.judge import JudgeAgent
from mast.validation.schemas import CriticIssue, CriticResponse, IssueSeverity, IssueType


def _make_agent() -> JudgeAgent:
    return JudgeAgent(OllamaClient())


def _sample_critique() -> CriticResponse:
    return CriticResponse(
        issues=[
            CriticIssue(
                severity=IssueSeverity.HIGH,
                type=IssueType.SECURITY,
                detail="Commits secrets to VCS",
            )
        ],
        summary="Critical security flaw",
    )


def test_prompt_loads_without_frontmatter() -> None:
    text = _load_prompt("mast.prompts.debate", "judge.md")
    assert not text.startswith("---"), "Frontmatter was not stripped"
    assert "version:" not in text[:50]


def test_template_renders_basic() -> None:
    agent = _make_agent()
    critique = _sample_critique()
    rendered = agent._template.render(
        thought="Store API key in config file",
        thought_number=1,
        total_thoughts=3,
        history_summary="(no previous thoughts)",
        critique_json=json.dumps(critique.model_dump(), ensure_ascii=False),
        mode="debate",
        is_revision=False,
    )
    assert "Store API key" in rendered
    assert "debate" in rendered
    assert "critique_json" not in rendered  # variable substituted


def test_no_unrendered_variables() -> None:
    agent = _make_agent()
    critique = _sample_critique()
    rendered = agent._template.render(
        thought="Test thought",
        thought_number=2,
        total_thoughts=4,
        history_summary="Some history",
        critique_json=json.dumps(critique.model_dump(), ensure_ascii=False),
        mode="debate",
        is_revision=False,
    )
    unrendered = re.findall(r"\{\{.*?\}\}", rendered)
    assert not unrendered, f"Unrendered variables: {unrendered}"


def test_critique_json_is_present_and_parseable() -> None:
    """The serialised critique dict must appear verbatim in the rendered prompt."""
    agent = _make_agent()
    critique = _sample_critique()
    critique_str = json.dumps(critique.model_dump(), ensure_ascii=False)
    rendered = agent._template.render(
        thought="Test",
        thought_number=1,
        total_thoughts=1,
        history_summary="",
        critique_json=critique_str,
        mode="validate",
        is_revision=False,
    )
    # The serialised JSON must appear verbatim — Jinja must not escape or mangle it.
    assert critique_str in rendered, "Critique JSON not found verbatim in rendered prompt"
    # Ensure it parses correctly (no corruption from template rendering)
    from mast.agents.base import _extract_json

    recovered = _extract_json(critique_str)
    assert recovered is not None and "issues" in recovered


def test_revision_context_shown() -> None:
    agent = _make_agent()
    rendered = agent._template.render(
        thought="Revised thought",
        thought_number=3,
        total_thoughts=5,
        history_summary="",
        critique_json="{}",
        mode="debate",
        is_revision=True,
    )
    assert "revision" in rendered.lower() or "REVISION" in rendered


def test_no_revision_context_when_not_revision() -> None:
    agent = _make_agent()
    rendered = agent._template.render(
        thought="Normal thought",
        thought_number=1,
        total_thoughts=3,
        history_summary="",
        critique_json="{}",
        mode="debate",
        is_revision=False,
    )
    assert "revision_context" not in rendered
