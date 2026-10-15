import asyncio
import json

import httpx
from pydantic import SecretStr

from omega.adapters.models import OpenAICompatibleGateway
from omega.config import ProviderConfig


def _gateway(model: str, client: httpx.AsyncClient) -> OpenAICompatibleGateway:
    return OpenAICompatibleGateway(
        ProviderConfig(
            name=f"test-{model}",
            base_url="https://api.example.test/v1",
            api_key=SecretStr("test-key-not-a-real-secret"),
            model=model,
            capabilities=frozenset({"reasoning"}),
            priority=100,
            timeout_seconds=10,
        ),
        client,
    )


def test_reasoning_model_request_omits_unsupported_temperature():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        assert request.headers.get("Authorization") == "Bearer test-key-not-a-real-secret"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OpenAI gateway works."}}]},
        )

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await _gateway("gpt-6.1-sol", client).complete(
                system="Be accurate",
                prompt="Return a short test response.",
            )
        assert result == "OpenAI gateway works."
        assert seen["url"] == "https://api.example.test/v1/chat/completions"
        assert seen["body"]["model"] == "gpt-6.1-sol"
        assert seen["body"]["messages"] == [
            {"role": "system", "content": "Be accurate"},
            {"role": "user", "content": "Return a short test response."},
        ]
        assert "temperature" not in seen["body"]

    asyncio.run(check())


def test_non_reasoning_compatible_provider_keeps_low_temperature():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Compatible gateway works."}}]},
        )

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await _gateway("Qwen/Qwen3-4B:featherless-ai", client).complete(
                system="Be accurate",
                prompt="Return a short test response.",
            )
        assert result == "Compatible gateway works."
        assert seen["body"]["temperature"] == 0.1

    asyncio.run(check())
