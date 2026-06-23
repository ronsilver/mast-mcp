"""Configuration via environment variables + optional TOML/JSON file with Pydantic v2.

Resolution order per field:
    1. Real env var set directly (highest)
    2. ${VAR} expansion in config file (env var must be set)
    3. ${VAR:-default} expansion (default if env var unset/empty)
    4. Literal value in config file
    5. Built-in code default (lowest)

Config file search:
    $MAST_CONFIG_FILE > ./mast.toml > ~/.config/mast/config.toml > absent
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from mast.config_loader import expand_env_value

MastMode = Literal[
    "passive",
    "validate",
    "debate",
    "debono",
    "actor_critic",
    "brainstorm",
    "tot",
    "kalman",
    "workflow",
]
FormatMode = Literal["schema", "json", "text"]
BedrockAuthMethod = Literal["iam", "token"]


class MastConfig(BaseSettings):
    """All MAST configuration, sourced from environment variables and optional file."""

    # ---- Config file location ---------------------------------------------
    mast_config_file: str | None = Field(default=None, alias="MAST_CONFIG_FILE")

    # ---- Provider selection -----------------------------------------------
    mast_provider: str = Field(default="ollama", alias="MAST_PROVIDER")
    mast_base_url: str | None = Field(default=None, alias="MAST_BASE_URL")
    mast_api_key: str | None = Field(default=None, alias="MAST_API_KEY")

    # ---- Ollama (legacy + current) ----------------------------------------
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        alias="OLLAMA_BASE_URL",
    )
    ollama_cloud_api_key: str | None = Field(default=None, alias="OLLAMA_CLOUD_API_KEY")

    # ---- Per-provider credentials -----------------------------------------
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    bedrock_auth_method: BedrockAuthMethod = Field(default="iam", alias="BEDROCK_AUTH_METHOD")
    bedrock_token: str | None = Field(default=None, alias="BEDROCK_TOKEN")
    bedrock_region: str = Field(default="us-east-1", alias="BEDROCK_REGION")
    bedrock_profile: str | None = Field(default=None, alias="BEDROCK_PROFILE")
    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")

    # ---- Agent models (role-based) ----------------------------------------
    critic_model: str = Field(default="mistral:7b-instruct", alias="CRITIC_MODEL")
    judge_model: str = Field(default="deepseek-r1:8b", alias="JUDGE_MODEL")

    # ---- Behaviour --------------------------------------------------------
    mast_mode: MastMode = Field(default="debate", alias="MAST_MODE")
    mast_timeout_ms: int = Field(default=15_000, alias="MAST_TIMEOUT_MS")
    mast_cache_ttl_s: int = Field(default=300, alias="MAST_CACHE_TTL_S")
    mast_max_history: int = Field(default=50, alias="MAST_MAX_HISTORY")
    mast_history_window: int = Field(default=3, alias="MAST_HISTORY_WINDOW")
    mast_history_max_tokens: int = Field(default=1500, alias="MAST_HISTORY_MAX_TOKENS")
    mast_skip_threshold_chars: int = Field(default=20, alias="MAST_SKIP_THRESHOLD_CHARS")
    mast_strategy_dir: str | None = Field(default=None, alias="MAST_STRATEGY_DIR")
    ollama_top_p: float = Field(default=0.9, alias="OLLAMA_TOP_P")

    # ---- Upstream compat ---------------------------------------------------
    disable_thought_logging: bool = Field(default=False, alias="DISABLE_THOUGHT_LOGGING")
    mast_format_mode: FormatMode = Field(default="schema", alias="MAST_FORMAT_MODE")
    color_thought_logging: bool = Field(default=False, alias="MAST_COLOR_THOUGHTS")

    # ---- De Bono Six Hats --------------------------------------------------
    debono_blue_open_model: str = Field(default="qwen2.5:3b", alias="DEBONO_BLUE_OPEN_MODEL")
    debono_white_model: str = Field(default="qwen2.5:3b", alias="DEBONO_WHITE_MODEL")
    debono_green_model: str = Field(default="qwen2.5:1.5b", alias="DEBONO_GREEN_MODEL")
    debono_yellow_model: str = Field(default="qwen2.5:3b", alias="DEBONO_YELLOW_MODEL")
    debono_black_model: str = Field(default="qwen2.5:3b", alias="DEBONO_BLACK_MODEL")
    debono_red_model: str = Field(default="qwen2.5:1.5b", alias="DEBONO_RED_MODEL")
    debono_blue_close_model: str = Field(default="qwen2.5:3b", alias="DEBONO_BLUE_CLOSE_MODEL")
    debono_skip_red: bool = Field(default=False, alias="DEBONO_SKIP_RED")

    # ---- Logging -----------------------------------------------------------
    mast_log_level: str = Field(default="INFO", alias="MAST_LOG_LEVEL")

    # ---- Mode-specific ----------------------------------------------------
    actor_critic_max_rounds: int = Field(default=3, alias="ACTOR_CRITIC_MAX_ROUNDS")
    brainstorm_models_str: str = Field(default="llama3:8b,mistral:7b", alias="BRAINSTORM_MODELS")
    brainstorm_synth_model: str = Field(default="qwen2.5:14b", alias="BRAINSTORM_SYNTH_MODEL")
    tot_branch_models_str: str = Field(
        default="llama3:8b,mistral:7b,qwen2.5:7b", alias="TOT_BRANCH_MODELS"
    )
    tot_voter_model: str = Field(default="deepseek-r1:8b", alias="TOT_VOTER_MODEL")
    kalman_scorer_models_str: str = Field(
        default="mistral:7b,qwen2.5:7b,phi3:mini", alias="KALMAN_SCORER_MODELS"
    )
    kalman_p_threshold: float = Field(default=0.18, alias="KALMAN_P_THRESHOLD")
    kalman_accept_threshold: float = Field(default=0.70, alias="KALMAN_ACCEPT_THRESHOLD")
    workflow_stages_str: str = Field(default="debate,kalman", alias="MAST_WORKFLOW_STAGES")

    model_config = SettingsConfigDict(
        populate_by_name=True,
        env_file=".env",
        extra="ignore",
    )

    # -----------------------------------------------------------------------
    # Validators
    # -----------------------------------------------------------------------

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
        allowed = {
            "passive",
            "validate",
            "debate",
            "debono",
            "actor_critic",
            "brainstorm",
            "tot",
            "kalman",
            "workflow",
        }
        if v not in allowed:
            raise ValueError(f"MAST_MODE must be one of {allowed}, got {v!r}")
        return v

    @field_validator("bedrock_auth_method", mode="before")
    @classmethod
    def validate_bedrock_auth(cls, v: str) -> str:
        if v not in {"iam", "token"}:
            raise ValueError(f"BEDROCK_AUTH_METHOD must be iam|token, got {v!r}")
        return v

    @model_validator(mode="after")
    def resolve_ollama_aliases(self) -> MastConfig:
        """Map legacy Ollama env vars to generic fields when generics unset."""
        if self.mast_base_url is None:
            object.__setattr__(self, "mast_base_url", self.ollama_base_url)
        if self.mast_api_key is None and self.ollama_cloud_api_key:
            object.__setattr__(self, "mast_api_key", self.ollama_cloud_api_key)
        return self

    # -----------------------------------------------------------------------
    # Computed properties
    # -----------------------------------------------------------------------

    @property
    def ollama_timeout(self) -> float:
        return self.mast_timeout_ms / 1000.0

    @property
    def effective_base_url(self) -> str:
        """Provider-agnostic base URL (Ollama legacy, or generic)."""
        return self.mast_base_url or self.ollama_base_url

    @property
    def effective_api_key(self) -> str | None:
        """Provider-agnostic API key."""
        return self.mast_api_key or self.ollama_cloud_api_key

    @property
    def brainstorm_models(self) -> list[str]:
        return [m.strip() for m in self.brainstorm_models_str.split(",") if m.strip()]

    @property
    def tot_branch_models(self) -> list[str]:
        return [m.strip() for m in self.tot_branch_models_str.split(",") if m.strip()]

    @property
    def kalman_scorer_models(self) -> list[str]:
        return [m.strip() for m in self.kalman_scorer_models_str.split(",") if m.strip()]

    @property
    def workflow_stages(self) -> list[str]:
        return [s.strip() for s in self.workflow_stages_str.split(",") if s.strip()]


def _load_config_with_interpolation() -> dict[str, object]:
    """Load TOML/JSON config file and expand ${VAR} placeholders.

    Called before MastConfig instantiation so pydantic-settings sees
    expanded values as if they were env vars.

    Returns: flat dict mapping UPPER_CASE_KEY -> expanded_value (as str).
    Pydantic-settings will re-parse to the declared field type.
    """
    from mast.config_loader import load_config_file

    raw: object = load_config_file()
    if not isinstance(raw, dict):
        return {}

    out: dict[str, str] = {}

    def walk(obj: object, prefix: str) -> None:
        if not isinstance(obj, dict):
            return
        items: list[tuple[object, object]] = list(obj.items())
        for k_raw, v_raw in items:
            if not isinstance(k_raw, str):
                continue
            key = f"{prefix}{k_raw}" if not prefix else f"{prefix}_{k_raw}"
            if isinstance(v_raw, dict):
                walk(v_raw, key)
            elif isinstance(v_raw, str):
                out[key] = expand_env_value(v_raw)
            else:
                out[key] = str(v_raw)

    walk(raw, "")
    return out  # type: ignore[return-value]


def _build_config() -> MastConfig:
    """Build MastConfig with config file values injected as env vars."""
    file_values = _load_config_with_interpolation()
    saved: dict[str, str | None] = {}
    try:
        for k, v in file_values.items():
            env_key = k.upper()
            saved[env_key] = os.environ.get(env_key)
            os.environ[env_key] = v  # type: ignore[assignment]
        return MastConfig()
    finally:
        for k, original in saved.items():
            if original is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = original


# Singleton — import this everywhere
config: MastConfig = _build_config()
