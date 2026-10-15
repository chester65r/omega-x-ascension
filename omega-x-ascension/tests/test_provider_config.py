import asyncio

import httpx
from pydantic import SecretStr

from omega.adapters.models import build_gateways
from omega.config import Settings


def make_settings(**overrides):
    values = {
        "database_url": "postgresql+asyncpg://app:pass@localhost/omega",
        "checkpoint_database_url": "postgresql://checkpoint:pass@localhost/omega",
        "redis_url": "redis://localhost:6379/0",
        "jwt_secret": "x" * 40,
        "model_providers": [],
        "hf_inference_token": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_no_hugging_face_token_does_not_create_a_fake_provider():
    async def check():
        settings = make_settings()
        async with httpx.AsyncClient() as client:
            assert build_gateways(settings, client) == []

    asyncio.run(check())


def test_hugging_face_token_adds_qwen_gateway_with_all_agent_capabilities():
    async def check():
        settings = make_settings(hf_inference_token=SecretStr("hf_test_only_not_a_real_token"))
        async with httpx.AsyncClient() as client:
            gateways = build_gateways(settings, client)

        assert len(gateways) == 1
        gateway = gateways[0]
        assert gateway.name == "huggingface-inference"
        assert gateway._config.base_url == "https://router.huggingface.co/v1"
        assert gateway._config.model == "Qwen/Qwen3-4B:featherless-ai"
        assert gateway._config.api_key.get_secret_value() == "hf_test_only_not_a_real_token"
        assert gateway.capabilities == {
            "reasoning",
            "coding",
            "mathematics",
            "planning",
            "analysis",
            "summarization",
            "research",
        }

    asyncio.run(check())


def test_openai_flagship_gateway_uses_configured_secret():
    async def check():
        settings = make_settings(
            openai_api_key=SecretStr("sk-test-not-a-real-key"),
            openai_model="gpt-6-astra",
            openai_base_url="https://api.openai.com/v1",
        )
        async with httpx.AsyncClient() as client:
            gateways = build_gateways(settings, client)

        assert len(gateways) == 1
        gateway = gateways[0]
        assert gateway.name == "openai-gpt-6-astra"
        assert gateway._config.base_url == "https://api.openai.com/v1"
        assert gateway._config.model == "gpt-6-astra"
        assert gateway._config.api_key.get_secret_value() == "sk-test-not-a-real-key"
        assert gateway.priority == 100

    asyncio.run(check())


def test_blank_openai_key_does_not_create_a_fake_provider():
    async def check():
        settings = make_settings(openai_api_key=SecretStr("  "))
        async with httpx.AsyncClient() as client:
            assert build_gateways(settings, client) == []

    asyncio.run(check())



def test_optional_openrouter_deepseek_and_groq_gateways_use_only_server_side_secrets():
    async def check():
        settings = make_settings(
            openrouter_api_key=SecretStr("or-test-key"),
            openrouter_model="google/gemini-3.8-flash",
            openrouter_base_url="https://openrouter.ai/api/v1",
            openrouter_priority=90,
            deepseek_api_key=SecretStr("ds-test-key"),
            deepseek_model="deepseek-flash",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_priority=85,
            groq_api_key=SecretStr("gq-test-key"),
            groq_model="qwen/qwen3.8-27b",
            groq_base_url="https://api.groq.com/openai/v1",
            groq_priority=80,
        )
        async with httpx.AsyncClient() as client:
            gateways = build_gateways(settings, client)

        assert [gateway.name for gateway in gateways] == ["openrouter", "deepseek", "groq"]
        assert [gateway._config.base_url for gateway in gateways] == [
            "https://openrouter.ai/api/v1",
            "https://api.deepseek.com",
            "https://api.groq.com/openai/v1",
        ]
        assert [gateway._config.model for gateway in gateways] == [
            "google/gemini-3.8-flash",
            "deepseek-flash",
            "qwen/qwen3.8-27b",
        ]
        assert [gateway.priority for gateway in gateways] == [90, 85, 80]
        assert [gateway._config.api_key.get_secret_value() for gateway in gateways] == [
            "or-test-key", "ds-test-key", "gq-test-key"
        ]

    asyncio.run(check())


def test_blank_optional_provider_keys_do_not_create_fallback_gateways():
    async def check():
        settings = make_settings(
            openrouter_api_key=SecretStr(" "),
            deepseek_api_key=SecretStr(""),
            groq_api_key=None,
        )
        async with httpx.AsyncClient() as client:
            assert build_gateways(settings, client) == []

    asyncio.run(check())
