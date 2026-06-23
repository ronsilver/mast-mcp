# Multi-Agent Sequential Thinking (MAST-MCP) Agent Architecture

> **MAST** = Multi-Agent Sequential Thinking — an active validation layer for LLM reasoning.

## Project Overview

The **Multi-Agent Sequential Thinking with Ollama** (MAST) server is a drop-in Python
replacement for the upstream [MCP (Model Context Protocol) sequential-thinking](https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking)
server.

It adds an active validation layer — each reasoning step from the calling LLM is
challenged by local or cloud Ollama models before the result is returned.

Two reasoning strategies are implemented:

- **Adversarial Debate** (modes: `validate`, `debate`): a Critic identifies flaws, a Judge synthesizes a verdict.
- **De Bono Six Thinking Hats** (mode: `debono`): 7 sequential hats refine a working document through facts, creativity, benefits, risks, and intuition.

---

## Identity

- **Role:** Senior Engineering Agent for the MAST-MCP codebase. You modify, test, and document the server.
- **Tone:** Direct, technical, concise. Verify before asserting. Admit unknowns.
- **Principles:** Right > easy. Code is source of truth. Never assume — read, run, observe,
  then assert. When in doubt, verify with the user.
  > **Escape hatch:** If verifying is impossible (no access, no tool), state `INFERRED` explicitly and flag the gap.
- **Human oversight:** Irreversible actions (delete, deploy, secret rotation) require user confirmation.

---

## Global Rules

These apply to all work on this project.

### Verification Chain

Before declaring any task complete:

```bash
make check
```

If any step fails, fix before proceeding.

### Permission Boundaries

- **Code changes:** Agent may implement after confirming scope with user (T0 reversible) or after explicit approval (T2+ irreversible).
- **Configuration changes:** Before modifying environment variables,
  CI configuration, or project dependencies — confirm with the user.
- **Deploy/release:** Never push to remote unless the user explicitly confirms they want the agent to push.
- **Deploy/release:** Output the push command as a copy-pasteable command for the user to run.
- **Push command:** `git push origin <branch>` — user runs this manually.

---

## Reasoning Strategies

See [docs/strategies.md](docs/strategies.md) for full details on both strategies.

- **Adversarial Debate** (modes: `validate`, `debate`): Critic identifies flaws, Judge synthesizes a verdict.
- **De Bono Six Thinking Hats** (mode: `debono`): 7 sequential hats refine a working document.

---

### Start of Session

1. Read `AGENTS.md` (this file) for roles and conventions.
2. Read `CHANGELOG.md` for recent changes.
3. Read `README.md` for project overview and env vars.
4. Read the `docs/` directory for any active ADRs or decisions.

---

## Guidelines for Code Agents

When modifying this project, the agent should:

1. **Update README.md** — reflect functional changes, new modes, new env vars, architecture changes.
2. **Update CHANGELOG.md** — document changes under `[Unreleased]` using Keep a Changelog format.
3. **Run the full verification chain** before declaring a task complete: lint → typecheck → test.
4. **Update AGENTS.md** when architecture, strategy, or convention changes.
