# Roadmap

Forward-looking feature proposals for MAST-Ollama, ordered by community impact.
Each item is written to be directly convertible into a GitHub issue (motivation,
scope, acceptance criteria). Contributions welcome — see the labels at the bottom.

> Status legend: 🔴 not started · 🟡 in progress · 🟢 done

---

## P0 — Highest leverage

### 1. 🔴 Distribution: PyPI + MCP Registry + Docker image

**Motivation.** The only documented install today is `uvx --from git+https://…`,
which limits discovery to people who already know the repo. Publishing to PyPI and
the official MCP Registry makes MAST discoverable from VS Code, Copilot, and
downstream registries, with updates propagating automatically on each tagged release.

**Scope.**

- Publish the package to PyPI so `uvx mast-ollama` / `pipx install mast-ollama` work.
- Add a `server.json` (namespace `io.github.ronsilver/mast-ollama`) and a release
  workflow that publishes to the MCP Registry via the MCP Publisher CLI using GitHub
  Actions OIDC, triggered on `v*` tags.
- Build and push a container image to `ghcr.io/ronsilver/mast-ollama` for users who
  run MCP servers in containers.

**Acceptance criteria.**

- `uvx mast-ollama` runs the server from PyPI with no `--from` flag.
- The server appears in the MCP Registry under the `io.github.ronsilver` namespace.
- `docker run ghcr.io/ronsilver/mast-ollama --doctor` works against a reachable Ollama.
- A tagged release triggers PyPI publish + registry publish + image push automatically.

---

### 2. 🔴 OpenAI-compatible backend (not only Ollama)

**Motivation.** `agents/base.py` is hardcoded to Ollama's `/api/chat`. The core value
of MAST — multi-model adversarial validation — generalizes to any inference backend.
Supporting an OpenAI-compatible endpoint opens the project to the entire vLLM / LM
Studio / TGI / llama.cpp ecosystem and to low-cost cloud endpoints, multiplying the
addressable audience without changing the validation logic.

**Scope.**

- Introduce a `ChatBackend` protocol and refactor `OllamaClient` to implement it.
- Add an `OpenAICompatBackend` that targets `/v1/chat/completions`.
- Select backend via env (`MAST_BACKEND=ollama|openai`), keeping Ollama the default.
- Map the structured-output `format` parameter to each backend's JSON-mode equivalent.

**Acceptance criteria.**

- The same mode runs unchanged against Ollama and against a vLLM/LM Studio endpoint.
- `--doctor` validates connectivity and model availability for the selected backend.
- No behavioral change for existing Ollama users (default path is byte-for-byte equal).

---

### 3. 🔴 Strategy registry / plugin system

**Motivation.** The orchestrator dispatches modes through a long `if/elif` chain
(`validation/orchestrator.py`, ~lines 178–401). Because MAST is fundamentally a
collection of reasoning strategies, making strategies pluggable is the single best
lever for inviting community contributions — and it removes a code smell flagged in
the code review.

**Scope.**

- Define a `Strategy` interface = `(name, agent, prompt package, output schema)`.
- Replace the `if/elif` dispatch with a registry lookup keyed by mode name.
- Expose registration via Python entry points so third-party packages can ship
  their own strategies as installable plugins.
- Provide a cookiecutter / template for "add a new strategy".

**Acceptance criteria.**

- Adding a new mode requires no edit to `orchestrator.run()`.
- A separate pip package can register a strategy discovered at startup.
- All existing modes are migrated to the registry with no output changes.

---

## P1 — High value

### 4. 🔴 Public eval benchmark: "best small Critic" leaderboard

**Motivation.** The community has no authoritative answer to "which 3B/7B model is the
best Critic/Judge?". MAST already has an `evals/` harness; expanding it into a labeled
benchmark and publishing results is high-value reference material and a reputation
driver for the project.

**Scope.**

- Curate a labeled dataset of sound vs. flawed reasoning steps (logic, factual,
  assumption, scope, consistency, completeness).
- Score model combinations on flaw-detection rate, false-positive rate, latency, and
  (for cloud) token cost.
- Publish a results table in `evals/RESULTS.md`, refreshed by a scheduled workflow.
- Ship eval-backed presets: `budget`, `balanced`, `max-quality`.

**Acceptance criteria.**

- `make eval` reproduces the published numbers on a documented hardware baseline.
- A user can select a preset via a single env var instead of tuning each model.

---

### 5. 🔴 Validation observability

**Motivation.** For a validation layer, trust *is* the product. Surfacing aggregate
behavior helps users tune configs and trust verdicts.

**Scope.**

- Track per-mode metrics: verdict-flip rate, mean confidence, per-model latency,
  cache hit rate, fallback rate.
- Expose them as an MCP resource and/or a `--stats` command.
- Optional Prometheus endpoint and OpenTelemetry spans.
- Optional JSONL audit log of every validation for offline analysis.

**Acceptance criteria.**

- Metrics are queryable without code changes and disabled by default (privacy-safe).
- A Grafana panel JSON example is provided in `docs/`.

---

### 6. 🔴 Config wizard (`mast-server --init`)

**Motivation.** The biggest onboarding friction is env-var sprawl (seven De Bono
variables, plus model lists for brainstorm/tot/kalman). An interactive init removes it.

**Scope.**

- Detect locally available Ollama models.
- Prompt for mode + preset, then write the MCP client config JSON (Claude Desktop,
  Cursor, VS Code) to stdout or a chosen path.

**Acceptance criteria.**

- A new user goes from zero to a working client config in one command.

---

### 7. 🔴 Bring-your-own prompts (`MAST_PROMPT_DIR`)

**Motivation.** Let users tune Critic/Judge/hat prompts for their domain (legal, code,
medical) without forking the repo.

**Scope.**

- Resolve prompt templates from `MAST_PROMPT_DIR` first, falling back to packaged ones.
- Document the contract each prompt must satisfy (inputs, required JSON output).

**Acceptance criteria.**

- A user-supplied prompt directory overrides packaged prompts with no code changes.

---

## P2 — Nice to have

- **Persistent cache (SQLite).** Survive restarts; key on a nonce for stochastic modes
  (`brainstorm`, `tot`) so caching does not freeze creative variety.
- **Cost/token accounting for cloud mode.** Per-call and per-session token + dollar
  accounting with an optional budget ceiling.
- **Self-consistency sampling.** Sample a single Critic N times and take a majority
  verdict for a cheap quality boost on critical steps.
- **Confidence calibration + abstention.** Allow an `abstain` verdict ("cannot validate
  reliably") and an optional calibration mode that tracks verdict vs. feedback.

---

## Contributing

Good first issues: #6 (config wizard), #7 (prompt overrides), and the P2 items are
self-contained. #2 and #3 are the most impactful structural changes. Open an issue
referencing the item number before starting larger work so we can align on the
interface.
