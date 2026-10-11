from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=('.env', '../.env'),
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
        populate_by_name=True,
    )

    service_name: str = 'Omega X Ascension API'
    environment: str = Field(default='development', validation_alias='ENVIRONMENT')
    database_url: str = Field(default='sqlite+aiosqlite:///./omega.db', validation_alias='DATABASE_URL')
    jwt_secret: SecretStr = Field(
        default=SecretStr('local-development-secret-replace-before-deploy-2026'),
        validation_alias='JWT_SECRET',
    )
    access_token_ttl_seconds: int = Field(default=3600, ge=300, le=86400, validation_alias='ACCESS_TOKEN_TTL_SECONDS')
    auto_create_schema: bool = Field(default=True, validation_alias='AUTO_CREATE_SCHEMA')
    provider_base_url: str = Field(default='https://openrouter.ai/api/v1', validation_alias='OPENAI_COMPATIBLE_BASE_URL')
    provider_api_key: SecretStr = Field(default=SecretStr(''), validation_alias='OPENAI_COMPATIBLE_API_KEY')
    model: str = Field(default='', validation_alias='AI_MODEL')
    provider_timeout_seconds: float = Field(default=45.0, ge=1, le=120, validation_alias='PROVIDER_TIMEOUT_SECONDS')

    @model_validator(mode='after')
    def validate_production_secrets(self) -> 'Settings':
        if self.environment.lower() == 'production':
            secret = self.jwt_secret.get_secret_value()
            if len(secret) < 32 or secret.startswith(('local-development-', 'replace-with-')):
                raise ValueError('JWT_SECRET must be a unique secret of at least 32 characters in production')
            if self.auto_create_schema:
                raise ValueError('AUTO_CREATE_SCHEMA must be false in production; use Alembic migrations')
            if not self.provider_api_key.get_secret_value():
                raise ValueError('OPENAI_COMPATIBLE_API_KEY is required in production')
            if not self.database_url.startswith(('postgres://', 'postgresql://', 'postgresql+asyncpg://')):
                raise ValueError('DATABASE_URL must use PostgreSQL in production')
            if not self.provider_base_url.startswith('https://'):
                raise ValueError('OPENAI_COMPATIBLE_BASE_URL must use HTTPS in production')
        if not self.model.strip() and (self.environment.lower() == 'production' or self.provider_api_key.get_secret_value()):
            raise ValueError('AI_MODEL must name a model confirmed for the configured provider account')
        if not self.provider_base_url.startswith(('https://', 'http://')):
            raise ValueError('OPENAI_COMPATIBLE_BASE_URL must be an HTTP(S) URL')
        return self


def normalize_database_url(url: str) -> str:
    """Normalize PostgreSQL URLs for SQLAlchemy's asyncpg dialect."""
    if url.startswith('postgres://'):
        url = 'postgresql+asyncpg://' + url.removeprefix('postgres://')
    elif url.startswith('postgresql://'):
        url = 'postgresql+asyncpg://' + url.removeprefix('postgresql://')
    elif url.startswith('sqlite:///') and not url.startswith('sqlite+aiosqlite:///'):
        return 'sqlite+aiosqlite:///' + url.removeprefix('sqlite:///')

    if url.startswith('postgresql+asyncpg://'):
        parsed = make_url(url)
        query = dict(parsed.query)
        # asyncpg does not accept libpq's channel_binding or sslmode as connect kwargs.
        query.pop('channel_binding', None)
        sslmode = query.pop('sslmode', None)
        if sslmode is not None:
            query['ssl'] = sslmode
        return parsed.set(query=query).render_as_string(hide_password=False)
    return url
