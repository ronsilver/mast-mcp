"""Configuration via environment variables with Pydantic v2."""
from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


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
    mast_mode: str = Field(default="debate", alias="MAST_MODE")
    mast_timeout_ms: int = Field(default=15_000, alias="MAST_TIMEOUT_MS")
    mast_cache_ttl_s: int = Field(default=300, alias="MAST_CACHE_TTL_S")
    mast_max_history: int = Field(default=50, alias="MAST_MAX_HISTORY")
    mast_history_window: int = Field(default=3, alias="MAST_HISTORY_WINDOW")
    mast_history_max_tokens: int = Field(default=1500, alias="MAST_HISTORY_MAX_TOKENS")

    # Upstream compat
    disable_thought_logging: bool = Field(default=False, alias="DISABLE_THOUGHT_LOGGING")

    # Logging
    mast_log_level: str = Field(default="INFO", alias="MAST_LOG_LEVEL")

    @field_validator("mast_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = {"passive", "validate", "debate"}
        if v not in allowed:
            raise ValueError(f"MAST_MODE must be one of {allowed}, got {v!r}")
        return v

    @property
    def ollama_timeout(self) -> float:
        return self.mast_timeout_ms / 1000.0

    model_config = {"populate_by_name": True, "env_file": ".env"}


# Singleton — import this everywhere
config = MastConfig()
