from __future__ import annotations

from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Capability = Literal[
    "reasoning", "coding", "mathematics", "planning", "analysis", "summarization", "research"
]


class ProviderConfig(BaseModel):
    name: str
    base_url: str
    api_key: SecretStr
    model: str
    capabilities: frozenset[Capability]
    priority: int = Field(default=50, ge=0, le=100)
    timeout_seconds: float = Field(default=90, gt=0, le=600)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OMEGA_", env_file=".env", extra="ignore")
    env: Literal["development", "test", "production"] = "development"
    database_url: str
    checkpoint_database_url: str
    migration_database_url: str | None = None
    worker_database_url: str | None = None
    redis_url: str
    jwt_secret: SecretStr = Field(min_length=32)
    jwt_issuer: str = "omega-x"
    jwt_audience: str = "omega-x-api"
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    model_providers: list[ProviderConfig] = Field(default_factory=list)
    # Optional OpenAI flagship gateway; set the API key only in a deployment secret store.
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-6-astra"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_priority: int = Field(default=100, ge=0, le=100)
    openai_timeout_seconds: float = Field(default=180, gt=0, le=600)
    # Optional hosted inference: set a narrowly scoped Hugging Face token in the secret store.
    hf_inference_token: SecretStr | None = None
    hf_inference_model: str = "Qwen/Qwen3-4B:featherless-ai"
    hf_inference_base_url: str = "https://router.huggingface.co/v1"
    hf_inference_priority: int = Field(default=80, ge=0, le=100)
    log_level: str = "INFO"
    enable_computer_execution: bool = False
    enable_computer_files: bool = True
    sandbox_url: str = "http://sandbox:8090"
    sandbox_token: SecretStr | None = None

    # Webhooks & External Notifications
    github_webhook_secret: SecretStr | None = None
    webhook_tenant_id: UUID = Field(
        default_factory=lambda: UUID("00000000-0000-0000-0000-000000000001")
    )
    slack_webhook_url: SecretStr | None = None
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    notifications_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
