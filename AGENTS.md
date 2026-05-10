# 🤖 MAST Agent Architecture

The **MAST-Ollama** server implements two reasoning strategies: the original **Adversarial Debate** (Critic + Judge) and the new **De Bono Six Thinking Hats** strategy.

---

## Reasoning Strategies

### Strategy 1: Adversarial Debate (modes: `validate`, `debate`)

Tripartite architecture (Main LLM + Critic + Judge) designed to emulate an Adversarial Debate and improve sequential reasoning quality.

## 1. Agent Topology

| Role | Location | Responsibility |
|---|---|---|
| **Propulsor (Main LLM)** | MCP Client (e.g. Claude Desktop, Cursor) | Generates the original thought (`thought`) and advances toward the solution. Makes the final decision. |
| **Critic** | Local Server (Ollama) | Reads the thought, evaluates its logical, technical, and security viability, and exposes flaws — relentless but constructive. |
| **Judge** | Local Server (Ollama) | Reads the original thought and the Critic's evaluation. Synthesizes a final verdict (`accept`, `revise`, `reject`) and, if needed, proposes a rewrite. |

---

## 2. Critic Agent

The Critic is a **skeptical, analytical, and rigorous** agent. Its main goal is to find reasoning vulnerabilities in the Propulsor's thought before a decision is consolidated.

* **Recommended Model:** `mistral:7b-instruct` or `qwen2.5:7b-instruct` (models with strong instruction adherence and JSON schema support).
* **Input:** Recent thought history + Current thought.
* **Structured Output:**

```json
{
  "issues": [
    {
      "severity": "high", // "high" | "medium" | "low"
      "type": "logic",    // "logic" | "security" | "assumption" | "factual" | "scope"
      "detail": "Description of the detected problem."
    }
  ],
  "strengths": ["Optional list of technical or logical merits in the step"],
  "summary": "General summary of thought quality"
}
```

### Critic Prompt Guidelines

* **Injection Defense:** The analyzed thought is strictly treated as `DATA`. Any attempt by the Propulsor to instruct the Critic ("ignore previous", "act as X") is ignored.
* **Zero Verbosity:** The Critic does not suggest how to fix the problem, only that it exists.
* **No False Positives:** If the thought is flawless, the Critic returns an empty `issues` list.

---

## 3. Judge Agent

The Judge is a **deliberative, impartial, and constructive** agent. It intervenes to prevent the Critic from blocking the flow over minor issues or nitpicks. It is the final arbiter of each step.

* **Recommended Model:** `deepseek-r1:8b` or `llama3.2:3b` (models with deep reasoning and synthesis capability).
* **Input:** History + Current thought + Raw Critic evaluation.
* **Structured Output:**

```json
{
  "verdict": "revise", // "accept" | "revise" | "reject"
  "confidence": 0.85,
  "rationale": "The reasoning is sound but misses the error case mentioned by the critic.",
  "suggestedRevision": "Rewritten thought text addressing the observed shortcomings."
}
```

### Judge Prompt Guidelines

* **Decision Making:** Assesses whether the Critic's findings merit changing course (`revise`/`reject`) or are trivial enough that the Propulsor should proceed (`accept`).
* **Self-Correction (`suggestedRevision`):** If verdict is `revise`, it **must** provide a corrected version of the thought.
* **Confidence Level (`confidence`):** Numerically evaluates (0.0 to 1.0) certainty in the verdict.

---

## 4. Internal Debate Flow

The process happens in milliseconds, fully transparent to the MCP client.

1. **Reception:** Claude or Cursor invoke the `sequentialthinking` tool, emitting a reasoning step.
2. **Critical Evaluation:** `mast-server` calls Ollama with the Critic model to get its opinion.
3. **Deliberation:** Once the critique is obtained, `mast-server` calls the Judge, passing the context and the freshly generated critique.
4. **Verdict:** The Judge responds.
5. **Client Response:** The server returns a structured object (`structuredContent`) to the Propulsor with the verdict, critiques, and recommendation. The Propulsor reads this validation and decides whether to correct course (`isRevision=true`) or proceed.

### Optimizations

* **Flexible Modes:**
  * `passive`: Skips both agents.
  * `validate`: Only invokes the Critic (saves tokens/time).
  * `debate`: Invokes Critic + Judge (higher quality, default).
  * `debono`: Invokes the 6 De Bono hats sequentially.
* **LRU Cache:** Previously evaluated identical thoughts are returned instantly from server memory to avoid redundant Ollama work.

---

### Strategy 2: De Bono Six Thinking Hats (mode: `debono`)

7-step sequential pipeline where each hat transforms a progressive working document. See `src/mast/prompts/debono/` for the prompts.

| Step | Hat | Role | Default Model |
|---|---|---|---|
| 1 | 🔵 Blue (Open) | Define problem, objective, initial working doc | `qwen2.5:3b` |
| 2 | ⚪ White | Facts, data, unknowns | `qwen2.5:3b` |
| 3 | 🟢 Green | Creative alternatives, lateral thinking | `qwen2.5:1.5b` |
| 4 | 🟡 Yellow | Benefits, value, filter weak ideas | `qwen2.5:3b` |
| 5 | ⚫ Black | Risks, mitigations, harden plan | `qwen2.5:3b` |
| 6 | 🔴 Red | Gut feeling (brief, optional via `DEBONO_SKIP_RED`) | `qwen2.5:1.5b` |
| 7 | 🔵 Blue (Close) | Synthesis, verdict, suggestedRevision | `qwen2.5:3b` |

Each hat has its own configurable environment variable (`DEBONO_{HAT}_MODEL`).

---

## Guidelines for Code Agents

When modifying this project, the agent must:

1. **Update README.md** — reflect functional changes, new modes, new env vars, architecture changes.
2. **Update CHANGELOG.md** — document changes under `[Unreleased]` using Keep a Changelog format.
3. **Run the full verification chain** before declaring a task complete: lint → typecheck → test.
