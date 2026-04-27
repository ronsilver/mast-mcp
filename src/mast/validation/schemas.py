"""Pydantic schemas for MAST validation pipeline."""
from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Upstream-compatible input schema
# ---------------------------------------------------------------------------


class SequentialThinkingInput(BaseModel):
    """Input schema — superset of upstream sequential-thinking."""

    thought: str
    thought_number: int = Field(alias="thoughtNumber")
    total_thoughts: int = Field(alias="totalThoughts")
    next_thought_needed: bool = Field(alias="nextThoughtNeeded")
    is_revision: bool | None = Field(default=None, alias="isRevision")
    revises_thought: int | None = Field(default=None, alias="revisesThought")
    branch_from_thought: int | None = Field(default=None, alias="branchFromThought")
    branch_id: str | None = Field(default=None, alias="branchId")
    needs_more_thoughts: bool | None = Field(default=None, alias="needsMoreThoughts")

    # MAST extensions (optional)
    mode: str | None = None  # overrides global MAST_MODE for this step
    skip_validation: bool = Field(default=False, alias="skipValidation")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Upstream-compatible output schema
# ---------------------------------------------------------------------------


class SequentialThinkingOutput(BaseModel):
    """Base output — compatible with upstream response."""

    thought_number: int = Field(serialization_alias="thoughtNumber")
    total_thoughts: int = Field(serialization_alias="totalThoughts")
    next_thought_needed: bool = Field(serialization_alias="nextThoughtNeeded")
    branches: list[str] = Field(default_factory=list)
    thought_history_length: int = Field(serialization_alias="thoughtHistoryLength")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# MAST extension schemas
# ---------------------------------------------------------------------------


class IssueSeverity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueType(StrEnum):
    LOGIC = "logic"
    SECURITY = "security"
    ASSUMPTION = "assumption"
    FACTUAL = "factual"
    SCOPE = "scope"


class CriticIssue(BaseModel):
    severity: IssueSeverity
    type: IssueType
    detail: str


class CriticResponse(BaseModel):
    issues: list[CriticIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    summary: str = ""


class Verdict(StrEnum):
    ACCEPT = "accept"
    REVISE = "revise"
    REJECT = "reject"


class JudgeResponse(BaseModel):
    verdict: Verdict
    confidence: float
    rationale: str
    suggested_revision: str | None = Field(default=None, alias="suggestedRevision")

    model_config = {"populate_by_name": True}


class ValidationResult(BaseModel):
    """Critic output enriched with model metadata."""

    issues: list[CriticIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    critic_model: str = Field(serialization_alias="criticModel")
    critic_latency_ms: int = Field(serialization_alias="criticLatencyMs")

    model_config = {"populate_by_name": True}


class MastOutput(SequentialThinkingOutput):
    """Extended output for validate/debate modes."""

    validation: ValidationResult | None = None
    verdict: Verdict | None = None
    confidence: float | None = None
    suggested_revision: str | None = Field(default=None, serialization_alias="suggestedRevision")
    judge_model: str | None = Field(default=None, serialization_alias="judgeModel")
    judge_latency_ms: int | None = Field(default=None, serialization_alias="judgeLatencyMs")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)
