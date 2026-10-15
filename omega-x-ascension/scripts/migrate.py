from __future__ import annotations

import asyncio
import os

import psycopg
from alembic.config import Config
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import sql

from alembic import command


def require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or "set-a-" in value or "change-me" in value:
        raise RuntimeError(f"{name} must be set to a non-default value")
    return value


def provision_roles() -> None:
    dsn = require("OMEGA_MIGRATION_DATABASE_URL").replace("postgresql+psycopg://", "postgresql://")
    roles = {
        "omega_app": require("OMEGA_APP_PASSWORD"),
        "omega_worker": require("OMEGA_WORKER_PASSWORD"),
        "omega_checkpoint": require("OMEGA_CHECKPOINT_PASSWORD"),
    }
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for role, password in roles.items():
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
            if cur.fetchone() is None:
                cur.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
                    ).format(sql.Identifier(role))
                )
            cur.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
            cur.execute("SELECT current_database()")
            database_name = cur.fetchone()[0]
            cur.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(database_name), sql.Identifier(role)
                )
            )
            cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))


async def checkpoint_schema() -> None:
    owner_dsn = require("OMEGA_MIGRATION_DATABASE_URL").replace(
        "postgresql+psycopg://", "postgresql://"
    )
    async with AsyncPostgresSaver.from_conn_string(owner_dsn) as saver:
        await saver.setup()
    with psycopg.connect(owner_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'checkpoint%'"
        )
        tables = [row[0] for row in cur.fetchall()]
        if not tables:
            raise RuntimeError("checkpoint setup created no checkpoint tables")
        for table in tables:
            cur.execute(
                sql.SQL(
                    "GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.{} TO omega_checkpoint"
                ).format(sql.Identifier(table))
            )


def main() -> None:
    provision_roles()
    command.upgrade(Config("alembic.ini"), "head")
    asyncio.run(checkpoint_schema())


if __name__ == "__main__":
    main()
