from __future__ import annotations

import asyncio

import httpx
from pydantic import SecretStr

from omega.adapters.models import build_gateways
from omega.config import ProviderConfig, Settings


def make_settings(
    *,
    hf_token: str | None,
    openrouter_token: str | None = None,
    enable_paid_model_fallback: bool = False,
) -> Settings:
    legacy_provider = ProviderConfig(
        name="legacy-custom",
        base_url="https://legacy.example/v1",
        api_key=SecretStr("legacy-custom-test-secret"),
        model="legacy-model",
        capabilities=frozenset({"planning"}),
        priority=10,
    )
    return Settings(
        env="test",
        database_url="postgresql+asyncpg://omega:test@localhost/omega",
        checkpoint_database_url="postgresql://omega:test@localhost/omega",
        redis_url="redis://localhost:6379/0",
        jwt_secret=SecretStr("test-only-jwt-secret-with-enough-entropy-123456"),
        model_providers=[legacy_provider],
        hf_inference_token=SecretStr(hf_token) if hf_token else None,
        openrouter_api_key=SecretStr(openrouter_token) if openrouter_token else None,
        openrouter_model="meta-llama/llama-3.3-70b-instruct:free",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openrouter_priority=100,
        hf_inference_model="Qwen/Qwen2.5-1.5B-Instruct:cheapest",
        hf_inference_base_url="https://router.huggingface.co/v1",
        hf_inference_priority=100,
        openai_api_key=SecretStr("legacy-openai-test-secret"),
        enable_paid_model_fallback=enable_paid_model_fallback,
        gemini_api_key=SecretStr("legacy-gemini-test-secret"),
    )


def test_gemini_is_first_and_huggingface_remains_a_fallback():
    config = make_settings(hf_token="test-huggingface-inference-token")
    client = httpx.AsyncClient()
    try:
        gateways = build_gateways(config, client)
        assert [gateway.name for gateway in gateways] == [
            "gemini-gemini-3.8-flash",
            "huggingface-inference-primary",
            "legacy-custom",
        ]
        assert gateways[0].priority == gateways[1].priority == 100
        hf_gateway = gateways[1]
        assert hf_gateway.capabilities == frozenset(
            {
                "reasoning",
                "coding",
                "mathematics",
                "planning",
                "analysis",
                "summarization",
                "research",
            }
        )
        assert hf_gateway._config.base_url == "https://router.huggingface.co/v1"
        assert hf_gateway._config.model == "Qwen/Qwen2.5-1.5B-Instruct:cheapest"
        assert hf_gateway._config.api_key.get_secret_value() == "test-huggingface-inference-token"
        assert not any(gateway.name.startswith("openai-") for gateway in gateways)
    finally:
        asyncio.run(client.aclose())


def test_gemini_and_explicit_legacy_provider_are_available():
    config = make_settings(hf_token=None)
    client = httpx.AsyncClient()
    try:
        gateways = build_gateways(config, client)
        assert [gateway.name for gateway in gateways] == [
            "gemini-gemini-3.8-flash",
            "legacy-custom",
        ]
        # A paid provider key alone must not silently enable billable fallback traffic.
        assert not any(gateway.name.startswith("openai-") for gateway in gateways)
    finally:
        asyncio.run(client.aclose())


def test_gemini_precedes_openrouter_and_huggingface_at_equal_priority():
    config = make_settings(
        hf_token="test-huggingface-token", openrouter_token="test-openrouter-token"
    )
    client = httpx.AsyncClient()
    try:
        gateways = build_gateways(config, client)
        assert [gateway.name for gateway in gateways] == [
            "gemini-gemini-3.8-flash",
            "openrouter-primary",
            "huggingface-inference-primary",
            "legacy-custom",
        ]
        assert [gateway.priority for gateway in gateways[:3]] == [100, 100, 100]
        openrouter_gateway = gateways[1]
        assert openrouter_gateway._config.base_url == "https://openrouter.ai/api/v1"
        assert openrouter_gateway._config.model == "meta-llama/llama-3.3-70b-instruct:free"
        assert openrouter_gateway._config.api_key.get_secret_value() == "test-openrouter-token"
    finally:
        asyncio.run(client.aclose())


def test_paid_openai_fallback_requires_explicit_opt_in():
    config = make_settings(
        hf_token=None,
        enable_paid_model_fallback=True,
    )
    client = httpx.AsyncClient()
    try:
        gateways = build_gateways(config, client)
        assert "openai-gpt-6.1-sol" in {gateway.name for gateway in gateways}
    finally:
        asyncio.run(client.aclose())
