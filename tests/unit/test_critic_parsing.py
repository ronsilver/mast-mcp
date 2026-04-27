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


def test_new_issue_types_consistency_and_completeness() -> None:
    raw = {
        "issues": [
            {
                "severity": "medium",
                "type": "consistency",
                "detail": "Contradicts thought #2",
                "evidence": "use Redis",
                "refs": ["#2"],
            },
            {
                "severity": "low",
                "type": "completeness",
                "detail": "Omits error handling case",
                "evidence": "always succeeds",
                "refs": [],
            },
        ],
        "summary": "Two new-type issues",
    }
    result = CriticResponse.model_validate(raw)
    assert result.issues[0].type == IssueType.CONSISTENCY
    assert result.issues[1].type == IssueType.COMPLETENESS
    assert result.issues[0].evidence == "use Redis"
    assert result.issues[0].refs == ["#2"]


def test_hardest_issue_field() -> None:
    raw = {
        "issues": [{"severity": "high", "type": "security", "detail": "Exposes secrets"}],
        "summary": "Critical",
        "hardestIssue": "Exposes secrets",
    }
    result = CriticResponse.model_validate(raw)
    assert result.hardest_issue == "Exposes secrets"


def test_detail_max_length_enforced() -> None:
    long_detail = "X" * 301
    raw = {
        "issues": [{"severity": "low", "type": "scope", "detail": long_detail}],
        "summary": "",
    }
    with pytest.raises(ValidationError):
        CriticResponse.model_validate(raw)


def test_summary_max_length_enforced() -> None:
    raw = {"issues": [], "summary": "S" * 121}
    with pytest.raises(ValidationError):
        CriticResponse.model_validate(raw)


def test_strengths_max_count_enforced() -> None:
    raw = {"issues": [], "strengths": ["a", "b", "c", "d"], "summary": ""}
    with pytest.raises(ValidationError):
        CriticResponse.model_validate(raw)
