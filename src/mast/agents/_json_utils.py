"""
Shared defensive JSON extraction utilities for all ChatBackend implementations.

Tolerates: <think> blocks, code fences, prose prefixes/suffixes.
Uses raw_decode so it stops at the first complete JSON object.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Minimum valid fallback shape for Critic responses
CRITIC_FALLBACK: dict[str, Any] = {
    "issues": [],
    "strengths": [],
    "summary": "validation_failed",
}

# Minimum valid fallback shape for Judge responses
JUDGE_FALLBACK: dict[str, Any] = {
    "verdict": "accept",
    "confidence": 0.0,
    "rationale": "validation_failed",
    "suggestedRevision": None,
}

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any] | None:
    """
    Defensively extract first balanced JSON object from arbitrary model output.

    Tolerates: <think> blocks, code fences, prose prefixes/suffixes.
    Uses raw_decode so it stops at the first complete JSON object.
    """
    text = _THINK_RE.sub("", text)

    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1)

    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text, i)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None
