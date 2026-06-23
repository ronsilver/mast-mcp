"""Provider registry — maps provider names to ChatBackend implementations.

Auto-detects provider from available environment credentials.
Default is ollama.
"""

from __future__ import annotations

import os

import structlog

from mast.agents.backends.anthropic import AnthropicBackend
from mast.agents.backends.bedrock import BedrockBackend
from mast.agents.backends.gemini import GeminiBackend
from mast.agents.backends.github import GitHubBackend
from mast.agents.backends.openai import OpenAICompatBackend
from mast.agents.backends.openrouter import OpenRouterBackend
from mast.agents.base import OllamaBackend
from mast.agents.protocols import ChatBackend

log = structlog.get_logger(__name__)

_PROVIDER_CLASSES: dict[str, type[ChatBackend]] = {
    "ollama": OllamaBackend,
    "openai": OpenAICompatBackend,
    "openrouter": OpenRouterBackend,
    "github": GitHubBackend,
    "anthropic": AnthropicBackend,
    "gemini": GeminiBackend,
    "bedrock": BedrockBackend,
}

# Auto-detect order: first match wins.
# Each entry: (provider_name, list of env-var names that signal availability)
_DETECT_ORDER: list[tuple[str, tuple[str, ...]]] = [
    ("ollama", ("OLLAMA_BASE_URL",)),
    ("openai", ("OPENAI_API_KEY",)),
    ("anthropic", ("ANTHROPIC_API_KEY",)),
    ("gemini", ("GEMINI_API_KEY",)),
    ("github", ("GITHUB_TOKEN",)),
    ("openrouter", ("OPENROUTER_API_KEY",)),
    ("bedrock", ("BEDROCK_TOKEN", "AWS_REGION")),
]

_cached: ChatBackend | None = None


def list_providers() -> list[str]:
    """Return the names of providers registered for explicit selection."""
    return list(_PROVIDER_CLASSES.keys())


def detect_provider() -> str | None:
    """Inspect environment and return the most likely provider, or None."""
    for provider, env_vars in _DETECT_ORDER:
        for var in env_vars:
            if os.environ.get(var):
                return provider
    return None


def get_backend(provider: str | None = None) -> ChatBackend:
    """Return a singleton ChatBackend for the requested provider.

    Resolution order:
      1. Explicit `provider` argument (if not None).
      2. Environment variable MAST_PROVIDER.
      3. Auto-detect from available credentials.
      4. Default: "ollama".

    Raises ValueError if the provider name is not registered.
    """
    global _cached

    name = provider or os.environ.get("MAST_PROVIDER") or detect_provider() or "ollama"

    if _cached is not None and getattr(_cached, "_provider_name", None) == name:
        return _cached

    if name not in _PROVIDER_CLASSES:
        available = ", ".join(list_providers())
        raise ValueError(
            f"Unknown provider {name!r}. Available: {available}. "
            f"To add support for {name!r}, implement a ChatBackend subclass "
            f"and register it in mast.agents.registry."
        )

    cls = _PROVIDER_CLASSES[name]
    instance = cls()
    instance._provider_name = name  # type: ignore[attr-defined]
    _cached = instance
    log.info("backend_initialized", provider=name)
    return instance


def register_provider(name: str, cls: type[ChatBackend]) -> None:
    """Register a new provider class. Used by T6-T11 backend implementations."""
    if not issubclass(cls, ChatBackend):
        raise TypeError(f"{cls.__name__} must subclass ChatBackend")
    _PROVIDER_CLASSES[name] = cls


def reset_cache() -> None:
    """Clear the singleton cache. Test helper."""
    global _cached
    _cached = None
