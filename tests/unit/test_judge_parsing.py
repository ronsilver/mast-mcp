"""Unit tests for Judge response parsing."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mast.validation.schemas import JudgeResponse, Verdict


def test_parse_accept_verdict() -> None:
    raw = {
        "verdict": "accept",
        "confidence": 0.9,
        "rationale": "Thought is logically sound",
        "suggestedRevision": None,
    }
    result = JudgeResponse.model_validate(raw)
    assert result.verdict == Verdict.ACCEPT
    assert result.suggested_revision is None


def test_parse_revise_verdict() -> None:
    raw = {
        "verdict": "revise",
        "confidence": 0.75,
        "rationale": "Minor assumption needs clarification",
        "suggestedRevision": "Use retry with exponential backoff instead of fixed delay",
    }
    result = JudgeResponse.model_validate(raw)
    assert result.verdict == Verdict.REVISE
    assert result.suggested_revision is not None


def test_parse_reject_verdict() -> None:
    raw = {
        "verdict": "reject",
        "confidence": 0.95,
        "rationale": "Fundamental security flaw",
        "suggestedRevision": None,
    }
    result = JudgeResponse.model_validate(raw)
    assert result.verdict == Verdict.REJECT


def test_invalid_verdict_raises() -> None:
    raw = {
        "verdict": "maybe",
        "confidence": 0.5,
        "rationale": "Unsure",
        "suggestedRevision": None,
    }
    with pytest.raises(ValidationError):
        JudgeResponse.model_validate(raw)


def test_confidence_range_valid() -> None:
    raw = {
        "verdict": "accept",
        "confidence": 0.0,
        "rationale": "validation_failed",
        "suggestedRevision": None,
    }
    result = JudgeResponse.model_validate(raw)
    assert result.confidence == 0.0
