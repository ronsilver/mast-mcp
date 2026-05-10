"""Debono orchestrator — executes the Six Hats sequential pipeline."""

from __future__ import annotations

import importlib.resources
import re
import time
from typing import Any

import jinja2
import structlog

from mast.agents.base import OllamaClient
from mast.config import config
from mast.validation.schemas import (
    DebonoResult,
    HatName,
    HatOutput,
)

log = structlog.get_logger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def _load_prompt(filename: str) -> str:
    text = (
        importlib.resources.files("mast.prompts.debono")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )
    return _FRONTMATTER_RE.sub("", text, count=1)


_HAT_MODEL_GETTER = {
    HatName.BLUE_OPEN: lambda: config.debono_blue_open_model,
    HatName.WHITE: lambda: config.debono_white_model,
    HatName.GREEN: lambda: config.debono_green_model,
    HatName.YELLOW: lambda: config.debono_yellow_model,
    HatName.BLACK: lambda: config.debono_black_model,
    HatName.RED: lambda: config.debono_red_model,
    HatName.BLUE_CLOSE: lambda: config.debono_blue_close_model,
}

_HAT_PROMPT_FILE = {
    HatName.BLUE_OPEN: "blue_open.md",
    HatName.WHITE: "white.md",
    HatName.GREEN: "green.md",
    HatName.YELLOW: "yellow.md",
    HatName.BLACK: "black.md",
    HatName.RED: "red.md",
    HatName.BLUE_CLOSE: "blue_close.md",
}

_HAT_TEMPERATURE = {
    HatName.BLUE_OPEN: 0.2,
    HatName.WHITE: 0.1,
    HatName.GREEN: 0.8,
    HatName.YELLOW: 0.4,
    HatName.BLACK: 0.2,
    HatName.RED: 0.7,
    HatName.BLUE_CLOSE: 0.3,
}

_HAT_NUM_PREDICT = {
    HatName.BLUE_OPEN: 512,
    HatName.WHITE: 512,
    HatName.GREEN: 768,
    HatName.YELLOW: 512,
    HatName.BLACK: 768,
    HatName.RED: 256,
    HatName.BLUE_CLOSE: 1024,
}

_DEBONO_FALLBACK: dict[str, str] = {
    "modified_document": "",
    "working_document": "",
    "rationale": "parse_failed",
}


class DebonoOrchestrator:
    """Runs the 7 De Bono hats in sequence, passing a working_document between them."""

    def __init__(self, client: OllamaClient) -> None:
        self._client = client
        self._templates: dict[str, jinja2.Template] = {}

    def _get_template(self, filename: str) -> jinja2.Template:
        if filename not in self._templates:
            self._templates[filename] = jinja2.Template(
                _load_prompt(filename),
                undefined=jinja2.Undefined,
            )
        return self._templates[filename]

    async def run(
        self,
        thought: str,
        thought_number: int,
        total_thoughts: int,
        history_summary: str,
        *,
        is_revision: bool = False,
        revises_thought: int | None = None,
        branch_id: str | None = None,
        branch_from: int | None = None,
        primary_model: str | None = None,
        creative_model: str | None = None,
        skip_red: bool | None = None,
    ) -> tuple[DebonoResult, dict[str, Any]]:
        t_start = time.monotonic()
        hats_output: list[HatOutput] = []
        working_doc = ""

        effective_skip_red = skip_red if skip_red is not None else config.debono_skip_red

        hat_order = [
            HatName.BLUE_OPEN,
            HatName.WHITE,
            HatName.GREEN,
            HatName.YELLOW,
            HatName.BLACK,
        ]
        if not effective_skip_red:
            hat_order.append(HatName.RED)
        hat_order.append(HatName.BLUE_CLOSE)

        for hat_name in hat_order:
            model = primary_model or _HAT_MODEL_GETTER[hat_name]()
            if hat_name in (HatName.GREEN, HatName.RED) and creative_model:
                model = creative_model

            prompt_file = _HAT_PROMPT_FILE[hat_name]
            tpl = self._get_template(prompt_file)

            prompt = tpl.render(
                thought=thought,
                working_document=working_doc,
                thought_number=thought_number,
                total_thoughts=total_thoughts,
                history_summary=history_summary,
                is_revision=is_revision,
                revises_thought=revises_thought,
                branch_id=branch_id,
                branch_from=branch_from,
                hat_contributions=_summarize_contributions(hats_output),
            )

            _DEBONO_FALLBACK = {
                "modified_document": working_doc,
                "working_document": working_doc,
                "rationale": "parse_failed",
            }
            raw, latency_ms = await self._client.chat(
                model=model,
                system_prompt=prompt,
                temperature=_HAT_TEMPERATURE[hat_name],
                num_predict=_HAT_NUM_PREDICT[hat_name],
                fallback=_DEBONO_FALLBACK,
            )

            doc_before = working_doc
            working_doc = raw.get("modified_document", raw.get("working_document", doc_before))

            hats_output.append(
                HatOutput(
                    hat=hat_name,
                    model=model,
                    latency_ms=latency_ms,
                    rationale=raw.get("rationale", ""),
                )
            )

            log.info(
                "debono_hat_done",
                hat=hat_name.value,
                model=model,
                latency_ms=latency_ms,
            )

        total_latency = int((time.monotonic() - t_start) * 1000)

        # blue_close raw is the response from the last hat
        last_hat = hat_order[-1]
        blue_close = raw if last_hat == HatName.BLUE_CLOSE else {}

        debono_result = DebonoResult(
            hats=hats_output,
            total_latency_ms=total_latency,
        )

        return debono_result, blue_close


def _summarize_contributions(hats: list[HatOutput]) -> str:
    if not hats:
        return "(no previous hats)"
    lines = []
    for h in hats:
        lines.append(f"[{h.hat.value}] model={h.model} latency={h.latency_ms}ms: {h.rationale}")
    return "\n".join(lines)
