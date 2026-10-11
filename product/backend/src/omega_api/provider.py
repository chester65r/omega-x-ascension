from dataclasses import dataclass

import httpx
from pydantic import SecretStr

from omega_api.config import Settings


class ProviderError(RuntimeError):
    """A sanitized upstream model failure."""


class ProviderNotConfigured(ProviderError):
    pass


@dataclass(frozen=True)
class Completion:
    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class OpenAICompatibleProvider:
    """Minimal chat-completions adapter; provider credentials stay server-side."""

    def __init__(self, settings: Settings):
        self.base_url = settings.provider_base_url.rstrip('/')
        self.api_key = settings.provider_api_key.get_secret_value()
        self.model = settings.model
        self.timeout = settings.provider_timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    async def complete(self, messages: list[dict[str, str]]) -> Completion:
        if not self.configured:
            raise ProviderNotConfigured('The server model provider is not configured.')
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'https://omega-x-ascension.invalid',
            'X-Title': 'Omega X Ascension',
        }
        payload = {'model': self.model, 'messages': messages, 'max_tokens': 1200}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f'{self.base_url}/chat/completions', headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            choices = data.get('choices') or []
            content = choices[0].get('message', {}).get('content') if choices else None
            if not isinstance(content, str) or not content.strip():
                raise ProviderError('The model provider returned no text content.')
            usage = data.get('usage') or {}
            return Completion(
                content=content.strip(),
                model=str(data.get('model') or self.model),
                prompt_tokens=_valid_tokens(usage.get('prompt_tokens')),
                completion_tokens=_valid_tokens(usage.get('completion_tokens')),
            )
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            # Do not disclose upstream response bodies or credentials in client errors/logs.
            raise ProviderError('The model provider request failed. Please retry later.') from None


def _valid_tokens(value) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None
