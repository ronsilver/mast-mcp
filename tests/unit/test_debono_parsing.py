"""Unit tests for De Bono Six Hats response parsing."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mast.validation.schemas import (
    DebonoResult,
    HatName,
    HatOutput,
    Verdict,
)


class TestHatOutput:
    def _make(self, hat: HatName, rationale: str = "ok") -> HatOutput:
        return HatOutput(hat=hat, model="qwen2.5:3b", latency_ms=800, rationale=rationale)

    def test_blue_open_minimal(self) -> None:
        h = self._make(HatName.BLUE_OPEN)
        assert h.hat == HatName.BLUE_OPEN
        assert h.model == "qwen2.5:3b"

    def test_white_hat(self) -> None:
        h = self._make(HatName.WHITE, "extracted facts")
        assert h.hat.value == "white"

    def test_green_hat(self) -> None:
        h = self._make(HatName.GREEN, "generated alternatives")
        assert h.hat == HatName.GREEN

    def test_yellow_hat(self) -> None:
        h = self._make(HatName.YELLOW, "identified benefits")
        assert h.hat == HatName.YELLOW

    def test_black_hat(self) -> None:
        h = self._make(HatName.BLACK, "found risks")
        assert h.hat == HatName.BLACK

    def test_red_hat(self) -> None:
        h = self._make(HatName.RED, "gut feeling")
        assert h.hat == HatName.RED

    def test_blue_close(self) -> None:
        h = self._make(HatName.BLUE_CLOSE, "synthesized verdict")
        assert h.hat == HatName.BLUE_CLOSE

    def test_rationale_max_length_enforced(self) -> None:
        with pytest.raises(ValidationError):
            HatOutput(
                hat=HatName.BLUE_OPEN,
                model="m",
                latency_ms=0,
                rationale="X" * 121,
            )

    def test_latency_zero_is_valid(self) -> None:
        h = HatOutput(hat=HatName.BLUE_OPEN, model="m", latency_ms=0, rationale="ok")
        assert h.latency_ms == 0

    def test_full_sequence(self) -> None:
        ordered = [
            (HatName.BLUE_OPEN, "defined"),
            (HatName.WHITE, "facts"),
            (HatName.GREEN, "ideas"),
            (HatName.YELLOW, "benefits"),
            (HatName.BLACK, "risks"),
            (HatName.RED, "intuition"),
            (HatName.BLUE_CLOSE, "verdict"),
        ]
        hats = [HatOutput(hat=h, model="m", latency_ms=100, rationale=r) for h, r in ordered]
        result = DebonoResult(hats=hats, total_latency_ms=700)
        assert len(result.hats) == 7
        assert [h.hat for h in result.hats] == [h for h, _ in ordered]
        assert result.total_latency_ms == 700

    def test_empty_sequence(self) -> None:
        result = DebonoResult(hats=[], total_latency_ms=0)
        assert result.hats == []


class TestDebonoInMastOutput:
    def test_debono_field_in_mast_output(self) -> None:
        from mast.validation.schemas import MastOutput

        hat = HatOutput(hat=HatName.BLUE_OPEN, model="q", latency_ms=100, rationale="ok")
        result = MastOutput(
            thought_number=1,
            total_thoughts=5,
            next_thought_needed=True,
            branches=[],
            thought_history_length=1,
            verdict=Verdict.ACCEPT,
            confidence=0.9,
            debono=DebonoResult(hats=[hat], total_latency_ms=100),
        )
        assert result.debono is not None
        assert result.debono.total_latency_ms == 100
        assert result.verdict == Verdict.ACCEPT
        assert result.confidence == 0.9

    def test_debono_to_dict(self) -> None:
        from mast.validation.schemas import MastOutput

        hat = HatOutput(
            hat=HatName.WHITE,
            model="qwen2.5:3b",
            latency_ms=750,
            rationale="facts",
        )
        result = MastOutput(
            thought_number=2,
            total_thoughts=3,
            next_thought_needed=False,
            branches=[],
            thought_history_length=2,
            verdict=Verdict.REVISE,
            confidence=0.75,
            debono=DebonoResult(hats=[hat], total_latency_ms=750),
        )
        d = result.to_dict()
        assert d["thoughtNumber"] == 2
        assert d["verdict"] == "revise"
        assert d["debono"]["total_latency_ms"] == 750
        assert d["debono"]["hats"][0]["hat"] == "white"
