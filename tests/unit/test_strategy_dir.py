"""Test for MAST_STRATEGY_DIR auto-load on startup."""

from __future__ import annotations

from pathlib import Path


def test_strategy_dir_load_via_registry_function(tmp_path: Path) -> None:
    """Custom .py in a directory is loaded via load_from_dir()."""
    from mast.validation import registry

    custom_file = tmp_path / "custom.py"
    custom_file.write_text(
        "STRATEGY = type(\n"
        "    'S',\n"
        "    (),\n"
        "    {\n"
        "        'name': 'custom_dir_strategy',\n"
        "        'run': lambda self, *a, **kw: None,\n"
        "        '__init__': lambda self: None,\n"
        "    },\n"
        ")()\n",
        encoding="utf-8",
    )

    registry.reset()
    from mast.validation.strategies import builtin_strategies

    for s in builtin_strategies():
        registry.register(s)

    count = registry.load_from_dir(tmp_path)
    assert count == 1
    assert registry.has("custom_dir_strategy")


def test_strategy_dir_missing_returns_zero(tmp_path: Path) -> None:
    from mast.validation import registry

    count = registry.load_from_dir(tmp_path / "nonexistent")
    assert count == 0


def test_mast_strategy_dir_env_var_respected() -> None:
    """Verify MAST_STRATEGY_DIR env var is wired into config."""
    from mast.config import MastConfig

    field = MastConfig.model_fields.get("mast_strategy_dir")
    assert field is not None
    assert field.alias == "MAST_STRATEGY_DIR"


def test_built_ins_block_duplicate_names(tmp_path: Path) -> None:
    """A custom .py using a built-in name does not shadow it."""
    from mast.validation import registry

    override = tmp_path / "override.py"
    override.write_text(
        "STRATEGY = type(\n"
        "    'S',\n"
        "    (),\n"
        "    {\n"
        "        'name': 'debate',\n"
        "        'run': lambda self, *a, **kw: 'CUSTOM',\n"
        "        '__init__': lambda self: None,\n"
        "    },\n"
        ")()\n",
        encoding="utf-8",
    )

    registry.reset()
    from mast.validation.strategies import builtin_strategies

    for s in builtin_strategies():
        registry.register(s)

    original = registry.get("debate")
    registry.load_from_dir(tmp_path)
    assert registry.get("debate") is original  # built-in preserved
