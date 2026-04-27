# 🧠 MAST-Ollama

**Multi-Agent Sequential Thinking with Ollama** — Active validation layer for the [MCP sequential-thinking](https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking) server.

Drop-in Python replacement that challenges each reasoning step with two local Ollama models (a **Critic** and a **Judge**) before returning the result to the calling LLM.

## Why

The upstream `sequential-thinking` MCP server is passive — it only persists thoughts. If the main LLM hallucinates or anchors on a bad assumption, nothing corrects it. MAST adds an active validation loop using small local models (3B–8B), keeping reasoning private and cost-free.

## Quick Start

### Prerequisites

- [Ollama](https://ollama.com) running locally
- Pull the required models:
  ```bash
  ollama pull mistral:7b-instruct
  ollama pull deepseek-r1:8b
  ```

### Run with uvx (recommended)

```bash
uvx --from git+https://github.com/<user>/mast-ollama.git mast-server
```

### Verify setup

```bash
mast-server --doctor
```

## Claude Desktop Configuration

```json
{
  "mcpServers": {
    "mast-ollama": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/<user>/mast-ollama.git",
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

## Modes

| Mode | Behavior | Extra latency |
|---|---|---|
| `passive` | Identical to upstream sequential-thinking | 0 ms |
| `validate` | Critic only — issues + strengths | ~1× critic model |
| `debate` | Critic + Judge — verdict + suggested revision (default) | ~2× |

## Tools

### `sequentialthinking` (drop-in compatible)

Same as upstream + optional MAST fields:
- `mode`: `"passive" | "validate" | "debate"` — overrides server default for this step
- `skipValidation`: bypass Critic/Judge for this specific step

### `mast_debate` (extended)

Forces debate mode with optional per-call model overrides (`criticModel`, `judgeModel`).

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server endpoint |
| `CRITIC_MODEL` | `mistral:7b-instruct` | Critic model |
| `JUDGE_MODEL` | `deepseek-r1:8b` | Judge model |
| `MAST_MODE` | `debate` | Default mode |
| `MAST_TIMEOUT_MS` | `15000` | Per-call Ollama timeout |
| `MAST_CACHE_TTL_S` | `300` | Validation cache TTL (seconds) |
| `MAST_LOG_LEVEL` | `INFO` | Log level |

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/unit/ tests/integration/ -v

# Lint
ruff check src/ tests/
mypy src/
```

## Architecture

```
LLM Client → MCP sequentialthinking tool
                    ↓
              MAST Server
              ├── _upstream.py  (1:1 port of lib.ts)
              ├── agents/
              │   ├── critic.py  → Ollama (Critic)
              │   └── judge.py   → Ollama (Judge)
              └── validation/
                  ├── orchestrator.py
                  ├── cache.py
                  └── schemas.py
```

## License

MIT — based on [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) (MIT).
