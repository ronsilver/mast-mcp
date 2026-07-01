"""
TOML/JSON config file loader with ${VAR} env interpolation.

Search order:
    $MAST_CONFIG_FILE > ./mast.toml > ~/.config/mast/config.toml > absent

${VAR} syntax:
    ${VAR}          — replaced by env var value; error if unset (fail fast)
    ${VAR:-default} — default if env var unset OR empty

Precedence (highest to lowest within a field):
    real env > ${VAR} expanded > ${VAR:-default} > literal in file > code default
"""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path

_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")


def expand_vars(text: str, source: str = "<config>") -> str:
    """
    Expand ${VAR} and ${VAR:-default} placeholders in a string.

    Raises ValueError on unset variable without default.
    """

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        default = m.group(2)
        val = os.environ.get(name)
        if val is not None and val != "":
            return val
        if default is not None:
            return default
        raise ValueError(
            f"{source}: env var ${{{name}}} is unset and has no default. "
            f"Set the env var or use ${{{name}:-<default>}} in the file."
        )

    return _VAR_RE.sub(repl, text)


def _find_config_file() -> Path | None:
    """
    Return the first existing config file path, or None.

    Search order:
        $MAST_CONFIG_FILE (any suffix)
        ./mast.toml | ./mast.json
        ~/.config/mast/config.toml | ~/.config/mast/config.json
    """
    if env := os.environ.get("MAST_CONFIG_FILE"):
        p = Path(env)
        if p.is_file():
            return p
        raise FileNotFoundError(f"MAST_CONFIG_FILE={env!r} set but file not found.")

    cwd_toml = Path.cwd() / "mast.toml"
    if cwd_toml.is_file():
        return cwd_toml
    cwd_json = Path.cwd() / "mast.json"
    if cwd_json.is_file():
        return cwd_json

    home_toml = Path.home() / ".config" / "mast" / "config.toml"
    if home_toml.is_file():
        return home_toml
    home_json = Path.home() / ".config" / "mast" / "config.json"
    if home_json.is_file():
        return home_json

    return None


def load_config_file() -> dict[str, object]:
    """
    Load and expand the first existing config file.

    Returns an empty dict if no file exists.
    """
    path = _find_config_file()
    if path is None:
        return {}

    raw = path.read_text(encoding="utf-8")
    expanded = expand_vars(raw, source=str(path))

    if path.suffix == ".json":
        result: dict[str, object] = json.loads(expanded)
        return result
    toml_result: dict[str, object] = tomllib.loads(expanded)
    return toml_result


def expand_env_value(value: str) -> str:
    """Expand ${VAR} placeholders in a single string value (no source label)."""
    return expand_vars(value)
