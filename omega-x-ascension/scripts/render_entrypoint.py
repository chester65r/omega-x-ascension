from __future__ import annotations

import os
from urllib.parse import quote, urlsplit, urlunsplit


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required Render setting is missing: {name}")
    return value


def database_url(user: str, password: str, driver: str) -> str:
    return (
        f"{driver}://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{required('OMEGA_DB_HOST')}:{required('OMEGA_DB_PORT')}/"
        f"{quote(required('OMEGA_DB_NAME'), safe='')}"
    )


def migration_database_url() -> str:
    # Prefer Render's secret-backed Postgres connection-string reference. This
    # avoids depending on separately synchronized user/password environment vars.
    connection = os.environ.get("OMEGA_DB_ADMIN_URL", "").strip()
    if connection:
        parsed = urlsplit(connection)
        if (
            parsed.scheme not in {"postgres", "postgresql"}
            or not parsed.hostname
            or not parsed.username
            or parsed.password is None
            or not parsed.path.strip("/")
        ):
            raise RuntimeError(
                "OMEGA_DB_ADMIN_URL must be a valid Render PostgreSQL connection URL"
            )
        return urlunsplit(
            ("postgresql+psycopg", parsed.netloc, parsed.path, parsed.query, parsed.fragment)
        )

    # Backward-compatible fallback for deployments that still expose the
    # database owner username and password as separate variables.
    owner = required("OMEGA_DB_OWNER_USER")
    owner_password = required("OMEGA_DB_OWNER_PASSWORD")
    return database_url(owner, owner_password, "postgresql+psycopg")


def main() -> None:
    import uvicorn
    # The script directory is sys.path[0] when launched as
    # "python scripts/render_entrypoint.py"; import the sibling module directly.
    from migrate import main as migrate_main

    os.environ["OMEGA_MIGRATION_DATABASE_URL"] = migration_database_url()
    os.environ["OMEGA_DATABASE_URL"] = database_url("omega_app", required("OMEGA_APP_PASSWORD"), "postgresql+asyncpg")
    os.environ["OMEGA_WORKER_DATABASE_URL"] = database_url("omega_worker", required("OMEGA_WORKER_PASSWORD"), "postgresql+asyncpg")
    os.environ["OMEGA_CHECKPOINT_DATABASE_URL"] = database_url("omega_checkpoint", required("OMEGA_CHECKPOINT_PASSWORD"), "postgresql")
    os.environ["OMEGA_ENV"] = "production"
    os.environ["OMEGA_EMBEDDED_WORKER"] = "true"

    print("OMEGA startup: applying database migrations and checkpoint schema.", flush=True)
    migrate_main()
    uvicorn.run("omega.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "10000")), proxy_headers=True)


if __name__ == "__main__":
    main()
