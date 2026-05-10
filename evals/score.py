#!/usr/bin/env python
"""Score eval results — computes metrics from run_eval.py output JSONL files.

Usage:
    python evals/score.py evals/results/
    python evals/score.py evals/results/mistral_7b-instruct/deepseek-r1_8b/20250427T123456Z.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast


def _load_records(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))
    elif path.is_dir():
        for f in sorted(path.rglob("*.jsonl")):
            for line in f.read_text().splitlines():
                if line.strip():
                    records.append(json.loads(line))
    return records


def _score(records: list[dict[str, object]]) -> dict[str, object]:
    n = len(records)
    if n == 0:
        return {"error": "no records"}

    json_ok = sum(
        1 for r in records if not r.get("critic_used_fallback") and not r.get("judge_used_fallback")
    )
    verdict_correct = sum(1 for r in records if r.get("verdict_correct"))

    # Issue-type recall: for each record, what fraction of expected types were found?
    recall_scores: list[float] = []
    for r in records:
        expected: list[str] = cast(list[str], r.get("expected_issue_types", []))
        missing: list[str] = cast(list[str], r.get("missing_types", []))
        if expected:
            recall_scores.append(1.0 - len(missing) / len(expected))

    # Brier score: (confidence - correct)^2, lower is better
    brier_scores: list[float] = []
    for r in records:
        correct = 1.0 if r.get("verdict_correct") else 0.0
        confidence = cast(float, r.get("confidence", 0.0))
        brier_scores.append((confidence - correct) ** 2)

    latencies = [cast(int, r["total_ms"]) for r in records if "total_ms" in r]
    latencies_sorted = sorted(latencies)

    def _percentile(data: list[int], p: int) -> int:
        if not data:
            return 0
        idx = max(0, int(len(data) * p / 100) - 1)
        return data[idx]

    return {
        "n": n,
        "json_conformance_rate": round(json_ok / n, 3),
        "verdict_accuracy": round(verdict_correct / n, 3),
        "issue_type_recall": round(sum(recall_scores) / len(recall_scores), 3)
        if recall_scores
        else None,
        "brier_score": round(sum(brier_scores) / n, 3),
        "latency_p50_ms": _percentile(latencies_sorted, 50),
        "latency_p95_ms": _percentile(latencies_sorted, 95),
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python evals/score.py <path>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    records = _load_records(path)
    if not records:
        print("No records found.", file=sys.stderr)
        sys.exit(1)

    metrics = _score(records)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
