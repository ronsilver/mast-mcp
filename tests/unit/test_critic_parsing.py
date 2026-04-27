"""Unit tests for Critic response parsing."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mast.validation.schemas import CriticResponse, IssueSeverity, IssueType


def test_parse_valid_response() -> None:
    raw = {
        "issues": [
            {"severity": "high", "type": "logic", "detail": "Contradicts step 2"},
            {"severity": "low", "type": "assumption", "detail": "Assumes network always available"},
        ],
        "strengths": ["Well-structured approach"],
        "summary": "One critical logic flaw found",
    }
    result = CriticResponse.model_validate(raw)
    assert len(result.issues) == 2
    assert result.issues[0].severity == IssueSeverity.HIGH
    assert result.issues[0].type == IssueType.LOGIC


def test_parse_empty_issues() -> None:
    raw = {"issues": [], "strengths": [], "summary": "No issues found"}
    result = CriticResponse.model_validate(raw)
    assert result.issues == []


def test_parse_no_strengths() -> None:
    raw = {"issues": [], "summary": "Clean"}
    result = CriticResponse.model_validate(raw)
    assert result.strengths == []


def test_invalid_severity_raises() -> None:
    raw = {
        "issues": [{"severity": "critical", "type": "logic", "detail": "Bad"}],
        "summary": "",
    }
    with pytest.raises(ValidationError):
        CriticResponse.model_validate(raw)


def test_invalid_type_raises() -> None:
    raw = {
        "issues": [{"severity": "high", "type": "unknown_type", "detail": "Bad"}],
        "summary": "",
    }
    with pytest.raises(ValidationError):
        CriticResponse.model_validate(raw)
