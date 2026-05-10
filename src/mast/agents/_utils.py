"""Shared utilities for agent prompt loading."""

from __future__ import annotations

import importlib.resources
import re

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def load_prompt(base_pkg: str, filename: str) -> str:
    """Read a prompt template and strip its YAML frontmatter."""
    text = importlib.resources.files(base_pkg).joinpath(filename).read_text(encoding="utf-8")
    return _FRONTMATTER_RE.sub("", text, count=1)
