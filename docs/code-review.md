# Code Review — v0.2.0

Point-in-time review of `main` (commit `5f66f1e`). Verified empirically: the repo was
cloned and the full toolchain was run (`pytest`, `ruff`, `mypy --strict`, coverage).

## Verdict

Solid, well-built foundation. Clean architecture, strict typing, and the v0.2.0 modes
are implemented and documented consistently. The improvements below cluster in three
areas: a latent **race condition** in the orchestrator, a **`--doctor` gap** covering
only 4 of 9 modes, and **coverage gaps at the MCP integration boundary**. None blocks
single-agent sequential use today, but all three matter under concurrent calls or when
starting in a mode other than `debate`/`debono`.

### Verified state

| Check | Result |
|---|---|
| `pytest` | 164 passed |
| `ruff check` | clean |
| `mypy --strict` (27 files) | no issues |
| Total coverage | 62% |
| Docs (README + docs/strategies.md) | all 9 modes covered |

## Strengths (keep)

- Clear layering: 1:1 upstream port, `agents/`, `validation/`, `prompts/` with
  progressive disclosure.
- Real type discipline: `mypy --strict` and `ruff` (E, F, I, UP, B, SIM, ANN) green.
- Prompt-injection defense present in prompts (content as DATA, XML tags, "ignore
  embedded commands") — verified in `prompts/debate/critic.md`.
- Graceful degradation: `asyncio.gather(return_exceptions=True)` per scorer/branch,
  HTTP-error fallbacks, and `_extract_json` tolerating `<think>` blocks, fences, prose.
- Config hygiene: Pydantic settings with env aliases and validators.

---

## Findings (prioritized)

### 1. Race condition in the orchestrator — HIGH (correctness)

`ValidationOrchestrator` is a process-global singleton (`server._orchestrator_state`).
On the `debate`/`debono` path, intermediate results are stored as **instance
attributes** instead of locals:

- `orchestrator.py:133-134` → `self._critic_response`, `self._critic_latency`
- `orchestrator.py:153-154` → `self._judge_response`, `self._judge_latency`
- `orchestrator.py:113-114` → `self._debono_result`, `self._debono_blue_close`

The MCP SDK can dispatch `call_tool` concurrently. If two `run()` calls overlap (or
`workflow` stages that recursively call `run()`), one overwrites the other's attributes
between `await`s, mixing verdicts across thoughts. The `actor_critic`, `brainstorm`,
`tot`, and `kalman` modes already use locals correctly — only `debate`/`debono` have
the anti-pattern.

**Fix (low effort).** Have `_run_critic` / `_run_judge` / `_run_debono` **return** their
tuples and consume them as locals inside `run()`. Removes the shared mutable state with
no logic change.

### 2. `--doctor` validates only `debate`/`debono` models — MEDIUM (operability)

In `__main__.py`, `_collect_configured_models()` and `_print_model_list()` enumerate
only `critic_model`, `judge_model`, and the seven De Bono models. If `MAST_MODE` is
`actor_critic`, `brainstorm`, `tot`, `kalman`, or `workflow`:

- `--doctor` checks the wrong models (critic/judge, which kalman/tot/brainstorm don't use).
- It never verifies `brainstorm_models`, `tot_branch_models`, `kalman_scorer_models`, or
  the per-stage workflow models.
- It prints "✅ Ready to run!" while the real models are missing → silent fallback at runtime.

**Fix.** Dispatch `_collect_configured_models()` by `config.mast_mode` (or validate the
union of all modes' models).

### 3. Coverage gaps at the integration boundary — MEDIUM (quality)

164 tests pass, but the path the MCP client actually executes is untested:

| Module | Coverage | Uncovered |
|---|---|---|
| `server.py` | **0%** | `_handle_thought`, tool dispatch, `mast_debate` `force_mode` logic, `skip_validation` |
| `__main__.py` | **0%** | `--doctor` command |
| `orchestrator.py` | 40% | new-mode dispatch (233–401) + `workflow` chaining (414–491) |
| `tot.py` / `kalman.py` / `brainstorm.py` / `actor_critic.py` | 37–54% | new agents have parsing tests but thin orchestration coverage |

Integration tests call the orchestrator directly rather than through `_handle_thought`,
so there is no end-to-end test through the real tool entry point. CI has no
`--cov-fail-under` gate, so coverage can erode unnoticed.

**Fix.** An e2e test that invokes `_call_tool("sequentialthinking", …)` and
`_call_tool("mast_debate", …)` with a mocked `OllamaClient` (the suite already uses
`respx`), plus `--cov-fail-under=70` in CI.

### 4. Kalman: `converged` is effectively unreachable at defaults — MEDIUM (tuning)

With `P0=1.0`, `Q=0.01`, and three scorers at moderate confidence, `P` settles around
~0.15 and never crosses `KALMAN_P_THRESHOLD=0.05` (`kalman.py`). As a result `converged`
is almost always `False`, and the `K5:no_new_information` trigger (which requires
`P > 0.20`) rarely fires as intended. The output `confidence = 1 − P` is reasonable; the
convergence signal itself is the dead part.

**Fix.** Raise the threshold to ~0.15–0.20, or increase scorer count/iterations, and add
a test pinning the expected `converged` behavior under default config.

### 5. `OllamaClient.chat` retry re-sends an identical payload — LOW

`base.py:115-145`: on JSON-parse failure, attempt 1 re-sends the same model, temperature,
and prompt with no backoff or nudge. At `temperature=0.1–0.2` a deterministic non-JSON
response is likely to repeat. The final fallback also returns `latency_ms=0`
(`base.py:160`), losing the failed-call latency for observability.

**Fix.** On retry, append a "respond with JSON only" reminder or nudge the temperature;
record real latency in the fallback path.

### 6. Cache freezes stochastic modes — LOW (design)

`orchestrator.py:191-202` keys the cache on `thought + models + mode + history`. For
`brainstorm`/`tot` (`temperature=0.75`), the first stochastic result is pinned for
`MAST_CACHE_TTL_S` (300 s). Re-running the same thought for variety returns the cached
result.

**Fix.** Bypass the cache for divergent modes, or include a nonce in their cache key.

### 7. ToT voter score mapping is positional — LOW (robustness)

`tot.py:_apply_voter_scores` maps `scores[i] → branches[i]` by index. If the voter
returns scores in a different order, with fewer entries, or with explicit indices, the
attribution silently misaligns; unscored branches sort to the bottom via `or 0`.

**Fix.** Have the voter return an explicit branch index and map by that field.

### 8. `mast_debate` no-op line + minor doc inconsistency — LOW (cleanup)

`server.py:60` → `force_mode = "debate" if user_mode == "debate" else user_mode` is a
logical no-op. The README/tool description say `mast_debate` defaults to `debate`, but
the code uses `arguments.get("mode") or config.mast_mode` (defaults to the configured
mode).

**Fix.** Remove the redundant line and align the default with the docs.

### 9. CI: single Python version, no coverage gate — LOW

`requires-python = ">=3.12"`, but CI runs a single interpreter with no 3.12/3.13 matrix
and no explicit uv cache.

**Fix.** Add a Python matrix and `--cov-fail-under`.

---

## Quick wins (suggested order)

1. Return locals in `_run_critic` / `_run_judge` / `_run_debono` → closes the race (#1).
2. `--doctor` by active mode → closes the operability gap (#2).
3. E2E test through `_call_tool` + `--cov-fail-under` in CI (#3).
4. Tune/test `KALMAN_P_THRESHOLD` (#4).

Items 5–9 are polish and can be grouped into a single "hardening" PR.
