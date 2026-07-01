"""Unit tests for MastConfig (validators + aliases + bedrock)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mast.config import MastConfig


def test_default_config_is_valid() -> None:
    cfg = MastConfig()
    assert cfg.mast_mode == "debate"
    assert cfg.mast_format_mode == "schema"
    assert cfg.mast_provider == "ollama"


def test_invalid_mast_mode_raises() -> None:
    with pytest.raises(ValidationError, match="MAST_MODE"):
        MastConfig(**{"MAST_MODE": "invalid"})  # type: ignore[arg-type]


def test_invalid_format_mode_raises() -> None:
    with pytest.raises(ValidationError, match="MAST_FORMAT_MODE"):
        MastConfig(**{"MAST_FORMAT_MODE": "bogus"})  # type: ignore[arg-type]


def test_invalid_bedrock_auth_raises() -> None:
    with pytest.raises(ValidationError, match="BEDROCK_AUTH_METHOD"):
        MastConfig(**{"BEDROCK_AUTH_METHOD": "oauth"})  # type: ignore[arg-type]


def test_valid_bedrock_auth_modes() -> None:
    cfg_iam = MastConfig(**{"BEDROCK_AUTH_METHOD": "iam"})  # type: ignore[arg-type]
    cfg_token = MastConfig(**{"BEDROCK_AUTH_METHOD": "token"})  # type: ignore[arg-type]
    assert cfg_iam.bedrock_auth_method == "iam"
    assert cfg_token.bedrock_auth_method == "token"


def test_ollama_legacy_aliases_to_generic_fields() -> None:
    """Ollama legacy env vars populate generic fields when generics unset."""
    cfg = MastConfig(
        **{  # type: ignore[arg-type]
            "OLLAMA_BASE_URL": "http://legacy:11434",
            "OLLAMA_CLOUD_API_KEY": "sk-legacy",
        }
    )
    assert cfg.ollama_base_url == "http://legacy:11434"
    assert cfg.ollama_cloud_api_key == "sk-legacy"
    # Aliases applied via model_validator
    assert cfg.mast_base_url == "http://legacy:11434"
    assert cfg.mast_api_key == "sk-legacy"
    assert cfg.effective_base_url == "http://legacy:11434"
    assert cfg.effective_api_key == "sk-legacy"


def test_generic_fields_override_ollama_legacy() -> None:
    """Generic env vars take precedence over Ollama legacy."""
    cfg = MastConfig(
        **{  # type: ignore[arg-type]
            "OLLAMA_BASE_URL": "http://legacy:11434",
            "MAST_BASE_URL": "http://override:9999",
        }
    )
    assert cfg.ollama_base_url == "http://legacy:11434"
    assert cfg.mast_base_url == "http://override:9999"
    assert cfg.effective_base_url == "http://override:9999"


def test_no_env_at_all_falls_back_to_ollama_defaults() -> None:
    cfg = MastConfig()
    assert cfg.ollama_base_url == "http://localhost:11434"
    assert cfg.mast_base_url == "http://localhost:11434"
    assert cfg.ollama_cloud_api_key is None
    assert cfg.mast_api_key is None


def test_openai_key_loaded() -> None:
    cfg = MastConfig(**{"OPENAI_API_KEY": "sk-test"})  # type: ignore[arg-type]
    assert cfg.openai_api_key == "sk-test"


def test_anthropic_key_loaded() -> None:
    cfg = MastConfig(**{"ANTHROPIC_API_KEY": "sk-ant-test"})  # type: ignore[arg-type]
    assert cfg.anthropic_api_key == "sk-ant-test"


def test_gemini_key_loaded() -> None:
    cfg = MastConfig(**{"GEMINI_API_KEY": "gem-test"})  # type: ignore[arg-type]
    assert cfg.gemini_api_key == "gem-test"


def test_github_token_loaded() -> None:
    cfg = MastConfig(**{"GITHUB_TOKEN": "ghp-test"})  # type: ignore[arg-type]
    assert cfg.github_token == "ghp-test"


def test_openrouter_key_loaded() -> None:
    cfg = MastConfig(**{"OPENROUTER_API_KEY": "sk-or-test"})  # type: ignore[arg-type]
    assert cfg.openrouter_api_key == "sk-or-test"


def test_bedrock_token_loaded() -> None:
    cfg = MastConfig(
        **{  # type: ignore[arg-type]
            "BEDROCK_AUTH_METHOD": "token",
            "BEDROCK_TOKEN": "br-tok",
        }
    )
    assert cfg.bedrock_auth_method == "token"
    assert cfg.bedrock_token == "br-tok"


def test_bedrock_default_auth_is_iam() -> None:
    cfg = MastConfig()
    assert cfg.bedrock_auth_method == "iam"
    assert cfg.bedrock_region == "us-east-1"


def test_kalman_default_p_threshold() -> None:
    cfg = MastConfig()
    assert cfg.kalman_p_threshold == 0.18


def test_workflow_stages_property_parses_comma_separated() -> None:
    cfg = MastConfig(**{"MAST_WORKFLOW_STAGES": "a,b,c"})  # type: ignore[arg-type]
    assert cfg.workflow_stages == ["a", "b", "c"]


def test_brainstorm_models_property() -> None:
    cfg = MastConfig(**{"BRAINSTORM_MODELS": "x:1, y:2,z:3"})  # type: ignore[arg-type]
    assert cfg.brainstorm_models == ["x:1", "y:2", "z:3"]


def test_tot_branch_models_property() -> None:
    cfg = MastConfig(**{"TOT_BRANCH_MODELS": "a,b"})  # type: ignore[arg-type]
    assert cfg.tot_branch_models == ["a", "b"]


def test_kalman_scorer_models_property() -> None:
    cfg = MastConfig(**{"KALMAN_SCORER_MODELS": "m1,m2,m3"})  # type: ignore[arg-type]
    assert cfg.kalman_scorer_models == ["m1", "m2", "m3"]


def test_ollama_timeout_from_ms() -> None:
    cfg = MastConfig(**{"MAST_TIMEOUT_MS": 5000})  # type: ignore[arg-type]
    assert cfg.ollama_timeout == 5.0
