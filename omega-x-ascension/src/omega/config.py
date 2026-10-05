from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Capability = Literal["reasoning", "coding", "mathematics", "planning", "analysis", "summarization", "research"]


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
    log_level: str = "INFO"
    enable_computer_execution: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
