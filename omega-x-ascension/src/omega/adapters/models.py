from __future__ import annotations
import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from omega.config import Capability, ProviderConfig, Settings

class OpenAICompatibleGateway:
    def __init__(self, config: ProviderConfig, client: httpx.AsyncClient):
        self._config=config; self._client=client
        self.name=config.name; self.capabilities=config.capabilities; self.priority=config.priority
    async def healthy(self) -> bool:
        try:
            response=await self._client.get(f"{self._config.base_url.rstrip('/')}/models", headers=self._headers(), timeout=5)
            return response.is_success
        except httpx.HTTPError:
            return False
    def _headers(self) -> dict[str,str]: return {"Authorization":f"Bearer {self._config.api_key.get_secret_value()}"}
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1,max=8), retry=retry_if_exception_type(httpx.TransportError), reraise=True)
    async def complete(self, *, system: str, prompt: str) -> str:
        response=await self._client.post(f"{self._config.base_url.rstrip('/')}/chat/completions", headers=self._headers(), json={"model":self._config.model,"messages":[{"role":"system","content":system},{"role":"user","content":prompt}],"temperature":0.1}, timeout=self._config.timeout_seconds)
        response.raise_for_status()
        data=response.json()
        return str(data["choices"][0]["message"]["content"])

class StaticRegistry:
    def __init__(self, gateways: list[OpenAICompatibleGateway]): self._gateways=gateways
    def all(self): return tuple(self._gateways)



def build_gateways(config: Settings, client: httpx.AsyncClient) -> list[OpenAICompatibleGateway]:
    """Build gateways identically for API and worker processes; never invent a fallback model."""
    providers = list(config.model_providers)
    openai_token = config.openai_api_key
    if openai_token is not None and openai_token.get_secret_value().strip():
        providers.append(
            ProviderConfig(
                name="openai-gpt-6-astra" if config.openai_model == "gpt-6-astra" else f"openai-{config.openai_model}",
                base_url=config.openai_base_url.rstrip("/"),
                api_key=openai_token,
                model=config.openai_model,
                capabilities=frozenset({
                    "reasoning", "coding", "mathematics", "planning",
                    "analysis", "summarization", "research",
                }),
                priority=config.openai_priority,
                timeout_seconds=config.openai_timeout_seconds,
            )
        )
    token = config.hf_inference_token
    if token is not None and token.get_secret_value().strip():
        providers.append(
            ProviderConfig(
                name="huggingface-inference",
                base_url=config.hf_inference_base_url.rstrip("/"),
                api_key=token,
                model=config.hf_inference_model,
                capabilities=frozenset({
                    "reasoning", "coding", "mathematics", "planning",
                    "analysis", "summarization", "research",
                }),
                priority=config.hf_inference_priority,
                timeout_seconds=90,
            )
        )
    return [OpenAICompatibleGateway(provider, client) for provider in providers]
