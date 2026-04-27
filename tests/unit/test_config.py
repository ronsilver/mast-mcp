"""Unit tests for MastConfig validators."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mast.config import MastConfig


def test_default_config_is_valid() -> None:
    cfg = MastConfig()
    assert cfg.mast_mode == "debate"
    assert cfg.mast_format_mode == "schema"


def test_invalid_mast_mode_raises() -> None:
    with pytest.raises(ValidationError, match="MAST_MODE"):
        MastConfig(**{"MAST_MODE": "invalid"})  # type: ignore[arg-type]


def test_valid_mast_modes() -> None:
    for mode in ("passive", "validate", "debate"):
        cfg = MastConfig(**{"MAST_MODE": mode})  # type: ignore[arg-type]
        assert cfg.mast_mode == mode


def test_invalid_format_mode_raises() -> None:
    with pytest.raises(ValidationError, match="MAST_FORMAT_MODE"):
        MastConfig(**{"MAST_FORMAT_MODE": "unsupported"})  # type: ignore[arg-type]


def test_valid_format_modes() -> None:
    for mode in ("schema", "json", "text"):
        cfg = MastConfig(**{"MAST_FORMAT_MODE": mode})  # type: ignore[arg-type]
        assert cfg.mast_format_mode == mode


def test_ollama_timeout_converts_ms_to_seconds() -> None:
    cfg = MastConfig(**{"MAST_TIMEOUT_MS": 30_000})  # type: ignore[arg-type]
    assert cfg.ollama_timeout == 30.0


def test_color_thought_logging_default_false() -> None:
    cfg = MastConfig()
    assert cfg.color_thought_logging is False
