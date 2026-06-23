"""Tests for ChatBackend protocol."""

from __future__ import annotations

from typing import Any

import pytest

from mast.agents.protocols import ChatBackend


class _MinimalBackend(ChatBackend):
    """Minimal subclass that satisfies the protocol."""

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
        return ["test-model"]

    async def aclose(self) -> None:
        pass


class _IncompleteBackend(ChatBackend):
    """Missing chat() — should fail to instantiate."""


def test_minimal_subclass_compiles() -> None:
    backend = _MinimalBackend()
    assert isinstance(backend, ChatBackend)


def test_chat_returns_fallback() -> None:
    backend = _MinimalBackend()
    result = backend.chat
    assert callable(result)


def test_incomplete_subclass_cannot_instantiate() -> None:
    with pytest.raises(TypeError):
        _IncompleteBackend()  # type: ignore[abstract]


@pytest.mark.asyncio
async def test_list_models_returns_list() -> None:
    backend = _MinimalBackend()
    models = await backend.list_models()
    assert models == ["test-model"]


@pytest.mark.asyncio
async def test_aclose_runs() -> None:
    backend = _MinimalBackend()
    await backend.aclose()


@pytest.mark.asyncio
async def test_chat_returns_tuple_dict_int() -> None:
    backend = _MinimalBackend()
    payload, latency = await backend.chat(
        model="m",
        system_prompt="s",
        fallback={"x": 1},
    )
    assert payload == {"x": 1}
    assert latency == 0


def test_ollama_backend_is_chat_backend() -> None:
    from mast.agents.base import OllamaBackend

    backend = OllamaBackend()
    assert isinstance(backend, ChatBackend)


def test_ollama_client_alias() -> None:
    from mast.agents.base import OllamaBackend, OllamaClient

    assert OllamaClient is OllamaBackend
