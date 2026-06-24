"""Entry point: python -m mast or mast-server CLI command."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable

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


_MODEL_COLLECTORS: dict[str, Callable[[], list[str]]] = {}


def _collect_configured_models() -> list[str]:
    """Return all configured model names for the active mode."""
    if not _MODEL_COLLECTORS:
        _init_model_collectors()
    mode = config.mast_mode
    collector = _MODEL_COLLECTORS.get(mode)
    if collector is not None:
        return collector()
    return []


def _init_model_collectors() -> None:
    _MODEL_COLLECTORS["passive"] = lambda: []
    _MODEL_COLLECTORS["validate"] = lambda: [config.critic_model, config.judge_model]
    _MODEL_COLLECTORS["debate"] = _MODEL_COLLECTORS["validate"]
    _MODEL_COLLECTORS["actor_critic"] = _MODEL_COLLECTORS["validate"]
    _MODEL_COLLECTORS["debono"] = _collect_debono_models
    _MODEL_COLLECTORS["brainstorm"] = lambda: (
        list(config.brainstorm_models) + [config.brainstorm_synth_model]
    )
    _MODEL_COLLECTORS["tot"] = lambda: list(config.tot_branch_models) + [config.tot_voter_model]
    _MODEL_COLLECTORS["kalman"] = lambda: list(config.kalman_scorer_models)
    _MODEL_COLLECTORS["workflow"] = _collect_workflow_models


def _collect_debono_models() -> list[str]:
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


def _collect_workflow_models() -> list[str]:
    workflow_models: list[str] = []
    for stage in config.workflow_stages:
        original_mode = config.mast_mode
        try:
            object.__setattr__(config, "mast_mode", stage)
            workflow_models.extend(_collect_configured_models())
        finally:
            object.__setattr__(config, "mast_mode", original_mode)
    return workflow_models


_TAG_RULES: list[tuple[Callable[[str], bool], str]] = []


def _make_set_check(s: set[str]) -> Callable[[str], bool]:
    return lambda m: m in s


def _init_tag_rules() -> None:
    _TAG_RULES.clear()
    _TAG_RULES.append((lambda m: m == config.critic_model, "CRITIC"))
    _TAG_RULES.append((lambda m: m == config.judge_model, "JUDGE"))
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
    _TAG_RULES.append((_make_set_check(debono_models), "DEBONO"))
    _TAG_RULES.append((lambda m: m in config.brainstorm_models, "BRAINSTORM"))
    _TAG_RULES.append((lambda m: m == config.brainstorm_synth_model, "BRAINSTORM-SYNTH"))
    _TAG_RULES.append((lambda m: m in config.tot_branch_models, "TOT-BRANCH"))
    _TAG_RULES.append((lambda m: m == config.tot_voter_model, "TOT-VOTER"))
    _TAG_RULES.append((lambda m: m in config.kalman_scorer_models, "KALMAN-SCORER"))


def _build_tags(m: str) -> list[str]:
    if not _TAG_RULES:
        _init_tag_rules()
    return [tag for predicate, tag in _TAG_RULES if predicate(m)]


def _print_model_list(models: list[str]) -> None:
    """Print available models with role tags."""
    print(f"✅ Reachable. Available models ({len(models)}):", flush=True)
    for m in models:
        tags = _build_tags(m)
        suffix = f" ← {' | '.join(tags)}" if tags else ""
        print(f"  • {m}{suffix}", flush=True)


_CREDENTIAL_CHECKS: dict[str, Callable[[], None]] = {}


def _check_bedrock_credentials() -> None:
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


def _check_simple_credential(provider: str, key: str, var: str) -> None:
    if not getattr(config, var, None):
        print(f"❌ {key.upper()} is required for provider={provider}.", flush=True)
        sys.exit(1)


def _init_credential_checks() -> None:
    _CREDENTIAL_CHECKS["bedrock"] = _check_bedrock_credentials
    _CREDENTIAL_CHECKS["openai"] = lambda: _check_simple_credential(
        "openai", "openai_api_key", "openai_api_key"
    )
    _CREDENTIAL_CHECKS["anthropic"] = lambda: _check_simple_credential(
        "anthropic", "anthropic_api_key", "anthropic_api_key"
    )
    _CREDENTIAL_CHECKS["gemini"] = lambda: _check_simple_credential(
        "gemini", "gemini_api_key", "gemini_api_key"
    )
    _CREDENTIAL_CHECKS["github"] = lambda: _check_simple_credential(
        "github", "github_token", "github_token"
    )
    _CREDENTIAL_CHECKS["openrouter"] = lambda: _check_simple_credential(
        "openrouter", "openrouter_api_key", "openrouter_api_key"
    )


def _check_credentials() -> None:
    """Pre-flight credential check for providers that need them."""
    if not _CREDENTIAL_CHECKS:
        _init_credential_checks()
    check = _CREDENTIAL_CHECKS.get(config.mast_provider)
    if check is not None:
        check()


def _print_no_models_error() -> None:
    is_cloud = config.ollama_cloud_api_key is not None
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


def _print_missing_models(missing: list[str]) -> None:
    is_cloud = config.ollama_cloud_api_key is not None
    print("", flush=True)
    if is_cloud:
        print("⚠️  Models not found on cloud. Check ollama.com/search?c=cloud:", flush=True)
    else:
        print("⚠️  Missing models. Pull them with:", flush=True)
    for m in missing:
        print(f"  {m}", flush=True)
    sys.exit(1)


def _check_models(models: list[str]) -> None:
    """Check model availability and print status."""
    if not models:
        _print_no_models_error()

    _print_model_list(models)

    configured = _collect_configured_models()
    if not configured:
        print(f"ℹ️  Mode {config.mast_mode!r} does not require any models.", flush=True)
        print("✅ Ready to run!", flush=True)
        return

    missing = [m for m in set(configured) if m not in models]
    if missing:
        _print_missing_models(missing)

    print("", flush=True)
    print("✅ All required models available. Ready to run!", flush=True)


def _print_doctor_header() -> None:
    print("🩺 MAST-MCP Doctor", flush=True)
    print(f"  Provider    : {config.mast_provider}", flush=True)
    print(f"  Base URL    : {config.effective_base_url}", flush=True)
    print(f"  Mode        : {config.mast_mode}", flush=True)
    if config.mast_provider == "bedrock":
        print(f"  Auth method : {config.bedrock_auth_method}", flush=True)
    print("", flush=True)


async def _doctor() -> None:
    """Validate backend connectivity, credentials, and model availability."""
    from mast.agents.registry import get_backend

    client = get_backend(config.mast_provider)
    _print_doctor_header()
    _check_credentials()
    models = await client.list_models()
    await client.aclose()
    _check_models(models)


def main() -> None:
    _configure_logging()

    if len(sys.argv) > 1 and sys.argv[1] == "--doctor":
        asyncio.run(_doctor())
        return

    from mast.server import run_server

    asyncio.run(run_server())


if __name__ == "__main__":
    main()
