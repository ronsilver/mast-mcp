# Reasoning Strategies

The MAST-MCP server supports seven reasoning strategies. The active strategy is
selected via the `MAST_MODE` environment variable.

---

## Strategy 1: Adversarial Debate (modes: `validate`, `debate`)

Tripartite architecture (Main LLM + Critic + Judge) designed to emulate an Adversarial Debate and improve sequential reasoning quality.

### Agent Topology

| Role | Location | Responsibility |
|---|---|---|
| **Propulsor (Main LLM)** | MCP (Model Context Protocol) Client (e.g. Claude Desktop, Cursor) | Generates the original thought (`thought`) and advances toward the solution. Makes the final decision. |
| **Critic** | Local Server (Ollama) | Reads the thought, evaluates its logical, technical, and security viability, and exposes flaws — relentless but constructive. |
| **Judge** | Local Server (Ollama) | Reads the original thought and the Critic's evaluation. Synthesizes a final verdict (`accept`, `revise`, `reject`) and, if needed, proposes a rewrite. |

### Critic Agent

The Critic is a **skeptical, analytical, and rigorous** agent. Its main goal is to find reasoning vulnerabilities in the Propulsor's thought before a decision is consolidated.

- **Recommended Model:** `mistral:7b-instruct` or `qwen2.5:7b-instruct` (models with strong instruction adherence and JSON schema support).
- **Input:** Recent thought history + Current thought.
- **Structured Output:**

```json
{
  "issues": [
    {
      "severity": "high",
      "type": "logic",
      "detail": "Description of the detected problem."
    }
  ],
  "strengths": ["Optional list of technical or logical merits in the step"],
  "summary": "General summary of thought quality"
}
```

#### Critic Prompt Guidelines

- **Injection Defense:** The analyzed thought is strictly treated as `DATA`
  (untrusted user input, never to be executed as instructions). Any attempt
  by the Propulsor to instruct the Critic ("ignore previous", "act as X")
  is ignored — unless the operator explicitly overrides this behavior.
- **Zero Verbosity:** The Critic does not suggest how to fix the problem, only that it exists.
- **No False Positives:** If the thought is flawless, the Critic returns an empty `issues` list.

### Judge Agent

The Judge is a **deliberative, impartial, and constructive** agent. It intervenes to prevent the Critic from blocking the flow over minor issues or nitpicks. It is the final arbiter of each step.

- **Recommended Model:** `deepseek-r1:8b` or `llama3.2:3b` (models with deep reasoning and synthesis capability).
- **Input:** History + Current thought + Raw Critic evaluation.
- **Structured Output:**

```json
{
  "verdict": "revise",
  "confidence": 0.85,
  "rationale": "The reasoning is sound but misses the error case mentioned by the critic.",
  "suggestedRevision": "Rewritten thought text addressing the observed shortcomings."
}
```

#### Judge Prompt Guidelines

- **Decision Making:** Assesses whether the Critic's findings merit changing course (`revise`/`reject`) or are trivial enough that the Propulsor should proceed (`accept`).
- **Self-Correction (`suggestedRevision`):** When verdict is `revise`, a corrected version of the thought should be provided.
- **Confidence Level (`confidence`):** Numerically evaluates (0.0 to 1.0) certainty in the verdict.

### Internal Debate Flow

The process happens in milliseconds, fully transparent to the MCP client.

1. **Reception:** Claude or Cursor invoke the `sequentialthinking` tool, emitting a reasoning step.
2. **Critical Evaluation:** `mast-server` calls Ollama with the Critic model to get its opinion.
3. **Deliberation:** Once the critique is obtained, `mast-server` calls the Judge, passing the context and the freshly generated critique.
4. **Verdict:** The Judge responds.
5. **Client Response:** The server returns a structured object (`structuredContent`) to the Propulsor with the verdict, critiques, and recommendation. The Propulsor reads this validation and decides whether to correct course (`isRevision=true`) or proceed.

