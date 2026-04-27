"""Unit tests for Judge response parsing."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mast.validation.schemas import JudgeResponse, Verdict


def test_parse_accept_verdict() -> None:
    raw = {
        "verdict": "accept",
        "confidence": 0.95,
        "rationale": "Solid approach, no issues",
        "suggestedRevision": None,
    }
    result = JudgeResponse.model_validate(raw)
    assert result.verdict == Verdict.ACCEPT
    assert result.confidence == 0.95
    assert result.suggested_revision is None


def test_parse_revise_verdict() -> None:
    raw = {
        "verdict": "revise",
        "confidence": 0.75,
        "rationale": "One correctable flaw",
        "suggestedRevision": "Use env vars instead",
        "suggestedRevisionMode": "rewrite",
    }
    result = JudgeResponse.model_validate(raw)
    assert result.verdict == Verdict.REVISE
    assert result.suggested_revision == "Use env vars instead"
    assert result.suggested_revision_mode == "rewrite"


def test_parse_reject_verdict() -> None:
    raw = {
        "verdict": "reject",
        "confidence": 0.9,
        "rationale": "Fundamental safety violation",
    }
    result = JudgeResponse.model_validate(raw)
    assert result.verdict == Verdict.REJECT


def test_invalid_verdict_raises() -> None:
    raw = {"verdict": "maybe", "confidence": 0.5, "rationale": "Unclear"}
    with pytest.raises(ValidationError):
        JudgeResponse.model_validate(raw)


def test_confidence_range_zero() -> None:
    raw = {"verdict": "accept", "confidence": 0.0, "rationale": "validation_failed"}
    result = JudgeResponse.model_validate(raw)
    assert result.confidence == 0.0


def test_evidence_seen_field() -> None:
    raw = {
        "verdict": "revise",
        "confidence": 0.7,
        "rationale": "Security risk confirmed",
        "evidenceSeen": ["Committing API keys to the repo"],
    }
    result = JudgeResponse.model_validate(raw)
    assert result.evidence_seen == ["Committing API keys to the repo"]


def test_evidence_seen_defaults_empty() -> None:
    raw = {"verdict": "accept", "confidence": 0.8, "rationale": "Fine"}
    result = JudgeResponse.model_validate(raw)
    assert result.evidence_seen == []


def test_rationale_max_length_enforced() -> None:
    raw = {"verdict": "accept", "confidence": 0.5, "rationale": "R" * 241}
    with pytest.raises(ValidationError):
        JudgeResponse.model_validate(raw)


def test_suggested_revision_max_length_enforced() -> None:
    raw = {
        "verdict": "revise",
        "confidence": 0.6,
        "rationale": "Too long revision",
        "suggestedRevision": "X" * 601,
    }
    with pytest.raises(ValidationError):
        JudgeResponse.model_validate(raw)


def test_suggested_revision_mode_patch() -> None:
    raw = {
        "verdict": "revise",
        "confidence": 0.65,
        "rationale": "Patch needed",
        "suggestedRevision": "- Add error handling\n- Use env vars",
        "suggestedRevisionMode": "patch",
    }
    result = JudgeResponse.model_validate(raw)
    assert result.suggested_revision_mode == "patch"


def test_invalid_revision_mode_raises() -> None:
    raw = {
        "verdict": "revise",
        "confidence": 0.6,
        "rationale": "Fix needed",
        "suggestedRevisionMode": "unknown_mode",
    }
    with pytest.raises(ValidationError):
        JudgeResponse.model_validate(raw)
