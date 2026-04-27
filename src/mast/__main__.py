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
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    logging.basicConfig(
        level=getattr(logging, config.mast_log_level.upper(), logging.INFO),
        stream=sys.stderr,
    )


async def _doctor() -> None:
    """Validate Ollama connectivity and model availability."""
    from mast.agents.base import OllamaClient

    client = OllamaClient()
    print("🩺 MAST Doctor", flush=True)
    print(f"  Ollama URL : {config.ollama_base_url}", flush=True)
    print(f"  Critic     : {config.critic_model}", flush=True)
    print(f"  Judge      : {config.judge_model}", flush=True)
    print(f"  Mode       : {config.mast_mode}", flush=True)
    print("", flush=True)

    models = await client.list_models()
    await client.aclose()

    if not models:
        print("❌ Cannot reach Ollama — is it running?", flush=True)
        sys.exit(1)

    print(f"✅ Ollama reachable. Available models ({len(models)}):", flush=True)
    for m in models:
        tag = ""
        if m == config.critic_model:
            tag = " ← CRITIC"
        elif m == config.judge_model:
            tag = " ← JUDGE"
        print(f"  • {m}{tag}", flush=True)

    missing: list[str] = []
    if config.critic_model not in models:
        missing.append(config.critic_model)
    if config.judge_model not in models:
        missing.append(config.judge_model)

    if missing:
        print("", flush=True)
        print("⚠️  Missing models. Pull them with:", flush=True)
        for m in missing:
            print(f"  ollama pull {m}", flush=True)
        sys.exit(1)
    else:
        print("", flush=True)
        print("✅ All required models present. Ready to run!", flush=True)


def main() -> None:
    _configure_logging()

    if len(sys.argv) > 1 and sys.argv[1] == "--doctor":
        asyncio.run(_doctor())
        return

    from mast.server import run_server
    run_server()  # FastMCP handles its own event loop


if __name__ == "__main__":
    main()