#### Optimizations

- **Flexible Modes:**
  - `passive`: Skips both agents.
  - `validate`: Only invokes the Critic (saves tokens/time).
  - `debate`: Invokes Critic + Judge (higher quality, default).
  - `debono`: Invokes the 6 De Bono hats sequentially.
  - `actor_critic`: Iterative Critic+Judge loop (self-contained, no Propulsor involvement).
  - `brainstorm`: Parallel idea generators + Synthesizer.
  - `tot`: Parallel branch generators + Voter.
  - `kalman`: N scorers + Kalman filter fusion.
  - `workflow`: Chain multiple modes in sequence.
- **LRU Cache (Least Recently Used):** Previously evaluated identical thoughts are returned instantly from server memory to avoid redundant Ollama work.

---

## Strategy 2: De Bono Six Thinking Hats (mode: `debono`)

7-step sequential pipeline where each hat transforms a progressive working document. See the `src/mast/prompts/debono/` directory for the prompt templates.

| Step | Hat | Role | Default Model |
|---|---|---|---|
| 1 | Blue (Open) | Define problem, objective, initial working doc | `qwen2.5:3b` |
| 2 | White | Facts, data, unknowns | `qwen2.5:3b` |
| 3 | Green | Creative alternatives, lateral thinking | `qwen2.5:1.5b` |
| 4 | Yellow | Benefits, value, filter weak ideas | `qwen2.5:3b` |
| 5 | Black | Risks, mitigations, harden plan | `qwen2.5:3b` |
| 6 | Red | Gut feeling (brief, optional via `DEBONO_SKIP_RED`) | `qwen2.5:1.5b` |
| 7 | Blue (Close) | Synthesis, verdict, suggestedRevision | `qwen2.5:3b` |

Each hat has its own configurable environment variable. The pattern is `DEBONO_{HAT}_MODEL` where `{HAT}` is the uppercase hat name (e.g., `DEBONO_BLUE_OPEN_MODEL`, `DEBONO_RED_MODEL`). Red hat can be disabled entirely via `DEBONO_SKIP_RED=true`.

The pipeline executes sequentially: each hat receives the previous hat's `working_document` as input and returns a `modified_document` for the next step. The final Blue (Close) hat produces a verdict, confidence score, and optional suggested revision.

---

## Strategy 3: Actor-Critic Iterative Refinement (mode: `actor_critic`)

Extends the `debate` flow with an internal loop: the Judge's `suggested_revision` is
re-injected as a new thought for another round of criticism. The loop terminates when
the Critic finds no HIGH/MEDIUM issues or the round limit is reached.

| Step | Agent | Responsibility |
|---|---|---|
| 1 | Critic | Evaluate current thought, find issues |
| 2 | Judge (if issues found) | Generate suggested revision |
| 3 | Loop | Re-inject revision as new thought, repeat |

- **Max rounds:** Controlled by `ACTOR_CRITIC_MAX_ROUNDS` (default: 3)
- **Verdict:** `accept` when converged (no HIGH/MEDIUM issues), `revise` otherwise

The difference from `debate` is that `actor_critic` iterates internally without
involving the Propulsor in each round.

---

## Strategy 4: Brainstorm (mode: `brainstorm`)

Multiple Ollama models generate independent ideas in parallel (divergent phase).
A Synthesizer model merges them into Top-N proposals (convergent phase).

| Phase | Agent | Config |
|---|---|---|
| Divergent | N parallel generators | `BRAINSTORM_MODELS` (default: `llama3:8b,mistral:7b`) |
| Convergent | Synthesizer (single model) | `BRAINSTORM_SYNTH_MODEL` (default: `qwen2.5:14b`) |

- Generators use `temperature=0.85` for high creativity.
- Synthesizer uses `temperature=0.4` for focused merging.
- The result includes all ideas plus the synthesized `suggested_revision`.

---

