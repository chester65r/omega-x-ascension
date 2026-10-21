from __future__ import annotations

import asyncio

import httpx
from pydantic import SecretStr

from omega.adapters.models import build_gateways
from omega.config import ProviderConfig, Settings


def make_settings(*, hf_token: str | None, openrouter_token: str | None = None) -> Settings:
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
        gemini_api_key=SecretStr("legacy-gemini-test-secret"),
    )


def test_huggingface_token_switches_all_model_calls_to_one_gateway():
    config = make_settings(hf_token="test-huggingface-inference-token")
    client = httpx.AsyncClient()
    try:
        gateways = build_gateways(config, client)
        assert len(gateways) == 1
        gateway = gateways[0]
        assert gateway.name == "huggingface-inference-primary"
        assert gateway.priority == 100
        assert gateway.capabilities == frozenset({
            "reasoning", "coding", "mathematics", "planning",
            "analysis", "summarization", "research",
        })
        assert gateway._config.base_url == "https://router.huggingface.co/v1"
        assert gateway._config.model == "Qwen/Qwen2.5-1.5B-Instruct:cheapest"
        assert gateway._config.api_key.get_secret_value() == "test-huggingface-inference-token"
    finally:
        asyncio.run(client.aclose())


def test_legacy_provider_configuration_stays_available_until_primary_token_is_set():
    config = make_settings(hf_token=None)
    client = httpx.AsyncClient()
    try:
        gateways = build_gateways(config, client)
        assert {gateway.name for gateway in gateways} == {
            "legacy-custom",
            "openai-gpt-6.1-sol",
            "gemini-gemini-3.8-flash",
        }
    finally:
        asyncio.run(client.aclose())


def test_openrouter_token_takes_precedence_over_other_model_gateways():
    config = make_settings(hf_token="test-huggingface-token", openrouter_token="test-openrouter-token")
    client = httpx.AsyncClient()
    try:
        gateways = build_gateways(config, client)
        assert len(gateways) == 1
        gateway = gateways[0]
        assert gateway.name == "openrouter-primary"
        assert gateway.priority == 100
        assert gateway._config.base_url == "https://openrouter.ai/api/v1"
        assert gateway._config.model == "meta-llama/llama-3.3-70b-instruct:free"
        assert gateway._config.api_key.get_secret_value() == "test-openrouter-token"
    finally:
        asyncio.run(client.aclose())
