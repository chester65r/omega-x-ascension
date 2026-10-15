import pytest
from pydantic import ValidationError

from omega.config import Settings, weak_secret_reason

GOOD_SECRET = "q7Zr2mVx9LbT4nKc8HdW1sPy6EjA3uFg5RoBt0Ni"
OTHER_SECRET = "Xv3Jp8LqW2mNr6Tb9Zc4HdK1sYf7GeA5UoPi0RtC"


def make_settings(**overrides):
    values = {
        "_env_file": None,
        "env": "production",
        "database_url": "postgresql+asyncpg://app:pass@localhost/omega",
        "checkpoint_database_url": "postgresql://checkpoint:pass@localhost/omega",
        "redis_url": "redis://localhost:6379/0",
        "jwt_secret": GOOD_SECRET,
    }
    values.update(overrides)
    return Settings(**values)


def test_production_accepts_random_secrets():
    settings = make_settings(sandbox_token=OTHER_SECRET)
    assert settings.env == "production"


@pytest.mark.parametrize(
    "secret",
    [
        "set-at-least-32-random-characters-here",  # shipped in .env.example
        "set-a-separate-random-32-character-token",
        "change-me-change-me-change-me-change-me",
        "a" * 40,
        "ab" * 20,
    ],
)
def test_production_rejects_placeholder_or_low_variety_jwt_secret(secret):
    with pytest.raises(ValidationError, match="OMEGA_JWT_SECRET"):
        make_settings(jwt_secret=secret)


def test_production_rejects_placeholder_sandbox_token():
    with pytest.raises(ValidationError, match="OMEGA_SANDBOX_TOKEN"):
        make_settings(sandbox_token="set-a-separate-random-32-character-token")


def test_production_rejects_reusing_jwt_secret_as_sandbox_token():
    with pytest.raises(ValidationError, match="must differ"):
        make_settings(sandbox_token=GOOD_SECRET)


@pytest.mark.parametrize("env", ["development", "test"])
def test_non_production_keeps_accepting_simple_secrets(env):
    assert make_settings(env=env, jwt_secret="x" * 40).env == env


def test_error_message_never_contains_the_secret():
    secret = "set-at-least-32-random-characters-here"
    with pytest.raises(ValidationError) as excinfo:
        make_settings(jwt_secret=secret)
    # The human-readable message must not echo the secret (pydantic's raw `input` field aside).
    assert secret not in excinfo.value.errors()[0]["msg"]


def test_good_secret_has_no_weakness_reason():
    assert weak_secret_reason(GOOD_SECRET) is None
