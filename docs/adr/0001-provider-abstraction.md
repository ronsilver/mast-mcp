# ADR-0001: Provider Abstraction — `ChatBackend` Protocol + Multi-Provider Strategy

Status: Accepted
Date: 2026-06-22
Supersedes: implicit single-Ollama design (pre-0.3.0)

## Context

`agents/base.py` is hardcoded to Ollama's `/api/chat` endpoint. The
core value of MAST — multi-model adversarial validation — generalizes
to any inference backend. We want to support OpenAI, Anthropic, Google
Gemini, Amazon Bedrock, GitHub Models, and OpenRouter without
duplicating the orchestration logic.

Constraints:

- 164 tests must continue to pass (orchestrator unchanged for Ollama).
- Zero regressions on the default Ollama path.
- Backwards-compat for users with existing `OLLAMA_*` env vars.
- Pluggable: third-party strategies via entry points.
- Pluggable: third-party strategies via local directory.

## Decision

Introduce a `ChatBackend` abstract base class in `agents/protocols.py`
with the **same signature** as `OllamaClient.chat` to enable a
mechanical refactor:

```python
class ChatBackend(ABC):
    @abstractmethod
    async def chat(
        self, model: str, system_prompt: str, *,
        temperature: float = 0.2, num_predict: int = 512,
        fallback: dict[str, Any],
        json_schema: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], int]: ...

    @abstractmethod
    async def list_models(self) -> list[str]: ...

    @abstractmethod
    async def aclose(self) -> None: ...
```

Rationale for keeping `num_predict` (Ollama's name) instead of the more
generic `max_tokens`: every existing callsite uses `num_predict`. A
backend-agnostic rename would touch 9 agents + orchestrator for no
behavioral benefit. Cloud backends map `num_predict`→`max_tokens`/
`max_output_tokens` internally in their `chat()` method.

### Backends (7 + Ollama)

| Provider | Class | Auth | JSON mode |
|---|---|---|---|
| Ollama | `OllamaBackend` | none / `OLLAMA_CLOUD_API_KEY` | `format: json` or schema |
| OpenAI | `OpenAICompatBackend` | `OPENAI_API_KEY` | `response_format` |
| Anthropic | `AnthropicBackend` | `ANTHROPIC_API_KEY` | tool use |
| Gemini | `GeminiBackend` | `GEMINI_API_KEY` | `response_mime_type` |
| Bedrock | `BedrockBackend` | IAM (`boto3`) or bearer (`BEDROCK_TOKEN`) | tool use / response_format |
| GitHub | `GitHubBackend` | `GITHUB_TOKEN` | `response_format` |
| OpenRouter | `OpenRouterBackend` | `OPENROUTER_API_KEY` | `response_format` |

### Model naming

```text
provider:model_id
  ollama:mistral:7b-instruct
  openai:gpt-4o-mini
  anthropic:claude-3-5-sonnet-20241022
  gemini:gemini-2.0-flash
  bedrock:anthropic.claude-3-5-sonnet-20241022-v2:0
  github:gpt-4o-mini
  openrouter:anthropic/claude-3.5-sonnet
```

Backwards compat: a string with no `:` while `MAST_PROVIDER=ollama` is
treated as a literal Ollama model name (existing behavior).

### Configuration

Pydantic v2 settings via `pydantic-settings`, supporting:

1. Environment variables (highest precedence).
2. Optional TOML config file (`mast.toml`) with `${VAR}` interpolation.
3. Built-in code defaults (lowest precedence).

Precedence within a field:

```text
real env > ${VAR} expanded > ${VAR:-default} > literal in file > default
```

Config file search order:

```text
$MAST_CONFIG_FILE > ./mast.toml > ~/.config/mast/config.toml > absent
```

`${VAR}` resolver: regex `\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}`. Unset
variable without default → `ValueError` (fail fast, actionable).

### Bedrock dual auth

- `auth_method=iam` (default): SigV4 via `boto3`. Needs
  `AWS_PROFILE`/`AWS_REGION`/explicit creds. If `boto3` is not
  installed → disabled gracefully.
- `auth_method=token`: bearer token via `httpx` to
  `bedrock-runtime.${region}.amazonaws.com`. No `boto3` required.

### Strategy registry

`validation/strategy.py` defines a `Strategy` Protocol:

```python
class Strategy(Protocol):
    name: str
    async def run(
        self, thought, history, upstream_response, *,
        critic_model, judge_model, backend, cache,
    ) -> MastOutput: ...
```

`validation/registry.py` is the lookup mechanism:

```python
class StrategyRegistry:
    def register(self, name: str, strategy: Strategy) -> None: ...
    def get(self, name: str) -> Strategy: ...
```

Two discovery sources:

1. **Entry points** — `pyproject.toml [project.entry-points."mast.strategies"]`
   for distributed plugins (`pip install my-mast-strategy`).
2. **Local directory** — `MAST_STRATEGY_DIR` (default
   `~/.config/mast/strategies/`) scanned at startup for `Strategy`
   subclasses. Drop a `.py` file → restart → discovered.

Conflict resolution: built-in entry points > `MAST_STRATEGY_DIR` >
external entry points. Conflicts log a warning; built-in wins.

## Consequences

- Orchestrator (`orchestrator.py:78`) switches from `OllamaClient()` to
  `get_backend(config.mast_provider)` — one-line change per agent.
- All 8 agent constructors change type hint `OllamaClient` →
  `ChatBackend`. No logic change.
- `_extract_json`, `_CRITIC_FALLBACK`, `_JUDGE_FALLBACK` move to
  `agents/_json_utils.py` so non-Ollama backends share the same
  defensive JSON extraction.
- A new backend is one file (`agents/backends/<provider>.py`) +
  registry entry. Zero changes to orchestrator or agents.
- `--doctor` must switch from hardcoded `OllamaClient` to
  `get_backend()` and dispatch validation per active mode (T16).
- Adding a new reasoning strategy requires zero edits to
  `orchestrator.run()` (T14).

## Alternatives considered

- **Strategy functions instead of classes** — rejected: need access to
  `backend`, `cache`, and dependencies. Classes keep construction
  explicit.
- **One backend class per HTTP client** — rejected: OpenAI-compatible
  shape (URL + bearer + JSON-mode) is shared by 3 providers
  (OpenAI/GitHub/OpenRouter). Use inheritance.
- **Dynamic plugin loading from arbitrary URLs** — rejected:
  security surface, deferred to ROADMAP.

## Implementation tasks

T3, T12, T4, T5a, T5, T6-T11, T9a, T13, T14, T26.
