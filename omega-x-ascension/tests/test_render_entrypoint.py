from __future__ import annotations

from scripts.render_entrypoint import _normalise_owner_dsn, _role_dsn


def test_normalise_owner_dsn_preserves_encoded_credentials_and_query() -> None:
    value = "postgres://owner:p%40ss@db.example:5432/omega?sslmode=require"
    assert _normalise_owner_dsn(value) == (
        "postgresql+psycopg://owner:p%40ss@db.example:5432/omega?sslmode=require"
    )


def test_role_dsn_uses_separate_encoded_credentials() -> None:
    owner = "postgresql+psycopg://owner:owner-secret@db.example:5432/omega?sslmode=require"
    assert _role_dsn(owner, "omega_app", "slash/password+value", "postgresql+psycopg") == (
        "postgresql+psycopg://omega_app:slash%2Fpassword%2Bvalue@db.example:5432/omega"
        "?sslmode=require"
    )


def test_role_dsn_supports_ipv6_hosts() -> None:
    owner = "postgresql+psycopg://owner:secret@[2001:db8::5]:5432/omega"
    assert _role_dsn(owner, "omega_worker", "worker-secret", "postgresql+psycopg") == (
        "postgresql+psycopg://omega_worker:worker-secret@[2001:db8::5]:5432/omega"
    )
