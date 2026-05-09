"""Configuration via environment variables with Pydantic v2."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

MastMode = Literal["passive", "validate", "debate", "debono"]
FormatMode = Literal["schema", "json", "text"]


class MastConfig(BaseSettings):
    """All MAST configuration, sourced from environment variables."""

    # Ollama
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        alias="OLLAMA_BASE_URL",
    )
    critic_model: str = Field(default="mistral:7b-instruct", alias="CRITIC_MODEL")
    judge_model: str = Field(default="deepseek-r1:8b", alias="JUDGE_MODEL")

    # Behaviour
    mast_mode: MastMode = Field(default="debate", alias="MAST_MODE")
    mast_timeout_ms: int = Field(default=15_000, alias="MAST_TIMEOUT_MS")
    mast_cache_ttl_s: int = Field(default=300, alias="MAST_CACHE_TTL_S")
    mast_max_history: int = Field(default=50, alias="MAST_MAX_HISTORY")
    mast_history_window: int = Field(default=3, alias="MAST_HISTORY_WINDOW")
    mast_history_max_tokens: int = Field(default=1500, alias="MAST_HISTORY_MAX_TOKENS")

    # Validation tuning
    mast_skip_threshold_chars: int = Field(default=20, alias="MAST_SKIP_THRESHOLD_CHARS")
    ollama_top_p: float = Field(default=0.9, alias="OLLAMA_TOP_P")

    # Upstream compat
    disable_thought_logging: bool = Field(default=False, alias="DISABLE_THOUGHT_LOGGING")

    # JSON format mode for Ollama /api/chat:
    #   "schema" — pass full JSON Schema (Ollama 0.5+, best conformance)
    #   "json"   — pass "json" string (legacy, broad compatibility)
    #   "text"   — omit format field (for proxies that don't support it)
    mast_format_mode: FormatMode = Field(default="schema", alias="MAST_FORMAT_MODE")

    # ANSI colours in format_thought console output
    color_thought_logging: bool = Field(default=False, alias="MAST_COLOR_THOUGHTS")

    # De Bono Six Hats — one env var per hat
    debono_blue_open_model: str = Field(
        default="qwen2.5:3b", alias="DEBONO_BLUE_OPEN_MODEL"
    )
    debono_white_model: str = Field(
        default="qwen2.5:3b", alias="DEBONO_WHITE_MODEL"
    )
    debono_green_model: str = Field(
        default="qwen2.5:1.5b", alias="DEBONO_GREEN_MODEL"
    )
    debono_yellow_model: str = Field(
        default="qwen2.5:3b", alias="DEBONO_YELLOW_MODEL"
    )
    debono_black_model: str = Field(
        default="qwen2.5:3b", alias="DEBONO_BLACK_MODEL"
    )
    debono_red_model: str = Field(
        default="qwen2.5:1.5b", alias="DEBONO_RED_MODEL"
    )
    debono_blue_close_model: str = Field(
        default="qwen2.5:3b", alias="DEBONO_BLUE_CLOSE_MODEL"
    )
    debono_skip_red: bool = Field(default=False, alias="DEBONO_SKIP_RED")

    # Logging
    mast_log_level: str = Field(default="INFO", alias="MAST_LOG_LEVEL")

    @field_validator("mast_format_mode", mode="before")
    @classmethod
    def validate_format_mode(cls, v: str) -> str:
        allowed = {"schema", "json", "text"}
        if v not in allowed:
            raise ValueError(f"MAST_FORMAT_MODE must be one of {allowed}, got {v!r}")
        return v

    @field_validator("mast_mode", mode="before")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = {"passive", "validate", "debate", "debono"}
        if v not in allowed:
            raise ValueError(f"MAST_MODE must be one of {allowed}, got {v!r}")
        return v

    @property
    def ollama_timeout(self) -> float:
        return self.mast_timeout_ms / 1000.0

    model_config = {"populate_by_name": True, "env_file": ".env"}


# Singleton — import this everywhere
config = MastConfig()
