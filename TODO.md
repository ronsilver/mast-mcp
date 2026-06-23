# TODO — MAST-MCP v0.3.0

> Estado post-implementación. Tareas completadas localmente (commits sin push).
> Solo T18 (distribución) queda pendiente como paso manual del usuario.

---

## Completado (27/28 tasks)

| ID | Task | Status |
|---|---|---|
| T0 | Decisión nombre `mast-mcp` (ADR) | ✅ |
| T1 | ADR provider abstraction | ✅ |
| T2 | Rename `mast-ollama` → `mast-mcp` | ✅ |
| T3 | ChatBackend protocol + `_json_utils` | ✅ |
| T4 | Provider registry + auto-detect | ✅ |
| T5 | Config refactor agnóstica + bedrock fields | ✅ |
| T5a | Config file (TOML/JSON) + `${VAR}` interpolation | ✅ |
| T6 | OpenAICompatBackend | ✅ |
| T7 | AnthropicBackend | ✅ |
| T8 | GeminiBackend | ✅ |
| T9 | BedrockBackend orchestración | ✅ |
| T9a | Bedrock dual-auth (iam + token) | ✅ |
| T10 | GitHubBackend | ✅ |
| T11 | OpenRouterBackend | ✅ |
| T12 | OllamaBackend refactor | ✅ |
| T13 | Inject provider into Orchestrator + 8 agentes | ✅ |
| T14 | Strategy registry + entry points | ✅ |
| T15 | Fix race condition (locals en vez de `self._*`) | ✅ |
| T16 | `--doctor` per-mode (9 modos + provider creds) | ✅ |
| T17 | E2E tests + coverage gate ≥70% | ✅ |
| T19 | Fix umbral Kalman (0.18) | ✅ |
| T20 | Fix retry Ollama nudge + latency | ✅ |
| T21 | Cache bypass stochastic (brainstorm, tot) | ✅ |
| T22 | ToT voter index explícito | ✅ |
| T23 | Cleanup `mast_debate` no-op | ✅ |
| T24 | CI hardening (matrix 3.12/3.13 + uv cache + cov + dependabot + CodeQL) | ✅ |
| T25 | Docs overhaul (README + CHANGELOG + `mast.toml.example` + ADRs) | ✅ |
| T26 | `MAST_STRATEGY_DIR` local loader | ✅ |

---

## Pendiente (manual — requiere push/publish del usuario)

### T18 — Distribution (PyPI + MCP Registry + Docker)

Pasos:

1. Tag `v0.3.0` y push → activa release workflow (a crear)
2. `server.json` con namespace `io.github.ronsilver/mast-mcp` para MCP Registry
3. `pyproject.toml` trusted publishing config (PyPI OIDC)
4. Docker multi-arch build+push a `ghcr.io/ronsilver/mast-mcp`

Acceptance criteria en [ROADMAP.md](ROADMAP.md) #1.

---

## Métricas finales

| Métrica | Valor |
|---|---|
| Tests passing | 343 |
| Coverage | 82% (gate ≥70%) |
| Backends | 7 (Ollama, OpenAI, Anthropic, Gemini, Bedrock, GitHub, OpenRouter) |
| Source files | 80+ |
| ADRs | 2 (naming, provider abstraction) |
| Ruff check | clean |
| Ruff format | clean |
| Mypy --strict | 0 issues |
| Markdown lint | clean |
