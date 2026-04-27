"""Unit tests for the defensive JSON parser in agents/base.py."""

from __future__ import annotations

from mast.agents.base import _extract_json


def test_clean_json() -> None:
    result = _extract_json('{"verdict": "accept", "confidence": 0.9}')
    assert result == {"verdict": "accept", "confidence": 0.9}


def test_json_with_prose_prefix() -> None:
    result = _extract_json('Here is the JSON: {"issues": [], "summary": "clean"}')
    assert result is not None
    assert result["issues"] == []


def test_json_with_prose_suffix() -> None:
    result = _extract_json('{"issues": []} Hope this helps!')
    assert result == {"issues": []}


def test_json_inside_think_block() -> None:
    text = '<think>Let me analyze...</think>{"verdict": "revise", "confidence": 0.7}'
    result = _extract_json(text)
    assert result is not None
    assert result["verdict"] == "revise"


def test_json_inside_code_fence() -> None:
    text = '```json\n{"issues": [], "summary": "ok"}\n```'
    result = _extract_json(text)
    assert result == {"issues": [], "summary": "ok"}


def test_json_inside_plain_code_fence() -> None:
    text = '```\n{"verdict": "accept"}\n```'
    result = _extract_json(text)
    assert result == {"verdict": "accept"}


def test_think_block_before_fence() -> None:
    text = '<think>Reasoning...</think>\n```json\n{"x": 1}\n```'
    result = _extract_json(text)
    assert result == {"x": 1}


def test_nested_braces_in_strings() -> None:
    text = '{"detail": "handles {curly} braces", "severity": "low"}'
    result = _extract_json(text)
    assert result is not None
    assert result["severity"] == "low"


def test_returns_none_for_invalid() -> None:
    result = _extract_json("this is just plain text with no JSON")
    assert result is None


def test_returns_none_for_empty_string() -> None:
    assert _extract_json("") is None


def test_returns_none_for_array_not_object() -> None:
    result = _extract_json("[1, 2, 3]")
    assert result is None


def test_case_insensitive_think_tag() -> None:
    text = "<THINK>internal</THINK>{'verdict': 'accept'}"
    # single-quoted JSON is invalid, should still return None
    result = _extract_json(text)
    assert result is None


def test_multiline_think_block() -> None:
    text = '<think>\nLine1\nLine2\n</think>\n{"ok": true}'
    result = _extract_json(text)
    assert result == {"ok": True}


def test_first_valid_object_wins() -> None:
    text = '{"first": 1} {"second": 2}'
    result = _extract_json(text)
    assert result == {"first": 1}
