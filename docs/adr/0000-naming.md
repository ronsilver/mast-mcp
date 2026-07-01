# ADR-0000: Project Rename — `mast-ollama` → `mast-mcp`

Status: Accepted
Date: 2026-06-22

## Context

The project started as an Ollama-only validation layer for the MCP
sequential-thinking server. With the move to multi-provider support
(see ADR-0001), the name `mast-ollama` no longer reflects scope. A
clean rename is needed before T2 (distribution to PyPI, MCP Registry,
Docker image) to avoid publishing under a misleading name.

PyPI name availability verified empirically this session:

| Candidate | HTTP status | Verdict |
|---|---|---|
| `mast` | 200 | taken (cannot use) |
| `mast-mcp` | 404 | available |
| `mast-validate` | 404 | available |
| `mast-llm` | 404 | available |
| `sequential-mast` | 404 | available |

## Decision

Rename to **`mast-mcp`**.

Rationale:

- Explicit: signals it is an MCP server (matches the project's role).
- Avoids generic collisions: `mast` is taken; `mast-llm` is too broad.
- Short enough for `uvx mast-mcp` invocations.
- Library import root stays `mast` (the package inside `src/`). Only the
  PyPI distribution name, the MCP server name (advertised to clients),
  the Docker image, and the README title change.

## Consequences

- `pyproject.toml` `name` field: `mast-ollama` → `mast-mcp`.
- `mcp.server.Server("mast-ollama")` → `Server("mast-mcp")`.
- Docker image: `ghcr.io/ronsilver/mast-ollama` → `ghcr.io/ronsilver/mast-mcp`.
- Entry point: `mast-server` kept for back-compat (existing uvx
  invocations continue to work); add `mast-mcp` as alias.
- MCP client configs that reference `mast-ollama` must update the server
  name; documented in README migration section (T25).
- CHANGELOG `[Unreleased]` notes the rename; `mast-ollama` retains
  entries under `[0.2.0]` as historical record.

## Alternatives considered

- **`mast-validate`** — describes core value but loses the MCP framing.
- **`mast-llm`** — too generic; misleading for users searching
  LLM-agnostic libraries.
- **`sequential-mast`** — closest to upstream but verbose.
- **`mast-mcp` (chosen)** — explicit, short, accurate.

## Migration

Users on v0.2.0 do nothing — `mast-server` entry point preserved. Only
MCP client configs referencing the literal server name `"mast-ollama"`
need the string updated to `"mast-mcp"`.
