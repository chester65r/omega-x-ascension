import asyncio
import json

import httpx
from pydantic import SecretStr

from omega.adapters.models import GeminiGateway, build_gateways
from omega.config import Settings


def _gateway(client: httpx.AsyncClient) -> GeminiGateway:
    return GeminiGateway(
        api_key="test-gemini-key",
        model="gemini-3.8-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        priority=100,
        timeout_seconds=10,
        client=client,
    )


def test_gemini_gateway_sends_key_in_header_and_parses_response():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "Gemini "}, {"text": "works."}]}}]
            },
        )

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            gateway = _gateway(client)
            result = await gateway.complete(system="Be accurate", prompt="Test")
        assert result == "Gemini works."
        assert seen["key"] == "test-gemini-key"
        assert "key=" not in seen["url"]
        assert seen["url"].endswith("/models/gemini-3.8-flash:generateContent")
        assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "Be accurate"
        assert seen["body"]["contents"][0]["parts"][0]["text"] == "Test"

    asyncio.run(check())


def test_gemini_gateway_health_uses_model_endpoint_and_key_header():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path.endswith("/models/gemini-3.8-flash")
        assert request.headers.get("x-goog-api-key") == "test-gemini-key"
        return httpx.Response(200, json={"name": "models/gemini-3.8-flash"})

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await _gateway(client).healthy() is True

    asyncio.run(check())


def test_build_gateways_adds_gemini_only_when_secret_is_configured():
    async def check():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
        ) as client:
            configured = Settings.model_construct(
                model_providers=[],
                gemini_api_key=SecretStr("configured-test-key"),
                gemini_model="gemini-3.8-flash",
                gemini_base_url="https://generativelanguage.googleapis.com/v1beta",
                gemini_priority=100,
                gemini_timeout_seconds=30,
                openai_api_key=None,
                hf_inference_token=None,
            )
            gateways = build_gateways(configured, client)
            assert len(gateways) == 1
            assert gateways[0].name == "gemini-gemini-3.8-flash"
            assert gateways[0].priority == 100

            unconfigured = Settings.model_construct(
                model_providers=[],
                gemini_api_key=None,
                openai_api_key=None,
                hf_inference_token=None,
            )
            assert build_gateways(unconfigured, client) == []

    asyncio.run(check())
