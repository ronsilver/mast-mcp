"""Abstract base class for inference backends.

Defines the contract every ChatBackend implementation must satisfy.
The chat() signature mirrors the existing OllamaClient.chat() exactly
to enable a mechanical refactor (see ADR-0001).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

ChatResult = tuple[dict[str, Any], int]


class ChatBackend(ABC):
    """Provider-agnostic async inference client.

    Implementations: OllamaBackend, OpenAICompatBackend,
    AnthropicBackend, GeminiBackend, BedrockBackend,
    GitHubBackend, OpenRouterBackend.
    """

    @abstractmethod
    async def chat(
        self,
        model: str,
        system_prompt: str,
        *,
        temperature: float = 0.2,
        num_predict: int = 512,
        fallback: dict[str, Any],
        json_schema: dict[str, Any] | None = None,
    ) -> ChatResult:
        """Call the inference endpoint and return (parsed_json, latency_ms).

        On parse failure (after any internal retries), return
        (fallback, latency_ms). Accepts an optional json_schema for
        structured-output enforcement where supported.
        """
        ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Return list of model names available on this backend."""
        ...

    @abstractmethod
    async def aclose(self) -> None:
        """Release resources (HTTP clients, etc.)."""
        ...
