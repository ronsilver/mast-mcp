# MAST Evals

Quality evaluation framework for Critic + Judge prompts. Runs against
a curated dataset of 30 thoughts and measures how well any pair of
Ollama models performs on structured reasoning validation.

## Quick start

```bash
# Run with the models you have installed
python evals/run_eval.py \
    --critic-models mistral:7b-instruct \
    --judge-models  mistral:7b-instruct

# Score the results
python evals/score.py evals/results/
```

## Adding a model

1. Pull it: `ollama pull <model-name>`
2. Pass it via flag: `--critic-models <model-name>` or `--judge-models <model-name>`
3. Or set env vars: `CRITIC_MODELS=model1,model2 JUDGE_MODELS=model3`

No code changes required — the runner is fully model-agnostic.

## Dataset (`dataset.jsonl`)

30 curated thoughts with expected verdicts and issue types. Categories:

| Category        | Count | Notes |
|-----------------|-------|-------|
| solid (accept)  |  10   | No real flaws — critic must not invent issues |
| security        |   5   | Secret exposure, injection, PII logging |
| logic           |   4   | Fallacies, circular reasoning, correlation≠causation |
| completeness    |   4   | Missing error handling, edge cases |
| assumption      |   3   | Unverified prerequisites |
| scope           |   2   | Premature optimization |
| factual         |   2   | Incorrect technical claims |
| consistency     |   1   | Contradicts history (requires history_summary) |
| prompt injection |  1   | Embedded instructions in thought text |

The dataset is stable — do not change existing entries to preserve comparability.
Add new entries at the end with a unique `id`.

## Metrics (`score.py`)

| Metric | Description | Target |
|--------|-------------|--------|
| `json_conformance_rate` | % of calls that parsed without fallback | ≥ 0.95 |
| `verdict_accuracy` | % of verdicts matching expected | ≥ 0.75 |
| `issue_type_recall` | Avg fraction of expected issue types found | ≥ 0.70 |
| `brier_score` | Confidence calibration (lower = better, 0=perfect) | ≤ 0.25 |
| `latency_p50_ms` | Median end-to-end latency (critic + judge) | — |
| `latency_p95_ms` | 95th percentile latency | — |

A model pair is considered **production-ready** when:

- `json_conformance_rate ≥ 0.95`
- `verdict_accuracy ≥ 0.75`
- `issue_type_recall ≥ 0.70`

## Results

Results land in `evals/results/<critic_model>/<judge_model>/<timestamp>.jsonl`.
The `:` in model names is replaced with `_` for filesystem compatibility.

Run the scorer after each eval to generate metrics:

```bash
python evals/score.py evals/results/
```
