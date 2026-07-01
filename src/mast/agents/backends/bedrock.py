"""
Amazon Bedrock backend — dual auth (iam via boto3, or bearer token via httpx).

`auth_method=iam` requires `pip install mast-mcp[bedrock]` (installs boto3).
`auth_method=token` works without boto3 — uses httpx with bearer header.
"""

from __future__ import annotations

import asyncio
import json as _json
import time as _time
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from mast.agents._json_utils import extract_json
from mast.agents.protocols import ChatBackend, ChatResult
from mast.config import config

if TYPE_CHECKING:
    pass  # placeholder type hint only

log = structlog.get_logger(__name__)


def _is_anthropic_model(model: str) -> bool:
    return "anthropic" in model.lower() or "claude" in model.lower()


_BEDROCK_STATIC_MODELS = [
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "anthropic.claude-3-5-haiku-20241022-v1:0",
    "amazon.nova-pro-v1:0",
    "amazon.nova-lite-v1:0",
    "meta.llama3-1-70b-instruct-v1:0",
]


class BedrockBackend(ChatBackend):
    """Async client for Amazon Bedrock runtime."""

    def __init__(
        self,
        *,
        region: str | None = None,
        auth_method: str | None = None,
        token: str | None = None,
        default_model: str | None = None,
    ) -> None:
        """Initialize Bedrock backend with region, auth method, and token."""
        self._region = region or config.bedrock_region
        self._auth_method = auth_method or config.bedrock_auth_method
        self._token = token or config.bedrock_token
        self._default_model = default_model or "anthropic.claude-3-5-sonnet-20241022-v2:0"
        self._boto3_client: Any = None
        self._boto3_unavailable: bool = False
        self._http: httpx.AsyncClient | None = None

        self._init_auth()

    def _init_auth(self) -> None:
        if self._auth_method == "iam":
            try:
                import boto3  # type: ignore[import-not-found]

                profile = config.bedrock_profile
                session_kwargs: dict[str, Any] = {"region_name": self._region}
                if profile:
                    session_kwargs["profile_name"] = profile
                session = boto3.Session(**session_kwargs)
                self._boto3_client = session.client("bedrock-runtime", region_name=self._region)
            except ImportError:
                log.warning(
                    "bedrock_iam_requires_boto3",
                    hint="pip install mast-mcp[bedrock] or set BEDROCK_AUTH_METHOD=token",
                )
                self._boto3_unavailable = True
        elif self._auth_method == "token":
            base = f"https://bedrock-runtime.{self._region}.amazonaws.com"
            self._http = httpx.AsyncClient(base_url=base, timeout=config.mast_timeout_ms / 1000.0)
        else:
            raise ValueError(
                f"BEDROCK_AUTH_METHOD must be 'iam' or 'token', got {self._auth_method!r}"
            )

    def _bearer_headers(self) -> dict[str, str]:
        if not self._token:
            raise ValueError("BEDROCK_TOKEN is required when BEDROCK_AUTH_METHOD=token")
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _build_anthropic_payload(
        system_prompt: str,
        temperature: float,
        num_predict: int,
        json_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": num_predict,
            "temperature": temperature,
            "messages": [{"role": "user", "content": system_prompt}],
        }
        if json_schema is not None:
            body["tools"] = [
                {
                    "name": "respond",
                    "description": "Emit JSON matching the schema.",
                    "input_schema": json_schema,
                }
            ]
            body["tool_choice"] = {"type": "tool", "name": "respond"}
        return body

    async def _invoke_iam(
        self,
        model: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        if self._boto3_unavailable:
            raise RuntimeError(
                "Bedrock iam auth requires boto3. "
                "Install with `pip install mast-mcp[bedrock]` "
                "or set BEDROCK_AUTH_METHOD=token."
            )
        if self._boto3_client is None:
            raise RuntimeError("boto3 client not initialized")

        def _call() -> dict[str, Any]:
            response = self._boto3_client.invoke_model(
                modelId=model or self._default_model,
                contentType="application/json",
                accept="application/json",
                body=_json.dumps(body),
            )
            payload: dict[str, Any] = _json.loads(response["body"].read())
            return payload

        result = await asyncio.to_thread(_call)
        return result

    async def _invoke_token(
        self,
        model: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        if self._http is None:
            raise RuntimeError("HTTP client not initialized for token auth")
        url = f"/model/{model or self._default_model}/invoke"
        response = await self._http.post(url, json=body, headers=self._bearer_headers())
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    @staticmethod
    def _extract_anthropic_tool_input(raw: dict[str, Any]) -> dict[str, Any] | None:
        content = raw.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    inner = block.get("input")
                    if isinstance(inner, dict):
                        return inner
        return None

    async def chat(
        self,
        model: str,
        system_prompt: str,
        *,
        temperature: float = 0.2,
        num_predict: int = 512,
        fallback: dict[str, Any],
        json_schema: dict[str, Any] | None = None,
    ) -> ChatResult:
        m = model or self._default_model
        is_anthropic = _is_anthropic_model(m)
        body = self._build_bedrock_body(m, system_prompt, temperature, num_predict, json_schema)
        content, last_latency_ms = "", 0
        for attempt in range(2):
            t0 = _time.monotonic()
            try:
                raw = await self._invoke_bedrock(m, body)
                latency_ms = int((_time.monotonic() - t0) * 1000)
                last_latency_ms = latency_ms
                content = self._extract_bedrock_content(raw, is_anthropic, json_schema)
                if content:
                    parsed = self._try_parse(content)
                    if parsed is not None:
                        return parsed, latency_ms
            except (httpx.HTTPError, RuntimeError, KeyError, IndexError) as exc:
                log.error("bedrock_response_error", error=str(exc), model=m)
                return fallback, last_latency_ms
            if attempt == 0:
                continue
        log.warning("bedrock_validation_failed_using_fallback", model=m)
        return fallback, last_latency_ms

    def _try_parse(self, content: str) -> dict[str, Any] | None:
        try:
            result: dict[str, Any] = _json.loads(content)
            return result
        except _json.JSONDecodeError:
            return extract_json(content)

    def _build_bedrock_body(
        self,
        model: str,
        system_prompt: str,
        temperature: float,
        num_predict: int,
        json_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if _is_anthropic_model(model):
            return self._build_anthropic_payload(
                system_prompt, temperature, num_predict, json_schema
            )
        return {
            "inputText": system_prompt,
            "textGenerationConfig": {"temperature": temperature, "maxTokenCount": num_predict},
        }

    async def _invoke_bedrock(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        if self._auth_method == "iam":
            return await self._invoke_iam(model, body)
        return await self._invoke_token(model, body)

    def _extract_bedrock_content(
        self, raw: dict[str, Any], is_anthropic: bool, json_schema: dict[str, Any] | None
    ) -> str:
        if is_anthropic:
            return self._extract_anthropic_content(raw, json_schema)
        results = raw.get("results", [])
        return str(results[0].get("outputText", "")) if results else ""

    def _extract_anthropic_content(
        self, raw: dict[str, Any], json_schema: dict[str, Any] | None
    ) -> str:
        if json_schema is not None:
            parsed = self._extract_anthropic_tool_input(raw)
            if parsed is not None:
                return _json.dumps(parsed)
        return "\n".join(
            str(b.get("text", ""))
            for b in raw.get("content", [])
            if isinstance(b, dict) and b.get("type") == "text"
        )

    async def list_models(self) -> list[str]:
        """Use boto3 ListFoundationModels if available, else static catalog."""
        if self._boto3_unavailable or self._boto3_client is None:
            return [
                "anthropic.claude-3-5-sonnet-20241022-v2:0",
                "anthropic.claude-3-5-haiku-20241022-v1:0",
                "amazon.nova-pro-v1:0",
                "amazon.nova-lite-v1:0",
                "meta.llama3-1-70b-instruct-v1:0",
            ]
        try:

            def _call() -> list[str]:
                response = self._boto3_client.meta.client.list_foundation_models()
                return [m["modelId"] for m in response.get("modelSummaries", [])]

            return await asyncio.to_thread(_call)
        except Exception:  # noqa: BLE001
            return []

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
