"""Tests for ToT voter index-based mapping (T22)."""

from __future__ import annotations

from mast.agents.tot import TreeOfThoughtsOrchestrator
from mast.validation.schemas import ToTBranch


def _make_branches(n: int) -> list[ToTBranch]:
    return [ToTBranch(nextStep=f"step-{i}", rationale=f"rationale-{i}") for i in range(n)]


def test_apply_voter_scores_by_explicit_index() -> None:
    """Scores with shuffled indices are applied to the correct branches."""
    branches = _make_branches(3)
    # Score returned in reversed order: index 2 first, then 0, then 1
    scores = [
        {"index": 2, "score": 0.9, "rationale": "best"},
        {"index": 0, "score": 0.3, "rationale": "worst"},
        {"index": 1, "score": 0.6, "rationale": "middle"},
    ]
    TreeOfThoughtsOrchestrator._apply_voter_scores(branches, scores)
    assert branches[0].voter_score == 0.3
    assert branches[0].voter_rationale == "worst"
    assert branches[1].voter_score == 0.6
    assert branches[1].voter_rationale == "middle"
    assert branches[2].voter_score == 0.9
    assert branches[2].voter_rationale == "best"


def test_apply_voter_scores_ignores_out_of_range_index() -> None:
    branches = _make_branches(2)
    scores = [
        {"index": 0, "score": 0.5, "rationale": "ok"},
        {"index": 5, "score": 0.9, "rationale": "out of range"},
    ]
    TreeOfThoughtsOrchestrator._apply_voter_scores(branches, scores)
    assert branches[0].voter_score == 0.5
    # Branch 1 stays unscored (None)
    assert branches[1].voter_score is None


def test_apply_voter_scores_ignores_missing_index() -> None:
    branches = _make_branches(2)
    scores = [
        {"score": 0.5, "rationale": "no index"},
        {"index": 1, "score": 0.7, "rationale": "with index"},
    ]
    TreeOfThoughtsOrchestrator._apply_voter_scores(branches, scores)
    assert branches[0].voter_score is None
    assert branches[1].voter_score == 0.7


def test_apply_voter_scores_ignores_non_int_index() -> None:
    branches = _make_branches(1)
    scores = [
        {"index": "zero", "score": 0.5, "rationale": "string idx"},
        {"index": 1, "score": 0.7, "rationale": "valid"},
    ]
    TreeOfThoughtsOrchestrator._apply_voter_scores(branches, scores)
    # String index ignored, only valid (out-of-range) score attempt
    assert branches[0].voter_score is None


def test_apply_voter_scores_handles_empty_scores() -> None:
    branches = _make_branches(2)
    TreeOfThoughtsOrchestrator._apply_voter_scores(branches, [])
    assert branches[0].voter_score is None
    assert branches[1].voter_score is None


def test_apply_voter_scores_handles_extra_scores() -> None:
    """
    More scores than branches: extras with valid indices within range.

    Extras with out-of-range are ignored.
    """
    branches = _make_branches(2)
    scores = [
        {"index": 0, "score": 0.4, "rationale": "a"},
        {"index": 1, "score": 0.7, "rationale": "b"},
        {"index": 0, "score": 0.5, "rationale": "duplicate"},
    ]
    TreeOfThoughtsOrchestrator._apply_voter_scores(branches, scores)
    # Last write wins for index 0
    assert branches[0].voter_score == 0.5
    assert branches[1].voter_score == 0.7
