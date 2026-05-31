"""Pydantic schemas for MAST validation pipeline."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

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
    CONSISTENCY = "consistency"
    COMPLETENESS = "completeness"


class CriticIssue(BaseModel):
    severity: IssueSeverity
    type: IssueType
    detail: str = Field(max_length=300)
    evidence: str | None = Field(default=None, max_length=120)
    refs: list[str] = Field(default_factory=list)


class CriticResponse(BaseModel):
    issues: list[CriticIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list, max_length=3)
    summary: str = Field(default="", max_length=120)
    hardest_issue: str | None = Field(default=None, alias="hardestIssue")

    model_config = {"populate_by_name": True}


class Verdict(StrEnum):
    ACCEPT = "accept"
    REVISE = "revise"
    REJECT = "reject"


class JudgeResponse(BaseModel):
    verdict: Verdict
    confidence: float
    rationale: str = Field(max_length=240)
    suggested_revision: str | None = Field(default=None, alias="suggestedRevision", max_length=600)
    suggested_revision_mode: Literal["rewrite", "patch"] | None = Field(
        default=None, alias="suggestedRevisionMode"
    )
    evidence_seen: list[str] = Field(default_factory=list, alias="evidenceSeen")

    model_config = {"populate_by_name": True}


class ValidationResult(BaseModel):
    """Critic output enriched with model metadata."""

    issues: list[CriticIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    critic_model: str = Field(serialization_alias="criticModel")
    critic_latency_ms: int = Field(serialization_alias="criticLatencyMs")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# De Bono Six Hats schemas
# ---------------------------------------------------------------------------


class HatName(StrEnum):
    BLUE_OPEN = "blue_open"
    WHITE = "white"
    GREEN = "green"
    YELLOW = "yellow"
    BLACK = "black"
    RED = "red"
    BLUE_CLOSE = "blue_close"


class HatOutput(BaseModel):
    hat: HatName
    model: str
    latency_ms: int
    rationale: str = Field(default="", max_length=120)


class DebonoResult(BaseModel):
    hats: list[HatOutput] = Field(default_factory=list)
    total_latency_ms: int = 0


# ---------------------------------------------------------------------------
# Actor-Critic schemas
# ---------------------------------------------------------------------------


class ActorCriticRound(BaseModel):
    round: int
    thought: str
    critic: CriticResponse
    verdict: Verdict
    suggested_revision: str | None = Field(default=None, alias="suggestedRevision")
    critic_latency_ms: int = Field(default=0, alias="criticLatencyMs")
    judge_latency_ms: int = Field(default=0, alias="judgeLatencyMs")

    model_config = {"populate_by_name": True}


class ActorCriticResult(BaseModel):
    rounds: list[ActorCriticRound]
    total_rounds: int = Field(alias="totalRounds")
    final_thought: str = Field(alias="finalThought")
    converged: bool

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Brainstorm schemas
# ---------------------------------------------------------------------------


class BrainstormIdea(BaseModel):
    idea: str = Field(max_length=400)
    rationale: str = Field(default="", max_length=120)
    angle: str = Field(default="")
    model: str = Field(default="")
    latency_ms: int = Field(default=0, alias="latencyMs")

    model_config = {"populate_by_name": True}


class BrainstormResult(BaseModel):
    ideas: list[BrainstormIdea]
    synthesis: str
    top_ideas: list[str] = Field(default_factory=list, alias="topIdeas")
    synth_latency_ms: int = Field(default=0, alias="synthLatencyMs")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Tree of Thoughts schemas
# ---------------------------------------------------------------------------


class ToTBranch(BaseModel):
    next_step: str = Field(max_length=600, alias="nextStep")
    rationale: str = Field(default="", max_length=120)
    model: str = Field(default="")
    voter_score: float | None = Field(default=None, alias="voterScore")
    voter_rationale: str | None = Field(default=None, alias="voterRationale")

    model_config = {"populate_by_name": True}


class ToTResult(BaseModel):
    branches: list[ToTBranch]
    selected_branch: ToTBranch | None = Field(default=None, alias="selectedBranch")
    voter_scores: list[dict[str, object]] = Field(default_factory=list, alias="voterScores")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Kalman Convergence schemas
# ---------------------------------------------------------------------------


class KalmanScoreEntry(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=80)
    model: str = Field(default="")
    latency_ms: int = Field(default=0, alias="latencyMs")

    model_config = {"populate_by_name": True}


class KalmanResult(BaseModel):
    scorers: list[KalmanScoreEntry]
    x_final: float = Field(alias="xFinal")
    P_final: float = Field(alias="PFinal")
    converged: bool
    triggers: list[str]
    verdict: Verdict
    confidence: float

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Workflow schemas
# ---------------------------------------------------------------------------


class WorkflowStageResult(BaseModel):
    stage: str
    verdict: Verdict
    confidence: float
    suggested_revision: str | None = Field(default=None, alias="suggestedRevision")
    input_thought: str = Field(alias="inputThought")
    output_thought: str = Field(alias="outputThought")
    error: str | None = None

    model_config = {"populate_by_name": True}


class WorkflowResult(BaseModel):
    stages: list[WorkflowStageResult]
    final_thought: str = Field(alias="finalThought")
    total_stages: int = Field(alias="totalStages")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# MastOutput — extended per-mode top-level output
# ---------------------------------------------------------------------------


class MastOutput(SequentialThinkingOutput):
    """Extended output for all validation modes."""

    validation: ValidationResult | None = None
    verdict: Verdict | None = None
    confidence: float | None = None
    suggested_revision: str | None = Field(default=None, alias="suggestedRevision")
    judge_model: str | None = Field(default=None, alias="judgeModel")
    judge_latency_ms: int | None = Field(default=None, alias="judgeLatencyMs")
    debono: DebonoResult | None = None
    actor_critic: ActorCriticResult | None = None
    brainstorm: BrainstormResult | None = None
    tot: ToTResult | None = None
    kalman: KalmanResult | None = None
    workflow: WorkflowResult | None = None

    model_config = {"populate_by_name": True}

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)
