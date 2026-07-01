"""Tests for Strategy registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from mast.validation import registry


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    registry.reset()
    from mast.validation.strategies import builtin_strategies

    for s in builtin_strategies():
        registry.register(s)


class _TestStrategy:
    """Minimal duck-typed strategy for tests."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def run(
        self,
        thought: object,
        history: list[object],
        upstream_response: dict[str, object],
        *,
        critic_model: str | None = None,
        judge_model: str | None = None,
        backend: object | None = None,
        cache: object | None = None,
    ) -> object:
        return None


def _make(name: str) -> _TestStrategy:
    return _TestStrategy(name)


def test_builtins_registered_on_import() -> None:
    names = registry.names()
    assert "passive" in names
    assert "validate" in names
    assert "debate" in names
    assert "debono" in names
    assert "actor_critic" in names
    assert "brainstorm" in names
    assert "tot" in names
    assert "kalman" in names
    assert "workflow" in names
    assert len(names) >= 9


def test_get_returns_registered_strategy() -> None:
    s = registry.get("debate")
    assert s is not None
    name_val: object = s.name  # type: ignore[attr-defined]
    assert name_val == "debate"


def test_get_unknown_raises_keyerror() -> None:
    with pytest.raises(KeyError, match="not registered"):
        registry.get("does_not_exist")


def test_has_returns_bool() -> None:
    assert registry.has("debate") is True
    assert registry.has("does_not_exist") is False


def test_register_custom_strategy() -> None:
    custom = _make("custom_mode")
    registry.register(custom)
    assert registry.has("custom_mode")


def test_register_duplicate_keeps_existing() -> None:
    original = registry.get("debate")
    duplicate = _make("debate")
    registry.register(duplicate)
    assert registry.get("debate") is original


def test_register_rejects_object_without_name() -> None:
    class _NoName:
        async def run(self, *args: object, **kwargs: object) -> object:
            return None

    with pytest.raises(TypeError, match="missing string `name`"):
        registry.register(_NoName())


def test_register_rejects_object_without_run() -> None:
    class _NoRun:
        name = "x"

    with pytest.raises(TypeError, match="missing callable `run`"):
        registry.register(_NoRun())


def test_names_sorted() -> None:
    names = registry.names()
    assert names == sorted(names)


def test_reset_clears_registry() -> None:
    registry.reset()
    assert registry.names() == []


def test_reset_then_re_register() -> None:
    registry.reset()
    s = _make("manual")
    registry.register(s)
    assert registry.has("manual")
    assert not registry.has("debate")


def test_load_from_dir_missing(tmp_path: Path) -> None:
    count = registry.load_from_dir(tmp_path / "does_not_exist")
    assert count == 0


def test_load_from_dir_empty(tmp_path: Path) -> None:
    count = registry.load_from_dir(tmp_path)
    assert count == 0


def test_load_from_dir_custom_strategy(tmp_path: Path) -> None:
    custom_file = tmp_path / "my_strategy.py"
    custom_file.write_text(
        "from typing import Any\n"
        "STRATEGY = type(\n"
        "    'MyStrat',\n"
        "    (),\n"
        "    {\n"
        "        'name': 'from_dir_test',\n"
        "        'run': lambda self, *a, **kw: None,\n"
        "        '__init__': lambda self: None,\n"
        "    },\n"
        ")()\n",
        encoding="utf-8",
    )
    count = registry.load_from_dir(tmp_path)
    assert count >= 1
    assert registry.has("from_dir_test")


def test_load_from_dir_malformed_skipped(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("this is not valid python", encoding="utf-8")
    count = registry.load_from_dir(tmp_path)
    assert count == 0


def test_load_from_dir_skips_underscore_files(tmp_path: Path) -> None:
    private = tmp_path / "_private.py"
    private.write_text(
        "STRATEGY = type('X', (), {'name': 'private', '__init__': lambda self: None})()\n",
        encoding="utf-8",
    )
    count = registry.load_from_dir(tmp_path)
    assert count == 0
    assert not registry.has("private")


def test_load_from_entry_points_empty_group() -> None:
    count = registry.load_from_entry_points("definitely.not.a.real.group.xyz")
    assert count == 0
