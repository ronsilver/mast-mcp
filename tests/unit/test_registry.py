"""Tests for provider registry + auto-detect."""

from __future__ import annotations

from typing import Any

import pytest

from mast.agents.base import OllamaBackend
from mast.agents.protocols import ChatBackend
from mast.agents.registry import (
    detect_provider,
    get_backend,
    list_providers,
    register_provider,
    reset_cache,
)


class _FakeBackend(ChatBackend):
    """Minimal fake for registration tests."""

    async def chat(
        self,
        model: str,
        system_prompt: str,
        *,
        temperature: float = 0.2,
        num_predict: int = 512,
        fallback: dict[str, Any],
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], int]:
        return fallback, 0

    async def list_models(self) -> list[str]:
        return ["fake"]

    async def aclose(self) -> None:
        pass


class _FakeBackendResult(_FakeBackend):
    async def chat(
        self,
        model: str,
        system_prompt: str,
        *,
        temperature: float = 0.2,
        num_predict: int = 512,
        fallback: dict[str, Any],
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], int]:
        return {"result": "fake"}, 10


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    reset_cache()


def test_list_providers_includes_ollama() -> None:
    providers = list_providers()
    assert "ollama" in providers


def test_get_backend_default_returns_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAST_PROVIDER", raising=False)
    for var in (
        "OLLAMA_BASE_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GITHUB_TOKEN",
        "OPENROUTER_API_KEY",
        "BEDROCK_TOKEN",
        "AWS_REGION",
    ):
        monkeypatch.delenv(var, raising=False)
    backend = get_backend()
    assert isinstance(backend, OllamaBackend)
    assert isinstance(backend, ChatBackend)


def test_get_backend_explicit_ollama() -> None:
    backend = get_backend("ollama")
    assert isinstance(backend, OllamaBackend)


def test_get_backend_explicit_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        get_backend("not_a_real_provider")


def test_get_backend_mast_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAST_PROVIDER", "ollama")
    backend = get_backend()
    assert isinstance(backend, OllamaBackend)


def test_detect_provider_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert detect_provider() == "openai"


def test_detect_provider_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    assert detect_provider() == "ollama"


def test_detect_provider_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert detect_provider() == "anthropic"


def test_detect_provider_bedrock_token(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "OLLAMA_BASE_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GITHUB_TOKEN",
        "OPENROUTER_API_KEY",
        "BEDROCK_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BEDROCK_TOKEN", "test")
    assert detect_provider() == "bedrock"


def test_detect_provider_bedrock_aws_region(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "OLLAMA_BASE_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GITHUB_TOKEN",
        "OPENROUTER_API_KEY",
        "BEDROCK_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    assert detect_provider() == "bedrock"


def test_detect_provider_none(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "OLLAMA_BASE_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GITHUB_TOKEN",
        "OPENROUTER_API_KEY",
        "BEDROCK_TOKEN",
        "AWS_REGION",
    ):
        monkeypatch.delenv(var, raising=False)
    assert detect_provider() is None


def test_detect_provider_priority_ollama_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert detect_provider() == "ollama"


def test_register_provider() -> None:
    register_provider("fake_test", _FakeBackend)
    assert "fake_test" in list_providers()


def test_register_provider_rejects_non_chatbackend() -> None:
    class NotABackend:
        pass

    with pytest.raises(TypeError):
        register_provider("bad", NotABackend)  # type: ignore[arg-type]


def test_registered_provider_gettable() -> None:
    register_provider("fake_get", _FakeBackendResult)
    backend = get_backend("fake_get")
    assert isinstance(backend, _FakeBackendResult)
    assert backend._provider_name == "fake_get"  # type: ignore[attr-defined]


def test_cache_returns_same_instance() -> None:
    a = get_backend("ollama")
    b = get_backend("ollama")
    assert a is b


def test_reset_cache() -> None:
    a = get_backend("ollama")
    reset_cache()
    b = get_backend("ollama")
    assert a is not b


def test_environment_var_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify env isolation in detect_provider."""
    for var in (
        "OLLAMA_BASE_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GITHUB_TOKEN",
        "OPENROUTER_API_KEY",
        "BEDROCK_TOKEN",
        "AWS_REGION",
    ):
        monkeypatch.delenv(var, raising=False)
    assert detect_provider() is None
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert detect_provider() == "gemini"
    monkeypatch.delenv("GEMINI_API_KEY")
