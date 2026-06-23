#!/usr/bin/env python
"""Eval runner — evaluates Critic+Judge quality against the curated dataset.

Usage:
    python evals/run_eval.py \\
        --critic-models mistral:7b-instruct,qwen2.5:7b-instruct \\
        --judge-models  deepseek-r1:8b,llama3.2:3b \\
        --dataset evals/dataset.jsonl \\
        --output evals/results/

If flags are omitted, reads from env vars CRITIC_MODELS / JUDGE_MODELS
(comma-separated), then falls back to configured CRITIC_MODEL / JUDGE_MODEL.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mast.agents.base import OllamaClient
from mast.agents.critic import CriticAgent
from mast.agents.judge import JudgeAgent
from mast.config import config

_TIMESTAMP_FMT = "%Y%m%dT%H%M%SZ"


def _parse_models(flag: str | None, env_key: str, fallback: str) -> list[str]:
    if flag:
        return [m.strip() for m in flag.split(",") if m.strip()]
    env = os.environ.get(env_key, "")
    if env:
        return [m.strip() for m in env.split(",") if m.strip()]
    return [fallback]


def _sanitize(name: str) -> str:
    return re.sub(r"[:/\\]", "_", name)


async def _eval_pair(
    dataset: list[dict[str, object]],
    critic_model: str,
    judge_model: str,
    output_dir: Path,
) -> None:
    client = OllamaClient()
    critic = CriticAgent(client)
    judge = JudgeAgent(client)

    ts = datetime.datetime.now(tz=datetime.UTC).strftime(_TIMESTAMP_FMT)
    out_path = output_dir / _sanitize(critic_model) / _sanitize(judge_model) / f"{ts}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n=== critic={critic_model}  judge={judge_model} ===", flush=True)

    with out_path.open("w", encoding="utf-8") as fh:
        for item in dataset:
            thought: str = str(item["thought"])
            history: str = str(item.get("history_summary", "(no previous thoughts)"))
            expected_verdict: str = str(item.get("expected_verdict", ""))
            expected_types: list[str] = list(item.get("expected_issue_types", []))  # type: ignore[arg-type]

            t0 = time.monotonic()

            # --- Critic ---
            critic_resp, critic_ms = await critic.critique(
                thought=thought,
                thought_number=1,
                total_thoughts=1,
                history_summary=history,
                model=critic_model,
            )

            # --- Judge ---
            judge_resp, judge_ms = await judge.judge(
                thought=thought,
                thought_number=1,
                total_thoughts=1,
                history_summary=history,
                critique=critic_resp,
                mode="debate",
                model=judge_model,
            )

            total_ms = int((time.monotonic() - t0) * 1000)
            actual_verdict = judge_resp.verdict.value
            actual_types = [i.type.value for i in critic_resp.issues]

            verdict_correct = actual_verdict == expected_verdict
            missing_types = [t for t in expected_types if t not in actual_types]

            record = {
                "id": item.get("id"),
                "expected_verdict": expected_verdict,
                "actual_verdict": actual_verdict,
                "verdict_correct": verdict_correct,
                "expected_issue_types": expected_types,
                "actual_issue_types": actual_types,
                "missing_types": missing_types,
                "critic_used_fallback": critic_resp.summary == "validation_failed",
                "judge_used_fallback": judge_resp.rationale == "validation_failed",
                "critic_ms": critic_ms,
                "judge_ms": judge_ms,
                "total_ms": total_ms,
                "confidence": judge_resp.confidence,
                "n_issues": len(critic_resp.issues),
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

            status = "✓" if verdict_correct else "✗"
            print(
                f"  {status} {item.get('id'):<35} "
                f"exp={expected_verdict:<7} got={actual_verdict:<7} "
                f"{total_ms}ms",
                flush=True,
            )

    await client.aclose()
    print(f"  → {out_path}", flush=True)


async def _main(args: argparse.Namespace) -> None:
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}", file=sys.stderr)
        sys.exit(1)

    dataset = [json.loads(line) for line in dataset_path.read_text().splitlines() if line.strip()]
    print(f"Loaded {len(dataset)} items from {dataset_path}", flush=True)

    critic_models = _parse_models(args.critic_models, "CRITIC_MODELS", config.critic_model)
    judge_models = _parse_models(args.judge_models, "JUDGE_MODELS", config.judge_model)
    output_dir = Path(args.output)

    for cm in critic_models:
        for jm in judge_models:
            await _eval_pair(dataset, cm, jm, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--critic-models", default=None, help="Comma-separated list of critic models"
    )
    parser.add_argument("--judge-models", default=None, help="Comma-separated list of judge models")
    parser.add_argument("--dataset", default="evals/dataset.jsonl", help="Path to dataset JSONL")
    parser.add_argument("--output", default="evals/results", help="Output directory for results")
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
