from __future__ import annotations

import asyncio

import httpx
from pydantic import SecretStr

from omega.adapters.models import build_gateways
from omega.config import ProviderConfig, Settings


def make_settings(*, openrouter_key: str | None) -> Settings:
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
        openrouter_api_key=SecretStr(openrouter_key) if openrouter_key else None,
        openrouter_model="openrouter/free",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openai_api_key=SecretStr("legacy-openai-test-secret"),
        gemini_api_key=SecretStr("legacy-gemini-test-secret"),
        hf_inference_token=SecretStr("legacy-huggingface-test-secret"),
    )


def test_openrouter_key_switches_all_capabilities_to_the_single_free_router():
    config = make_settings(openrouter_key="test-openrouter-api-key")
    client = httpx.AsyncClient()
    try:
        gateways = build_gateways(config, client)
        assert len(gateways) == 1
        gateway = gateways[0]
        assert gateway.name == "openrouter-free-router"
        assert gateway.priority == 100
        assert gateway.capabilities == frozenset({
            "reasoning", "coding", "mathematics", "planning",
            "analysis", "summarization", "research",
        })
        assert gateway._config.base_url == "https://openrouter.ai/api/v1"
        assert gateway._config.model == "openrouter/free"
        assert gateway._config.api_key.get_secret_value() == "test-openrouter-api-key"
    finally:
        asyncio.run(client.aclose())


def test_legacy_provider_configuration_stays_available_before_openrouter_key_is_set():
    config = make_settings(openrouter_key=None)
    client = httpx.AsyncClient()
    try:
        gateways = build_gateways(config, client)
        assert {gateway.name for gateway in gateways} == {
            "legacy-custom",
            "openai-gpt-6.1-sol",
            "gemini-gemini-3.8-flash",
            "huggingface-inference",
        }
    finally:
        asyncio.run(client.aclose())
