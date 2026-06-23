"""Entry point: python -m mast or mast-server CLI command."""

from __future__ import annotations

import asyncio
import sys

import structlog

from mast.config import config


def _configure_logging() -> None:
    import logging

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, config.mast_log_level.upper(), logging.INFO),
            stream=sys.stderr,
        )


def _collect_configured_models() -> list[str]:
    """Return all configured model names for the active mode.

    Dispatches by `config.mast_mode` so each mode is checked against
    exactly the models it actually uses. Workflows union the models
    from every stage.
    """
    mode = config.mast_mode
    if mode == "passive":
        return []
    if mode in ("validate", "debate", "actor_critic"):
        return [config.critic_model, config.judge_model]
    if mode == "debono":
        models = [
            config.debono_blue_open_model,
            config.debono_white_model,
            config.debono_green_model,
            config.debono_yellow_model,
            config.debono_black_model,
        ]
        if not config.debono_skip_red:
            models.append(config.debono_red_model)
        models.append(config.debono_blue_close_model)
        return models
    if mode == "brainstorm":
        return list(config.brainstorm_models) + [config.brainstorm_synth_model]
    if mode == "tot":
        return list(config.tot_branch_models) + [config.tot_voter_model]
    if mode == "kalman":
        return list(config.kalman_scorer_models)
    if mode == "workflow":
        workflow_models: list[str] = []
        for stage in config.workflow_stages:
            original_mode = config.mast_mode
            try:
                object.__setattr__(config, "mast_mode", stage)
                workflow_models.extend(_collect_configured_models())
            finally:
                object.__setattr__(config, "mast_mode", original_mode)
        return workflow_models
    return []


def _print_model_list(models: list[str]) -> None:
    """Print available models with role tags."""
    print(f"✅ Reachable. Available models ({len(models)}):", flush=True)
    for m in models:
        tags: list[str] = []
        if m == config.critic_model:
            tags.append("CRITIC")
        if m == config.judge_model:
            tags.append("JUDGE")
        debono_models = {
            config.debono_blue_open_model,
            config.debono_white_model,
            config.debono_green_model,
            config.debono_yellow_model,
            config.debono_black_model,
        }
        if not config.debono_skip_red:
            debono_models.add(config.debono_red_model)
        debono_models.add(config.debono_blue_close_model)
        if m in debono_models:
            tags.append("DEBONO")
        if m in config.brainstorm_models:
            tags.append("BRAINSTORM")
        if m == config.brainstorm_synth_model:
            tags.append("BRAINSTORM-SYNTH")
        if m in config.tot_branch_models:
            tags.append("TOT-BRANCH")
        if m == config.tot_voter_model:
            tags.append("TOT-VOTER")
        if m in config.kalman_scorer_models:
            tags.append("KALMAN-SCORER")
        suffix = f" ← {' | '.join(tags)}" if tags else ""
        print(f"  • {m}{suffix}", flush=True)


async def _doctor() -> None:
    """Validate backend connectivity, credentials, and model availability."""
    from mast.agents.registry import get_backend

    client = get_backend(config.mast_provider)
    is_cloud = config.ollama_cloud_api_key is not None

    print("🩺 MAST-MCP Doctor", flush=True)
    print(f"  Provider    : {config.mast_provider}", flush=True)
    print(f"  Base URL    : {config.effective_base_url}", flush=True)
    print(f"  Mode        : {config.mast_mode}", flush=True)
    if config.mast_provider == "bedrock":
        print(
            f"  Auth method : {config.bedrock_auth_method}",
            flush=True,
        )
    print("", flush=True)

    # Pre-flight credential check for providers that need them.
    if config.mast_provider == "bedrock":
        if config.bedrock_auth_method == "token" and not config.bedrock_token:
            print("❌ BEDROCK_AUTH_METHOD=token requires BEDROCK_TOKEN.", flush=True)
            sys.exit(1)
        if config.bedrock_auth_method == "iam":
            import importlib.util

            spec = importlib.util.find_spec("boto3")
            if spec is None:
                print(
                    "❌ BEDROCK_AUTH_METHOD=iam requires boto3. "
                    "Install with `pip install mast-mcp[bedrock]`.",
                    flush=True,
                )
                sys.exit(1)
            print("  IAM auth: boto3 available ✓", flush=True)
    if config.mast_provider == "openai" and not config.openai_api_key:
        print("❌ OPENAI_API_KEY is required for provider=openai.", flush=True)
        sys.exit(1)
    if config.mast_provider == "anthropic" and not config.anthropic_api_key:
        print("❌ ANTHROPIC_API_KEY is required for provider=anthropic.", flush=True)
        sys.exit(1)
    if config.mast_provider == "gemini" and not config.gemini_api_key:
        print("❌ GEMINI_API_KEY is required for provider=gemini.", flush=True)
        sys.exit(1)
    if config.mast_provider == "github" and not config.github_token:
        print("❌ GITHUB_TOKEN is required for provider=github.", flush=True)
        sys.exit(1)
    if config.mast_provider == "openrouter" and not config.openrouter_api_key:
        print("❌ OPENROUTER_API_KEY is required for provider=openrouter.", flush=True)
        sys.exit(1)

    models = await client.list_models()
    await client.aclose()

    if not models:
        if config.mast_provider == "ollama" and is_cloud:
            print("❌ Cannot reach Ollama Cloud — check OLLAMA_BASE_URL and API key", flush=True)
        elif config.mast_provider == "ollama":
            print("❌ Cannot reach Ollama — is it running?", flush=True)
        else:
            print(
                f"❌ Cannot reach {config.mast_provider} — check credentials and connectivity",
                flush=True,
            )
        sys.exit(1)

    _print_model_list(models)

    configured = _collect_configured_models()
    if not configured:
        print(
            f"ℹ️  Mode {config.mast_mode!r} does not require any models.",
            flush=True,
        )
        print("✅ Ready to run!", flush=True)
        return
    missing = [m for m in set(configured) if m not in models]

    if missing:
        print("", flush=True)
        if is_cloud:
            print(
                "⚠️  Models not found on cloud. Check ollama.com/search?c=cloud:",
                flush=True,
            )
        else:
            print("⚠️  Missing models. Pull them with:", flush=True)
        for m in missing:
            print(f"  {m}", flush=True)
        sys.exit(1)
    print("", flush=True)
    print("✅ All required models available. Ready to run!", flush=True)


def main() -> None:
    _configure_logging()

    if len(sys.argv) > 1 and sys.argv[1] == "--doctor":
        asyncio.run(_doctor())
        return

    from mast.server import run_server

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
