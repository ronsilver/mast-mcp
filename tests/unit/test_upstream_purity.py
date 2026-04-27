"""Architecture test: _upstream.py must not import MAST-specific modules."""

from __future__ import annotations

from pathlib import Path

UPSTREAM_PATH = Path(__file__).parent.parent.parent / "src" / "mast" / "_upstream.py"

_FORBIDDEN = [
    "mast.config",
    "mast.agents",
    "mast.validation",
    "mast.server",
    "CriticAgent",
    "JudgeAgent",
    "ValidationOrchestrator",
]


def test_upstream_contains_no_mast_specific_imports() -> None:
    """_upstream.py is a pure port — must not reference MAST extensions."""
    source = UPSTREAM_PATH.read_text(encoding="utf-8")
    violations = [term for term in _FORBIDDEN if term in source]
    assert not violations, (
        f"_upstream.py contains MAST-specific references: {violations}. "
        "Keep this file a pure port of the upstream TS logic."
    )
