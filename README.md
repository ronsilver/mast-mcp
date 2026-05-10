# MAST-Ollama

**Multi-Agent Sequential Thinking with Ollama** — Active validation layer for the [MCP sequential-thinking](https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking) server.

Drop-in Python replacement that challenges each reasoning step with local Ollama models before returning the result to the calling LLM.

Available validation strategies:
- **Adversarial Debate** (modes: `validate`, `debate`): a Critic identifies flaws, a Judge synthesizes a verdict
- **De Bono Six Thinking Hats** (mode: `debono`): 7 sequential hats refine a working document through facts, creativity, benefits, risks, and intuition into a final verdict

## Why

The upstream `sequential-thinking` MCP server is passive — it only persists thoughts. If the main LLM hallucinates or anchors on a bad assumption, nothing corrects it. MAST adds an active validation loop using small local models (3B–8B), keeping reasoning private and cost-free.

## Quick Start

### Prerequisites

- [Ollama](https://ollama.com) running locally or an [Ollama Cloud](https://ollama.com/pricing) account
- Pull the required models for your chosen strategy:

```bash
# Debate mode (Critic + Judge):
ollama pull mistral:7b-instruct
ollama pull deepseek-r1:8b

# Debono mode (Six Hats):
ollama pull qwen2.5:3b
ollama pull qwen2.5:1.5b
```

For Ollama Cloud, see the [Cloud section](#ollama-cloud).

### Run with `uvx`

```bash
uvx --from git+https://github.com/ronsilver/mast-ollama.git mast-server
```

### Verify setup

```bash
mast-server --doctor
```

Checks Ollama connectivity and validates that all models configured via env vars are pulled and available.

## Ollama Cloud

MAST supports both local Ollama and [Ollama Cloud](https://ollama.com/pricing). Two access modes:

### A) Direct Cloud API (programmatic)

Connect directly to `https://ollama.com/api` with an API key:

```bash
OLLAMA_BASE_URL=https://ollama.com/api \
OLLAMA_CLOUD_API_KEY=sk-xxx \
CRITIC_MODEL=mistral:7b-instruct \
mast-server
```

API keys are created at [ollama.com/settings/keys](https://ollama.com/settings/keys).

### B) Local Proxy (after `ollama signin`)

Authenticate locally, then add `-cloud` suffix to model names:

```bash
ollama signin
# then use normal OLLAMA_BASE_URL + cloud-tagged model names
DEBONO_WHITE_MODEL=qwen2.5:3b-cloud mast-server
```

The local Ollama instance proxies to cloud transparently.

### Cloud configuration examples

**Debate mode:**

```json
{
  "env": {
    "OLLAMA_BASE_URL": "https://ollama.com/api",
    "OLLAMA_CLOUD_API_KEY": "sk-xxx",
    "CRITIC_MODEL": "mistral:7b-instruct",
    "JUDGE_MODEL": "deepseek-r1:8b",
    "MAST_MODE": "debate"
  }
}
```

**Debono mode:**

```json
{
  "env": {
    "OLLAMA_BASE_URL": "https://ollama.com/api",
    "OLLAMA_CLOUD_API_KEY": "sk-xxx",
    "MAST_MODE": "debono",
    "DEBONO_BLUE_OPEN_MODEL": "qwen2.5:3b"
  }
}
```

## MCP Client Configuration

Add to your MCP client config (`claude_desktop_config.json`, `~/.cursor/mcp.json`, `.vscode/mcp.json`, etc.):

### Debate strategy (Critic + Judge)

```json
{
  "mcpServers": {
    "mast-ollama": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/ronsilver/mast-ollama.git",
        "mast-server"
      ],
      "env": {
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "CRITIC_MODEL": "mistral:7b-instruct",
        "JUDGE_MODEL": "deepseek-r1:8b",
        "MAST_MODE": "debate"
      }
    }
  }
}
```

### Debono strategy (Six Hats)

```json
{
  "mcpServers": {
    "mast-ollama": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/ronsilver/mast-ollama.git",
        "mast-server"
      ],
      "env": {
        "OLLAMA_BASE_URL": "http://localhost:11434",
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

Works with any MCP-compatible agent: Claude Desktop, Cursor, VS Code, Continue, and others.

## Modes

| Mode | Behavior | Extra latency |
|---|---|---|
| `passive` | Identical to upstream sequential-thinking (passthrough) | 0 ms |
| `validate` | Critic only — identifies issues + strengths | ~1x critic model |
| `debate` | Critic + Judge — verdict + suggested revision | ~2x |
| `debono` | De Bono Six Hats: Blue, White, Green, Yellow, Black, Red, Blue Close — progressive document refinement | ~5s |

## Tools

### `sequentialthinking` (drop-in compatible)

Same as upstream sequential-thinking plus optional MAST fields:

- `mode`: `"passive" | "validate" | "debate" | "debono"` — overrides server default for this step
- `skipValidation`: bypass validation for this specific thought

### `mast_debate` (extended)

Same schema as `sequentialthinking` plus optional model overrides per call:

- `criticModel`, `judgeModel` — override the Critic/Judge models (debate mode)
- `debonoPrimaryModel`, `debonoCreativeModel` — override primary/creative models (debono mode)

When no `mode` is specified, defaults to `debate`. Explicit `mode` from the client is respected.

## De Bono Six Hats Mode

When `MAST_MODE=debono`, each reasoning step passes through 7 sequential hats. Each hat receives the current working document and returns an enriched version:

| Step | Hat | Role | Default Model |
|---|---|---|---|
| 1 | Blue Open | Define problem, set objective | `qwen2.5:3b` |
| 2 | White | Facts, data, unknowns | `qwen2.5:3b` |
| 3 | Green | Creative alternatives, lateral thinking | `qwen2.5:1.5b` |
| 4 | Yellow | Benefits, value, prune weak ideas | `qwen2.5:3b` |
| 5 | Black | Risks, mitigations, harden plan | `qwen2.5:3b` |
| 6 | Red | Gut feeling, intuition (30s, optional) | `qwen2.5:1.5b` |
| 7 | Blue Close | Synthesize, verdict, suggested revision | `qwen2.5:3b` |

Red hat can be disabled entirely by setting `DEBONO_SKIP_RED=true`.

## Environment Variables

### Core

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server endpoint |
| `OLLAMA_CLOUD_API_KEY` | — | Ollama Cloud API key for `https://ollama.com/api` |
| `MAST_MODE` | `debate` | Default validation mode |
| `MAST_TIMEOUT_MS` | `15000` | Per-call Ollama timeout |
| `MAST_FORMAT_MODE` | `schema` | Ollama JSON format: `schema`, `json`, or `text` |
| `MAST_SKIP_THRESHOLD_CHARS` | `20` | Skip validation if thought is under this many chars |
| `MAST_CACHE_TTL_S` | `300` | Validation cache TTL (seconds) |
| `MAST_MAX_HISTORY` | `50` | Maximum thoughts retained in server memory |
| `MAST_HISTORY_WINDOW` | `3` | Most recent thoughts shown in full to agents |
| `MAST_HISTORY_MAX_TOKENS` | `1500` | Max tokens in history context sent to agents |
| `MAST_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `DISABLE_THOUGHT_LOGGING` | `false` | Suppress console thought output (upstream compat) |
| `MAST_COLOR_THOUGHTS` | `false` | ANSI colours in console thought output |
| `OLLAMA_TOP_P` | `0.9` | Ollama top-p sampling parameter |

### Debate mode (Critic + Judge)

| Variable | Default | Description |
|---|---|---|
| `CRITIC_MODEL` | `mistral:7b-instruct` | Critic model |
| `JUDGE_MODEL` | `deepseek-r1:8b` | Judge model |

### Debono mode (Six Hats)

| Variable | Default | Description |
|---|---|---|
| `DEBONO_BLUE_OPEN_MODEL` | `qwen2.5:3b` | Blue Open hat model |
| `DEBONO_WHITE_MODEL` | `qwen2.5:3b` | White hat model |
| `DEBONO_GREEN_MODEL` | `qwen2.5:1.5b` | Green hat model |
| `DEBONO_YELLOW_MODEL` | `qwen2.5:3b` | Yellow hat model |
| `DEBONO_BLACK_MODEL` | `qwen2.5:3b` | Black hat model |
| `DEBONO_RED_MODEL` | `qwen2.5:1.5b` | Red hat model |
| `DEBONO_BLUE_CLOSE_MODEL` | `qwen2.5:3b` | Blue Close hat model |
| `DEBONO_SKIP_RED` | `false` | Skip Red hat entirely |

## Development

```bash
uv venv
source .venv/bin/activate
uv sync --extra dev

# Run all tests
make test

# Lint and type check
make lint
make format
make typecheck

# Full check (lint + format + type + test)
make check
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Architecture

```
LLM Client → MCP sequentialthinking tool
                    ↓
              MAST Server
              ├── __main__.py        (entry point)
              ├── _upstream.py       (1:1 port of lib.ts)
              ├── agents/
              │   ├── base.py        (Ollama HTTP client)
              │   ├── critic.py      → Ollama (Critic)   [debate mode]
              │   ├── judge.py       → Ollama (Judge)     [debate mode]
              │   └── debono.py      → Ollama x7 hats     [debono mode]
              ├── validation/
              │   ├── orchestrator.py (mode dispatch)
              │   ├── cache.py       (LRU+TTL cache)
              │   └── schemas.py     (Pydantic models)
              └── prompts/
                  ├── debate/
                  │   ├── critic.md
                  │   └── judge.md
                  └── debono/
                      ├── blue_open.md
                      ├── white.md
                      ├── green.md
                      ├── yellow.md
                      ├── black.md
                      ├── red.md
                      └── blue_close.md
```

## License

MIT — based on [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) (MIT).