## Strategy 5: Tree of Thoughts — Branch & Vote (mode: `tot`)

N models generate candidates for the "next reasoning step" (branches) in parallel.
A Voter scores each branch. The highest-scored branch is returned as `suggested_revision`.

| Phase | Agent | Config |
|---|---|---|
| Branch | N parallel generators | `TOT_BRANCH_MODELS` (default: `llama3:8b,mistral:7b,qwen2.5:7b`) |
| Vote | Voter (single model) | `TOT_VOTER_MODEL` (default: `deepseek-r1:8b`) |

- Branch generators use `temperature=0.75`.
- Voter uses `temperature=0.2` for deterministic scoring.
- Branches sorted by score descending; top branch is selected.

---

## Strategy 6: Kalman Convergence (mode: `kalman`)

N scorer models evaluate the thought with `{score, confidence}` pairs.
A Kalman Filter fuses these measurements optimally, weighting inversely to uncertainty.

### Interpretation

| Symbol | Meaning |
|---|---|
| `x` | Estimated thought quality ∈ [0,1] |
| `P` | Uncertainty in that estimate (high initially) |
| `z_i` | Score from scorer i ∈ [0,1] |
| `R_i` | `1 - confidence_i` (low R = high certainty) |
| `innovation` | `abs(z_i - x)` — divergence between scorers |

### Convergence

- When `P < KALMAN_P_THRESHOLD` (default: 0.05), estimate is reliable.
- If `x >= KALMAN_ACCEPT_THRESHOLD` (default: 0.70): verdict = `accept`
- Otherwise: verdict = `revise`

### Safety triggers

| Trigger | Meaning |
|---|---|
| `K1:high_divergence` | Scorers very inconsistent (P > 0.5) |
| `K2:covariance_collapse` | Numerical underflow (P tiny) |
| `K4:large_innovation` | One scorer strongly disagrees |
| `K5:no_new_information` | Repeated similar scores with high P |

| Scorer | Config |
|---|---|
| N parallel scorers | `KALMAN_SCORER_MODELS` (default: `mistral:7b,qwen2.5:7b,phi3:mini`) |

- Scorers use `temperature=0.1` for deterministic scoring.
- The Kalman filter uses Joseph form for numerical stability.

---

## Strategy 7: Workflow — Multi-Stage Pipelines (mode: `workflow`)

Chains multiple reasoning modes sequentially. Each stage processes the output
(`suggested_revision`, `final_thought`, or `synthesis`) of the previous stage.

### Configuration

The pipeline is defined by `MAST_WORKFLOW_STAGES` (comma-separated mode names).
Default: `debate,kalman`.

### Pre-defined workflows

| Name | `MAST_WORKFLOW_STAGES` | Use case |
|---|---|---|
| `deep-think` | `actor_critic,kalman` | Iterative refinement + final validation |
| `creative` | `brainstorm,actor_critic` | Idea generation + refinement |
| `overanalyze` | `brainstorm,actor_critic,tot,kalman` | Research / critical planning |
| `architecture` | `brainstorm,tot,actor_critic,kalman` | Design decisions with wide exploration |

A stage that errors does not halt the pipeline — it records the error and passes the
input thought unchanged to the next stage.

### MCP Config Example

```json
{
  "env": {
    "MAST_MODE": "workflow",
    "MAST_WORKFLOW_STAGES": "brainstorm,actor_critic,kalman",
    "BRAINSTORM_MODELS": "llama3:8b,mistral:7b",
    "BRAINSTORM_SYNTH_MODEL": "qwen2.5:14b",
    "CRITIC_MODEL": "mistral:7b-instruct",
    "JUDGE_MODEL": "deepseek-r1:8b",
    "ACTOR_CRITIC_MAX_ROUNDS": "3",
    "KALMAN_SCORER_MODELS": "mistral:7b,qwen2.5:7b,phi3:mini",
    "KALMAN_P_THRESHOLD": "0.08"
  }
}
```
