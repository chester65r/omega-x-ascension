from __future__ import annotations

from urllib.parse import quote

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from omega.config import Capability, ProviderConfig, Settings
from omega.ports import ModelGateway

_ALL_CAPABILITIES: frozenset[Capability] = frozenset(
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


class OpenAICompatibleGateway:
    def __init__(self, config: ProviderConfig, client: httpx.AsyncClient):
        self._config = config
        self._client = client
        self.name = config.name
        self.capabilities = config.capabilities
        self.priority = config.priority

    async def healthy(self) -> bool:
        try:
            response = await self._client.get(
                f"{self._config.base_url.rstrip('/')}/models", headers=self._headers(), timeout=5
            )
            return response.is_success
        except httpx.HTTPError:
            return False

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._config.api_key.get_secret_value()}"}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(httpx.TransportError),
        reraise=True,
    )
    async def complete(self, *, system: str, prompt: str) -> str:
        payload: dict[str, object] = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        # New reasoning models (including GPT-6) reject temperature when their
        # reasoning effort is active; keep deterministic sampling on compatible
        # non-reasoning/OpenAI-compatible providers.
        model_id = self._config.model.strip().lower()
        reasoning_model = model_id.startswith(("gpt-6", "gpt-5.6", "gpt-5.5", "o1", "o3", "o4"))
        if not reasoning_model:
            payload["temperature"] = 0.1

        response = await self._client.post(
            f"{self._config.base_url.rstrip('/')}/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=self._config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return str(data["choices"][0]["message"]["content"])


class GeminiGateway:
    """Direct Gemini generateContent adapter; credentials stay in server-side headers."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        priority: int,
        timeout_seconds: float,
        client: httpx.AsyncClient,
    ):
        self._api_key = api_key
        self._model = model.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._client = client
        self.name = f"gemini-{self._model}"
        self.capabilities = _ALL_CAPABILITIES
        self.priority = priority

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self._api_key,
            "x-goog-api-client": "omega-x-ascension/0.8.3",
            "Content-Type": "application/json",
        }

    def _model_url(self, action: str = "") -> str:
        model = quote(self._model, safe="")
        suffix = f":{action}" if action else ""
        return f"{self._base_url}/models/{model}{suffix}"

    async def healthy(self) -> bool:
        try:
            response = await self._client.get(
                self._model_url(), headers=self._headers(), timeout=5
            )
            return response.is_success
        except httpx.HTTPError:
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=8),
        retry=retry_if_exception_type(httpx.TransportError),
        reraise=True,
    )
    async def complete(self, *, system: str, prompt: str) -> str:
        response = await self._client.post(
            self._model_url("generateContent"),
            headers=self._headers(),
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 4096},
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(
            str(part["text"]) for part in parts if isinstance(part, dict) and "text" in part
        )


class StaticRegistry:
    def __init__(self, gateways: list[ModelGateway]):
        self._gateways = gateways

    def all(self):
        return tuple(self._gateways)


def build_gateways(config: Settings, client: httpx.AsyncClient) -> list[ModelGateway]:
    """Build gateways identically for API and worker processes; never invent a fallback model."""
    gateways: list[ModelGateway] = []

    # When configured, Gemini is the first provider at the default priority. Raise or
    # lower OMEGA_GEMINI_PRIORITY to choose another provider without changing code.
    gemini_token = config.gemini_api_key
    if gemini_token is not None and gemini_token.get_secret_value().strip():
        gateways.append(
            GeminiGateway(
                api_key=gemini_token.get_secret_value(),
                model=config.gemini_model,
                base_url=config.gemini_base_url,
                priority=config.gemini_priority,
                timeout_seconds=config.gemini_timeout_seconds,
                client=client,
            )
        )

    providers = list(config.model_providers)
    openai_token = config.openai_api_key
    if openai_token is not None and openai_token.get_secret_value().strip():
        providers.append(
            ProviderConfig(
                name="openai-gpt-6-astra"
                if config.openai_model == "gpt-6-astra"
                else f"openai-{config.openai_model}",
                base_url=config.openai_base_url.rstrip("/"),
                api_key=openai_token,
                model=config.openai_model,
                capabilities=_ALL_CAPABILITIES,
                priority=config.openai_priority,
                timeout_seconds=config.openai_timeout_seconds,
            )
        )
    hf_token = config.hf_inference_token
    if hf_token is not None and hf_token.get_secret_value().strip():
        providers.append(
            ProviderConfig(
                name="huggingface-inference",
                base_url=config.hf_inference_base_url.rstrip("/"),
                api_key=hf_token,
                model=config.hf_inference_model,
                capabilities=_ALL_CAPABILITIES,
                priority=config.hf_inference_priority,
                timeout_seconds=90,
            )
        )
    gateways.extend(OpenAICompatibleGateway(provider, client) for provider in providers)
    return gateways
