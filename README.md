# MAST-MCP

[![Codacy Badge](https://app.codacy.com/project/badge/Grade/e1b069af215841d4a31e123bc782121f)](https://app.codacy.com/gh/ronsilver/mast-mcp/dashboard)

Multi-provider active validation layer for the
[MCP sequential-thinking](https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking)
server. Drop-in replacement that challenges each reasoning step with
local or cloud LLMs before returning the result to the calling agent.

Works with Ollama, OpenAI, Anthropic, Google Gemini, Amazon Bedrock,
GitHub Models, OpenRouter, and any OpenAI-compatible endpoint.

## Validation modes

| Mode | Behavior |
|---|---|
| `validate` | Critic only — identifies issues + strengths |
| `debate` | Critic + Judge — verdict + suggested revision |
| `debono` | De Bono Six Thinking Hats (7 sequential hats) |
| `actor_critic` | Iterative Critic+Judge loop until convergence |
| `brainstorm` | N parallel generators + synthesizer |
| `tot` | Tree of Thoughts (parallel branches + voter) |
| `kalman` | Bayesian fusion of quality scores |
| `workflow` | Pipeline of modes chained in sequence |
| `passive` | Passthrough (no validation) |

## Table of Contents

- [Why](#why)
- [Quick Start](#quick-start)
- [Providers](#providers)
  - [Ollama](#ollama)
  - [OpenAI](#openai)
  - [Anthropic](#anthropic)
  - [Gemini](#gemini)
  - [Bedrock](#bedrock)
  - [GitHub Models](#github-models)
  - [OpenRouter](#openrouter)
- [Configuration](#configuration)
  - [Config File (`mast.toml`)](#config-file-masttoml)
  - [Environment Variables](#environment-variables)
  - [Precedence](#precedence)
- [Provider Selection Guide](#provider-selection-guide)
- [MCP Client Configuration](#mcp-client-configuration)
- [Modes](#modes)
- [Tools](#tools)
- [Custom Strategies](#custom-strategies)
- [Architecture](#architecture)
- [Development](#development)
- [Changelog](#changelog)
- [License](#license)

## Why

The upstream `sequential-thinking` MCP server is passive — it only
persists thoughts. If the main LLM hallucinates or anchors on a bad
assumption, nothing corrects it. MAST adds an active validation loop
using small local models (3B–8B) for privacy and cost, or any
frontier model for max quality. The same MCP tool API — drop-in
compatible with the original.

## Quick Start

### Install via `uvx`

```bash
uvx --from git+https://github.com/ronsilver/mast-mcp.git mast-server
```

### Verify setup

```bash
mast-server --doctor
```

Checks backend connectivity, validates credentials, and lists required
vs available models for the active mode.

## Providers

MAST ships with 7 backend implementations, all interchangeable via
`MAST_PROVIDER` or the `mast.toml` config file.

### Ollama

Default provider. Local-first; no API key required.

```bash
MAST_PROVIDER=ollama \
OLLAMA_BASE_URL=http://localhost:11434 \
CRITIC_MODEL=mistral:7b-instruct \
JUDGE_MODEL=deepseek-r1:8b \
mast-server
```

[Ollama Cloud](https://ollama.com/pricing) supported via the same
provider with `OLLAMA_BASE_URL=https://ollama.com/api` +
`OLLAMA_CLOUD_API_KEY=sk-xxx`.

### OpenAI

```bash
MAST_PROVIDER=openai \
OPENAI_API_KEY=sk-xxx \
CRITIC_MODEL=gpt-4o-mini \
JUDGE_MODEL=gpt-4o-mini \
mast-server
```

Also accepts `OPENAI_BASE_URL` to point at vLLM, LM Studio, TGI, or
any OpenAI-compatible endpoint.

### Anthropic

```bash
MAST_PROVIDER=anthropic \
ANTHROPIC_API_KEY=sk-ant-xxx \
CRITIC_MODEL=claude-3-5-sonnet-20241022 \
JUDGE_MODEL=claude-3-5-sonnet-20241022 \
mast-server
```

### Gemini

```bash
MAST_PROVIDER=gemini \
GEMINI_API_KEY=xxx \
CRITIC_MODEL=gemini-2.0-flash \
JUDGE_MODEL=gemini-2.0-flash \
mast-server
```

### Bedrock

Dual authentication supported:

```bash
# Token auth (no boto3 needed)
MAST_PROVIDER=bedrock \
BEDROCK_AUTH_METHOD=token \
BEDROCK_TOKEN=xxx \
AWS_REGION=us-east-1 \
CRITIC_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0 \
mast-server

# IAM auth (requires boto3 — pip install mast-mcp[bedrock])
MAST_PROVIDER=bedrock \
BEDROCK_AUTH_METHOD=iam \
AWS_REGION=us-east-1 \
AWS_PROFILE=default \
CRITIC_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0 \
mast-server
```

### GitHub Models

```bash
MAST_PROVIDER=github \
GITHUB_TOKEN=ghp_xxx \
CRITIC_MODEL=gpt-4o-mini \
JUDGE_MODEL=gpt-4o-mini \
mast-server
```

### OpenRouter

```bash
MAST_PROVIDER=openrouter \
OPENROUTER_API_KEY=sk-or-xxx \
CRITIC_MODEL=anthropic/claude-3.5-sonnet \
JUDGE_MODEL=anthropic/claude-3.5-sonnet \
mast-server
```

## Configuration

Three layers, merged in this order (highest precedence wins):

1. **Environment variables** — `MAST_*`, `OPENAI_*`, `ANTHROPIC_*`, etc.
2. **Config file** — `mast.toml` or `mast.json` with `${VAR}` interpolation
3. **Built-in defaults** — defined in source code

### Config File (`mast.toml`)

Place `mast.toml` in any of these locations (first found wins):

- `$MAST_CONFIG_FILE` (any path)
- `./mast.toml` or `./mast.json`
- `~/.config/mast/config.toml` or `~/.config/mast/config.json`

The file supports `${VAR}` interpolation with optional defaults:

```toml
# mast.toml — copied from mast.toml.example
[provider]
default = "openai"                    # or ${MAST_PROVIDER:-openai}

[provider.openai]
api_key = ${OPENAI_API_KEY}            # required, resolved at load

[provider.bedrock]
auth_method = "token"                  # or ${BEDROCK_AUTH_METHOD:-iam}
region = "us-east-1"                   # or ${AWS_REGION:-us-east-1}
token = ${BEDROCK_TOKEN}               # bearer token when auth=token

[provider.ollama]
base_url = "http://localhost:11434"    # or ${OLLAMA_BASE_URL:-http://localhost:11434}

[strategy]
default = "debate"                     # or ${MAST_MODE:-debate}
dir = "~/.config/mast/strategies"      # custom strategies dir

[agents]
critic_model = "gpt-4o-mini"           # or ${CRITIC_MODEL:-gpt-4o-mini}
judge_model  = "gpt-4o-mini"

[modes.debono]
blue_open_model = "qwen2.5:3b"
# ... (7 hats)

[modes.workflow]
stages = "debate,kalman"
```

**`${VAR}` rules:**

- `${VAR}` — replaced by env var value. **Error** if unset (fail fast).
- `${VAR:-default}` — replaced by env var, or `default` if unset/empty.
- Lowercase identifiers are not expanded.
- See [`mast.toml.example`](mast.toml.example) for the full template.

> **Security:** `mast.toml` is gitignored by default. **Never** commit
> it with real credentials.

### Environment Variables

#### Provider selection

| Variable | Default | Description |
|---|---|---|
| `MAST_PROVIDER` | `ollama` | One of: `ollama`, `openai`, `anthropic`, `gemini`, `bedrock`, `github`, `openrouter`. If unset, auto-detect from available credentials |
| `MAST_BASE_URL` | — | Generic base URL override |
| `MAST_API_KEY` | — | Generic API key (provider-specific keys take precedence) |
| `MAST_CONFIG_FILE` | — | Explicit path to `mast.toml` |

#### Ollama

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server endpoint |
| `OLLAMA_CLOUD_API_KEY` | — | Bearer token for `https://ollama.com/api` |
| `OLLAMA_TOP_P` | `0.9` | Top-p sampling |

#### OpenAI-compatible

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | OpenAI API key |
| `OPENAI_BASE_URL` | — | Override for vLLM/LM Studio/TGI |

#### Anthropic

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Anthropic API key |

#### Gemini

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Google Gemini API key |

#### Bedrock

| Variable | Default | Description |
|---|---|---|
| `BEDROCK_AUTH_METHOD` | `iam` | `iam` (SigV4 via boto3) or `token` (bearer via httpx) |
| `BEDROCK_TOKEN` | — | Bearer token (required when `BEDROCK_AUTH_METHOD=token`) |
| `AWS_REGION` | `us-east-1` | Bedrock region |
| `AWS_PROFILE` | — | AWS CLI profile (iam only) |
| `AWS_ACCESS_KEY_ID` | — | Explicit IAM creds (optional) |
| `AWS_SECRET_ACCESS_KEY` | — | Explicit IAM creds (optional) |
| `AWS_SESSION_TOKEN` | — | STS session token (optional) |

#### GitHub Models

| Variable | Default | Description |
|---|---|---|
| `GITHUB_TOKEN` | — | GitHub PAT for Models inference |

#### OpenRouter

| Variable | Default | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | — | OpenRouter API key |

#### Server / behavior

| Variable | Default | Description |
|---|---|---|
| `MAST_MODE` | `debate` | Default validation mode |
| `MAST_TIMEOUT_MS` | `15000` | Per-call backend timeout |
| `MAST_FORMAT_MODE` | `schema` | Ollama JSON format: `schema`, `json`, `text` |
| `MAST_SKIP_THRESHOLD_CHARS` | `20` | Skip validation for thoughts under this many chars |
| `MAST_CACHE_TTL_S` | `300` | Validation cache TTL (stochastic modes always bypass) |
| `MAST_MAX_HISTORY` | `50` | Max thoughts retained in server memory |
| `MAST_HISTORY_WINDOW` | `3` | Most recent thoughts shown in full to agents |
| `MAST_HISTORY_MAX_TOKENS` | `1500` | Max tokens in history context |
| `MAST_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `MAST_STRATEGY_DIR` | — | Custom strategy plugins directory (e.g. `~/.config/mast/strategies`) |
| `DISABLE_THOUGHT_LOGGING` | `false` | Suppress console thought output |
| `MAST_COLOR_THOUGHTS` | `false` | ANSI colours in console output |

#### Agent models

| Variable | Default | Description |
|---|---|---|
| `CRITIC_MODEL` | `mistral:7b-instruct` | Critic model (validate, debate, actor_critic, workflow) |
| `JUDGE_MODEL` | `deepseek-r1:8b` | Judge model (debate, actor_critic, workflow) |

#### Mode-specific

| Variable | Default | Mode |
|---|---|---|
| `DEBONO_BLUE_OPEN_MODEL` | `qwen2.5:3b` | debono |
| `DEBONO_WHITE_MODEL` | `qwen2.5:3b` | debono |
| `DEBONO_GREEN_MODEL` | `qwen2.5:1.5b` | debono |
| `DEBONO_YELLOW_MODEL` | `qwen2.5:3b` | debono |
| `DEBONO_BLACK_MODEL` | `qwen2.5:3b` | debono |
| `DEBONO_RED_MODEL` | `qwen2.5:1.5b` | debono |
| `DEBONO_BLUE_CLOSE_MODEL` | `qwen2.5:3b` | debono |
| `DEBONO_SKIP_RED` | `false` | Skip Red hat entirely |
| `ACTOR_CRITIC_MAX_ROUNDS` | `3` | actor_critic |
| `BRAINSTORM_MODELS` | `llama3:8b,mistral:7b` | brainstorm (comma-separated) |
| `BRAINSTORM_SYNTH_MODEL` | `qwen2.5:14b` | brainstorm |
| `TOT_BRANCH_MODELS` | `llama3:8b,mistral:7b,qwen2.5:7b` | tot |
| `TOT_VOTER_MODEL` | `deepseek-r1:8b` | tot |
| `KALMAN_SCORER_MODELS` | `mistral:7b,qwen2.5:7b,phi3:mini` | kalman |
| `KALMAN_P_THRESHOLD` | `0.18` | kalman convergence threshold |
| `KALMAN_ACCEPT_THRESHOLD` | `0.70` | kalman min score to accept |
| `MAST_WORKFLOW_STAGES` | `debate,kalman` | workflow chain |

## Precedence

For any given field, the value is resolved in this order:

```text
real env var > ${VAR} expanded > ${VAR:-default} > literal in file > code default
```

Examples:

| Source | `api_key = "sk-xxx"` | `${OPENAI_API_KEY}` (env set) | `${OPENAI_API_KEY}` (env unset) |
|---|---|---|---|
| env `OPENAI_API_KEY=sk-yyy` | `sk-yyy` wins | `sk-yyy` wins | `sk-xxx` wins |
| env unset | `sk-xxx` wins | **error** | `sk-xxx` wins |

## Provider Selection Guide

| Priority | If you need... | Recommended provider |
|---|---|---|
| Privacy, free, offline | Local inference | **Ollama** (3B–8B models) |
| Best quality | Frontier reasoning | **Anthropic** (`claude-3-5-sonnet`) or **Gemini** (`gemini-2.0-flash`) |
| Cheapest cloud | Pay-per-token minimal cost | **OpenRouter** (DeepSeek, Llama, etc.) |
| GitHub Copilot users | Already have GitHub token | **GitHub Models** |
| AWS enterprise | IAM roles, VPC, audit logs | **Bedrock** (iam) |
| Self-hosted OpenAI | vLLM, LM Studio, llama.cpp server | **OpenAI** + `OPENAI_BASE_URL` override |
| Multi-model router | Switch models per request | **OpenRouter** with `provider:model` syntax |

## MCP Client Configuration

Add to your MCP client config (`claude_desktop_config.json`,
`~/.cursor/mcp.json`, `.vscode/mcp.json`, etc.).

### Ollama (default)

```json
{
  "mcpServers": {
    "mast-mcp": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/ronsilver/mast-mcp.git", "mast-server"],
      "env": {
        "MAST_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "CRITIC_MODEL": "mistral:7b-instruct",
        "JUDGE_MODEL": "deepseek-r1:8b",
        "MAST_MODE": "debate"
      }
    }
  }
}
```

### OpenAI

```json
{
  "mcpServers": {
    "mast-mcp": {
      "command": "uvx",
      "args": ["mast-mcp"],
      "env": {
        "MAST_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-xxx",
        "CRITIC_MODEL": "gpt-4o-mini",
        "JUDGE_MODEL": "gpt-4o-mini",
        "MAST_MODE": "debate"
      }
    }
  }
}
```

### Debono (Six Hats)

```json
{
  "mcpServers": {
    "mast-mcp": {
      "command": "uvx",
      "args": ["mast-mcp"],
      "env": {
        "MAST_PROVIDER": "ollama",
        "MAST_MODE": "debono",
        "DEBONO_BLUE_OPEN_MODEL": "qwen2.5:3b",
        "DEBONO_WHITE_MODEL": "qwen2.5:3b",
        "DEBONO_GREEN_MODEL": "qwen2.5:1.5b",
        "DEBONO_YELLOW_MODEL": "qwen2.5:3b",
        "DEBONO_BLACK_MODEL": "qwen2.5:3b",
        "DEBONO_RED_MODEL": "qwen2.5:1.5b",
        "DEBONO_BLUE_CLOSE_MODEL": "qwen2.5:3b"
      }
    }
  }
}
```

### Migration from v0.2.x (Ollama-only)

If upgrading from `mast-ollama`, replace the server name `"mast-ollama"`
with `"mast-mcp"` in your client config and rename any references to
the old GitHub repo. The `mast-server` entry point is preserved.

## Modes

| Mode | Behavior | Extra latency |
|---|---|---|
| `passive` | Identical to upstream sequential-thinking (passthrough) | 0 ms |
| `validate` | Critic only | ~1x critic model |
| `debate` | Critic + Judge | ~2x |
| `debono` | De Bono Six Hats: Blue, White, Green, Yellow, Black, Red, Blue Close | ~5s |
| `actor_critic` | Iterative Critic+Judge loop up to `ACTOR_CRITIC_MAX_ROUNDS` | ~2x × rounds |
| `brainstorm` | N parallel generators + Synthesizer | ~2x × N models |
| `tot` | N parallel branch generators + Voter | ~2x × N branches |
| `kalman` | N scorers + Bayesian fusion | ~1x × N scorers |
| `workflow` | Pipeline of modes chained in sequence | Sum of stages |

## Tools

### `sequentialthinking` (drop-in compatible)

Same as upstream sequential-thinking plus optional MAST fields:

- `mode`: override the server default for this step
- `skipValidation`: bypass validation for this specific thought

### `mast_debate` (extended)

Same schema as `sequentialthinking` plus optional model overrides per call:

- `criticModel`, `judgeModel` — override the Critic/Judge models
- `debonoPrimaryModel`, `debonoCreativeModel` — override primary/creative (debono)

When no `mode` is specified, defaults to `debate`. Explicit `mode` from
the client is respected.

## Custom Strategies

MAST ships with 9 built-in strategies. You can add more via two
mechanisms:

### Entry points (pip packages)

Publish a Python package with an entry point in `pyproject.toml`:

```toml
[project.entry-points."mast.strategies"]
my_strategy = "my_pkg.strategies:MyStrategy"
```

`MyStrategy` must expose a `name` attribute and an async `run` method
matching the `Strategy` protocol.

### Local directory (`MAST_STRATEGY_DIR`)

Drop a `.py` file in `~/.config/mast/strategies/` (or wherever
`MAST_STRATEGY_DIR` points):

```python
# ~/.config/mast/strategies/redteam.py
from typing import Any
from mast.validation.strategy import Strategy

class RedTeamStrategy:
    name = "redteam"

    async def run(
        self,
        thought,
        history,
        upstream_response,
        *,
        critic_model=None,
        judge_model=None,
        backend,
        cache,
    ) -> Any:
        # ... your custom validation logic ...
        return None
```

MAST auto-discovers `*.py` files in this directory at startup. Built-in
strategy names win on conflict (warnings logged).

## Architecture

```text
LLM Client → MCP sequentialthinking tool
                    ↓
              MAST Server (mast-mcp)
              ├── __main__.py        (entry point)
              ├── _upstream.py       (1:1 port of upstream lib.ts)
              ├── config.py          (Pydantic settings + mast.toml)
              ├── config_loader.py   (TOML/JSON + ${VAR} resolver)
              ├── agents/
              │   ├── protocols.py   (ChatBackend ABC)
              │   ├── registry.py    (provider factory + auto-detect)
              │   ├── base.py        (OllamaBackend)
              │   ├── backends/
              │   │   ├── openai.py  (OpenAICompatBackend)
              │   │   ├── openrouter.py
              │   │   ├── github.py
              │   │   ├── anthropic.py
              │   │   ├── gemini.py
              │   │   └── bedrock.py (iam + token dual-auth)
              │   ├── critic.py, judge.py, debono.py
              │   ├── actor_critic.py, brainstorm.py
              │   ├── tot.py, kalman.py
              │   └── _json_utils.py (shared defensive parser)
              ├── validation/
              │   ├── orchestrator.py (mode dispatch)
              │   ├── cache.py       (LRU+TTL)
              │   ├── strategy.py    (Strategy Protocol)
              │   ├── registry.py    (entry-point + dir loader)
              │   ├── strategies/    (9 built-in placeholders)
              │   └── schemas.py     (Pydantic models)
              └── prompts/
                  ├── debate/, debono/, brainstorm/, tot/, kalman/
```

## Development

```bash
uv venv
source .venv/bin/activate
uv sync --extra dev

# Run all tests (343 expected)
make test

# Coverage (terminal + HTML report, gate ≥ 70%)
make coverage

# Lint, format, type check
make lint
make format
make typecheck

# Full check (lint + format + type + test)
make check

# Install Bedrock extra (optional)
uv sync --extra bedrock

# Verify backend connectivity
mast-server --doctor
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

MIT — based on [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) (MIT).
