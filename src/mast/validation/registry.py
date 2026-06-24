"""
Strategy registry — lookup reasoning modes by name.

Built-in strategies are registered eagerly on import. External plugins
are discovered via Python entry points under the
`mast.strategies` group. Custom local strategies are loaded from the
`MAST_STRATEGY_DIR` directory at registry initialization.

Conflict resolution: built-in entry points > `MAST_STRATEGY_DIR` >
external entry points. Conflicts log a warning; built-in wins.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)

_strategies: dict[str, object] = {}


def register(strategy: object) -> None:
    """
    Register a strategy instance.

    Existing entries with the same name take precedence (built-in loaded
    first). Accepts any object exposing a string `name` attribute and a
    callable `run` method. Runtime checks enforce the contract.
    """
    name = getattr(strategy, "name", None)
    if not isinstance(name, str):
        raise TypeError(f"Cannot register {strategy!r}: missing string `name` attribute.")
    run = getattr(strategy, "run", None)
    if not callable(run):
        raise TypeError(f"Cannot register {name!r}: missing callable `run` method.")
    if name in _strategies:
        log.warning("strategy_already_registered", name=name, kept="existing")
        return
    _strategies[name] = strategy
    log.debug("strategy_registered", name=name, type=type(strategy).__name__)


def get(name: str) -> object:
    """
    Return the strategy registered under `name`.

    Raises KeyError if not found.
    """
    if name not in _strategies:
        raise KeyError(f"Strategy {name!r} not registered. Available: {sorted(_strategies.keys())}")
    return _strategies[name]


def has(name: str) -> bool:
    return name in _strategies


def names() -> list[str]:
    return sorted(_strategies.keys())


def _import_module(file: Path, module_name: str) -> object | None:
    spec = importlib.util.spec_from_file_location(module_name, file)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _register_from_module(module: object) -> int:
    strategy_obj = getattr(module, "STRATEGY", None)
    if strategy_obj is not None and hasattr(strategy_obj, "name"):
        register(strategy_obj)
        return 1
    count = 0
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and hasattr(attr, "name")
            and hasattr(attr, "run")
            and attr_name != "Strategy"
        ):
            register(attr())
            count += 1
    return count


def load_from_dir(path: str | Path) -> int:
    """Load strategies from a local directory."""
    p = Path(path).expanduser()
    if not p.is_dir():
        log.warning("strategy_dir_not_found", path=str(p))
        return 0
    count = 0
    for file in sorted(p.glob("*.py")):
        if file.name.startswith("_"):
            continue
        module_name = f"_mast_strategy_{file.stem}"
        try:
            module = _import_module(file, module_name)
            if module is not None:
                count += _register_from_module(module)
        except Exception as exc:  # noqa: BLE001
            log.warning("strategy_load_failed", file=str(file), error=str(exc))
    return count


def load_from_entry_points(group: str = "mast.strategies") -> int:
    """Load strategies from Python entry points."""
    count = 0
    try:
        from importlib.metadata import entry_points
    except ImportError:
        return 0
    try:
        eps = entry_points(group=group)
    except Exception:  # noqa: BLE001
        return 0
    for ep in eps:
        try:
            obj = ep.load()
            if hasattr(obj, "name") and hasattr(obj, "run"):
                register(obj())
            elif hasattr(obj, "name"):
                register(obj)
        except Exception as exc:  # noqa: BLE001
            log.warning("strategy_entry_point_failed", ep=ep.name, error=str(exc))
    return count


def reset() -> None:
    """Clear the registry. Test helper."""
    _strategies.clear()


# Bootstrap built-in strategies on import.
def _bootstrap_builtins() -> None:
    """
    Register the 9 built-in reasoning modes.

    Built-ins wrap the existing mode handlers in orchestrator.py and
    agents. They are registered eagerly so external entry points cannot
    shadow them.
    """
    from mast.validation.strategies import builtin_strategies

    for strategy in builtin_strategies():
        register(strategy)


_bootstrap_builtins()
