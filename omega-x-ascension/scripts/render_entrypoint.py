from __future__ import annotations

"""Render entry point for the OMEGA-X API container.

On Render, configure database references in render.yaml. This entrypoint runs
idempotent role/schema migrations, switches runtime URLs to least-privilege
PostgreSQL roles, and binds Uvicorn to Render's assigned PORT.
"""

import os
import subprocess
import sys
from urllib.parse import quote, urlsplit, urlunsplit


def _normalise_owner_dsn(value: str) -> str:
    """Convert Render's postgres:// URL to SQLAlchemy's synchronous psycopg URL."""
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise SystemExit("OMEGA_MIGRATION_DATABASE_URL must be a PostgreSQL connection URL")
    if not parsed.hostname or not parsed.path:
        raise SystemExit("OMEGA_MIGRATION_DATABASE_URL must include a host and database name")
    return urlunsplit(
        ("postgresql+psycopg", parsed.netloc, parsed.path, parsed.query, "")
    )


def _role_dsn(owner_dsn: str, role: str, password: str, scheme: str) -> str:
    """Build a role-specific URL without leaking credentials into logs."""
    parsed = urlsplit(owner_dsn)
    host = parsed.hostname
    if not host or not parsed.path:
        raise SystemExit("PostgreSQL owner URL is missing its host or database name")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{quote(role, safe='')}:{quote(password, safe='')}@{host}"
    if parsed.port is not None:
        netloc += f":{parsed.port}"
    return urlunsplit((scheme, netloc, parsed.path, parsed.query, ""))


def _configure_database() -> None:
    """Provision roles and apply migrations before starting the API if enabled."""
    if os.environ.get("OMEGA_BOOTSTRAP_DATABASE", "").strip().lower() != "true":
        return

    owner_dsn = _normalise_owner_dsn(os.environ.get("OMEGA_MIGRATION_DATABASE_URL", ""))
    passwords = {
        "OMEGA_APP_PASSWORD": os.environ.get("OMEGA_APP_PASSWORD", ""),
        "OMEGA_WORKER_PASSWORD": os.environ.get("OMEGA_WORKER_PASSWORD", ""),
        "OMEGA_CHECKPOINT_PASSWORD": os.environ.get("OMEGA_CHECKPOINT_PASSWORD", ""),
    }
    for key, value in passwords.items():
        if not value or len(value) < 32:
            raise SystemExit(f"{key} must be set to a strong, server-side secret")

    # migrate.py creates separate no-bypass-RLS roles and applies the schema.
    os.environ["OMEGA_MIGRATION_DATABASE_URL"] = owner_dsn
    print("OMEGA-X: applying idempotent database migrations")
    subprocess.run([sys.executable, "scripts/migrate.py"], check=True)

    os.environ["OMEGA_DATABASE_URL"] = _role_dsn(
        owner_dsn, "omega_app", passwords["OMEGA_APP_PASSWORD"], "postgresql+psycopg"
    )
    os.environ["OMEGA_WORKER_DATABASE_URL"] = _role_dsn(
        owner_dsn, "omega_worker", passwords["OMEGA_WORKER_PASSWORD"], "postgresql+psycopg"
    )
    os.environ["OMEGA_CHECKPOINT_DATABASE_URL"] = _role_dsn(
        owner_dsn, "omega_checkpoint", passwords["OMEGA_CHECKPOINT_PASSWORD"], "postgresql"
    )

    # Keep owner credentials and role passwords out of the long-running API environment.
    for key in (
        "OMEGA_MIGRATION_DATABASE_URL",
        "OMEGA_APP_PASSWORD",
        "OMEGA_WORKER_PASSWORD",
        "OMEGA_CHECKPOINT_PASSWORD",
    ):
        os.environ.pop(key, None)


def _configure_sandbox_url() -> None:
    """Use the sandbox's assigned public hostname; its command endpoint stays disabled."""
    host = os.environ.get("OMEGA_SANDBOX_HOST", "").strip()
    if host:
        host = host.removeprefix("https://").removeprefix("http://").strip("/")
        if host:
            os.environ["OMEGA_SANDBOX_URL"] = f"https://{host}"


def main() -> None:
    _configure_database()
    _configure_sandbox_url()

    raw_port = os.environ.get("PORT", "8000")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("PORT must be an integer between 1 and 65535") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be an integer between 1 and 65535")

    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "omega.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--proxy-headers",
        ],
    )


if __name__ == "__main__":
    main()
