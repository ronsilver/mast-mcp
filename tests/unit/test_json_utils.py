"""Tests for shared JSON extraction utilities."""

from __future__ import annotations

from mast.agents._json_utils import (
    CRITIC_FALLBACK,
    JUDGE_FALLBACK,
    extract_json,
)


def test_extract_json_clean() -> None:
    text = '{"issues": [], "summary": "ok"}'
    assert extract_json(text) == {"issues": [], "summary": "ok"}


def test_extract_json_with_think_block() -> None:
    text = '<think>reasoning</think>\n{"verdict": "accept"}'
    assert extract_json(text) == {"verdict": "accept"}


def test_extract_json_with_code_fence() -> None:
    text = '```json\n{"x": 1}\n```'
    assert extract_json(text) == {"x": 1}


def test_extract_json_with_prose_prefix() -> None:
    text = 'Here is the response:\n{"key": "value"}'
    assert extract_json(text) == {"key": "value"}


def test_extract_json_no_json_returns_none() -> None:
    assert extract_json("just prose") is None


def test_extract_json_nested() -> None:
    text = '{"a": {"b": [1, 2, 3]}}'
    assert extract_json(text) == {"a": {"b": [1, 2, 3]}}


def test_critic_fallback_shape() -> None:
    assert "issues" in CRITIC_FALLBACK
    assert "strengths" in CRITIC_FALLBACK
    assert "summary" in CRITIC_FALLBACK


def test_judge_fallback_shape() -> None:
    assert "verdict" in JUDGE_FALLBACK
    assert "confidence" in JUDGE_FALLBACK
    assert "rationale" in JUDGE_FALLBACK
    assert "suggestedRevision" in JUDGE_FALLBACK
