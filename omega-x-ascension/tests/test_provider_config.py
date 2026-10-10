from pydantic import SecretStr
import httpx

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
    settings = make_settings()
    with httpx.AsyncClient() as client:
        assert build_gateways(settings, client) == []


def test_hugging_face_token_adds_qwen_gateway_with_all_agent_capabilities():
    settings = make_settings(hf_inference_token=SecretStr("hf_test_only_not_a_real_token"))
    with httpx.AsyncClient() as client:
        gateways = build_gateways(settings, client)

    assert len(gateways) == 1
    gateway = gateways[0]
    assert gateway.name == "huggingface-inference"
    assert gateway._config.base_url == "https://router.huggingface.co/v1"
    assert gateway._config.model == "Qwen/Qwen3-4B"
    assert gateway._config.api_key.get_secret_value() == "hf_test_only_not_a_real_token"
    assert gateway.capabilities == {
        "reasoning", "coding", "mathematics", "planning",
        "analysis", "summarization", "research",
    }
