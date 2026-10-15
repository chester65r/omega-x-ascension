from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Capability = Literal[
    "reasoning", "coding", "mathematics", "planning", "analysis", "summarization", "research"
]

_PLACEHOLDER_PREFIXES = ("set-", "your-")
_PLACEHOLDER_MARKERS = ("change-me", "changeme", "replace-me", "placeholder", "do-not")


def weak_secret_reason(value: str) -> str | None:
    """Return why a secret is unsafe for production, or None if it looks acceptable."""
    lowered = value.lower()
    if lowered.startswith(_PLACEHOLDER_PREFIXES) or any(m in lowered for m in _PLACEHOLDER_MARKERS):
        return "looks like a placeholder copied from an example file"
    if len(set(value)) < 10:
        return "has too little variety to be a random secret"
    return None


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

    @model_validator(mode="after")
    def _reject_unsafe_production_secrets(self) -> Settings:
        if self.env != "production":
            return self
        secrets = {"OMEGA_JWT_SECRET": self.jwt_secret.get_secret_value()}
        if self.sandbox_token is not None:
            secrets["OMEGA_SANDBOX_TOKEN"] = self.sandbox_token.get_secret_value()
        for name, value in secrets.items():
            reason = weak_secret_reason(value)
            if reason:
                raise ValueError(
                    f"{name} {reason}; generate real secrets with scripts/generate_env.py"
                )
        if len(secrets) == 2 and secrets["OMEGA_SANDBOX_TOKEN"] == secrets["OMEGA_JWT_SECRET"]:
            raise ValueError("OMEGA_SANDBOX_TOKEN must differ from OMEGA_JWT_SECRET")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
