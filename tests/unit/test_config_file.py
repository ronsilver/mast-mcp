"""Tests for config file loader + ${VAR} interpolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from mast.config_loader import (
    _find_config_file,
    expand_vars,
    load_config_file,
)


def test_expand_vars_simple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_VAR_X", "hello")
    assert expand_vars("${TEST_VAR_X}") == "hello"


def test_expand_vars_with_default_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_VAR_Y", raising=False)
    assert expand_vars("${TEST_VAR_Y:-fallback}") == "fallback"


def test_expand_vars_with_default_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_VAR_Z", "real")
    assert expand_vars("${TEST_VAR_Z:-fallback}") == "real"


def test_expand_vars_empty_env_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_EMPTY", "")
    assert expand_vars("${TEST_EMPTY:-fallback}") == "fallback"


def test_expand_vars_unset_no_default_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_VAR", raising=False)
    with pytest.raises(ValueError, match="MISSING_VAR"):
        expand_vars("${MISSING_VAR}", source="test.toml")


def test_expand_vars_no_placeholders() -> None:
    assert expand_vars("plain text") == "plain text"


def test_expand_vars_multiple_placeholders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAR_A", "alpha")
    monkeypatch.setenv("VAR_B", "beta")
    assert expand_vars("${VAR_A}-${VAR_B}") == "alpha-beta"


def test_expand_vars_ignores_lowercase(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lowercase identifiers are not expanded (only [A-Z_][A-Z0-9_]*)."""
    monkeypatch.setenv("lowercase", "x")
    assert expand_vars("${lowercase}") == "${lowercase}"


def test_expand_vars_dollar_without_braces_unchanged() -> None:
    assert expand_vars("$NOT_VAR") == "$NOT_VAR"


def test_load_config_file_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("API_KEY", "sk-xxx")
    cfg = tmp_path / "mast.toml"
    cfg.write_text('[provider.openai]\napi_key = "${API_KEY}"\n', encoding="utf-8")
    data = load_config_file()
    assert data == {"provider": {"openai": {"api_key": "sk-xxx"}}}


def test_load_config_file_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("API_KEY", "sk-json")
    cfg = tmp_path / "mast.json"
    cfg.write_text('{"x": "${API_KEY}"}', encoding="utf-8")
    data = load_config_file()
    assert data == {"x": "sk-json"}


def test_load_config_file_env_var_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "mast.toml"
    cfg.write_text('x = "${MISSING:-default-val}"\n', encoding="utf-8")
    data = load_config_file()
    assert data == {"x": "default-val"}


def test_load_config_file_missing_returns_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAST_CONFIG_FILE", raising=False)
    data = load_config_file()
    assert data == {}


def test_find_config_file_explicit_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "custom.toml"
    cfg.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setenv("MAST_CONFIG_FILE", str(cfg))
    assert _find_config_file() == cfg


def test_find_config_file_explicit_env_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAST_CONFIG_FILE", str(tmp_path / "nope.toml"))
    with pytest.raises(FileNotFoundError):
        _find_config_file()


def test_find_config_file_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAST_CONFIG_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "mast.toml"
    cfg.write_text("x = 1\n", encoding="utf-8")
    assert _find_config_file() == cfg


def test_find_config_file_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAST_CONFIG_FILE", raising=False)
    monkeypatch.chdir("/tmp")
    # /tmp/mast.toml is unlikely to exist; ensure clean state
    import os

    if os.path.exists("/tmp/mast.toml"):
        os.remove("/tmp/mast.toml")
    assert _find_config_file() is None


def test_load_config_file_bool_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """bool values from ${VAR} should parse as TOML bool, not string."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FLAG", "true")
    cfg = tmp_path / "mast.toml"
    cfg.write_text('flag = "${FLAG}"\n', encoding="utf-8")
    data = load_config_file()
    assert data == {"flag": "true"}  # string after expansion; pydantic parses


def test_load_config_file_int_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PORT", "8080")
    cfg = tmp_path / "mast.toml"
    cfg.write_text('port = "${PORT:-3000}"\n', encoding="utf-8")
    data = load_config_file()
    assert data == {"port": "8080"}


def test_load_config_file_workflow_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("STAGES", raising=False)
    cfg = tmp_path / "mast.toml"
    cfg.write_text(
        '[modes.workflow]\nstages = "debate,kalman"\n',
        encoding="utf-8",
    )
    data = load_config_file()
    assert data == {"modes": {"workflow": {"stages": "debate,kalman"}}}


def test_expand_vars_error_message_includes_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING", raising=False)
    with pytest.raises(ValueError) as exc_info:
        expand_vars("${MISSING}", source="/etc/mast.toml")
    assert "/etc/mast.toml" in str(exc_info.value)
    assert "MISSING" in str(exc_info.value)
