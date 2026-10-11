import asyncio

import httpx
from pydantic import SecretStr
import pytest

import omega_api.provider as provider_module
from omega_api.config import Settings
from omega_api.provider import OpenAICompatibleProvider, ProviderError


TEST_KEY = 'test-provider-secret-never-log'


def build_provider() -> OpenAICompatibleProvider:
    settings = Settings(
        environment='test',
        auto_create_schema=False,
        provider_base_url='https://api.example.test/v1',
        provider_api_key=SecretStr(TEST_KEY),
        model='test/model',
    )
    return OpenAICompatibleProvider(settings)


def install_transport(monkeypatch, handler):
    original_client = httpx.AsyncClient

    def make_client(*, timeout):
        return original_client(timeout=timeout, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(provider_module.httpx, 'AsyncClient', make_client)


def test_openai_compatible_request_and_usage_parsing(monkeypatch):
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url == 'https://api.example.test/v1/chat/completions'
        assert request.headers['authorization'] == f'Bearer {TEST_KEY}'
        body = __import__('json').loads(request.content)
        assert body['model'] == 'test/model'
        assert body['messages'][-1] == {'role': 'user', 'content': 'Hello'}
        return httpx.Response(200, json={
            'model': 'test/model-v2',
            'choices': [{'message': {'content': 'A genuine adapter response.'}}],
            'usage': {'prompt_tokens': 14, 'completion_tokens': 6},
        })

    install_transport(monkeypatch, handle)
    result = asyncio.run(build_provider().complete([{'role': 'user', 'content': 'Hello'}]))
    assert result.content == 'A genuine adapter response.'
    assert result.model == 'test/model-v2'
    assert (result.prompt_tokens, result.completion_tokens) == (14, 6)


def test_upstream_failure_is_sanitized(monkeypatch):
    install_transport(monkeypatch, lambda _request: httpx.Response(429, text='provider private error payload'))
    with pytest.raises(ProviderError) as error:
        asyncio.run(build_provider().complete([{'role': 'user', 'content': 'Hello'}]))
    assert str(error.value) == 'The model provider request failed. Please retry later.'
    assert TEST_KEY not in str(error.value)
    assert 'private error payload' not in str(error.value)


def test_missing_provider_key_does_not_make_network_request():
    settings = Settings(environment='test', auto_create_schema=False, provider_api_key=SecretStr(''))
    provider = OpenAICompatibleProvider(settings)
    assert not provider.configured
    with pytest.raises(ProviderError, match='not configured'):
        asyncio.run(provider.complete([{'role': 'user', 'content': 'Hello'}]))
