"""Unit tests for De Bono Six Hats prompts loading and rendering."""

from __future__ import annotations

import re

import jinja2
import pytest

from mast.agents._utils import load_prompt as _load_prompt

PROMPT_FILES = [
    "blue_open.md",
    "white.md",
    "green.md",
    "yellow.md",
    "black.md",
    "red.md",
    "blue_close.md",
]

BASE_VARS = {
    "thought": "Test thought for evaluation",
    "working_document": "## Objective\nSolve the problem.\n## Constraints\nNone.",
    "thought_number": 2,
    "total_thoughts": 5,
    "history_summary": "#1: Initial problem definition",
    "is_revision": False,
    "revises_thought": None,
    "branch_id": None,
    "branch_from": None,
    "hat_contributions": "#1 [blue_open] model=qwen2.5:3b latency=800ms: defined scope",
}

ALL_PROMT_VARS = {
    "thought",
    "working_document",
    "thought_number",
    "total_thoughts",
    "history_summary",
    "is_revision",
    "revises_thought",
    "branch_id",
    "branch_from",
    "hat_contributions",
}


@pytest.mark.parametrize("filename", PROMPT_FILES)
def test_prompt_loads_without_frontmatter(filename: str) -> None:
    text = _load_prompt("mast.prompts.debono", filename)
    assert not text.startswith("---"), "Frontmatter was not stripped"
    assert len(text) > 100


@pytest.mark.parametrize("filename", PROMPT_FILES)
def test_prompt_renders_basic(filename: str) -> None:
    text = _load_prompt("mast.prompts.debono", filename)
    tpl = jinja2.Template(text, undefined=jinja2.Undefined)
    rendered = tpl.render(**BASE_VARS)
    assert "Test thought for evaluation" in rendered


@pytest.mark.parametrize("filename", PROMPT_FILES)
def test_no_unrendered_variables(filename: str) -> None:
    text = _load_prompt("mast.prompts.debono", filename)
    tpl = jinja2.Template(text, undefined=jinja2.Undefined)
    rendered = tpl.render(**BASE_VARS)
    unrendered = re.findall(r"\{\{.*?\}\}", rendered)
    assert not unrendered, f"Unrendered variables in {filename}: {unrendered}"


@pytest.mark.parametrize("filename", PROMPT_FILES)
def test_renders_with_empty_history(filename: str) -> None:
    text = _load_prompt("mast.prompts.debono", filename)
    tpl = jinja2.Template(text, undefined=jinja2.Undefined)
    vars_no_history = dict(BASE_VARS)
    vars_no_history["history_summary"] = ""
    rendered = tpl.render(**vars_no_history)
    assert rendered


def test_blue_close_requires_hat_contributions() -> None:
    text = _load_prompt("mast.prompts.debono", "blue_close.md")
    assert "hat_contributions" in text


def test_revision_context_shown() -> None:
    text = _load_prompt("mast.prompts.debono", "blue_open.md")
    tpl = jinja2.Template(text, undefined=jinja2.Undefined)
    vars_revision = dict(BASE_VARS)
    vars_revision["is_revision"] = True
    vars_revision["revises_thought"] = 2
    rendered = tpl.render(**vars_revision)
    assert "revises" in rendered.lower() or "#2" in rendered


def test_working_document_passed_to_all_hats_except_blue_open() -> None:
    hats_with_wd = ["white", "green", "yellow", "black", "red", "blue_close"]
    for hat in hats_with_wd:
        text = _load_prompt("mast.prompts.debono", f"{hat}.md")
        assert "working_document" in text, f"{hat}.md missing working_document"


def test_blue_open_does_not_use_working_document_var() -> None:
    text = _load_prompt("mast.prompts.debono", "blue_open.md")
    assert "thought" in text
    assert "{{ working_document }}" not in text
